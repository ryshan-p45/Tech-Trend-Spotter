from fastapi import Request

from config import COLLECTION_RUN_COOLDOWN_SECONDS, SOURCES_CONFIG_PATH
from database.connection import Database
from functionality.collection_runs.run_service import CollectionRunService
from functionality.data_collection.collectors.base import BaseCollector
from functionality.data_collection.sources import build_collectors, load_sources_config
from functionality.storage.items_repository import ItemsRepository
from functionality.storage.runs_repository import RunsRepository

"""
FastAPI dependencies: how endpoints get their repositories and services.

Endpoints never build these themselves, so tests can swap in fakes with
app.dependency_overrides without touching a real database or the network.
"""


def get_database(request: Request) -> Database:
    """The shared connection pool created in main.py's lifespan."""
    return request.app.state.database


def get_items_repository(request: Request) -> ItemsRepository:
    return ItemsRepository(get_database(request))


def get_runs_repository(request: Request) -> RunsRepository:
    return RunsRepository(get_database(request))


def _collectors_from_sources_file() -> list[BaseCollector]:
    """Reads sources.yaml on every run, so edits apply without restarting the API."""
    return build_collectors(load_sources_config(SOURCES_CONFIG_PATH))


def get_run_service(request: Request) -> CollectionRunService:
    return CollectionRunService(
        runs=get_runs_repository(request), items=get_items_repository(request),
        build_collectors=_collectors_from_sources_file, cooldown_seconds=COLLECTION_RUN_COOLDOWN_SECONDS,
    )
