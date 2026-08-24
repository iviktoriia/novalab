"""
Админ-панель:
  - преподаватели (пакетное создание)
  - студенты по группам
  - группы (создание, назначение преподавателей)
  - дисциплины (создание, назначение преподавателей)
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import (
    set_session_user,
    clear_session,
    verify_admin_credentials,
    is_admin_session,
    admin_login_redirect,
)
from app.core.security import (
    hash_password,
    generate_password,
    generate_teacher_login,
    generate_registration_code,
)
from app.models.db_models import (
    Teacher,
    TempTeacherPassword,
    Student,
    Group,
    TempPassword,
    Subject,
    GroupTeacher,
    SubjectTeacher,
    GroupSubject,
    Assignment,
    Material,
    Submission,
    RegistrationMethod,
    AttestationType,
)
from app.templates_config import templates
from app.services.grade_prediction import ATTESTATION_LABELS

router = APIRouter(prefix="/admin", tags=["admin"])

def _as_id_list(value) -> list:
    """Form checkbox: None | int | list[int] → list[int]."""
    if value is None:
        return []
    if isinstance(value, list):
        return [int(x) for x in value]
    return [int(value)]

def _safe_reg_code() -> str:
    """Код регистрации группы."""
    try:
        return generate_registration_code()
    except Exception:
        import secrets
        return secrets.token_urlsafe(16)

def _guard(request: Request):
    """True при активной сессии администратора."""
    if not is_admin_session(request):
        return None
    return True

@router.get("/login")
async def admin_login_page(request: Request):
    """HTML-страница: admin login page."""
    if is_admin_session(request):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        "admin_login.html", {"request": request, "error": None}
    )

@router.post("/login")
async def admin_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    """Админ-обработчик: login."""
    if not verify_admin_credentials(login, password):
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Неверный логин или пароль"},
            status_code=401,
        )
    set_session_user(
        request, role="admin", user_id=0, extra={"full_name": "Администратор"}
    )
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.get("/logout")
async def admin_logout(request: Request):
    """Админ-обработчик: logout."""
    clear_session(request)
    return RedirectResponse(url="/admin/login", status_code=303)

@router.get("/dashboard")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Админ-обработчик: dashboard."""
    if not _guard(request):
        return admin_login_redirect()
    created_list = request.session.pop("created_teachers", None)
    success = request.session.pop("flash_success", None)
    error = request.session.pop("flash_error", None)
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "teachers": _teachers_with_passwords(db),
            "error": error,
            "success": success,
            "created_list": created_list,
        },
    )

@router.get("/teachers/create")
async def create_teachers_page(request: Request):
    """HTML-страница: create teachers page."""
    if not _guard(request):
        return admin_login_redirect()
    return templates.TemplateResponse(
        "admin_teachers_create.html",
        {"request": request, "error": None, "full_names": ""},
    )

