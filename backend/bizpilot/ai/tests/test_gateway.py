from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase

from bizpilot.ai.gateway import MockProvider
from bizpilot.ai.gateway import extract_json_array
from bizpilot.ai.gateway import extract_json_object
from bizpilot.ai.gateway import get_cached_or_complete

EXPECTED_CHUNKS = 5


class AIGatewayTest(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def tearDown(self) -> None:
        cache.clear()

    def test_mock_provider_complete_and_stream(self) -> None:
        provider = MockProvider()
        res = provider.complete([{"role": "user", "content": "Hello AI"}])
        assert res.content != ""
        assert res.model == "mock/bizpilot-ai"

        chunks = list(provider.stream([{"role": "user", "content": "Hello"}]))
        assert len(chunks) == EXPECTED_CHUNKS

    def test_extract_json_array(self) -> None:
        text = 'Here is your list:\n```json\n[{"name": "Item 1"}]\n```'
        arr = extract_json_array(text)
        assert arr == [{"name": "Item 1"}]

        # Direct JSON array without backticks
        text2 = '[{"a": 1}, {"b": 2}]'
        assert extract_json_array(text2) == [{"a": 1}, {"b": 2}]

        # Invalid
        assert extract_json_array("no json here") is None

    def test_extract_json_object(self) -> None:
        text = 'Result: ```json\n{"status": "ok", "count": 42}\n```'
        obj = extract_json_object(text)
        assert obj == {"status": "ok", "count": 42}

        # Direct
        assert extract_json_object('{"key": "val"}') == {"key": "val"}
        assert extract_json_object("invalid") is None

    def test_cached_complete(self) -> None:
        provider = MockProvider()
        messages = [{"role": "user", "content": "Cache me please"}]
        res1 = get_cached_or_complete(provider, messages)
        res2 = get_cached_or_complete(provider, messages)
        assert res1.content == res2.content
