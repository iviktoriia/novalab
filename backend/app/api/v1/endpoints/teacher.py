from fastapi import APIRouter, Depends, HTTPException, Form, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List, Optional
import json
import os
import bcrypt
import secrets
import string
import re
from datetime import datetime
from app.core.timeutils import local_now, format_dt
import pytz

from app.core.database import get_db
from app.core.storage import file_response, FILE_MISSING_DETAIL
from app.core.auth import get_teacher_from_session
from app.core.security import generate_password as sec_generate_password, generate_student_login, generate_registration_code as sec_reg_code
from app.core.permissions import (
    groups_for_teacher,
    subjects_for_teacher,
    teacher_can_manage_group,
    teacher_can_access_group,
    teacher_can_edit_subject,
    teacher_can_access_subject,
    teacher_can_use_subject,
    ensure_subject_teacher_link,
)
from app.models.db_models import (
    Student, Group, Subject, Assignment, Submission, GroupSubject, AttestationType,
    Material, TempPassword, Teacher, GroupTeacher, SubjectTeacher,
    RegistrationMethod, SubmissionStatus, MaterialType
)
from app.templates_config import templates
from app.services.grade_prediction import (
    predict_subject_attestation, attestation_label, predicts_numeric_grade,
    ATTESTATION_LABELS,
)

def _require_teacher(request: Request, db: Session):
    """Преподаватель из сессии или None."""
    return get_teacher_from_session(request, db)

def _deny():
    """Не залогинен как преподаватель -> на страницу входа."""
    return RedirectResponse(url="/teacher/login", status_code=303)

def _forbid():
    """Залогинен, но нет прав на ресурс -> к списку (не сырой 403)."""
    return RedirectResponse(url="/teacher/dashboard", status_code=303)

router = APIRouter(prefix="/teacher", tags=["teacher"])
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

MATERIALS_DIR = Path("materials")
MATERIALS_DIR.mkdir(exist_ok=True)
ASSIGNMENT_FILES_DIR = Path("assignment_files")
ASSIGNMENT_FILES_DIR.mkdir(exist_ok=True)

TEXT_EXTENSIONS = [
    '.py', '.txt', '.js', '.cpp', '.c', '.h', '.hpp', '.cs', '.go', '.rs',
    '.rb', '.php', '.swift', '.kt', '.scala', '.sh', '.sql', '.html', '.css',
    '.vue', '.jsx', '.tsx', '.json', '.xml', '.yml', '.yaml', '.md', '.csv',
    '.toml', '.ini', '.cfg', '.conf'
]

ALLOWED_MATERIALS_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.rtf', '.odt', '.txt',
    '.ppt', '.pptx', '.odp',
    '.xls', '.xlsx', '.ods', '.csv',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
    '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp',
    '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.kts',
    '.scala', '.sh', '.bash', '.sql', '.html', '.htm',
    '.css', '.scss', '.sass', '.less', '.vue', '.jsx', '.tsx',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.md', '.markdown',
    '.ipynb', '.r', '.lua', '.pl', '.pm', '.ex', '.exs',
    '.clj', '.cljs', '.dart', '.groovy', '.tf', '.dockerfile'
}

def generate_password(length=8):
    """Генерирует случайный буквенно-цифровой пароль."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_registration_code():
    """Генерирует код регистрации группы."""
    return secrets.token_urlsafe(16)

def read_file_content(file_path: str) -> str:
    """Читает текстовый файл с диска."""
    try:
        path = Path(file_path)
        if not path.exists():
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""

def transliterate_name(name: str) -> str:
    """Транслитерирует кириллическое имя в латиницу."""
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    result = ''
    for char in name:
        if char in translit_map:
            result += translit_map[char]
        elif char.isalpha():
            result += char
        elif char == ' ':
            result += '_'
        else:
            result += char
    return result

def generate_login(full_name: str, group_id: int, db: Session) -> str:
    """Логин студента: translit + random seed + group_id."""
    alphabet = string.ascii_lowercase + string.digits
    seed = "".join(secrets.choice(alphabet) for _ in range(4))
    base_login = transliterate_name(full_name.lower())
    base_login = re.sub(r"[^a-z0-9_]", "", base_login).strip("_")
    if not base_login:
        base_login = "student"
    login = f"{base_login}_{seed}_{group_id}"
    existing = db.query(Student).filter(Student.login == login).first()
    if existing:
        for _ in range(20):
            seed2 = "".join(secrets.choice(alphabet) for _ in range(3))
            candidate = f"{login}_{seed2}"
            if not db.query(Student).filter(Student.login == candidate).first():
                return candidate
        return f"{login}_{secrets.token_hex(3)}"
    return login

@router.get("/test")
async def test_teacher():
    """Test teacher."""
    return {"message": "Teacher routes are working!"}

@router.get("/dashboard", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, db: Session = Depends(get_db)):
    """Обработчик преподавателя: dashboard."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    groups = groups_for_teacher(db, teacher.id)
    group_ids = [g.id for g in groups]
    subjects = subjects_for_teacher(db, teacher.id)
    subject_ids = [s.id for s in subjects]

    assignments = []
    if subject_ids:
        assignments = db.query(Assignment).filter(
            Assignment.subject_id.in_(subject_ids),
            Assignment.is_active == True,
            Assignment.deleted_at.is_(None)
        ).all()

    total_students = 0
    if group_ids:
        total_students = db.query(Student).filter(
            Student.group_id.in_(group_ids),
            Student.is_active == True,
            Student.deleted_at.is_(None)
        ).count()

    assignment_ids = [a.id for a in assignments]
    total_submissions = 0
    graded_submissions = 0
    pending_review = 0
    recent_submissions = []
    if assignment_ids:
        total_submissions = db.query(Submission).filter(
            Submission.assignment_id.in_(assignment_ids),
            Submission.deleted_at.is_(None)
        ).count()
        graded_submissions = db.query(Submission).filter(
            Submission.assignment_id.in_(assignment_ids),
            Submission.grade.isnot(None),
            Submission.deleted_at.is_(None)
        ).count()
        pending_review = db.query(Submission).filter(
            Submission.assignment_id.in_(assignment_ids),
            Submission.grade.is_(None),
            Submission.deleted_at.is_(None)
        ).count()

        recent = (
            db.query(Submission)
            .filter(
                Submission.assignment_id.in_(assignment_ids),
                Submission.deleted_at.is_(None),
            )
            .order_by(Submission.submitted_at.desc())
            .limit(8)
            .all()
        )
        for sub in recent:
            student = db.query(Student).filter(Student.id == sub.student_id).first()
            assignment = next((a for a in assignments if a.id == sub.assignment_id), None)
            recent_submissions.append({
                "id": sub.id,
                "student_name": student.full_name if student else "—",
                "assignment_title": assignment.title if assignment else "—",
                "submitted_at": sub.submitted_at,
                "grade": sub.grade,
                "status": sub.status.value if sub.status else "submitted",
            })

    group_activity = []
    for g in groups:
        g_students = db.query(Student).filter(
            Student.group_id == g.id,
            Student.deleted_at.is_(None),
            Student.is_active == True,
        ).count()
        g_subs = 0
        if assignment_ids:
            student_ids = [
                s.id for s in db.query(Student).filter(
                    Student.group_id == g.id, Student.deleted_at.is_(None)
                ).all()
            ]
            if student_ids:
                g_subs = db.query(Submission).filter(
                    Submission.assignment_id.in_(assignment_ids),
                    Submission.student_id.in_(student_ids),
                    Submission.deleted_at.is_(None),
                ).count()
        group_activity.append({
            "name": g.name,
            "students": g_students,
            "submissions": g_subs,
        })

    return templates.TemplateResponse(
        "teacher_dashboard.html",
        {
            "request": request,
            "groups": groups,
            "assignments": assignments,
            "total_students": total_students,
            "total_submissions": total_submissions,
            "graded_submissions": graded_submissions,
            "pending_review": pending_review,
            "recent_submissions": recent_submissions,
            "group_activity": group_activity,
            "teacher": teacher,
        }
    )

