from typing import Annotated

from fastapi import APIRouter, Depends, Query

from endpoints.dependencies import get_items_repository
from endpoints.errors import ApiError
from functionality.storage.items_repository import InvalidCursorError, ItemsRepository
from interfaces.api_interfaces import DataResponse, ErrorResponse, ItemResponse, ItemStatsResponse, PageResponse, Pagination
from interfaces.collection_interfaces import SourceType

"""
Read-only endpoints for collected items.

Authentication: none yet - these are public, read-only endpoints. Add auth
before the API is exposed beyond local development / a private deployment.
"""


router = APIRouter(tags=["items"])

# Shared error responses documented on every endpoint (OpenAPI)
COMMON_ERRORS = {400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}


@router.get("/items", response_model=PageResponse[ItemResponse], responses=COMMON_ERRORS)
def list_items(
    repository: Annotated[ItemsRepository, Depends(get_items_repository)],
    source_type: Annotated[SourceType | None, Query(description="Only items of this type")] = None,
    source_name: Annotated[str | None, Query(pattern=r"^[a-z0-9_:]{1,100}$",
                                             description="Only items from this source, e.g. 'cisa_kev'")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page (1-100)")] = 25,
    cursor: Annotated[str | None, Query(max_length=500, description="`next_cursor` from the previous page")] = None,
) -> PageResponse[ItemResponse]:
    """Collected items, newest first (by publication date, or first collection if the source gives no date)."""
    try:
        items, next_cursor = repository.list_items(source_type=source_type, source_name=source_name,
                                                   limit=limit, cursor=cursor)
    except InvalidCursorError:
        raise ApiError(400, "invalid_cursor",
                       "The page cursor is not valid. Reload the list from the first page.") from None
    return PageResponse(data=items, pagination=Pagination(next_cursor=next_cursor, limit=limit))


@router.get("/item-stats", response_model=DataResponse[ItemStatsResponse], responses=COMMON_ERRORS)
def get_item_stats(
    repository: Annotated[ItemsRepository, Depends(get_items_repository)],
    days: Annotated[int, Query(ge=1, le=90, description="Window for daily counts and advisory figures (1-90)")] = 14,
) -> DataResponse[ItemStatsResponse]:
    """Totals, daily counts and advisory breakdowns for the dashboard."""
    return DataResponse(data=repository.get_stats(days))
