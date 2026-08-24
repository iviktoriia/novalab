
"""Авторизация через session cookie. Роли: student | teacher | admin."""
from typing import Optional, Union

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import Student, Teacher

def set_session_user(
    request: Request,
    role: str,
    user_id: int,
    extra: Optional[dict] = None,
) -> None:
    """Записать пользователя в session (предыдущая сессия очищается)."""
    request.session.clear()
    request.session["role"] = role
    request.session["user_id"] = user_id
    if extra:
        for k, v in extra.items():
            request.session[k] = v

def clear_session(request: Request) -> None:
    """Очищает текущую сессию."""
    request.session.clear()

def get_session_role(request: Request) -> Optional[str]:
    """Возвращает роль из сессии или None."""
    return request.session.get("role")

def get_session_user_id(request: Request) -> Optional[int]:
    """Возвращает user_id из сессии или None."""
    return request.session.get("user_id")

def verify_admin_credentials(login: str, password: str) -> bool:
    """Проверяет логин и пароль администратора."""
    return login == settings.admin_login and password == settings.admin_password

def get_student_from_session(request: Request, db: Session) -> Optional[Student]:
    """Активный студент из сессии или None."""
    if request.session.get("role") != "student":
        return None
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(Student).filter(
        Student.id == user_id,
        Student.deleted_at.is_(None),
        Student.is_active == True
    ).first()

def get_teacher_from_session(request: Request, db: Session) -> Optional[Teacher]:
    """Активный преподаватель из сессии или None."""
    if request.session.get("role") != "teacher":
        return None
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(Teacher).filter(
        Teacher.id == user_id,
        Teacher.deleted_at.is_(None),
        Teacher.is_active == True
    ).first()

def is_admin_session(request: Request) -> bool:
    """True, если в сессии роль admin."""
    return request.session.get("role") == "admin"

def require_student(request: Request, db: Session = Depends(get_db)) -> Student:
    """Depends: требует вход студента, иначе 401."""
    student = get_student_from_session(request, db)
    if not student:
        raise HTTPException(status_code=401, detail="Требуется вход студента")
    return student

def require_teacher(request: Request, db: Session = Depends(get_db)) -> Teacher:
    """Depends: требует вход преподавателя, иначе 401."""
    teacher = get_teacher_from_session(request, db)
    if not teacher:
        raise HTTPException(status_code=401, detail="Требуется вход преподавателя")
    return teacher

def require_admin(request: Request) -> dict:
    """Depends: требует сессию администратора, иначе 401."""
    if not is_admin_session(request):
        raise HTTPException(status_code=401, detail="Требуется вход администратора")
    return {"role": "admin", "login": settings.admin_login}

def student_login_redirect() -> RedirectResponse:
    """Редирект на страницу входа студента."""
    return RedirectResponse(url="/student/login", status_code=303)

def teacher_login_redirect() -> RedirectResponse:
    """Редирект на страницу входа преподавателя."""
    return RedirectResponse(url="/teacher/login", status_code=303)

def admin_login_redirect() -> RedirectResponse:
    """Редирект на страницу входа администратора."""
    return RedirectResponse(url="/admin/login", status_code=303)

def optional_session(request: Request) -> dict:
    """Информация о текущей сессии без обязательного входа."""
    return {
        "role": request.session.get("role"),
        "user_id": request.session.get("user_id"),
        "full_name": request.session.get("full_name"),
    }
