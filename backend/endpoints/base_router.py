from fastapi import APIRouter
from interfaces.query_interfaces import HealthResponse


"""
Where main functionality endpoints go
"""


# Initialise router
router = APIRouter()

# Health check route - confirms the API is up (used by Railway and the frontend)
@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
