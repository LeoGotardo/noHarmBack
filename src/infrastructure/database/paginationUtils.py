"""Pagination utilities for database repositories.

This module provides helper functions for implementing pagination
in SQLAlchemy repository queries.
"""

from sqlalchemy.orm import Query
from typing import TypeVar, Generic, List, Tuple
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

T = TypeVar('T')


def paginateQuery(
    query: Query,
    page: int,
    pageSize: int
) -> Tuple[List[T], int]:
    """Apply pagination to a SQLAlchemy query.

    Args:
        query: SQLAlchemy query object
        page: Page number (1-indexed)
        pageSize: Number of items per page

    Returns:
        Tuple of (paginated items, total count)
    """
    # Get total count before applying pagination
    total = query.count()

    # Apply pagination
    offset = (page - 1) * pageSize
    paginatedQuery = query.offset(offset).limit(pageSize)

    return paginatedQuery.all(), total


def getPaginatedResult(
    query: Query,
    params: PaginationParams
) -> PaginatedResponse[T]:
    """Execute a paginated query and return a PaginatedResponse.

    This is a convenience method that combines paginateQuery and
    createPaginatedResponse.

    Args:
        query: SQLAlchemy query object
        params: Pagination parameters

    Returns:
        PaginatedResponse with items and metadata
    """
    items, total = paginateQuery(query, params.page, params.pageSize)
    return createPaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        pageSize=params.pageSize
    )


class PaginatedRepository:
    """Mixin class for repositories that need pagination support.

    Example:
        class UserRepository(PaginatedRepository):
            def findAllPaginated(self, params: PaginationParams):
                query = self.session.query(UserModel)
                return self.paginate(query, params)
    """

    def paginate(
        self,
        query: Query,
        params: PaginationParams
    ) -> PaginatedResponse[T]:
        """Apply pagination to a query using this repository's session.

        Args:
            query: SQLAlchemy query object
            params: Pagination parameters

        Returns:
            PaginatedResponse with items and metadata
        """
        return getPaginatedResult(query, params)
