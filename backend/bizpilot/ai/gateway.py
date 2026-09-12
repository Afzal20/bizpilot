from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol

if TYPE_CHECKING:
    from collections.abc import Generator

import requests
from django.conf import settings
from django.core.cache import cache


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


class AiUnavailableError(Exception):
    pass


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        json_mode: bool = False,
        temperature: float = 0.4,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        temperature: float = 0.4,
    ) -> Generator[str]: ...


class OpenRouterProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (
            api_key
            or getattr(settings, "OPENROUTER_API_KEY", "")
            or getattr(settings, "OPEN_ROUTER_API_KEY", "")
        ).strip()
        self.base_url = getattr(
            settings,
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.models = getattr(
            settings,
            "AI_DEFAULT_MODELS",
            [
                "nvidia/nemotron-3-super-120b-a12b:free",
                "liquid/lfm-2.5-2.6b:free",
                "nex-agi/nex-n2.5-mini:free",
                "google/gemma-4-31b-it:free",
            ],
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        json_mode: bool = False,
        temperature: float = 0.4,
    ) -> LLMResponse:
        if not self.api_key:
            msg = "AI is not configured. OPENROUTER_API_KEY is missing."
            raise AiUnavailableError(msg)

        last_err = "Unknown error"
        start_time = time.time()

        for model in self.models:
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            try:
                resp = requests.post(
                    self.base_url,
                    json=body,
                    headers=headers,
                    timeout=45,
                )
                if (
                    not resp.ok
                    and json_mode
                    and resp.status_code == requests.codes.bad_request
                ):
                    # Retry without response_format if model lacks structured output
                    body_no_rf = dict(body)
                    body_no_rf.pop("response_format", None)
                    resp = requests.post(
                        self.base_url,
                        json=body_no_rf,
                        headers=headers,
                        timeout=45,
                    )

                if not resp.ok:
                    last_err = f"{model}: HTTP {resp.status_code}"
                    continue

                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if not content or not content.strip():
                    last_err = f"{model}: empty response"
                    continue

                usage = data.get("usage", {})
                latency = int((time.time() - start_time) * 1000)

                return LLMResponse(
                    content=content.strip(),
                    model=model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    latency_ms=latency,
                )
            except Exception as err:  # noqa: BLE001
                last_err = f"{model}: {err}"

        msg = f"All AI models are unavailable ({last_err})."
        raise AiUnavailableError(msg)

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        temperature: float = 0.4,
    ) -> Generator[str]:
        if not self.api_key:
            msg = "AI is not configured. OPENROUTER_API_KEY is missing."
            raise AiUnavailableError(msg)

        body = {
            "model": self.models[0],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            self.base_url,
            json=body,
            headers=headers,
            stream=True,
            timeout=45,
        )
        if not resp.ok:
            msg = f"Streaming failed: HTTP {resp.status_code}"
            raise AiUnavailableError(msg)

        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                raw = decoded[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(raw)
                    delta = (
                        chunk_json.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        yield delta
                except json.JSONDecodeError:
                    continue


def _mock_agent_content(user_content: str) -> str:
    """Deterministic tool-call proposals for agent prompts."""
    if "client" in user_content:
        actions: list[dict[str, Any]] = [
            {
                "tool": "add_client",
                "args": {"name": "Mock Client", "email": "mock@example.com"},
            },
        ]
    elif "product" in user_content:
        actions = [
            {
                "tool": "add_product",
                "args": {"name": "Mock Product", "unit_price": 25},
            },
        ]
    elif "payment" in user_content:
        match = re.search(r"INV-[0-9]{4}-[A-Za-z0-9-]+", user_content)
        actions = [
            {
                "tool": "record_payment",
                "args": {
                    "invoice_number": match.group(0) if match else "",
                    "amount": 500,
                },
            },
        ]
    elif "invoice" in user_content:
        actions = [
            {
                "tool": "create_invoice",
                "args": {
                    "client_name": "Mock Client",
                    "items": [
                        {
                            "description": "Mock Service",
                            "quantity": 2,
                            "rate": 50,
                        },
                    ],
                },
            },
        ]
    elif "expense" in user_content:
        actions = [
            {
                "tool": "add_expense",
                "args": {
                    "title": "Mock Expense",
                    "amount": 60,
                    "category": "supplies",
                },
            },
        ]
    else:
        actions = []
    return json.dumps({"reply": "Proposal ready.", "actions": actions})


class MockProvider:
    """Mock LLM Provider for testing and local sandbox environments."""

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        json_mode: bool = False,
        temperature: float = 0.4,
    ) -> LLMResponse:
        user_content = ""
        for m in messages:
            if m.get("role") == "user":
                user_content = m.get("content", "")

        # Agent tool-calling mock
        if "Available tools" in str(messages):
            res_content = _mock_agent_content(user_content)
        # Invoice items mock
        elif "invoice" in str(messages).lower() and "[" in user_content:
            res_content = json.dumps([
                {
                    "description": "Website Design & Prototyping",
                    "quantity": 1,
                    "rate": 1200,
                },
                {
                    "description": "Frontend Development & Testing",
                    "quantity": 20,
                    "rate": 75,
                },
            ])
        # Expense categorization mock
        elif "expense" in str(messages).lower() or "vendor" in str(messages).lower():
            res_content = json.dumps({
                "category": "Software & Subscriptions",
                "vendor": "GitHub",
                "confidence": 0.95,
            })
        # Payment reminder mock
        elif "reminder" in str(messages).lower() or "overdue" in str(messages).lower():
            res_content = json.dumps({
                "subject": "Friendly reminder: Invoice payment due",
                "body": (
                    "Dear Customer, please be reminded that "
                    "your invoice is due soon."
                ),
            })
        else:
            res_content = (
                "Based on the provided organization data, your metrics "
                "show positive trajectory with steady cash flow."
            )

        return LLMResponse(
            content=res_content,
            model="mock/bizpilot-ai",
            prompt_tokens=50,
            completion_tokens=25,
            latency_ms=10,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        temperature: float = 0.4,
    ) -> Generator[str]:
        chunks = [
            "Based on the provided ",
            "organization data, ",
            "your financial metrics ",
            "show positive trajectory ",
            "with steady cash flow.",
        ]
        yield from chunks


def get_llm_provider() -> LLMProvider:
    api_key = (
        getattr(settings, "OPENROUTER_API_KEY", "")
        or getattr(settings, "OPEN_ROUTER_API_KEY", "")
    ).strip()
    if api_key:
        return OpenRouterProvider(api_key=api_key)
    return MockProvider()


def get_cached_or_complete(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 1200,
    json_mode: bool = False,
    cache_ttl: int = 300,
) -> LLMResponse:
    """Check Redis/memory cache before querying the LLM."""
    serialized = json.dumps(messages, sort_keys=True)
    cache_key = (
        f"ai_cache:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
    )

    cached_data = cache.get(cache_key)
    if cached_data:
        return LLMResponse(**cached_data)

    res = provider.complete(
        messages,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )
    cache.set(
        cache_key,
        {
            "content": res.content,
            "model": res.model,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "latency_ms": res.latency_ms,
        },
        timeout=cache_ttl,
    )
    return res


def _find_array_in_dict(obj: dict[str, Any]) -> list[Any] | None:
    for key in ("items", "line_items", "invoice_items", "data", "results"):
        if key in obj and isinstance(obj[key], list):
            return obj[key]
    for val in obj.values():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    has_item_fields = "rate" in obj or "quantity" in obj
    if "description" in obj and has_item_fields:
        return [obj]
    return None


def _parse_json_slice(candidate: str, start_char: str, end_char: str) -> Any | None:
    start, end = candidate.find(start_char), candidate.rfind(end_char)
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def extract_json_array(text: str) -> list[Any] | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate = (fenced.group(1) if fenced else text).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = _parse_json_slice(
            candidate,
            "[",
            "]",
        ) or _parse_json_slice(candidate, "{", "}")

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return _find_array_in_dict(parsed)
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate = (fenced.group(1) if fenced else text).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
