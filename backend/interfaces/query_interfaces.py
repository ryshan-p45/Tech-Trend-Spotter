from typing import Literal
from pydantic import BaseModel, Field

"""
Interfaces related to search queries
"""


class HealthResponse(BaseModel):
    """Response returned by the health check endpoint."""
    status: Literal["ok"] = Field(description="Always 'ok' when the API is reachable")
