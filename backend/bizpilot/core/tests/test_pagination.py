from __future__ import annotations

from bizpilot.core.pagination import CursorSetPagination
from bizpilot.core.pagination import StandardResultsSetPagination

EXPECTED_PAGE_SIZE = 20
EXPECTED_MAX_PAGE_SIZE = 100


def test_standard_pagination_attributes():
    paginator = StandardResultsSetPagination()
    assert paginator.page_size == EXPECTED_PAGE_SIZE
    assert paginator.max_page_size == EXPECTED_MAX_PAGE_SIZE
    assert paginator.page_size_query_param == "page_size"


def test_cursor_pagination_attributes():
    paginator = CursorSetPagination()
    assert paginator.page_size == EXPECTED_PAGE_SIZE
    assert paginator.ordering == "-created_at"
