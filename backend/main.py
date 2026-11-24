from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_logging import get_logger
from config import DATABASE_URL, FRONTEND_ORIGINS
from database.connection import Database, DatabaseUnavailableError
from endpoints.base_router import router as base_router
from endpoints.collection_runs_router import router as collection_runs_router
from endpoints.database_router import router as database_router
from endpoints.errors import register_error_handlers
from endpoints.items_router import router as items_router
from functionality.storage.runs_repository import RunsRepository


"""
Application entry point. Run from the backend/ directory:
    uvicorn main:app --reload

Apply database migrations first (separate step): python -m database.migrate
"""


logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup: create the (lazy) connection pool and fail any run left active by a previous
    process, so it can't block new runs. The API still starts if the database is down.
    Shutdown: close the pool.
    """
    app.state.database = Database(DATABASE_URL)
    try:
        interrupted = RunsRepository(app.state.database).fail_interrupted_runs(datetime.now(timezone.utc))
        if interrupted:
            logger.warning("Marked interrupted collection runs as failed", extra={"context": {"count": interrupted}})
    except DatabaseUnavailableError as error:
        logger.warning("Database unavailable at startup; data endpoints will return 503 until it is reachable",
                       extra={"context": {"error": str(error)}})
    yield
    app.state.database.close()


app = FastAPI(title="Tech Trend Spotter API", lifespan=lifespan)

# Cors Settings - only the listed frontend origins may call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],  # lets the dashboard read the cool-down on 429s
)

# Every error uses the same {"error": {...}} envelope
register_error_handlers(app)

# Include routes - every route is versioned under /v1
app.include_router(base_router, prefix="/v1")
app.include_router(database_router, prefix="/v1")
app.include_router(items_router, prefix="/v1")
app.include_router(collection_runs_router, prefix="/v1")
