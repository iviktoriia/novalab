"""AI-анализ: удалён из платформы."""
from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis-removed"])

@router.get("/")
async def analysis_disabled():
    return {"status": "disabled", "message": "AI-анализ отключён"}