@router.get("/groups", response_class=HTMLResponse)
async def teacher_groups(request: Request, db: Session = Depends(get_db)):
    """Обработчик преподавателя: groups."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    groups = groups_for_teacher(db, teacher.id)
    subjects = subjects_for_teacher(db, teacher.id)

    groups_data = []
    for group in groups:
        students = db.query(Student).filter(
            Student.group_id == group.id,
            Student.deleted_at.is_(None)
        ).all()
        group_subjects = db.query(GroupSubject).filter(GroupSubject.group_id == group.id).all()

        for gs in group_subjects:
            gs.subject = db.query(Subject).filter(
                Subject.id == gs.subject_id,
                Subject.deleted_at.is_(None)
            ).first()

        is_assigned = db.query(GroupTeacher).filter(
            GroupTeacher.group_id == group.id,
            GroupTeacher.teacher_id == teacher.id
        ).first()

        groups_data.append({
            "id": group.id,
            "name": group.name,
            "registration_method": group.registration_method.value if group.registration_method else "auto",
            "students_count": len(students),
            "subjects_count": len(group_subjects),
            "students": students,
            "group_subjects": group_subjects,
            "can_manage": teacher_can_manage_group(db, teacher.id, group),
            "is_shared": bool(group.created_by_admin) and is_assigned is not None,
        })

    return templates.TemplateResponse(
        "teacher_groups.html",
        {"request": request, "groups": groups_data, "subjects": subjects, "teacher": teacher}
    )

@router.get("/assignments", response_class=HTMLResponse)
async def teacher_assignments(request: Request, db: Session = Depends(get_db)):
    """Обработчик преподавателя: assignments."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subjects = subjects_for_teacher(db, teacher.id)
    subject_ids = [s.id for s in subjects]
    groups = groups_for_teacher(db, teacher.id)

    assignments = []
    if subject_ids:
        assignments = db.query(Assignment).filter(
            Assignment.subject_id.in_(subject_ids),
            Assignment.deleted_at.is_(None),
            Assignment.is_active == True
        ).all()

    assignments_data = []
    for assignment in assignments:
        subject = db.query(Subject).filter(
            Subject.id == assignment.subject_id,
            Subject.deleted_at.is_(None)
        ).first()
        submissions = db.query(Submission).filter(
            Submission.assignment_id == assignment.id,
            Submission.deleted_at.is_(None)
        ).all()
        graded = sum(1 for s in submissions if s.grade is not None)

        files_count = 0
        if assignment.files:
            try:
                files = json.loads(assignment.files)
                files_count = len(files)
            except Exception:
                pass

        assignments_data.append({
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "requirements": assignment.requirements,
            "subject_name": subject.name if subject else "Unknown",
            "deadline": assignment.deadline,
            "submissions_count": len(submissions),
            "graded_count": graded,
            "created_at": assignment.created_at,
            "files_count": files_count
        })

    by_subject = {}
    for a in assignments_data:
        key = a.get("subject_name") or "Без дисциплины"
        by_subject.setdefault(key, []).append(a)
    assignments_by_subject = [
        {"subject_name": name, "assignments": alist}
        for name, alist in sorted(by_subject.items(), key=lambda x: x[0].lower())
    ]

    return templates.TemplateResponse(
        "teacher_assignments.html",
        {
            "request": request,
            "assignments": assignments_data,
            "assignments_by_subject": assignments_by_subject,
            "subjects": subjects,
            "groups": groups,
            "teacher": teacher,
        }
    )

