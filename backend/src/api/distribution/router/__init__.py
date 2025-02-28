"""
Distribution API Router Package
"""
from fastapi import APIRouter
from .spray_router import router as spray_router
from .receive_router import router as receive_router
from .lookup_router import router as lookup_router

router = APIRouter()

# Include all sub-routers
router.include_router(spray_router, tags=["spray"])
router.include_router(receive_router, tags=["receive"])
router.include_router(lookup_router, tags=["lookup"]) 