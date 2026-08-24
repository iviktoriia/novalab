# app/main.py
from pathlib import Path

from fastapi import HTTPException, FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router
from app.core.config import settings
from app.core.database import engine, Base, get_db, ensure_schema
from app.core.auth import get_student_from_session, student_login_redirect, set_session_user
from app.core.auth_middleware import AuthMiddleware
from app.core.security import verify_password
from app.models.db_models import Student
from app.templates_config import templates

Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(
    title="NovaLab",
    description="NovaLab — платформа для сдачи работ, материалов и аттестации",
    version="1.0.0",
)

@app.exception_handler(HTTPException)
async def html_http_exception_handler(request: Request, exc: HTTPException):
    """401/403 в браузере -> логин; 404 файла -> JSON (модалка) или редирект назад."""
    from fastapi.responses import JSONResponse

    accept = (request.headers.get("accept") or "").lower()
    wants_html = (
        "text/html" in accept
        or request.headers.get("sec-fetch-mode") == "navigate"
        or request.headers.get("sec-fetch-dest") == "document"
        or (request.method in ("GET", "HEAD") and ("*/*" in accept or not accept))
    )

    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail or "")
    is_file_missing = exc.status_code == 404 and (
        "файл" in detail.lower()
        or "file" in detail.lower()
        or "хранилищ" in detail.lower()
    )

    if is_file_missing:
        if wants_html and request.headers.get("sec-fetch-mode") == "navigate":
            referer = request.headers.get("referer") or "/"
            return RedirectResponse(url=referer, status_code=303)
        return JSONResponse({"detail": detail or "Файл не найден или удалён из хранилища"}, status_code=404)

    if exc.status_code in (401, 403) and wants_html:
        pth = request.url.path
        if pth.startswith("/admin"):
            return RedirectResponse(url="/admin/login", status_code=303)
        if pth.startswith("/teacher"):
            return RedirectResponse(url="/teacher/login", status_code=303)
        if pth.startswith("/student") or pth.startswith("/students"):
            return RedirectResponse(url="/student/login", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="college_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)

app.include_router(router)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/student/login")
async def student_login_page(request: Request):
    student_id = request.session.get("user_id")
    if request.session.get("role") == "student" and student_id:
        return RedirectResponse(
            url="/student/dashboard", status_code=303
        )
    return templates.TemplateResponse(
        "student_login.html", {"request": request, "error": None, "login": ""}
    )


@app.post("/student/login")
async def student_login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Вход студента с формы /student/login."""
    login = (login or "").strip()
    if not login or not password:
        return templates.TemplateResponse(
            "student_login.html",
            {"request": request, "error": "Логин и пароль обязательны", "login": login},
            status_code=400,
        )

    student = (
        db.query(Student)
        .filter(Student.login == login, Student.deleted_at.is_(None))
        .first()
    )
    if not student or not verify_password(password, student.password_hash):
        return templates.TemplateResponse(
            "student_login.html",
            {
                "request": request,
                "error": "Неверные учетные данные",
                "login": login,
            },
            status_code=401,
        )
    if not student.is_active:
        return templates.TemplateResponse(
            "student_login.html",
            {
                "request": request,
                "error": "Аккаунт отключён",
                "login": login,
            },
            status_code=403,
        )

    set_session_user(
        request,
        role="student",
        user_id=student.id,
        extra={"full_name": student.full_name},
    )
    return RedirectResponse(url="/student/dashboard", status_code=303)


@app.get("/student/register")
async def student_register_page(request: Request):
    return templates.TemplateResponse(
        "student_register.html",
        {
            "request": request,
            "group_code": "",
            "error": None,
            "success": None,
            "login": "",
        },
    )


@app.get("/student/dashboard")
async def student_dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
):
    student = get_student_from_session(request, db)
    if not student:
        return student_login_redirect()

    return templates.TemplateResponse(
        "student_dashboard.html",
        {
            "request": request,
            "student_id": student.id,
            "student_name": student.full_name,
        },
    )



@app.get("/student/logout")
async def student_logout_page(request: Request):
    """Выход студента."""
    from app.core.auth import clear_session
    clear_session(request)
    return RedirectResponse(url="/student/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Главная страница платформы."""
    return templates.TemplateResponse(
        "home.html",
        {"request": request},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)