@router.get("/groups/create", response_class=HTMLResponse)
async def create_group_page(request: Request, db: Session = Depends(get_db)):
    """HTML-страница: create group page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()
    subjects = subjects_for_teacher(db, teacher.id)
    return templates.TemplateResponse(
        "teacher_groups_create.html",
        {
            "request": request,
            "subjects": subjects,
            "edit_mode": False,
            "group": None,
            "selected_subjects": [],
            "students_text": "",
            "registration_method": "auto",
            "teacher": teacher,
            "error": None,
        }
    )

@router.post("/groups/create")
async def create_group(
    request: Request,
    name: str = Form(...),
    students: Optional[str] = Form(None),
    subject_ids: Optional[List[int]] = Form(None),
    registration_method: str = Form("auto"),
    db: Session = Depends(get_db)
):
    """Создание: group."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    existing = db.query(Group).filter(
        Group.name == name,
        Group.deleted_at.is_(None)
    ).first()
    if existing:
        subjects = subjects_for_teacher(db, teacher.id)
        return templates.TemplateResponse(
            "teacher_groups_create.html",
            {
                "request": request,
                "subjects": subjects,
                "edit_mode": False,
                "group": None,
                "selected_subjects": subject_ids or [],
                "students_text": students or "",
                "registration_method": registration_method,
                "teacher": teacher,
                "error": f"Группа с названием «{name}» уже существует",
            },
            status_code=400,
        )

    reg_method = RegistrationMethod.AUTO if registration_method == "auto" else RegistrationMethod.SELF

    group = Group(
        name=name,
        registration_method=reg_method,
        owner_teacher_id=teacher.id,
        created_by_admin=False,
        is_active=True,
    )

    if registration_method == "self":
        group.registration_code = generate_registration_code()
        group.registration_enabled = True

    db.add(group)
    db.flush()

    student_names = []
    if students:
        student_names = [s.strip() for s in students.split('\n') if s.strip()]

    if registration_method == "auto":
        for student_name in student_names:
            login = generate_login(student_name, group.id, db)
            password = generate_password()
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            student = Student(
                full_name=student_name,
                login=login,
                password_hash=password_hash,
                group_id=group.id,
                registered=True,
                registration_code=None,
                is_active=True,
            )
            db.add(student)
            db.flush()

            temp_password = TempPassword(student_id=student.id, password=password, is_used=False)
            db.add(temp_password)

    available_subject_ids = [s.id for s in subjects_for_teacher(db, teacher.id)]

    if subject_ids:
        for subject_id in subject_ids:
            if subject_id in available_subject_ids:
                subject = db.query(Subject).filter(
                    Subject.id == subject_id,
                    Subject.deleted_at.is_(None)
                ).first()
                if subject:
                    group_subject = GroupSubject(
                        group_id=group.id,
                        subject_id=subject_id,
                        assigned_by=teacher.full_name
                    )
                    db.add(group_subject)

    db.commit()

    return RedirectResponse(
        url=f"/teacher/groups/{group.id}/students?method={registration_method}",
        status_code=303
    )

@router.get("/groups/{group_id}/edit", response_class=HTMLResponse)
async def edit_group_page(request: Request, group_id: int, db: Session = Depends(get_db)):
    """HTML-страница: edit group page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None)
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    if not teacher_can_manage_group(db, teacher.id, group):
        is_assigned = db.query(GroupTeacher).filter(
            GroupTeacher.group_id == group_id,
            GroupTeacher.teacher_id == teacher.id
        ).first()
        if not is_assigned:
            return _forbid()

    subjects = subjects_for_teacher(db, teacher.id)
    available_subject_ids = [s.id for s in subjects]

    group_subjects = db.query(GroupSubject).filter(GroupSubject.group_id == group_id).all()
    selected_subjects = [gs.subject_id for gs in group_subjects if gs.subject_id in available_subject_ids]

    students = db.query(Student).filter(
        Student.group_id == group_id,
        Student.deleted_at.is_(None)
    ).all()
    students_text = "\n".join([s.full_name for s in students])

    return templates.TemplateResponse(
        "teacher_groups_create.html",
        {
            "request": request,
            "subjects": subjects,
            "edit_mode": True,
            "group": group,
            "selected_subjects": selected_subjects,
            "students_text": students_text,
            "registration_method": group.registration_method.value if group.registration_method else "auto",
            "teacher": teacher,
            "error": None,
        }
    )

@router.post("/groups/{group_id}/edit")
async def edit_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    students: Optional[str] = Form(None),
    subject_ids: Optional[List[int]] = Form(None),
    registration_method: str = Form("auto"),
    db: Session = Depends(get_db)
):
    """Редактирование: edit group."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None)
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    if not teacher_can_manage_group(db, teacher.id, group):
        is_assigned = db.query(GroupTeacher).filter(
            GroupTeacher.group_id == group_id,
            GroupTeacher.teacher_id == teacher.id
        ).first()
        if not is_assigned:
            return _forbid()

    existing = db.query(Group).filter(
        Group.name == name,
        Group.id != group_id,
        Group.deleted_at.is_(None)
    ).first()
    if existing:
        subjects = subjects_for_teacher(db, teacher.id)
        available_subject_ids = [s.id for s in subjects]
        group_subjects = db.query(GroupSubject).filter(GroupSubject.group_id == group_id).all()
        selected_subjects = [gs.subject_id for gs in group_subjects if gs.subject_id in available_subject_ids]
        students_q = db.query(Student).filter(Student.group_id == group_id, Student.deleted_at.is_(None)).all()
        students_text = "\n".join([s.full_name for s in students_q])
        return templates.TemplateResponse(
            "teacher_groups_create.html",
            {
                "request": request,
                "subjects": subjects,
                "edit_mode": True,
                "group": group,
                "selected_subjects": selected_subjects,
                "students_text": students_text,
                "registration_method": registration_method,
                "teacher": teacher,
                "error": f"Группа с названием «{name}» уже существует",
            },
            status_code=400,
        )

    old_method = group.registration_method.value if group.registration_method else "auto"

    group.name = name
    group.registration_method = RegistrationMethod.AUTO if registration_method == "auto" else RegistrationMethod.SELF
    group.updated_at = datetime.now()

    if registration_method == "self":
        if not group.registration_code:
            group.registration_code = generate_registration_code()
        group.registration_enabled = True
    else:
        group.registration_code = None
        group.registration_enabled = False

    existing_students = db.query(Student).filter(
        Student.group_id == group_id,
        Student.deleted_at.is_(None)
    ).all()

    new_student_names = []
    if students and students.strip():
        new_student_names = [s.strip() for s in students.split('\n') if s.strip()]

    if new_student_names:
        existing_names = [s.full_name for s in existing_students]

        for student in existing_students:
            if student.full_name not in new_student_names:
                student.deleted_at = datetime.now()
                student.is_active = False

        for student_name in new_student_names:
            if student_name not in existing_names:
                if registration_method == "auto":
                    login = generate_login(student_name, group_id, db)
                    password = generate_password()
                    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                    student = Student(
                        full_name=student_name,
                        login=login,
                        password_hash=password_hash,
                        group_id=group_id,
                        registered=True,
                        registration_code=None,
                        is_active=True,
                    )
                    db.add(student)
                    db.flush()

                    temp_password = TempPassword(student_id=student.id, password=password, is_used=False)
                    db.add(temp_password)
                else:
                    registration_code = generate_registration_code()
                    temp_login = f"temp_{registration_code[:8]}"

                    existing_login = db.query(Student).filter(Student.login == temp_login).first()
                    if existing_login:
                        temp_login = f"temp_{registration_code[:8]}_{len(db.query(Student).all())}"

                    student = Student(
                        full_name=student_name,
                        login=temp_login,
                        password_hash="",
                        group_id=group_id,
                        registered=False,
                        registration_code=registration_code,
                        is_active=True,
                    )
                    db.add(student)

    if old_method != registration_method:
        current_students = db.query(Student).filter(
            Student.group_id == group_id,
            Student.deleted_at.is_(None)
        ).all()
        for student in current_students:
            if registration_method == "auto" and old_method == "self":
                student.registration_code = None
                student.updated_at = datetime.now()
                temp = db.query(TempPassword).filter(TempPassword.student_id == student.id).first()
                if not temp and student.registered and student.password_hash:
                    pass
                elif not temp and student.registered and not student.password_hash:
                    password = generate_password()
                    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    student.password_hash = password_hash
                    db.add(TempPassword(student_id=student.id, password=password, is_used=False))
            elif registration_method == "self" and old_method == "auto":
                if not student.registration_code:
                    student.registration_code = generate_registration_code()
                    student.updated_at = datetime.now()

    available_subject_ids = [s.id for s in subjects_for_teacher(db, teacher.id)]

    db.query(GroupSubject).filter(GroupSubject.group_id == group_id).delete()

    if subject_ids:
        for subject_id in subject_ids:
            if subject_id in available_subject_ids:
                subject = db.query(Subject).filter(
                    Subject.id == subject_id,
                    Subject.deleted_at.is_(None)
                ).first()
                if subject:
                    group_subject = GroupSubject(
                        group_id=group_id,
                        subject_id=subject_id,
                        assigned_by=teacher.full_name
                    )
                    db.add(group_subject)

    db.commit()
    return RedirectResponse(
        url=f"/teacher/groups/{group_id}/students",
        status_code=303,
    )

