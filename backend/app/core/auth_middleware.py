
"""
Защита маршрутов по session cookie.

Публичные (без входа):
  - /student/login, /student/register
  - /students/login, /students/register, /students/register-web
  - /teacher/login
  - /admin/login
  - /static/*, /docs, /openapi.json, /redoc, /

Защищённые:
  - /admin/* -> role admin
  - /teacher/* -> role teacher
  - /student/* -> role student
  - /students/* -> role student 
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

PUBLIC_EXACT = {
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/student/login",
    "/student/register",
    "/students/login",
    "/students/register",
    "/students/register-web",
    "/teacher/login",
    "/admin/login",
    "/test",
}

PUBLIC_PREFIXES = (
    "/static/",
    "/docs",
    "/redoc",
    "/openapi.json",
)

def _is_public(path: str) -> bool:
    """True, если путь доступен без входа."""
    if path in PUBLIC_EXACT:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False

def _wants_html(request: Request) -> bool:
    """Браузерная навигация / форма -> редирект на логин, иначе JSON."""
    accept = (request.headers.get("accept") or "").lower()

    if "application/json" in accept and "text/html" not in accept:
        return False

    if request.headers.get("sec-fetch-mode") == "navigate":
        return True
    if request.headers.get("sec-fetch-dest") in ("document", "iframe"):
        return True
    if "text/html" in accept:
        return True
    if request.method in ("GET", "HEAD") and (
        not accept or "*/*" in accept or "text/*" in accept
    ):
        return True
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        return True
    if "multipart/form-data" in content_type:
        return True
    return False

def _unauthorized(request: Request, login_url: str, detail: str):
    """Редирект на логин (HTML) или JSON 401 (API)."""
    if _wants_html(request):
        return RedirectResponse(url=login_url, status_code=303)
    return JSONResponse({"detail": detail}, status_code=401)

class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware проверки ролей по session cookie."""
    async def dispatch(self, request: Request, call_next):
        """Проверка роли и доступности маршрута."""
        path = request.url.path

        if _is_public(path):
            return await call_next(request)

        role = request.session.get("role")
        user_id = request.session.get("user_id")

        if path.startswith("/admin"):
            if role != "admin":
                return _unauthorized(
                    request, "/admin/login", "Требуется вход администратора"
                )
            return await call_next(request)

        if path.startswith("/teacher"):
            if role != "teacher":
                return _unauthorized(
                    request, "/teacher/login", "Требуется вход преподавателя"
                )
            return await call_next(request)

        if path.startswith("/student"):
            if role != "student" or not user_id:
                return _unauthorized(
                    request, "/student/login", "Требуется вход студента"
                )
            return await call_next(request)

        if path.startswith("/students/"):
            if role != "student" or not user_id:
                return _unauthorized(
                    request, "/student/login", "Требуется вход студента"
                )
            parts = path.rstrip("/").split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                if int(parts[2]) != int(user_id):
                    if _wants_html(request):
                        return RedirectResponse(url="/student/dashboard", status_code=303)
                    return JSONResponse(
                        {"detail": "Нет доступа к данным другого студента"},
                        status_code=403,
                    )
            return await call_next(request)

        return await call_next(request)