@router.post("/teachers/create")
async def create_teacher(
    request: Request,
    full_name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Создание: teacher."""
    if not _guard(request):
        return admin_login_redirect()
    names = [full_name.strip()] if full_name.strip() else []
    return await _create_teachers_bulk(request, names, db)

@router.post("/teachers/create-bulk")
async def create_teachers_bulk(
    request: Request,
    full_names: str = Form(...),
    db: Session = Depends(get_db),
):
    """Создание: teachers bulk."""
    if not _guard(request):
        return admin_login_redirect()
    names = [n.strip() for n in full_names.splitlines() if n.strip()]
    return await _create_teachers_bulk(request, names, db)

async def _create_teachers_bulk(request: Request, names: list, db: Session):
    """Вспомогательная функция: create teachers bulk."""
    if not names:
        return templates.TemplateResponse(
            "admin_teachers_create.html",
            {"request": request, "error": "Укажите хотя бы одно имя", "full_names": ""},
            status_code=400,
        )

    created_list = []
    errors = []
    for full_name in names:
        try:
            login = generate_teacher_login(full_name, db)
            password = generate_password(10)
            teacher = Teacher(
                full_name=full_name,
                login=login,
                password_hash=hash_password(password),
                is_active=True,
            )
            db.add(teacher)
            db.flush()
            db.add(TempTeacherPassword(
                teacher_id=teacher.id,
                password=password,
                is_used=False
            ))
            db.flush()
            created_list.append(
                {"full_name": full_name, "login": login, "password": password}
            )
        except Exception as e:
            errors.append(f"{full_name}: {e}")

    db.commit()
    if created_list:
        request.session["created_teachers"] = created_list
        request.session["flash_success"] = f"Создано преподавателей: {len(created_list)}"
    if errors:
        request.session["flash_error"] = "; ".join(errors)
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.post("/teachers/{teacher_id}/delete")
async def delete_teacher(
    request: Request, teacher_id: int, db: Session = Depends(get_db)
):
    """Мягко удаляет преподавателя."""
    if not _guard(request):
        return admin_login_redirect()

    teacher = db.query(Teacher).filter(
        Teacher.id == teacher_id,
        Teacher.deleted_at.is_(None),
    ).first()

    if teacher:
        name = teacher.full_name
        teacher.deleted_at = datetime.now()
        teacher.is_active = False
        db.commit()
        request.session["flash_success"] = f"Преподаватель «{name}» удалён."
    else:
        request.session["flash_error"] = "Преподаватель не найден."

    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.post("/teachers/{teacher_id}/toggle")
async def toggle_teacher(
    request: Request, teacher_id: int, db: Session = Depends(get_db)
):
    """Toggle teacher."""
    if not _guard(request):
        return admin_login_redirect()

    teacher = (
        db.query(Teacher)
        .filter(Teacher.id == teacher_id, Teacher.deleted_at.is_(None))
        .first()
    )

    if not teacher:
        request.session["flash_error"] = "Преподаватель не найден."
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    teacher.is_active = not bool(teacher.is_active)
    db.add(teacher)
    db.commit()
    db.refresh(teacher)

    state = "включён" if teacher.is_active else "отключён"
    request.session["flash_success"] = (
        f"Аккаунт «{teacher.full_name}» {state}."
    )
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.get("/students")
async def admin_students(request: Request, db: Session = Depends(get_db)):
    """Админ-обработчик: students."""
    if not _guard(request):
        return admin_login_redirect()

    groups = db.query(Group).filter(
        Group.deleted_at.is_(None),
        Group.is_active == True
    ).order_by(Group.name).all()

    groups_data = []
    for group in groups:
        students = (
            db.query(Student)
            .filter(
                Student.group_id == group.id,
                Student.deleted_at.is_(None)
            )
            .order_by(Student.full_name)
            .all()
        )
        rows = []
        for s in students:
            temp = (
                db.query(TempPassword)
                .filter(TempPassword.student_id == s.id)
                .first()
            )
            rows.append(
                {
                    "id": s.id,
                    "full_name": s.full_name,
                    "login": s.login,
                    "password": temp.password if temp else None,
                    "registered": s.registered,
                    "created_at": s.created_at,
                    "is_active": s.is_active,
                }
            )
        groups_data.append(
            {
                "id": group.id,
                "name": group.name,
                "registration_code": group.registration_code,
                "registration_method": group.registration_method.value if group.registration_method else "auto",
                "students": rows,
                "students_count": len(rows),
            }
        )

    return templates.TemplateResponse(
        "admin_students.html",
        {"request": request, "groups": groups_data},
    )

@router.get("/groups")
async def admin_groups(request: Request, db: Session = Depends(get_db)):
    """Админ-обработчик: groups."""
    if not _guard(request):
        return admin_login_redirect()

    groups = db.query(Group).filter(
        Group.deleted_at.is_(None),
        Group.is_active == True
    ).order_by(Group.name).all()

    teachers = db.query(Teacher).filter(
        Teacher.deleted_at.is_(None),
        Teacher.is_active == True
    ).order_by(Teacher.full_name).all()

    subjects = db.query(Subject).filter(
        Subject.deleted_at.is_(None),
        Subject.is_active == True
    ).order_by(Subject.name).all()

    rows = []
    for g in groups:
        links = (
            db.query(GroupTeacher).filter(GroupTeacher.group_id == g.id).all()
        )
        teacher_ids = [l.teacher_id for l in links]
        teacher_names = [
            t.full_name for t in teachers if t.id in teacher_ids
        ]
        gs = (
            db.query(GroupSubject).filter(GroupSubject.group_id == g.id).all()
        )
        subject_ids = [x.subject_id for x in gs]
        students_count = (
            db.query(Student)
            .filter(
                Student.group_id == g.id,
                Student.deleted_at.is_(None)
            )
            .count()
        )
        owner = None
        if g.owner_teacher_id:
            owner = (
                db.query(Teacher)
                .filter(
                    Teacher.id == g.owner_teacher_id,
                    Teacher.deleted_at.is_(None)
                )
                .first()
            )
        rows.append(
            {
                "id": g.id,
                "name": g.name,
                "created_by_admin": g.created_by_admin,
                "owner_name": owner.full_name if owner else None,
                "registration_method": g.registration_method.value if g.registration_method else "auto",
                "registration_code": g.registration_code,
                "teacher_ids": teacher_ids,
                "teacher_names": teacher_names,
                "subject_ids": subject_ids,
                "students_count": students_count,
            }
        )

    error_code = request.query_params.get("error")
    success_code = request.query_params.get("success")
    error_messages = {
        "empty": "Укажите название группы.",
        "not_found": "Группа не найдена.",
    }
    success_messages = {
        "created": "Группа создана.",
        "deleted": "Группа удалена.",
        "updated": "Группа обновлена.",
    }

    return templates.TemplateResponse(
        "admin_groups.html",
        {
            "request": request,
            "groups": rows,
            "error": error_messages.get(error_code),
            "success": success_messages.get(success_code),
        },
    )

def _admin_form_teachers(db: Session):
    """Активные преподаватели для форм админки."""
    return (
        db.query(Teacher)
        .filter(Teacher.deleted_at.is_(None), Teacher.is_active == True)
        .order_by(Teacher.full_name)
        .all()
    )

def _admin_form_subjects(db: Session):
    """Активные дисциплины для форм админки."""
    subjects = (
        db.query(Subject)
        .filter(Subject.deleted_at.is_(None), Subject.is_active == True)
        .order_by(Subject.name)
        .all()
    )
    rows = []
    for s in subjects:
        names = [t.full_name for t in s.teachers if t.is_active and t.deleted_at is None]
        s.teacher_name = names[0] if names else None
        rows.append(s)
    return rows

@router.get("/groups/create")
async def admin_create_group_page(request: Request, db: Session = Depends(get_db)):
    """HTML-страница: admin create group page."""
    if not _guard(request):
        return admin_login_redirect()
    return templates.TemplateResponse(
        "admin_groups_create.html",
        {
            "request": request,
            "teachers": _admin_form_teachers(db),
            "subjects": _admin_form_subjects(db),
            "error": None,
            "name": "",
            "students": "",
            "registration_method": "self",
            "selected_teachers": [],
            "selected_subjects": [],
        },
    )

@router.post("/groups/create")
async def admin_create_group(
    request: Request,
    name: str = Form(...),
    registration_method: str = Form("self"),
    students: Optional[str] = Form(None),
    teacher_ids: Optional[List[int]] = Form(None),
    subject_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_db),
):
    """Админ-обработчик: create group."""
    if not _guard(request):
        return admin_login_redirect()

    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            "admin_groups_create.html",
            {
                "request": request,
                "teachers": _admin_form_teachers(db),
                "subjects": _admin_form_subjects(db),
                "error": "Укажите название группы",
                "name": "",
                "students": students or "",
                "registration_method": registration_method,
                "selected_teachers": _as_id_list(teacher_ids),
                "selected_subjects": _as_id_list(subject_ids),
            },
            status_code=400,
        )

    existing = db.query(Group).filter(
        Group.name == name,
        Group.deleted_at.is_(None)
    ).first()

    if existing:
        return templates.TemplateResponse(
            "admin_groups_create.html",
            {
                "request": request,
                "teachers": _admin_form_teachers(db),
                "subjects": _admin_form_subjects(db),
                "error": f"Группа «{name}» уже существует",
                "name": name,
                "students": students or "",
                "registration_method": registration_method,
                "selected_teachers": _as_id_list(teacher_ids),
                "selected_subjects": _as_id_list(subject_ids),
            },
            status_code=400,
        )

    reg_method = RegistrationMethod.SELF if registration_method == "self" else RegistrationMethod.AUTO

    group = Group(
        name=name,
        registration_method=reg_method,
        created_by_admin=True,
        owner_teacher_id=None,
        is_active=True,
    )

    if registration_method == "self":
        group.registration_code = _safe_reg_code()
        group.registration_enabled = True
    else:
        group.registration_code = None
        group.registration_enabled = False

    db.add(group)
    db.flush()

    if registration_method == "auto" and students:
        student_names = [s.strip() for s in students.split('\n') if s.strip()]
        from app.core.security import generate_password as gen_pass, generate_student_login
        import bcrypt

        for student_name in student_names:
            login = generate_student_login(student_name, db)
            password = gen_pass(8)
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

            temp_password = TempPassword(
                student_id=student.id,
                password=password,
                is_used=False
            )
            db.add(temp_password)

    for tid in _as_id_list(teacher_ids):
        teacher = db.query(Teacher).filter(
            Teacher.id == tid,
            Teacher.deleted_at.is_(None),
            Teacher.is_active == True
        ).first()
        if teacher:
            db.add(GroupTeacher(
                group_id=group.id,
                teacher_id=tid,
                assigned_by="admin"
            ))

    for sid in _as_id_list(subject_ids):
        subject = db.query(Subject).filter(
            Subject.id == sid,
            Subject.deleted_at.is_(None),
            Subject.is_active == True
        ).first()
        if subject:
            db.add(GroupSubject(
                group_id=group.id,
                subject_id=sid,
                assigned_by="admin"
            ))

    db.commit()
    return RedirectResponse(url="/admin/groups?success=created", status_code=303)

@router.get("/groups/{group_id}/edit")
async def admin_edit_group_page(
    request: Request, group_id: int, db: Session = Depends(get_db)
):
    """HTML-страница: admin edit group page."""
    if not _guard(request):
        return admin_login_redirect()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None)
    ).first()

    if not group:
        return RedirectResponse(url="/admin/groups", status_code=303)

    teachers = db.query(Teacher).filter(
        Teacher.deleted_at.is_(None),
        Teacher.is_active == True
    ).order_by(Teacher.full_name).all()

    subjects = db.query(Subject).filter(
        Subject.deleted_at.is_(None),
        Subject.is_active == True
    ).order_by(Subject.name).all()

    selected_teachers = [
        l.teacher_id
        for l in db.query(GroupTeacher).filter(GroupTeacher.group_id == group_id).all()
    ]
    selected_subjects = [
        x.subject_id
        for x in db.query(GroupSubject).filter(GroupSubject.group_id == group_id).all()
    ]

    students = db.query(Student).filter(
        Student.group_id == group_id,
        Student.deleted_at.is_(None)
    ).all()
    students_text = "\n".join([s.full_name for s in students])

    return templates.TemplateResponse(
        "admin_group_edit.html",
        {
            "request": request,
            "group": group,
            "teachers": teachers,
            "subjects": subjects,
            "selected_teachers": selected_teachers,
            "selected_subjects": selected_subjects,
            "students_text": students_text,
            "error": None,
        },
    )

@router.post("/groups/{group_id}/edit")
async def admin_edit_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    registration_method: str = Form("self"),
    students: Optional[str] = Form(None),
    teacher_ids: Optional[List[int]] = Form(None),
    subject_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_db),
):
    """Админ-обработчик: edit group."""
    if not _guard(request):
        return admin_login_redirect()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None)
    ).first()

    if not group:
        return RedirectResponse(url="/admin/groups", status_code=303)

    name = name.strip()
    clash = (
        db.query(Group)
        .filter(
            Group.name == name,
            Group.id != group_id,
            Group.deleted_at.is_(None)
        )
        .first()
    )

    if clash:
        return templates.TemplateResponse(
            "admin_group_edit.html",
            {
                "request": request,
                "group": group,
                "teachers": db.query(Teacher).filter(
                    Teacher.deleted_at.is_(None),
                    Teacher.is_active == True
                ).order_by(Teacher.full_name).all(),
                "subjects": db.query(Subject).filter(
                    Subject.deleted_at.is_(None),
                    Subject.is_active == True
                ).order_by(Subject.name).all(),
                "selected_teachers": teacher_ids or [],
                "selected_subjects": subject_ids or [],
                "error": "Группа с таким названием уже есть",
            },
            status_code=400,
        )

    old_method = group.registration_method.value if group.registration_method else "auto"

    group.name = name
    group.registration_method = RegistrationMethod.SELF if registration_method == "self" else RegistrationMethod.AUTO
    group.updated_at = datetime.now()

    if registration_method == "self":
        if not group.registration_code:
            group.registration_code = _safe_reg_code()
        group.registration_enabled = True
    else:
        group.registration_code = None
        group.registration_enabled = False

    if registration_method == "auto" and students:
        student_names = [s.strip() for s in students.split('\n') if s.strip()]
        from app.core.security import generate_password as gen_pass
        import bcrypt

        existing_students = db.query(Student).filter(
            Student.group_id == group_id,
            Student.deleted_at.is_(None)
        ).all()
        existing_names = [s.full_name for s in existing_students]

        for student_name in student_names:
            if student_name not in existing_names:
                try:
                    from app.api.v1.endpoints.teacher import generate_login
                    login = generate_login(student_name, group_id, db)
                except:
                    from app.core.security import generate_student_login
                    login = generate_student_login(student_name, db)

                password = gen_pass(8)
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

                temp_password = TempPassword(
                    student_id=student.id,
                    password=password,
                    is_used=False
                )
                db.add(temp_password)

    if old_method == "self" and registration_method == "auto":
        existing_students = db.query(Student).filter(
            Student.group_id == group_id,
            Student.deleted_at.is_(None)
        ).all()
        from app.core.security import generate_password as gen_pass
        import bcrypt

        for student in existing_students:
            if not student.password_hash or student.password_hash == "":
                password = gen_pass(8)
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                student.password_hash = password_hash
                student.registered = True
                student.registration_code = None
                student.updated_at = datetime.now()

                temp = db.query(TempPassword).filter(TempPassword.student_id == student.id).first()
                if temp:
                    temp.password = password
                else:
                    temp_password = TempPassword(
                        student_id=student.id,
                        password=password,
                        is_used=False
                    )
                    db.add(temp_password)

    db.query(GroupTeacher).filter(GroupTeacher.group_id == group_id).delete()
    for tid in _as_id_list(teacher_ids):
        teacher = db.query(Teacher).filter(
            Teacher.id == tid,
            Teacher.deleted_at.is_(None),
            Teacher.is_active == True
        ).first()
        if teacher:
            db.add(GroupTeacher(
                group_id=group_id,
                teacher_id=tid,
                assigned_by="admin"
            ))

    db.query(GroupSubject).filter(GroupSubject.group_id == group_id).delete()
    for sid in _as_id_list(subject_ids):
        subject = db.query(Subject).filter(
            Subject.id == sid,
            Subject.deleted_at.is_(None),
            Subject.is_active == True
        ).first()
        if subject:
            db.add(GroupSubject(
                group_id=group_id,
                subject_id=sid,
                assigned_by="admin"
            ))

    db.commit()
    return RedirectResponse(url="/admin/groups", status_code=303)

@router.post("/groups/{group_id}/delete")
async def admin_delete_group(
    request: Request, group_id: int, db: Session = Depends(get_db)
):
    """Мягко удаляет группу, студентов и их работы."""
    if not _guard(request):
        return admin_login_redirect()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None),
    ).first()

    if group:
        now = datetime.now()
        group.deleted_at = now
        group.is_active = False

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

        db.commit()
    return RedirectResponse(url="/admin/groups?success=deleted", status_code=303)


@router.get("/subjects")
async def admin_subjects(request: Request, db: Session = Depends(get_db)):
    """Админ-обработчик: subjects."""
    if not _guard(request):
        return admin_login_redirect()

    subjects = db.query(Subject).filter(
        Subject.deleted_at.is_(None),
        Subject.is_active == True
    ).order_by(Subject.name).all()

    teachers = db.query(Teacher).filter(
        Teacher.deleted_at.is_(None),
        Teacher.is_active == True
    ).order_by(Teacher.full_name).all()

    rows = []
    for s in subjects:
        teacher_names = [t.full_name for t in s.teachers if t.is_active and t.deleted_at is None]

        owner = None
        if s.owner_teacher_id:
            owner = (
                db.query(Teacher)
                .filter(
                    Teacher.id == s.owner_teacher_id,
                    Teacher.deleted_at.is_(None)
                )
                .first()
            )
        rows.append(
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "created_by_admin": s.created_by_admin,
                "owner_name": owner.full_name if owner else None,
                "teacher_names": teacher_names,
            }
        )

    error_code = request.query_params.get("error")
    success_code = request.query_params.get("success")
    error_messages = {
        "has_assignments": "Нельзя удалить дисциплину: к ней привязаны задания. Сначала удалите задания.",
        "not_found": "Дисциплина не найдена.",
    }
    success_messages = {
        "deleted": "Дисциплина удалена.",
        "created": "Дисциплина создана.",
        "updated": "Дисциплина обновлена.",
    }
    error_msg = error_messages.get(error_code) if error_code else None
    if error_code and not error_msg and error_code not in error_messages:
        error_msg = None
    success_msg = success_messages.get(success_code) if success_code else None

    return templates.TemplateResponse(
        "admin_subjects.html",
        {
            "request": request,
            "subjects": rows,
            "teachers": teachers,
            "error": error_msg,
            "success": success_msg,
        },
    )

@router.get("/subjects/create")
async def admin_create_subject_page(request: Request, db: Session = Depends(get_db)):
    """HTML-страница: admin create subject page."""
    if not _guard(request):
        return admin_login_redirect()
    return templates.TemplateResponse(
        "admin_subjects_create.html",
        {
            "request": request,
            "teachers": _admin_form_teachers(db),
            "error": None,
            "name": "",
            "description": "",
            "selected_teachers": [],
            "attestation_options": [{"value": k.value, "label": v} for k, v in ATTESTATION_LABELS.items()],
            "selected_attestation": "none",
        },
    )

@router.post("/subjects/create")
async def admin_create_subject(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    attestation_type: str = Form("none"),
    teacher_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_db),
):
    """Админ-обработчик: create subject."""
    if not _guard(request):
        return admin_login_redirect()

    name = name.strip()

    existing = db.query(Subject).filter(
        Subject.name == name,
        Subject.deleted_at.is_(None)
    ).first()

    if existing:
        return templates.TemplateResponse(
            "admin_subjects_create.html",
            {
                "request": request,
                "teachers": _admin_form_teachers(db),
                "error": f"Дисциплина «{name}» уже существует",
                "name": name,
                "description": description or "",
                "selected_teachers": _as_id_list(teacher_ids),
                "attestation_options": [{"value": k.value, "label": v} for k, v in ATTESTATION_LABELS.items()],
                "selected_attestation": attestation_type or "none",
            },
            status_code=400,
        )

    try:
        att = AttestationType(attestation_type or "none")
    except Exception:
        att = AttestationType.NONE

    subject = Subject(
        name=name,
        description=description,
        attestation_type=att,
        owner_teacher_id=None,
        created_by_admin=True,
        is_active=True,
    )
    db.add(subject)
    db.flush()

    for tid in _as_id_list(teacher_ids):
        teacher = db.query(Teacher).filter(
            Teacher.id == tid,
            Teacher.deleted_at.is_(None),
            Teacher.is_active == True
        ).first()
        if teacher:
            db.add(SubjectTeacher(
                subject_id=subject.id,
                teacher_id=tid,
                assigned_by="admin"
            ))

    db.commit()
    return RedirectResponse(url="/admin/subjects?success=created", status_code=303)

@router.get("/subjects/{subject_id}/edit")
async def admin_edit_subject_page(
    request: Request, subject_id: int, db: Session = Depends(get_db)
):
    """HTML-страница: admin edit subject page."""
    if not _guard(request):
        return admin_login_redirect()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()

    if not subject:
        return RedirectResponse(url="/admin/subjects", status_code=303)

    teachers = db.query(Teacher).filter(
        Teacher.deleted_at.is_(None),
        Teacher.is_active == True
    ).order_by(Teacher.full_name).all()

    selected = [
        l.teacher_id
        for l in db.query(SubjectTeacher)
        .filter(SubjectTeacher.subject_id == subject_id)
        .all()
    ]

    return templates.TemplateResponse(
        "admin_subject_edit.html",
        {
            "request": request,
            "subject": subject,
            "teachers": teachers,
            "selected_teachers": selected,
            "error": None,
            "attestation_options": [{"value": k.value, "label": v} for k, v in ATTESTATION_LABELS.items()],
        },
    )

@router.post("/subjects/{subject_id}/edit")
async def admin_edit_subject(
    request: Request,
    subject_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    attestation_type: str = Form("none"),
    teacher_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_db),
):
    """Админ-обработчик: edit subject."""
    if not _guard(request):
        return admin_login_redirect()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()

    if not subject:
        return RedirectResponse(url="/admin/subjects", status_code=303)

    name = name.strip()
    clash = (
        db.query(Subject)
        .filter(
            Subject.name == name,
            Subject.id != subject_id,
            Subject.deleted_at.is_(None)
        )
        .first()
    )

    if clash:
        return templates.TemplateResponse(
            "admin_subject_edit.html",
            {
                "request": request,
                "subject": subject,
                "teachers": db.query(Teacher).filter(
                    Teacher.deleted_at.is_(None),
                    Teacher.is_active == True
                ).order_by(Teacher.full_name).all(),
                "selected_teachers": teacher_ids or [],
                "error": "Дисциплина с таким названием уже есть",
            },
            status_code=400,
        )

    subject.name = name
    subject.description = description
    try:
        subject.attestation_type = AttestationType(attestation_type or "none")
    except Exception:
        subject.attestation_type = AttestationType.NONE
    subject.updated_at = datetime.now()

    db.query(SubjectTeacher).filter(
        SubjectTeacher.subject_id == subject_id
    ).delete()

    for tid in _as_id_list(teacher_ids):
        teacher = db.query(Teacher).filter(
            Teacher.id == tid,
            Teacher.deleted_at.is_(None),
            Teacher.is_active == True
        ).first()
        if teacher:
            db.add(SubjectTeacher(
                subject_id=subject_id,
                teacher_id=tid,
                assigned_by="admin"
            ))

    db.commit()
    return RedirectResponse(url="/admin/subjects", status_code=303)

@router.post("/subjects/{subject_id}/delete")
async def admin_delete_subject(
    request: Request, subject_id: int, db: Session = Depends(get_db)
):
    """Мягкое удаление дисциплины.

    Админ может удалить дисциплину даже если у неё есть задания:
    задания и сдачи тоже помечаются deleted_at (каскад).
    Преподаватели при этом уже могут быть удалены — это не мешает.
    """
    if not _guard(request):
        return admin_login_redirect()

    subject = db.query(Subject).filter(
        Subject.id == subject_id,
        Subject.deleted_at.is_(None)
    ).first()

    if not subject:
        return RedirectResponse(
            url="/admin/subjects?error=not_found", status_code=303
        )

    now = datetime.now()

    assignments = (
        db.query(Assignment)
        .filter(
            Assignment.subject_id == subject_id,
            Assignment.deleted_at.is_(None),
        )
        .all()
    )
    assignment_ids = [a.id for a in assignments]
    for a in assignments:
        a.deleted_at = now
        a.is_active = False

    if assignment_ids:
        submissions = (
            db.query(Submission)
            .filter(
                Submission.assignment_id.in_(assignment_ids),
                Submission.deleted_at.is_(None),
            )
            .all()
        )
        for sub in submissions:
            sub.deleted_at = now

    materials = (
        db.query(Material)
        .filter(
            Material.subject_id == subject_id,
            Material.deleted_at.is_(None),
        )
        .all()
    )
    for m in materials:
        m.deleted_at = now

    db.query(SubjectTeacher).filter(SubjectTeacher.subject_id == subject_id).delete()
    db.query(GroupSubject).filter(GroupSubject.subject_id == subject_id).delete()

    subject.deleted_at = now
    subject.is_active = False
    db.commit()
    return RedirectResponse(
        url="/admin/subjects?success=deleted", status_code=303
    )

def _teachers_with_passwords(db: Session) -> list:
    """Преподаватели с временными паролями."""
    teachers = db.query(Teacher).filter(
        Teacher.deleted_at.is_(None)
    ).order_by(Teacher.full_name.asc(), Teacher.id.asc()).all()

    rows = []
    for t in teachers:
        temp = (
            db.query(TempTeacherPassword)
            .filter(TempTeacherPassword.teacher_id == t.id)
            .first()
        )
        rows.append(
            {
                "id": t.id,
                "full_name": t.full_name,
                "login": t.login,
                "password": temp.password if temp else None,
                "is_active": t.is_active,
                "created_at": t.created_at,
            }
        )
    return rows

@router.get("/groups/{group_id}")
async def admin_group_detail(request: Request, group_id: int, db: Session = Depends(get_db)):
    """Админ-обработчик: group detail."""
    if not _guard(request):
        return admin_login_redirect()

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at.is_(None)
    ).first()

    if not group:
        return RedirectResponse(url="/admin/groups", status_code=303)

    students = (
        db.query(Student)
        .filter(
            Student.group_id == group_id,
            Student.deleted_at.is_(None)
        )
        .order_by(Student.full_name)
        .all()
    )

    rows = []
    for s in students:
        temp = db.query(TempPassword).filter(TempPassword.student_id == s.id).first()
        rows.append({
            "id": s.id,
            "full_name": s.full_name,
            "login": s.login,
            "password": temp.password if temp else None,
            "registered": s.registered,
            "is_active": s.is_active,
        })

    return templates.TemplateResponse(
        "admin_group_detail.html",
        {"request": request, "group": group, "students": rows},
    )

@router.post("/students/{student_id}/delete")
async def admin_delete_student(request: Request, student_id: int, db: Session = Depends(get_db)):
    """Мягко удаляет студента и его работы."""
    if not _guard(request):
        return admin_login_redirect()

    student = db.query(Student).filter(
        Student.id == student_id,
        Student.deleted_at.is_(None),
    ).first()

    group_id = student.group_id if student else None

    if student:
        now = datetime.now()
        student.deleted_at = now
        student.is_active = False
        for sub in (
            db.query(Submission)
            .filter(
                Submission.student_id == student_id,
                Submission.deleted_at.is_(None),
            )
            .all()
        ):
            sub.deleted_at = now
        db.commit()

    if group_id:
        return RedirectResponse(url=f"/admin/groups/{group_id}", status_code=303)
    return RedirectResponse(url="/admin/groups", status_code=303)


@router.post("/students/{student_id}/toggle")
async def admin_toggle_student(request: Request, student_id: int, db: Session = Depends(get_db)):
    """Админ-обработчик: toggle student."""
    if not _guard(request):
        return admin_login_redirect()

    student = db.query(Student).filter(
        Student.id == student_id,
        Student.deleted_at.is_(None)
    ).first()

    if student:
        student.is_active = not student.is_active
        db.commit()
        return RedirectResponse(url=f"/admin/groups/{student.group_id}", status_code=303)
    return RedirectResponse(url="/admin/groups", status_code=303)
