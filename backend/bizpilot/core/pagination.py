from rest_framework.pagination import CursorPagination
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Standard page-number pagination with customizable page size."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CursorSetPagination(CursorPagination):
    """Cursor-based pagination for high-volume or real-time event streams."""

    page_size = 20
    page_size_query_param = "page_size"
    ordering = "-created_at"
