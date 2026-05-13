from pydantic import BaseModel, ConfigDict, Field
from typing import Generic, TypeVar, Optional
from uuid import UUID
from datetime import datetime

T = TypeVar('T')


class PaginationParams(BaseModel):
    """Query parameters for pagination.

    Use with FastAPI's Depends to extract pagination from query params.
    """
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    pageSize: int = Field(20, ge=1, le=100, description="Number of items per page")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "page": 1,
            "pageSize": 20
        }
    })


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper.

    Wraps any list response with pagination metadata.
    """
    items: list[T] = Field(..., description="List of items for the current page")
    total: int = Field(..., ge=0, description="Total number of items across all pages")
    page: int = Field(..., ge=1, description="Current page number")
    pageSize: int = Field(..., ge=1, description="Number of items per page")
    totalPages: int = Field(..., ge=0, description="Total number of pages")
    hasNext: bool = Field(..., description="Whether there is a next page")
    hasPrevious: bool = Field(..., description="Whether there is a previous page")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "items": [],
            "total": 100,
            "page": 1,
            "pageSize": 20,
            "totalPages": 5,
            "hasNext": True,
            "hasPrevious": False
        }
    })


class PaginationMetadata(BaseModel):
    """Pagination metadata for response headers or separate endpoint."""
    total: int = Field(..., ge=0, description="Total number of items")
    page: int = Field(..., ge=1, description="Current page number")
    pageSize: int = Field(..., ge=1, description="Number of items per page")
    totalPages: int = Field(..., ge=0, description="Total number of pages")
    hasNext: bool = Field(..., description="Whether there is a next page")
    hasPrevious: bool = Field(..., description="Whether there is a previous page")


def createPaginatedResponse(
    items: list[T],
    total: int,
    page: int,
    pageSize: int
) -> PaginatedResponse[T]:
    """Create a paginated response with calculated metadata.

    Args:
        items: List of items for the current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        pageSize: Number of items per page

    Returns:
        PaginatedResponse with calculated hasNext, hasPrevious, totalPages
    """
    totalPages = (total + pageSize - 1) // pageSize if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        pageSize=pageSize,
        totalPages=totalPages,
        hasNext=page < totalPages,
        hasPrevious=page > 1
    )


def calculateOffset(page: int, pageSize: int) -> int:
    """Calculate the SQL OFFSET value from page and pageSize.

    Args:
        page: Page number (1-indexed)
        pageSize: Number of items per page

    Returns:
        SQL OFFSET value (0-indexed)
    """
    return (page - 1) * pageSize