@router.get("/groups/{group_id}/students", response_class=HTMLResponse)
async def group_students(
    request: Request,
    group_id: int,
    method: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Group students."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None)
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if not teacher_can_access_group(db, teacher.id, group):
        return _forbid()

    if not method:
        method = group.registration_method.value if group.registration_method else "auto"

    students = db.query(Student).filter(
        Student.group_id == group_id,
        Student.deleted_at.is_(None)
    ).all()

    registration_data = None
    if method == "self" and group.registration_code:
        registration_data = {"code": group.registration_code}

    for student in students:
        temp_pass = db.query(TempPassword).filter(TempPassword.student_id == student.id).first()
        student.password = temp_pass.password if temp_pass else None

        if method == "self" and not student.registered and student.registration_code:
            student.registration_code_display = student.registration_code

    return templates.TemplateResponse(
        "teacher_group_students.html",
        {
            "request": request,
            "group": group,
            "students": students,
            "registration_method": method,
            "registration_data": registration_data
        }
    )

@router.delete("/groups/{group_id}/delete")
async def delete_group(request: Request, group_id: int, db: Session = Depends(get_db)):
    """Мягко удаляет группу, студентов и их сдачи. Только владелец группы."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None),
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if not teacher_can_manage_group(db, teacher.id, group):
        return _forbid()

    now = datetime.now()
    students = (
        db.query(Student)
        .filter(Student.group_id == group_id, Student.deleted_at.is_(None))
        .all()
    )
    student_ids = [s.id for s in students]
    for student in students:
        student.deleted_at = now
        student.is_active = False

    if student_ids:
        for sub in (
            db.query(Submission)
            .filter(
                Submission.student_id.in_(student_ids),
                Submission.deleted_at.is_(None),
            )
            .all()
        ):
            sub.deleted_at = now

    group.deleted_at = now
    group.is_active = False
    db.commit()
    return {"status": "success", "message": "Группа удалена"}


@router.get("/assignments/create", response_class=HTMLResponse)
async def create_assignment_page(request: Request, db: Session = Depends(get_db)):
    """HTML-страница: create assignment page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()
    subjects = subjects_for_teacher(db, teacher.id)
    groups = groups_for_teacher(db, teacher.id)
    return templates.TemplateResponse(
        "teacher_assignments_create.html",
        {"request": request, "subjects": subjects, "groups": groups, "draft": None, "teacher": teacher}
    )

@router.post("/assignments/create")
async def create_assignment(
    request: Request,
    title: str = Form(...),
    subject_id: int = Form(...),
    group_ids: List[int] = Form(...),
    description: Optional[str] = Form(None),
    requirements: Optional[str] = Form(None),
    deadline: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Создание: assignment."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    deadline_dt = None
    if deadline:
        try:
            deadline_dt = datetime.fromisoformat(deadline)
        except:
            deadline_dt = None

    assignment = Assignment(
        title=title,
        subject_id=subject_id,
        description=description,
        requirements=requirements,
        deadline=deadline_dt,
        is_active=True,
    )
    db.add(assignment)
    db.flush()

    saved_files = []
    if files:
        for file in files:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in ALLOWED_MATERIALS_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {file.filename}")

            content = await file.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Файл {file.filename} слишком большой (максимум 20MB)")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"assignment_{assignment.id}_{timestamp}_{file.filename}"
            file_path = ASSIGNMENT_FILES_DIR / safe_filename

            with open(file_path, "wb") as f:
                f.write(content)

            saved_files.append({
                "original_name": file.filename,
                "saved_name": safe_filename,
                "path": str(file_path),
                "size": len(content),
                "extension": file_extension
            })

    if saved_files:
        assignment.files = json.dumps(saved_files)

    for group_id in group_ids:
        group = db.query(Group).filter(
            Group.id == group_id,
            Group.deleted_at.is_(None)
        ).first()
        if group:
            existing = db.query(GroupSubject).filter(
                GroupSubject.group_id == group_id,
                GroupSubject.subject_id == subject_id
            ).first()
            if not existing:
                group_subject = GroupSubject(
                    group_id=group_id,
                    subject_id=subject_id,
                    assigned_by=teacher.full_name
                )
                db.add(group_subject)

    db.commit()
    return RedirectResponse(url="/teacher/assignments", status_code=303)

@router.get("/assignments/{assignment_id}/edit", response_class=HTMLResponse)
async def edit_assignment_page(request: Request, assignment_id: int, db: Session = Depends(get_db)):
    """HTML-страница: edit assignment page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None)
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    subject = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject or not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    subjects = subjects_for_teacher(db, teacher.id)
    groups = groups_for_teacher(db, teacher.id)

    group_subjects = db.query(GroupSubject).filter(GroupSubject.subject_id == assignment.subject_id).all()
    selected_groups = [gs.group_id for gs in group_subjects]

    files_list = []
    if assignment.files:
        try:
            files_list = json.loads(assignment.files)
        except:
            pass

    deadline_value = ""
    if assignment.deadline:
        deadline_value = assignment.deadline.strftime("%Y-%m-%dT%H:%M")

    return templates.TemplateResponse(
        "teacher_assignments_edit.html",
        {
            "request": request,
            "assignment": assignment,
            "subjects": subjects,
            "groups": groups,
            "selected_groups": selected_groups,
            "files_list": files_list,
            "deadline_value": deadline_value
        }
    )

@router.post("/assignments/{assignment_id}/edit")
async def edit_assignment(
    request: Request,
    assignment_id: int,
    title: str = Form(...),
    subject_id: int = Form(...),
    group_ids: List[int] = Form(...),
    description: Optional[str] = Form(None),
    requirements: Optional[str] = Form(None),
    deadline: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    files_to_remove: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Редактирование: edit assignment."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None)
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    subj = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subj or not teacher_can_use_subject(db, teacher.id, subj):
        return _forbid()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")

    assignment.title = title
    assignment.subject_id = subject_id
    assignment.description = description
    assignment.requirements = requirements
    assignment.updated_at = datetime.now()

    if deadline:
        try:
            assignment.deadline = datetime.fromisoformat(deadline)
        except:
            assignment.deadline = None
    else:
        assignment.deadline = None

    current_files = []
    if assignment.files:
        try:
            current_files = json.loads(assignment.files)
        except:
            pass

    if files_to_remove:
        try:
            indices_to_remove = json.loads(files_to_remove)
            for idx in sorted(indices_to_remove, reverse=True):
                if 0 <= idx < len(current_files):
                    file_path = Path(current_files[idx]["path"])
                    if file_path.exists():
                        file_path.unlink()
                    current_files.pop(idx)
        except:
            pass

    if files:
        for file in files:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in ALLOWED_MATERIALS_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {file.filename}")

            content = await file.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Файл {file.filename} слишком большой (максимум 20MB)")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"assignment_{assignment_id}_{timestamp}_{file.filename}"
            file_path = ASSIGNMENT_FILES_DIR / safe_filename

            with open(file_path, "wb") as f:
                f.write(content)

            current_files.append({
                "original_name": file.filename,
                "saved_name": safe_filename,
                "path": str(file_path),
                "size": len(content),
                "extension": file_extension
            })

    if current_files:
        assignment.files = json.dumps(current_files)
    else:
        assignment.files = None

    db.query(GroupSubject).filter(GroupSubject.subject_id == subject_id).delete()

    for group_id in group_ids:
        group = db.query(Group).filter(
            Group.id == group_id,
            Group.deleted_at.is_(None)
        ).first()
        if group:
            group_subject = GroupSubject(
                group_id=group_id,
                subject_id=subject_id,
                assigned_by=teacher.full_name
            )
            db.add(group_subject)

    db.commit()
    return RedirectResponse(url="/teacher/assignments", status_code=303)

@router.get("/assignments/{assignment_id}/download/{file_index}")
async def download_assignment_file(
    assignment_id: int,
    file_index: int = 0,
    db: Session = Depends(get_db)
):
    """Скачивание: assignment file."""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None)
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    if assignment.files:
        try:
            files = json.loads(assignment.files)
        except Exception:
            files = []
        if files and 0 <= file_index < len(files):
            return file_response(files[file_index])

    raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

@router.delete("/assignments/{assignment_id}/delete")
async def delete_assignment(request: Request, assignment_id: int, db: Session = Depends(get_db)):
    """Мягко удаляет задание и все связанные сдачи (даже если работы уже есть)."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None),
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    subject = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None),
    ).first()
    if not subject or not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    now = datetime.now()
    submissions = (
        db.query(Submission)
        .filter(
            Submission.assignment_id == assignment_id,
            Submission.deleted_at.is_(None),
        )
        .all()
    )
    for sub in submissions:
        # файлы сдач оставляем в хранилище или чистим — мягкое удаление записи
        sub.deleted_at = now
    assignment.deleted_at = now
    assignment.is_active = False
    db.commit()
    return {
        "status": "success",
        "message": "Задание удалено",
        "submissions_deleted": len(submissions),
    }


