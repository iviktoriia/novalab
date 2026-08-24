from fastapi.templating import Jinja2Templates
from pathlib import Path
import json

from app.core.timeutils import format_dt, to_local

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def from_json_filter(value):
    """Преобразует JSON строку в Python объект."""
    if not value:
        return {}
    try:
        return json.loads(value)
    except:
        return {}

templates.env.filters["format_dt"] = format_dt
templates.env.filters["to_local"] = to_local
templates.env.filters["from_json"] = from_json_filter
