from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import bcrypt
import os
import json
from datetime import datetime
from app.core.timeutils import local_now
from pathlib import Path

from app.core.database import get_db
from app.models.db_models import (
    Student, Group, Submission, Assignment, Subject, GroupSubject,
    TempPassword, Material, RegistrationMethod, SubmissionStatus
)
from app.schemas.pydantic_models import StudentCreate, StudentResponse
from app.templates_config import templates
from app.core.auth import set_session_user, clear_session
from app.core.security import verify_password
from app.core.storage import FILE_MISSING_DETAIL,  save_upload, delete_stored, file_response

router = APIRouter(prefix="/students", tags=["students"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp', '.cs', '.go', '.rs',
    '.rb', '.php', '.swift', '.kt', '.scala', '.sh', '.sql', '.html', '.css', '.vue', '.jsx', '.tsx',
    '.txt', '.pdf', '.doc', '.docx', '.rtf', '.odt',
    '.ppt', '.pptx', '.odp',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico',
    '.zip', '.rar', '.7z', '.tar', '.gz'
}

def _get_active_student(student_id: int, db: Session):
    """Студент для API: не удалён. is_active не режем — иначе пустые 404 после отключения."""
    return (
        db.query(Student)
        .filter(Student.id == student_id, Student.deleted_at.is_(None))
        .first()
    )

def get_files_from_submission(submission) -> List[dict]:
    """Получение списка файлов из поля files (JSON)."""
    if submission.files:
        try:
            return json.loads(submission.files)
        except:
            pass
    return []

@router.post("/register-web")
async def student_register_web(
    request: Request,
    group_code: str = Form(...),
    full_name: str = Form(...),
    login: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Обработчик студента: register web."""
    if password != confirm_password:
        return templates.TemplateResponse(
            "student_register.html",
            {"request": request, "error": "Пароли не совпадают", "group_code": group_code, "login": login}
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            "student_register.html",
            {"request": request, "error": "Пароль должен содержать минимум 6 символов", "group_code": group_code, "login": login}
        )

    group = db.query(Group).filter(
        Group.registration_code == group_code,
        Group.registration_enabled == True,
        Group.deleted_at.is_(None),
        Group.is_active == True
    ).first()

    if not group:
        return templates.TemplateResponse(
            "student_register.html",
            {"request": request, "error": "Неверный код группы", "group_code": group_code, "login": login}
        )

    existing = db.query(Student).filter(
        Student.login == login,
        Student.deleted_at.is_(None)
    ).first()
    if existing:
        return templates.TemplateResponse(
            "student_register.html",
            {"request": request, "error": "Этот логин уже занят", "group_code": group_code, "login": login}
        )

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    student = Student(
        full_name=full_name,
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
    db.commit()

    return templates.TemplateResponse(
        "student_register.html",
        {"request": request, "success": "Регистрация прошла успешно!", "group_code": None, "login": None, "error": None}
    )

@router.post("/register", response_model=StudentResponse)
async def register_student_api(student: StudentCreate, db: Session = Depends(get_db)):
    """Register student api."""
    existing = db.query(Student).filter(
        Student.login == student.login,
        Student.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Логин уже зарегистрирован")

    group = db.query(Group).filter(
        Group.id == student.group_id,
        Group.deleted_at.is_(None),
        Group.is_active == True
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    password_hash = bcrypt.hashpw(student.password.encode('utf-8'), bcrypt.gensalt())

    db_student = Student(
        full_name=student.full_name,
        login=student.login,
        password_hash=password_hash.decode('utf-8'),
        group_id=student.group_id,
        registered=True,
        is_active=True,
    )
    db.add(db_student)
    db.flush()

    temp_password = TempPassword(
        student_id=db_student.id,
        password=student.password,
        is_used=False
    )
    db.add(temp_password)
    db.commit()
    db.refresh(db_student)

    return db_student

@router.post("/login")
async def login_student(request: Request, db: Session = Depends(get_db)):
    """Login student."""
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        data = await request.json()
        login = data.get("login")
        password = data.get("password")

        if not login or not password:
            raise HTTPException(status_code=400, detail="Логин и пароль обязательны")

        student = db.query(Student).filter(
            Student.login == login,
            Student.deleted_at.is_(None)
        ).first()

        if not student:
            raise HTTPException(status_code=401, detail="Неверные учетные данные")

        if not verify_password(password, student.password_hash):
            raise HTTPException(status_code=401, detail="Неверные учетные данные")

        if not student.is_active:
            raise HTTPException(status_code=401, detail="Аккаунт отключён")

        set_session_user(
            request,
            role="student",
            user_id=student.id,
            extra={"full_name": student.full_name},
        )
        return {
            "id": student.id,
            "full_name": student.full_name,
            "login": student.login,
            "group_id": student.group_id,
        }
    else:
        form_data = await request.form()
        login = form_data.get("login")
        password = form_data.get("password")

        if not login or not password:
            return templates.TemplateResponse(
                "student_login.html",
                {"request": request, "error": "Логин и пароль обязательны"},
            )

        student = db.query(Student).filter(
            Student.login == login,
            Student.deleted_at.is_(None)
        ).first()

        if not student:
            return templates.TemplateResponse(
                "student_login.html",
                {"request": request, "error": "Неверные учетные данные", "login": login or ""},
            )

        if not verify_password(password, student.password_hash):
            return templates.TemplateResponse(
                "student_login.html",
                {"request": request, "error": "Неверные учетные данные", "login": login or ""},
            )

        set_session_user(
            request,
            role="student",
            user_id=student.id,
            extra={"full_name": student.full_name},
        )
        return RedirectResponse(url="/student/dashboard", status_code=303)

@router.get("/logout")
async def student_logout(request: Request):
    """Обработчик студента: logout."""
    clear_session(request)
    return RedirectResponse(url="/student/login", status_code=303)

@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(student_id: int, db: Session = Depends(get_db)):
    """Получение: get student."""
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.deleted_at.is_(None)
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")
    return student

@router.get("/{student_id}/assignments")
async def get_student_assignments(student_id: int, db: Session = Depends(get_db)):
    """Получение: get student assignments."""
    student = _get_active_student(student_id, db)
    if not student:
        return []
    if not student.group_id:
        return []

    group_subjects = db.query(GroupSubject.subject_id).filter(
        GroupSubject.group_id == student.group_id
    ).all()
    subject_ids = [gs[0] for gs in group_subjects]

    if not subject_ids:
        return []

    assignments = db.query(Assignment).filter(
        Assignment.subject_id.in_(subject_ids),
        Assignment.deleted_at.is_(None),
        Assignment.is_active == True
    ).all()

    submitted_ids = set()
    submissions = db.query(Submission).filter(
        Submission.student_id == student_id,
        Submission.deleted_at.is_(None)
    ).all()
    for sub in submissions:
        submitted_ids.add(sub.assignment_id)

    result = []
    for assignment in assignments:
        subject = db.query(Subject).filter(
            Subject.id == assignment.subject_id,
            Subject.deleted_at.is_(None)
        ).first()
        is_submitted = assignment.id in submitted_ids

        submission = None
        grade_value = None
        files_list = []
        github_link = None
        status = None
        feedback = None

        if is_submitted:
            submission = db.query(Submission).filter(
                Submission.student_id == student_id,
                Submission.assignment_id == assignment.id,
                Submission.deleted_at.is_(None)
            ).first()
            if submission:
                grade_value = submission.grade
                github_link = submission.github_link
                status = submission.status.value if submission.status else 'submitted'
                feedback = submission.feedback
                files_list = get_files_from_submission(submission)

        assignment_files = []
        if assignment.files:
            try:
                raw = json.loads(assignment.files)
                if isinstance(raw, list):
                    for i, f in enumerate(raw):
                        assignment_files.append({
                            "index": i,
                            "original_name": f.get("original_name") or f.get("name") or f"файл_{i+1}",
                            "size": f.get("size"),
                        })
            except Exception:
                assignment_files = []

        result.append({
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "requirements": assignment.requirements,
            "deadline": assignment.deadline,
            "subject_name": subject.name if subject else "Unknown",
            "is_submitted": is_submitted,
            "submission_id": submission.id if submission else None,
            "grade": grade_value,
            "submitted_at": submission.submitted_at if submission else None,
            "files_list": files_list,
            "assignment_files": assignment_files,
            "github_link": github_link,
            "status": status,
            "feedback": feedback
        })

    return result

@router.get("/{student_id}/materials")
async def get_student_materials(student_id: int, db: Session = Depends(get_db)):
    """Материалы дисциплин, привязанных к группе студента."""
    student = _get_active_student(student_id, db)
    if not student or not student.group_id:
        return []

    subject_ids = [
        gs[0]
        for gs in db.query(GroupSubject.subject_id)
        .filter(GroupSubject.group_id == student.group_id)
        .all()
    ]
    if not subject_ids:
        return []

    materials = (
        db.query(Material)
        .filter(
            Material.subject_id.in_(subject_ids),
            Material.deleted_at.is_(None),
            Material.is_published == True
        )
        .order_by(Material.order.asc(), Material.created_at.desc())
        .all()
    )

    result = []
    for m in materials:
        subject = db.query(Subject).filter(
            Subject.id == m.subject_id,
            Subject.deleted_at.is_(None)
        ).first()

        files = []
        if m.files:
            try:
                files = json.loads(m.files)
            except Exception:
                files = []

        result.append({
            "id": m.id,
            "title": m.title,
            "description": m.description,
            "material_type": m.material_type.value if m.material_type else "other",
            "subject_name": subject.name if subject else "—",
            "files": files,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "order": m.order,
        })
    return result

@router.get("/materials/{material_id}/download/{file_index}")
async def student_download_material_file(
    material_id: int,
    file_index: int,
    db: Session = Depends(get_db),
):
    """Обработчик студента: download material file."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.deleted_at.is_(None),
        Material.is_published == True
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")

    files = []
    if material.files:
        try:
            files = json.loads(material.files)
        except Exception:
            files = []

    if not (0 <= file_index < len(files)):
        raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

    file_info = files[file_index]
    path = Path(file_info.get("path", ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

    return FileResponse(
        path=str(path),
        filename=file_info.get("original_name") or path.name,
    )

@router.get("/assignments/{assignment_id}/download/{file_index}")
async def student_download_assignment_file(
    assignment_id: int,
    file_index: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Скачать файл задания (от преподавателя) студентом своей группы."""
    from pathlib import Path as FsPath
    from fastapi.responses import FileResponse

    student_id = request.session.get("user_id")
    if request.session.get("role") != "student" or not student_id:
        raise HTTPException(status_code=401, detail="Требуется вход")

    student = _get_active_student(int(student_id), db)
    if not student or not student.group_id:
        raise HTTPException(status_code=404, detail="Студент не найден")

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None),
        Assignment.is_active == True,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    allowed = (
        db.query(GroupSubject)
        .filter(
            GroupSubject.group_id == student.group_id,
            GroupSubject.subject_id == assignment.subject_id,
        )
        .first()
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к этому заданию")

    if not assignment.files:
        raise HTTPException(status_code=404, detail="Файлы не прикреплены")
    try:
        files = json.loads(assignment.files)
    except Exception:
        raise HTTPException(status_code=404, detail="Файлы недоступны")
    if not (0 <= file_index < len(files)):
        raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

    info = files[file_index]
    try:
        return file_response(info, filename=info.get("original_name") or info.get("name") or "file")
    except Exception:
        raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

@router.post("/{student_id}/upload")
async def upload_submission(
    student_id: int,
    assignment_id: int = Form(...),
    github_link: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Загрузка: submission."""
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.deleted_at.is_(None),
        Student.is_active == True
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.deleted_at.is_(None),
        Assignment.is_active == True
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    existing = db.query(Submission).filter(
        Submission.student_id == student_id,
        Submission.assignment_id == assignment_id,
        Submission.deleted_at.is_(None)
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Вы уже сдали это задание")

    has_files = files and len(files) > 0 and any(f.filename for f in files)
    has_github = github_link and github_link.strip()

    if not has_files and not has_github:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы один файл или укажите ссылку на GitHub")

    saved_files = []

    if has_files:
        for file in files:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Недопустимый тип файла: {file.filename}"
                )

            content = await file.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Файл {file.filename} слишком большой (максимум 20MB)")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"student_{student_id}_assignment_{assignment_id}_{timestamp}_{file.filename}"
            saved_files.append(
                save_upload(
                    content,
                    folder="uploads",
                    safe_filename=safe_filename,
                    original_name=file.filename,
                    extension=file_extension,
                )
            )

    submission = Submission(
        student_id=student_id,
        assignment_id=assignment_id,
        files=json.dumps(saved_files) if saved_files else None,
        github_link=github_link.strip() if github_link and github_link.strip() else None,
        grade=None,
        status=SubmissionStatus.SUBMITTED,
        submitted_at=local_now(),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    return {
        "status": "success",
        "message": "Работа успешно загружена",
        "submission_id": submission.id,
        "files_count": len(saved_files),
        "has_github_link": bool(github_link and github_link.strip())
    }

@router.get("/{student_id}/submissions")
async def get_student_submissions(student_id: int, db: Session = Depends(get_db)):
    """Получение: get student submissions."""
    student = _get_active_student(student_id, db)
    if not student:
        return []

    submissions = db.query(Submission).filter(
        Submission.student_id == student_id,
        Submission.deleted_at.is_(None)
    ).order_by(Submission.submitted_at.desc()).all()

    result = []
    for sub in submissions:
        assignment = db.query(Assignment).filter(
            Assignment.id == sub.assignment_id,
            Assignment.deleted_at.is_(None)
        ).first()
        subject = None
        if assignment:
            subject = db.query(Subject).filter(
                Subject.id == assignment.subject_id,
                Subject.deleted_at.is_(None)
            ).first()

        files_list = get_files_from_submission(sub)

        assignment_files = []
        if assignment and assignment.files:
            try:
                import json as _json
                raw = _json.loads(assignment.files) if isinstance(assignment.files, str) else assignment.files
                if isinstance(raw, list):
                    for i, f in enumerate(raw):
                        assignment_files.append({
                            "name": f.get("original_name") or f.get("name") or f.get("saved_name") or f"file_{i}",
                            "index": i,
                        })
            except Exception:
                assignment_files = []

        result.append({
            "id": sub.id,
            "assignment_id": sub.assignment_id,
            "assignment_title": assignment.title if assignment else "Unknown",
            "description": assignment.description if assignment else None,
            "requirements": assignment.requirements if assignment else None,
            "assignment_files": assignment_files,
            "subject_name": subject.name if subject else "Unknown",
            "files_list": files_list,
            "github_link": sub.github_link,
            "submitted_at": sub.submitted_at,
            "grade": sub.grade,
            "is_graded": sub.grade is not None,
            "status": sub.status.value if sub.status else 'submitted',
            "feedback": sub.feedback,
            "resubmission_count": sub.resubmission_count or 0
        })

    return result

@router.get("/submission/{submission_id}/download/{file_index}")
async def download_submission_file(
    submission_id: int,
    file_index: int = 0,
    db: Session = Depends(get_db)
):
    """Скачивание: submission file."""
    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.deleted_at.is_(None)
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")

    files = get_files_from_submission(submission)

    if files and 0 <= file_index < len(files):
        try:
            return file_response(files[file_index])
        except Exception:
            pass
    raise HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

@router.get("/submission/{submission_id}/download")
async def download_submission(submission_id: int, db: Session = Depends(get_db)):
    """Скачивание: submission."""
    return await download_submission_file(submission_id, 0, db)

@router.post("/{student_id}/reload")
async def reload_submission(
    student_id: int,
    submission_id: int = Form(...),
    github_link: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Reload submission."""
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.deleted_at.is_(None),
        Student.is_active == True
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.student_id == student_id,
        Submission.deleted_at.is_(None)
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")

    if submission.grade is not None:
        raise HTTPException(status_code=400, detail="Нельзя перезагрузить уже оцененную работу")

    has_files = files and len(files) > 0 and any(f.filename for f in files)
    has_github = github_link and github_link.strip()

    if not has_files and not has_github:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы один файл или укажите ссылку на GitHub")

    old_files = get_files_from_submission(submission)
    for file_info in old_files:
        delete_stored(file_info)

    saved_files = []

    if has_files:
        for file in files:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {file.filename}")

            content = await file.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Файл {file.filename} слишком большой (максимум 20MB)")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"student_{student_id}_assignment_{submission.assignment_id}_{timestamp}_{file.filename}"
            saved_files.append(
                save_upload(
                    content,
                    folder="uploads",
                    safe_filename=safe_filename,
                    original_name=file.filename,
                    extension=file_extension,
                )
            )

    submission.files = json.dumps(saved_files) if saved_files else None
    submission.github_link = github_link.strip() if github_link and github_link.strip() else None
    submission.submitted_at = local_now()
    submission.resubmission_count += 1
    submission.resubmitted_at = local_now()
    submission.status = SubmissionStatus.SUBMITTED
    
    db.commit()

    return {
        "status": "success",
        "message": "Работа успешно перезагружена",
        "submission_id": submission.id,
        "files_count": len(saved_files),
        "has_github_link": bool(github_link and github_link.strip())
    }

@router.delete("/submission/{submission_id}/delete")
async def delete_submission(request: Request, submission_id: int, db: Session = Depends(get_db)):
    """Мягко удаляет несданную/неоценённую работу текущего студента."""
    student_id = request.session.get("user_id")
    if request.session.get("role") != "student" or not student_id:
        raise HTTPException(status_code=401, detail="Требуется вход студента")

    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.deleted_at.is_(None),
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    if int(submission.student_id) != int(student_id):
        raise HTTPException(status_code=403, detail="Нельзя удалить чужую работу")

    # оценённую или принятую нельзя удалить
    if submission.grade is not None:
        raise HTTPException(status_code=400, detail="Нельзя удалить уже оцененную работу")
    if submission.status is not None:
        st = submission.status.value if hasattr(submission.status, "value") else str(submission.status)
        if st in ("accepted",):
            raise HTTPException(status_code=400, detail="Нельзя удалить принятую работу")

    files = get_files_from_submission(submission)
    for file_info in files:
        try:
            delete_stored(file_info)
        except Exception:
            pass

    submission.deleted_at = local_now()
    db.commit()
    return {
        "status": "success",
        "message": "Работа успешно удалена",
        "submission_id": submission_id,
    }