@router.get("/subjects", response_class=HTMLResponse)
async def teacher_subjects(request: Request, db: Session = Depends(get_db)):
    """Обработчик преподавателя: subjects."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subjects = subjects_for_teacher(db, teacher.id)

    subjects_data = []
    for subject in subjects:
        subject.materials = db.query(Material).filter(
            Material.subject_id == subject.id,
            Material.deleted_at.is_(None)
        ).all()
        subject.assignments = db.query(Assignment).filter(
            Assignment.subject_id == subject.id,
            Assignment.deleted_at.is_(None),
            Assignment.is_active == True
        ).all()

        teacher_names = [t.full_name for t in subject.teachers if t.is_active and t.deleted_at is None]

        subjects_data.append({
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "teacher_name": ", ".join(teacher_names) if teacher_names else None,
            "attestation_label": attestation_label(getattr(subject, "attestation_type", None)),
            "materials": subject.materials,
            "assignments": subject.assignments,
            "can_edit": teacher_can_edit_subject(db, teacher.id, subject),
            "is_shared": bool(subject.created_by_admin) or (
                subject.owner_teacher_id is not None and subject.owner_teacher_id != teacher.id
            ),
        })

    return templates.TemplateResponse(
        "teacher_subjects.html",
        {"request": request, "subjects": subjects_data, "teacher": teacher},
    )

@router.get("/subjects/create", response_class=HTMLResponse)
async def create_subject_page(request: Request, db: Session = Depends(get_db)):
    """HTML-страница: create subject page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()
    return templates.TemplateResponse(
        "teacher_subjects_create.html",
        {
            "request": request,
            "draft": None,
            "teacher": teacher,
            "attestation_options": [{"value": k.value, "label": v} for k, v in ATTESTATION_LABELS.items()],
        },
    )

