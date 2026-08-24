"""Единое локальное время (Europe/Moscow) для записи и отображения."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("Europe/Moscow")

def local_now() -> datetime:
    """Naive datetime в часовом поясе приложения (для записи в БД)."""
    return datetime.now(APP_TZ).replace(tzinfo=None)

def to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Привести datetime из БД к локальному поясу для отображения.
    SQLite CURRENT_TIMESTAMP / func.now() обычно даёт UTC (naive) —
    считаем naive UTC и конвертируем в APP_TZ.
    Если уже aware — конвертируем как есть.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(APP_TZ).replace(tzinfo=None)

def format_dt(dt: Optional[datetime], fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Форматирует datetime для шаблонов."""
    local = to_local(dt)
    if not local:
        return "—"
    return local.strftime(fmt)
