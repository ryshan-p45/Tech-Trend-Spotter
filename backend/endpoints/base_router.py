from fastapi import APIRouter
from interfaces.api_interfaces import DataResponse
from interfaces.query_interfaces import HealthResponse


"""
Where main functionality endpoints go
"""


# Initialise router
router = APIRouter()

# Health check route - confirms the API is up (used by Railway and the frontend)
# Public, no auth. Doesn't touch the database, so it answers even when Postgres is down.
@router.get("/health", response_model=DataResponse[HealthResponse])
def health_check() -> DataResponse[HealthResponse]:
    return DataResponse(data=HealthResponse(status="ok"))