@router.post("/subjects/create")
async def create_subject(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    attestation_type: str = Form("none"),
    db: Session = Depends(get_db),
):
    """Создание: subject."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название дисциплины")

    existing = db.query(Subject).filter(
        Subject.name == name,
        Subject.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Дисциплина с таким названием уже существует")

    try:
        att = AttestationType(attestation_type or "none")
    except Exception:
        att = AttestationType.NONE

    subject = Subject(
        name=name,
        description=description,
        attestation_type=att,
        owner_teacher_id=teacher.id,
        created_by_admin=False,
        is_active=True,
    )
    db.add(subject)
    db.flush()
    ensure_subject_teacher_link(db, subject.id, teacher.id)
    db.commit()
    db.refresh(subject)

    return RedirectResponse(url="/teacher/subjects", status_code=303)

@router.delete("/subjects/{subject_id}/delete")
async def delete_subject(request: Request, subject_id: int, db: Session = Depends(get_db)):
    """Мягко удаляет дисциплину вместе с заданиями, сдачами и материалами."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None),
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_edit_subject(db, teacher.id, subject):
        return _forbid()

    now = datetime.now()
    assignments = (
        db.query(Assignment)
        .filter(Assignment.subject_id == subject_id, Assignment.deleted_at.is_(None))
        .all()
    )
    assignment_ids = [a.id for a in assignments]
    for a in assignments:
        a.deleted_at = now
        a.is_active = False

    if assignment_ids:
        for sub in (
            db.query(Submission)
            .filter(
                Submission.assignment_id.in_(assignment_ids),
                Submission.deleted_at.is_(None),
            )
            .all()
        ):
            sub.deleted_at = now

    for m in (
        db.query(Material)
        .filter(Material.subject_id == subject_id, Material.deleted_at.is_(None))
        .all()
    ):
        m.deleted_at = now

    subject.deleted_at = now
    subject.is_active = False
    db.commit()
    return {"status": "success", "message": "Дисциплина удалена"}


@router.get("/subjects/{subject_id}/edit", response_class=HTMLResponse)
async def edit_subject_page(request: Request, subject_id: int, db: Session = Depends(get_db)):
    """HTML-страница: edit subject page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_access_subject(db, teacher.id, subject):
        return _forbid()

    can_edit = teacher_can_edit_subject(db, teacher.id, subject)
    return templates.TemplateResponse(
        "teacher_subjects_edit.html",
        {
            "request": request,
            "subject": subject,
            "can_edit": can_edit,
            "teacher": teacher,
            "attestation_options": [{"value": k.value, "label": v} for k, v in ATTESTATION_LABELS.items()],
        },
    )

@router.post("/subjects/{subject_id}/edit")
async def edit_subject(
    request: Request,
    subject_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    attestation_type: str = Form("none"),
    db: Session = Depends(get_db)
):
    """Редактирование: edit subject."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_edit_subject(db, teacher.id, subject):
        return _forbid()

    existing = db.query(Subject).filter(
        Subject.name == name,
        Subject.id != subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Дисциплина с таким названием уже существует")

    subject.name = name
    subject.description = description
    try:
        subject.attestation_type = AttestationType(attestation_type or "none")
    except Exception:
        subject.attestation_type = AttestationType.NONE
    subject.updated_at = datetime.now()
    db.commit()
    return RedirectResponse(url="/teacher/subjects", status_code=303)

@router.get("/subjects/{subject_id}/attestation", response_class=HTMLResponse)
async def subject_attestation_page(request: Request, subject_id: int, db: Session = Depends(get_db)):
    """Итоги / прогноз аттестации по дисциплине (только преподаватель)."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None),
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    summary = predict_subject_attestation(db, subject)
    return templates.TemplateResponse(
        "teacher_subject_attestation.html",
        {
            "request": request,
            "teacher": teacher,
            "subject": subject,
            "summary": summary,
            "attestation_label": attestation_label,
        },
    )

@router.get("/subjects/{subject_id}/materials", response_class=HTMLResponse)
async def subject_materials(request: Request, subject_id: int, db: Session = Depends(get_db)):
    """Subject materials."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    materials = db.query(Material).filter(
        Material.subject_id == subject_id,
        Material.deleted_at.is_(None)
    ).order_by(
        Material.order.asc(),
        Material.created_at.desc()
    ).all()

    for material in materials:
        if material.files:
            try:
                material.files = json.loads(material.files)
            except:
                material.files = []
        else:
            material.files = []

    return templates.TemplateResponse(
        "teacher_subject_materials.html",
        {"request": request, "subject": subject, "materials": materials}
    )

@router.get("/subjects/{subject_id}/materials/create", response_class=HTMLResponse)
async def create_material_page(request: Request, subject_id: int, db: Session = Depends(get_db)):
    """HTML-страница: create material page."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    return templates.TemplateResponse(
        "teacher_materials_create.html",
        {"request": request, "subject": subject, "draft": None, "teacher": teacher}
    )

@router.post("/subjects/{subject_id}/materials/create")
async def create_materials(
    request: Request,
    subject_id: int,
    title: str = Form(...),
    material_type: str = Form("other"),
    description: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):

    """Создание: materials."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    if not files:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один файл")

    material_type_enum = MaterialType.OTHER
    for mt in MaterialType:
        if mt.value == material_type:
            material_type_enum = mt
            break

    saved_files = []
    for file in files:
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in ALLOWED_MATERIALS_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {file.filename}")

        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Файл {file.filename} слишком большой (максимум 50MB)")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"subject_{subject_id}_{timestamp}_{file.filename}"
        file_path = MATERIALS_DIR / safe_filename

        with open(file_path, "wb") as f:
            f.write(content)

        saved_files.append({
            "original_name": file.filename,
            "saved_name": safe_filename,
            "path": str(file_path),
            "size": len(content),
            "extension": file_extension
        })

    max_order = db.query(Material).filter(
        Material.subject_id == subject_id,
        Material.deleted_at.is_(None)
    ).count()

    material = Material(
        subject_id=subject_id,
        title=title,
        description=description,
        material_type=material_type_enum,
        files=json.dumps(saved_files) if saved_files else '[]',
        order=max_order,
        is_published=True,
    )
    db.add(material)
    db.commit()

    return RedirectResponse(url=f"/teacher/subjects/{subject_id}/materials", status_code=303)

