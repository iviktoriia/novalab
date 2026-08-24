
"""Вход / выход преподавателя."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import (
    set_session_user,
    clear_session,
    get_teacher_from_session,
)
from app.core.security import verify_password
from app.models.db_models import Teacher
from app.templates_config import templates

router = APIRouter(prefix="/teacher", tags=["teacher-auth"])

@router.get("/login")
async def teacher_login_page(request: Request, db: Session = Depends(get_db)):
    """HTML-страница: teacher login page."""
    if get_teacher_from_session(request, db):
        return RedirectResponse(url="/teacher/dashboard", status_code=303)
    return templates.TemplateResponse(
        "teacher_login.html",
        {"request": request, "error": None, "login": ""},
    )

@router.post("/login")
async def teacher_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Обработчик преподавателя: login."""
    login = login.strip()
    teacher = db.query(Teacher).filter(
        Teacher.login == login,
        Teacher.deleted_at.is_(None)
    ).first()

    if not teacher or not verify_password(password, teacher.password_hash):
        return templates.TemplateResponse(
            "teacher_login.html",
            {
                "request": request,
                "error": "Неверный логин или пароль",
                "login": login,
            },
            status_code=401,
        )

    if not teacher.is_active:
        return templates.TemplateResponse(
            "teacher_login.html",
            {
                "request": request,
                "error": "Аккаунт отключён. Обратитесь к администратору.",
                "login": login,
            },
            status_code=403,
        )

    set_session_user(
        request,
        role="teacher",
        user_id=teacher.id,
        extra={"full_name": teacher.full_name},
    )
    return RedirectResponse(url="/teacher/dashboard", status_code=303)

@router.get("/logout")
async def teacher_logout(request: Request):
    """Обработчик преподавателя: logout."""
    clear_session(request)
    return RedirectResponse(url="/teacher/login", status_code=303)
