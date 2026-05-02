from fastapi import APIRouter

from .admin import router as admin_router
from .ai import router as ai_router
from .attachments import router as attachments_router
from .auth import router as auth_router
from .experiments import router as experiments_router
from .jupyterhub import router as jupyterhub_router
from .student import router as student_router
from .submissions import router as submissions_router
from .system import router as system_router
from .teacher import router as teacher_router

router = APIRouter()

router.include_router(system_router)
router.include_router(auth_router)
router.include_router(jupyterhub_router)
router.include_router(admin_router)
router.include_router(experiments_router)
router.include_router(submissions_router)
router.include_router(student_router)
router.include_router(teacher_router)
router.include_router(attachments_router)
router.include_router(ai_router)