@router.get("/materials/{material_id}/download/{file_index}")
async def download_material_file(
    material_id: int,
    file_index: int = 0,
    db: Session = Depends(get_db)
):
    """Скачивание: material file."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.deleted_at.is_(None)
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")

    if material.files:
        try:
            files = json.loads(material.files)
        except Exception:
            files = []
        if files and 0 <= file_index < len(files):
            return file_response(files[file_index])

    raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

@router.get("/materials/{material_id}/download")
async def download_material(material_id: int, db: Session = Depends(get_db)):
    """Скачивание: material."""
    return await download_material_file(material_id, 0, db)

@router.delete("/materials/{material_id}/delete")
async def delete_material(request: Request, material_id: int, db: Session = Depends(get_db)):
    """Удаление: material."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    material = db.query(Material).filter(
        Material.id == material_id,
        Material.deleted_at.is_(None)
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")

    subject = db.query(Subject).filter(
        Subject.id == material.subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject or not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    if material.files:
        try:
            files = json.loads(material.files)
            for file_info in files:
                file_path = Path(file_info["path"])
                if file_path.exists():
                    file_path.unlink()
        except:
            pass

    material.deleted_at = datetime.now()
    db.commit()
    return {"status": "success", "message": "Материал удален"}

@router.get("/materials/{material_id}/edit", response_class=HTMLResponse)
async def edit_material_page(request: Request, material_id: int, db: Session = Depends(get_db)):
    """HTML-страница: edit material page."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.deleted_at.is_(None)
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")

    subject = db.query(Subject).filter(
        Subject.id == material.subject_id,
        Subject.deleted_at.is_(None)
    ).first()

    files_list = []
    if material.files:
        try:
            files_list = json.loads(material.files)
        except:
            pass

    return templates.TemplateResponse(
        "teacher_materials_edit.html",
        {"request": request, "material": material, "subject": subject, "files_list": files_list}
    )

@router.post("/materials/{material_id}/edit")
async def edit_material(
    material_id: int,
    title: str = Form(...),
    material_type: str = Form("other"),
    description: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    files_to_remove: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Редактирование: edit material."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.deleted_at.is_(None)
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")

    material_type_enum = MaterialType.OTHER
    for mt in MaterialType:
        if mt.value == material_type:
            material_type_enum = mt
            break

    material.title = title
    material.material_type = material_type_enum
    material.description = description
    material.updated_at = datetime.now()

    current_files = []
    if material.files:
        try:
            current_files = json.loads(material.files)
        except:
            pass

    if files_to_remove:
        try:
            indices_to_remove = json.loads(files_to_remove)
            if indices_to_remove:
                for idx in sorted(indices_to_remove, reverse=True):
                    if 0 <= idx < len(current_files):
                        file_path = Path(current_files[idx]["path"])
                        if file_path.exists():
                            file_path.unlink()
                        current_files.pop(idx)
        except json.JSONDecodeError:
            pass

    if files:
        for file in files:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in ALLOWED_MATERIALS_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {file.filename}")

            content = await file.read()
            if len(content) > 50 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Файл {file.filename} слишком большой (максимум 50MB)")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"subject_{material.subject_id}_{timestamp}_{file.filename}"
            file_path = MATERIALS_DIR / safe_filename

            with open(file_path, "wb") as f:
                f.write(content)

            current_files.append({
                "original_name": file.filename,
                "saved_name": safe_filename,
                "path": str(file_path),
                "size": len(content),
                "extension": file_extension
            })

    if not current_files:
        raise HTTPException(status_code=400, detail="У материала должен быть хотя бы один файл")

    material.files = json.dumps(current_files)
    db.commit()

    return RedirectResponse(url=f"/teacher/subjects/{material.subject_id}/materials", status_code=303)

@router.get("/assignment/{assignment_id}/submissions", response_class=HTMLResponse)
async def teacher_assignment_submissions(
    request: Request,
    assignment_id: int,
    db: Session = Depends(get_db)
):
    """Обработчик преподавателя: assignment submissions."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None)
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    subject_check = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None)
    ).first()
    if not subject_check or not teacher_can_use_subject(db, teacher.id, subject_check):
        return _forbid()

    subject = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None)
    ).first()

    submissions = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.deleted_at.is_(None)
    ).all()

    submissions_data = []
    for sub in submissions:
        student = db.query(Student).filter(
            Student.id == sub.student_id,
            Student.deleted_at.is_(None)
        ).first()

        student_group = None
        if student:
            group = db.query(Group).filter(
                Group.id == student.group_id,
                Group.deleted_at.is_(None)
            ).first()
            student_group = group.name if group else None

        files_list = []
        if sub.files:
            try:
                files_list = json.loads(sub.files)
            except:
                pass

        submissions_data.append({
            "id": sub.id,
            "student_name": student.full_name if student else "Unknown",
            "student_group": student_group,
            "files_count": len(files_list),
            "github_link": sub.github_link,
            "submitted_at": sub.submitted_at,
            "grade": sub.grade,
            "is_graded": sub.grade is not None,
            "status": sub.status.value if sub.status else 'submitted',
            "resubmission_count": sub.resubmission_count or 0,
            "feedback": sub.feedback,
        })

    return templates.TemplateResponse(
        "teacher_submissions.html",
        {
            "request": request,
            "assignment": assignment,
            "subject": subject,
            "submissions": submissions_data,
            "total": len(submissions_data),
            "graded": sum(1 for s in submissions_data if s["is_graded"])
        }
    )

