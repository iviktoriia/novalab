
"""Хеширование паролей и генерация логинов/паролей."""
import re
import secrets
import string
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

def hash_password(password: str) -> str:
    """Хеширует пароль с помощью bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверяет пароль против bcrypt-хеша."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False

def generate_password(length: int = 10) -> str:
    """Генерирует случайный буквенно-цифровой пароль."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def generate_registration_code() -> str:
    """Генерирует код регистрации группы."""
    return secrets.token_urlsafe(16)

def transliterate_name(name: str) -> str:
    """Транслитерирует кириллическое имя в латиницу."""
    translit_map = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
        "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
        "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
        "Ф": "F", "Х": "H", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Sch",
        "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    }
    result = ""
    for char in name:
        if char in translit_map:
            result += translit_map[char]
        elif char.isalpha():
            result += char
        elif char == " ":
            result += "_"
        else:
            result += char
    return result

def _login_suffix(length: int = 4) -> str:
    """Случайный суффикс (не предсказуем из имени)."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def _unique_login(base: str, exists_fn) -> str:
    """base уже с суффиксом; при коллизии добавляем ещё один random."""
    login = base
    if not exists_fn(login):
        return login
    for _ in range(20):
        candidate = f"{base}_{_login_suffix(3)}"
        if not exists_fn(candidate):
            return candidate

    return f"{base}_{secrets.token_hex(3)}"

def generate_student_login(full_name: str, db: Session) -> str:
    """
    Логин студента: translit + случайный суффикс.
    Пример: ivan_petrov_x7k2
    """
    from app.models.db_models import Student

    base = transliterate_name(full_name.lower())
    base = re.sub(r"[^a-z0-9_]", "", base).strip("_")
    if not base:
        base = "student"

    seed = _login_suffix(4)
    candidate = f"{base}_{seed}"

    def exists(login: str) -> bool:
        return db.query(Student).filter(
            Student.login == login,
            Student.deleted_at.is_(None)
        ).first() is not None

    return _unique_login(candidate, exists)

def generate_teacher_login(full_name: str, db: Session) -> str:
    """
    Логин преподавателя: translit + случайный суффикс.
    Пример: mariya_ivanova_a3f9
    """
    from app.models.db_models import Teacher

    base = transliterate_name(full_name.lower())
    base = re.sub(r"[^a-z0-9_]", "", base).strip("_")
    if not base:
        base = "teacher"

    seed = _login_suffix(4)
    candidate = f"{base}_{seed}"

    def exists(login: str) -> bool:
        return db.query(Teacher).filter(
            Teacher.login == login,
            Teacher.deleted_at.is_(None)
        ).first() is not None

    return _unique_login(candidate, exists)
