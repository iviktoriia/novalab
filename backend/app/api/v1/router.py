from fastapi import APIRouter
from app.api.v1.endpoints import students, teacher, admin, teacher_auth

router = APIRouter()

router.include_router(students.router)
router.include_router(teacher_auth.router)
router.include_router(teacher.router)
router.include_router(admin.router)

@router.get("/test")
async def test_route():
    """Test route."""
    return {
        "message": "API v1 is working",
        "routes": ["/students", "/teacher", "/admin"],
    }