@router.get("/submission/{submission_id}/download/{file_index}")
async def teacher_download_submission_file(
    submission_id: int,
    file_index: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Обработчик преподавателя: download submission file."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.deleted_at.is_(None),
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")

    assignment = db.query(Assignment).filter(
        Assignment.id == submission.assignment_id,
        Assignment.deleted_at.is_(None),
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    subject = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None),
    ).first()
    if not subject or not teacher_can_use_subject(db, teacher.id, subject):
        return _forbid()

    if not submission.files:
        raise HTTPException(status_code=404, detail="Файлы не прикреплены")
    try:
        files = json.loads(submission.files)
    except Exception:
        raise HTTPException(status_code=404, detail="Файлы недоступны")
    if not isinstance(files, list) or not (0 <= file_index < len(files)):
        raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

    return file_response(files[file_index])

@router.get("/submission/{submission_id}/view", response_class=HTMLResponse)
async def view_submission(request: Request, submission_id: int, db: Session = Depends(get_db)):
    """View submission."""
    teacher = _require_teacher(request, db)
    if not teacher:
        return _deny()

    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.deleted_at.is_(None)
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")

    assignment_check = db.query(Assignment).filter(
        Assignment.id == submission.assignment_id,
        Assignment.deleted_at.is_(None)
    ).first()
    if assignment_check:
        subject_check = db.query(Subject).filter(
            Subject.id == assignment_check.subject_id,
            Subject.deleted_at.is_(None)
        ).first()
        if not subject_check or not teacher_can_use_subject(db, teacher.id, subject_check):
            return _forbid()

    student = db.query(Student).filter(
        Student.id == submission.student_id,
        Student.deleted_at.is_(None)
    ).first()
    if student:
        student.group = db.query(Group).filter(
            Group.id == student.group_id,
            Group.deleted_at.is_(None)
        ).first()

    assignment = db.query(Assignment).filter(
        Assignment.id == submission.assignment_id,
        Assignment.deleted_at.is_(None)
    ).first()
    subject = db.query(Subject).filter(
        Subject.id == assignment.subject_id,
        Subject.deleted_at.is_(None)
    ).first() if assignment else None

    analysis_data = None

    files_list = []
    file_contents = {}
    if submission.files:
        try:
            files_list = json.loads(submission.files)
            if not isinstance(files_list, list):
                files_list = []
            for file_info in files_list:
                extension = (file_info.get('extension') or '').lower()
                if not extension and file_info.get('original_name'):
                    name = file_info['original_name']
                    extension = ('.' + name.rsplit('.', 1)[-1].lower()) if '.' in name else ''
                    file_info['extension'] = extension
                if extension in TEXT_EXTENSIONS:
                    content = read_file_content(file_info.get('path', ''))
                    if content:
                        key = file_info.get('saved_name') or file_info.get('original_name') or ''
                        file_contents[key] = content
        except Exception:
            files_list = []

    assignment_files = []
    assignment_file_contents = {}
    if assignment and assignment.files:
        try:
            raw = json.loads(assignment.files)
            if isinstance(raw, list):
                for i, f in enumerate(raw):
                    name = f.get("original_name") or f.get("name") or f"файл_{i+1}"
                    ext = (f.get("extension") or "").lower()
                    if not ext and "." in name:
                        ext = "." + name.rsplit(".", 1)[-1].lower()
                    assignment_files.append({
                        "index": i,
                        "original_name": name,
                        "size": f.get("size"),
                        "extension": ext,
                        "path": f.get("path"),
                    })
                    if ext in TEXT_EXTENSIONS:
                        content = read_file_content(f.get("path", ""))
                        if content:
                            assignment_file_contents[str(i)] = content
        except Exception:
            assignment_files = []
            assignment_file_contents = {}

    return templates.TemplateResponse(
        "teacher_view_submission.html",
        {
            "request": request,
            "submission": {
                "id": submission.id,
                "grade": submission.grade,
                "submitted_at": submission.submitted_at,
                "github_link": submission.github_link,
                "files": files_list,
                "files_list": files_list,
                "status": submission.status.value if submission.status else 'submitted',
                "feedback": submission.feedback,
                "resubmission_count": submission.resubmission_count or 0,
            },
            "student": student,
            "assignment": assignment,
            "assignment_files": assignment_files,
            "assignment_file_contents": assignment_file_contents,
            "subject": subject,
            "analysis": analysis_data,
            "files_list": files_list,
            "file_contents": file_contents,
        }
    )

@router.post("/submission/{submission_id}/review")
async def review_submission(
    submission_id: int,
    action: str = Form(...),
    grade: Optional[int] = Form(None),
    feedback: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Review submission."""
    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.deleted_at.is_(None)
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")

    allowed_actions = ['accept', 'revision', 'reject', 'reset']
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Недопустимое действие")

    if action == 'accept':
        if grade is None or grade not in [2, 3, 4, 5]:
            raise HTTPException(status_code=400, detail="Необходимо выбрать оценку (2, 3, 4 или 5)")

        submission.status = SubmissionStatus.ACCEPTED
        submission.grade = grade
        submission.feedback = feedback if feedback is not None else f"Работа принята. Оценка: {grade}"

    elif action == 'revision':
        submission.status = SubmissionStatus.REVISION
        submission.grade = None
        submission.resubmission_count += 1
        submission.resubmitted_at = local_now()
        submission.feedback = feedback if feedback is not None else "Отправлено на доработку. Исправьте замечания и сдайте заново."

    elif action == 'reject':
        submission.status = SubmissionStatus.REJECTED
        submission.grade = None
        submission.feedback = feedback if feedback is not None else "Работа отклонена. Требуется серьезная доработка."

    elif action == 'reset':
        submission.status = SubmissionStatus.SUBMITTED
        submission.grade = None
        submission.feedback = None

    submission.updated_at = datetime.now()
    db.commit()
    return RedirectResponse(url=f"/teacher/submission/{submission_id}/view", status_code=303)

@router.post("/assignment/{assignment_id}/submissions/{submission_id}/grade")
async def grade_submission_web(
    assignment_id: int,
    submission_id: int,
    grade: int = Form(...),
    db: Session = Depends(get_db)
):
    """Grade submission web."""
    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.deleted_at.is_(None)
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")

    if submission.status != SubmissionStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Оценку можно выставить только после принятия работы")

    if grade not in [2, 3, 4, 5]:
        raise HTTPException(status_code=400, detail="Оценка должна быть 2, 3, 4 или 5")

    submission.grade = grade
    submission.updated_at = datetime.now()
    db.commit()
    return RedirectResponse(url=f"/teacher/submission/{submission_id}/view", status_code=303)
