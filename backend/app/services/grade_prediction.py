
"""
Прогноз итоговой оценки по дисциплине (экзамен / дифзачёт).
Только эвристика по сданным ДЗ: оценки, покрытие, сроки.
Без LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.db_models import (
    Assignment,
    AttestationType,
    GroupSubject,
    Student,
    Subject,
    Submission,
    SubmissionStatus,
)

ATTESTATION_LABELS = {
    AttestationType.EXAM: "Экзамен",
    AttestationType.DIF_CREDIT: "Дифзачёт",
    AttestationType.CREDIT: "Зачёт",
    AttestationType.PROJECT: "Проект",
    AttestationType.OTHER: "Другое",
    AttestationType.NONE: "Нет",
}

def attestation_label(value) -> str:
    """Человекочитаемое название вида аттестации."""
    try:
        if isinstance(value, str):
            value = AttestationType(value)
        return ATTESTATION_LABELS.get(value, str(value))
    except Exception:
        return str(value or "—")

def predicts_numeric_grade(attestation_type) -> bool:
    """Прогноз 2–5 только для экзамена и дифзачёта."""
    try:
        if isinstance(attestation_type, str):
            attestation_type = AttestationType(attestation_type)
    except Exception:
        return False
    return attestation_type in (AttestationType.EXAM, AttestationType.DIF_CREDIT)

@dataclass
class StudentPrediction:
    """Результат прогноза оценки по студенту."""
    student_id: int
    student_name: str
    group_name: str
    total_assignments: int
    submitted_count: int
    graded_count: int
    accepted_count: int
    on_time_count: int
    late_count: int
    missing_count: int
    avg_grade: Optional[float]
    coverage: float
    on_time_ratio: float
    predicted_grade: Optional[int]
    confidence: str
    explanation: str

def _assignments_for_subject(db: Session, subject_id: int) -> List[Assignment]:
    """Вспомогательная функция: assignments for subject."""
    return (
        db.query(Assignment)
        .filter(
            Assignment.subject_id == subject_id,
            Assignment.deleted_at.is_(None),
            Assignment.is_active == True,
        )
        .all()
    )

def _students_for_subject(db: Session, subject_id: int) -> List[Student]:
    """Вспомогательная функция: students for subject."""
    group_ids = [
        gs.group_id
        for gs in db.query(GroupSubject).filter(GroupSubject.subject_id == subject_id).all()
    ]
    if not group_ids:
        return []
    return (
        db.query(Student)
        .options(joinedload(Student.group))
        .filter(
            Student.group_id.in_(group_ids),
            Student.deleted_at.is_(None),
        )
        .order_by(Student.full_name)
        .all()
    )

def _is_on_time(submission: Submission, assignment: Assignment) -> bool:
    """Вспомогательная функция: is on time."""
    if not assignment.deadline or not submission.submitted_at:
        return True

    dl = assignment.deadline.replace(tzinfo=None) if assignment.deadline.tzinfo else assignment.deadline
    st = submission.submitted_at.replace(tzinfo=None) if submission.submitted_at.tzinfo else submission.submitted_at
    return st <= dl

def predict_for_student(
    assignments: List[Assignment],
    submissions_by_assignment: Dict[int, Submission],
    student: Student,
) -> StudentPrediction:
    """Эвристический прогноз оценки для одного студента."""
    total = len(assignments)
    grades: List[int] = []
    submitted = 0
    graded = 0
    accepted = 0
    on_time = 0
    late = 0

    for a in assignments:
        sub = submissions_by_assignment.get(a.id)
        if not sub:
            continue
        submitted += 1
        if _is_on_time(sub, a):
            on_time += 1
        else:
            late += 1
        if sub.grade is not None:
            graded += 1
            grades.append(int(sub.grade))
        if sub.status == SubmissionStatus.ACCEPTED or (
            isinstance(sub.status, str) and sub.status == "accepted"
        ):
            accepted += 1

    missing = max(0, total - submitted)
    coverage = (submitted / total) if total else 0.0
    on_time_ratio = (on_time / submitted) if submitted else 0.0
    avg_grade = (sum(grades) / len(grades)) if grades else None

    predicted: Optional[int] = None
    confidence = "low"
    parts: List[str] = []

    if total == 0:
        explanation = "По дисциплине нет активных заданий — прогноз невозможен."
    elif submitted == 0:
        predicted = 2
        confidence = "medium"
        explanation = "Нет ни одной сданной работы → прогноз 2."
    else:

        base = float(avg_grade) if avg_grade is not None else 3.0

        coverage_factor = coverage

        punctual = on_time_ratio

        score = (
            0.55 * base
            + 0.30 * (2 + 3 * coverage_factor)
            + 0.15 * (2 + 3 * punctual)
        )

        if coverage < 0.5:
            score -= 0.6
        elif coverage < 0.75:
            score -= 0.25
        if late and submitted and (late / submitted) > 0.4:
            score -= 0.3

        predicted = int(max(2, min(5, round(score))))

        if graded >= max(1, total // 2) and coverage >= 0.7:
            confidence = "high"
        elif graded >= 1 or coverage >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        if avg_grade is not None:
            parts.append(f"ср. оценка ДЗ {avg_grade:.1f}")
        else:
            parts.append("оценок ДЗ пока нет")
        parts.append(f"сдано {submitted}/{total}")
        if submitted:
            parts.append(f"вовремя {on_time}/{submitted}")
        if missing:
            parts.append(f"не сдано {missing}")
        explanation = "; ".join(parts) + f" → прогноз {predicted}."

    group_name = student.group.name if getattr(student, "group", None) else "—"

    return StudentPrediction(
        student_id=student.id,
        student_name=student.full_name or f"#{student.id}",
        group_name=group_name,
        total_assignments=total,
        submitted_count=submitted,
        graded_count=graded,
        accepted_count=accepted,
        on_time_count=on_time,
        late_count=late,
        missing_count=missing,
        avg_grade=round(avg_grade, 2) if avg_grade is not None else None,
        coverage=round(coverage, 3),
        on_time_ratio=round(on_time_ratio, 3),
        predicted_grade=predicted,
        confidence=confidence,
        explanation=explanation,
    )

def predict_subject_attestation(
    db: Session, subject: Subject
) -> Dict[str, Any]:
    """
    Сводка по дисциплине для преподавателя.
    Прогноз 2–5 — только если attestation_type in (exam, dif_credit).
    """
    att = subject.attestation_type or AttestationType.NONE
    if isinstance(att, str):
        try:
            att = AttestationType(att)
        except Exception:
            att = AttestationType.NONE

    assignments = _assignments_for_subject(db, subject.id)
    students = _students_for_subject(db, subject.id)
    assignment_ids = [a.id for a in assignments]

    rows: List[Dict[str, Any]] = []
    can_predict = predicts_numeric_grade(att)

    for student in students:
        subs = []
        if assignment_ids:
            subs = (
                db.query(Submission)
                .filter(
                    Submission.student_id == student.id,
                    Submission.assignment_id.in_(assignment_ids),
                    Submission.deleted_at.is_(None),
                )
                .all()
            )
        by_a = {s.assignment_id: s for s in subs}
        pred = predict_for_student(assignments, by_a, student)
        d = asdict(pred)
        if not can_predict:
            d["predicted_grade"] = None
            d["explanation"] = (
                f"Вид аттестации «{attestation_label(att)}» — числовой прогноз не строится "
                f"(только для экзамена и дифзачёта)."
            )
            d["confidence"] = "n/a"
        rows.append(d)

    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        gname = row.get("group_name") or "Без группы"
        by_group.setdefault(gname, []).append(row)
    groups_out = [
        {"group_name": name, "students": list_rows, "students_count": len(list_rows)}
        for name, list_rows in sorted(by_group.items(), key=lambda x: x[0].lower())
    ]

    return {
        "subject_id": subject.id,
        "subject_name": subject.name,
        "attestation_type": att.value if hasattr(att, "value") else str(att),
        "attestation_label": attestation_label(att),
        "predicts_grade": can_predict,
        "assignments_count": len(assignments),
        "students_count": len(students),
        "students": rows,
        "groups": groups_out,
    }
