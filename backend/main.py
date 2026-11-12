from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import FRONTEND_ORIGINS
from endpoints.base_router import router as base_router
from endpoints.database_router import router as database_router


"""
Application entry point. Run from the backend/ directory:
    uvicorn main:app --reload
"""


app = FastAPI(title="Tech Trend Spotter API")

# Cors Settings - only the listed frontend origins may call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routes - every route is versioned under /v1
app.include_router(base_router, prefix="/v1")
app.include_router(database_router, prefix="/v1")
