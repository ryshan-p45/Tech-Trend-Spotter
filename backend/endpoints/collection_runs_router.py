from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from endpoints.dependencies import get_run_service, get_runs_repository
from endpoints.errors import ApiError
from functionality.collection_runs.run_service import CollectionRunService, RunCooldownError
from functionality.storage.runs_repository import RunAlreadyActiveError, RunsRepository
from interfaces.api_interfaces import CollectionRunResponse, DataResponse, ErrorResponse

"""
Endpoints to start a collection run and follow its progress.

A run takes several seconds (it calls every external source), so it is
asynchronous: POST returns 202 with the queued run straight away, and the
client polls GET /v1/collection-runs/{run_id} until it is 'completed' or 'failed'.

Authentication: none yet. POST triggers outbound requests, so it is guarded by
"one run at a time" (409) and a cool-down between runs (429). Add auth before
exposing the API publicly.
"""


router = APIRouter(tags=["collection runs"])

COMMON_ERRORS = {503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}


@router.post("/collection-runs", status_code=202, response_model=DataResponse[CollectionRunResponse],
             responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, **COMMON_ERRORS})
def create_collection_run(
    background_tasks: BackgroundTasks,
    service: Annotated[CollectionRunService, Depends(get_run_service)],
) -> DataResponse[CollectionRunResponse]:
    """Starts collecting from every enabled source. Returns the queued run to poll."""
    try:
        run = service.request_run()
    except RunAlreadyActiveError:
        raise ApiError(409, "run_in_progress",
                       "A collection run is already in progress. Wait for it to finish.") from None
    except RunCooldownError as error:
        raise ApiError(429, "run_cooldown",
                       f"A run was started recently. Try again in {error.retry_after_seconds} seconds.",
                       headers={"Retry-After": str(error.retry_after_seconds)}) from None

    background_tasks.add_task(service.execute_run, run.run_id)  # runs after the 202 is sent
    return DataResponse(data=run)


@router.get("/collection-runs/latest", response_model=DataResponse[CollectionRunResponse],
            responses={404: {"model": ErrorResponse}, **COMMON_ERRORS})
def get_latest_collection_run(
    repository: Annotated[RunsRepository, Depends(get_runs_repository)],
) -> DataResponse[CollectionRunResponse]:
    """The most recently requested run."""
    runs = repository.list_runs(limit=1)
    if not runs:
        raise ApiError(404, "no_runs", "No collection has been run yet. Start one to collect data.")
    return DataResponse(data=runs[0])


@router.get("/collection-runs/{run_id}", response_model=DataResponse[CollectionRunResponse],
            responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, **COMMON_ERRORS})
def get_collection_run(
    run_id: UUID,
    repository: Annotated[RunsRepository, Depends(get_runs_repository)],
) -> DataResponse[CollectionRunResponse]:
    """One run, for polling its progress."""
    run = repository.get_run(str(run_id))
    if run is None:
        raise ApiError(404, "run_not_found", "That collection run doesn't exist. Start a new run.")
    return DataResponse(data=run)
