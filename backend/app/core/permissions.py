
"""Права преподавателя на группы и дисциплины."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.db_models import (
    Group,
    GroupTeacher,
    Subject,
    SubjectTeacher,
    Teacher,
)

def teacher_can_access_group(db: Session, teacher_id: int, group: Group) -> bool:
    """Своя группа или назначенная админом."""
    if group.deleted_at is not None or not group.is_active:
        return False

    if group.owner_teacher_id == teacher_id:
        return True
    link = (
        db.query(GroupTeacher)
        .filter(
            GroupTeacher.group_id == group.id,
            GroupTeacher.teacher_id == teacher_id,
        )
        .first()
    )
    return link is not None

def teacher_can_manage_group(db: Session, teacher_id: int, group: Group) -> bool:
    """Редактирование / удаление / смена регистрации — только владелец."""
    if group.deleted_at is not None or not group.is_active:
        return False
    return group.owner_teacher_id == teacher_id and not group.created_by_admin

def groups_for_teacher(db: Session, teacher_id: int) -> List[Group]:
    """Группы, доступные преподавателю."""
    owned = db.query(Group).filter(
        Group.owner_teacher_id == teacher_id,
        Group.deleted_at.is_(None),
        Group.is_active == True
    ).all()

    assigned_ids = [
        r.group_id
        for r in db.query(GroupTeacher).filter(GroupTeacher.teacher_id == teacher_id).all()
    ]
    assigned = []
    if assigned_ids:
        assigned = db.query(Group).filter(
            Group.id.in_(assigned_ids),
            Group.deleted_at.is_(None),
            Group.is_active == True
        ).all()

    by_id = {g.id: g for g in owned + assigned}
    return list(by_id.values())

def teacher_can_access_subject(db: Session, teacher_id: int, subject: Subject) -> bool:

    """Может ли преподаватель просматривать дисциплину."""
    if subject.deleted_at is not None or not subject.is_active:
        return False

    if subject.owner_teacher_id == teacher_id:
        return True
    link = (
        db.query(SubjectTeacher)
        .filter(
            SubjectTeacher.subject_id == subject.id,
            SubjectTeacher.teacher_id == teacher_id,
        )
        .first()
    )
    return link is not None

def teacher_can_edit_subject(db: Session, teacher_id: int, subject: Subject) -> bool:
    """Редактирование названия/описания — только владелец ."""
    if subject.deleted_at is not None or not subject.is_active:
        return False
    return subject.owner_teacher_id == teacher_id and not subject.created_by_admin

def teacher_can_use_subject(db: Session, teacher_id: int, subject: Subject) -> bool:
    """Материалы и задания — при любом доступе."""
    return teacher_can_access_subject(db, teacher_id, subject)

def subjects_for_teacher(db: Session, teacher_id: int) -> List[Subject]:
    """Дисциплины, доступные преподавателю."""
    owned = db.query(Subject).filter(
        Subject.owner_teacher_id == teacher_id,
        Subject.deleted_at.is_(None),
        Subject.is_active == True
    ).all()

    assigned_ids = [
        r.subject_id
        for r in db.query(SubjectTeacher)
        .filter(SubjectTeacher.teacher_id == teacher_id)
        .all()
    ]
    assigned = []
    if assigned_ids:
        assigned = db.query(Subject).filter(
            Subject.id.in_(assigned_ids),
            Subject.deleted_at.is_(None),
            Subject.is_active == True
        ).all()
    by_id = {s.id: s for s in owned + assigned}
    return list(by_id.values())

def ensure_subject_teacher_link(db: Session, subject_id: int, teacher_id: int) -> None:
    """Создаёт связь SubjectTeacher при отсутствии."""
    exists = (
        db.query(SubjectTeacher)
        .filter(
            SubjectTeacher.subject_id == subject_id,
            SubjectTeacher.teacher_id == teacher_id,
        )
        .first()
    )
    if not exists:
        db.add(SubjectTeacher(
            subject_id=subject_id,
            teacher_id=teacher_id,
            assigned_by="system"
        ))
