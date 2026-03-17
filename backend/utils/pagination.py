"""
Standardized pagination utilities for KeyForge API routes.

Usage in routes:
    from backend.utils.pagination import PaginationParams, paginated_response

    @router.get("/items")
    async def list_items(pagination: PaginationParams = Depends()):
        cursor = db.collection.find(query).skip(pagination.skip).limit(pagination.limit)
        items = await cursor.to_list(pagination.limit)
        total = await db.collection.count_documents(query)
        return paginated_response(items, total, pagination)
"""
from fastapi import Query
from typing import List, Any, Dict
from math import ceil


class PaginationParams:
    """Standard pagination parameters as a FastAPI dependency."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    ):
        self.page = page
        self.page_size = page_size
        self.skip = (page - 1) * page_size
        self.limit = page_size


def paginated_response(
    items: List[Any],
    total: int,
    pagination: PaginationParams,
) -> Dict:
    """
    Create a standardized paginated response.

    Returns:
        {
            "items": [...],
            "pagination": {
                "page": 1,
                "page_size": 20,
                "total_items": 150,
                "total_pages": 8,
                "has_next": true,
                "has_previous": false
            }
        }
    """
    total_pages = ceil(total / pagination.page_size) if pagination.page_size > 0 else 0

    return {
        "items": items,
        "pagination": {
            "page": pagination.page,
            "page_size": pagination.page_size,
            "total_items": total,
            "total_pages": total_pages,
            "has_next": pagination.page < total_pages,
            "has_previous": pagination.page > 1,
        },
    }


# Legacy skip/limit support for backward compatibility
class LegacyPaginationParams:
    """Skip/limit pagination for backward compatibility."""

    def __init__(
        self,
        skip: int = Query(0, ge=0, description="Number of items to skip"),
        limit: int = Query(50, ge=1, le=200, description="Maximum items to return"),
    ):
        self.skip = skip
        self.limit = limit
