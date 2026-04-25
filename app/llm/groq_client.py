"""Thin async client for Groq's OpenAI-compatible chat completions endpoint.

We talk directly to the REST API rather than depending on Groq's SDK so we
keep the dependency surface small and consistent with the rest of the code.

Groq's API is fully OpenAI-compatible at the chat-completions level, so the
same request/response shape applies. We only use a couple of features:

- ``response_format={"type": "json_object"}`` to force structured output
- a low temperature for deterministic-ish reviews
- retry on transient failures (429, 5xx)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

GROQ_API_BASE = "https://api.groq.com/openai/v1"
DEFAULT_TIMEOUT = 60.0
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (1, 3, 7)
TRANSIENT_STATUSES = {429, 500, 502, 503, 504}

log = logging.getLogger("prsage.llm")


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatCompletion:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class GroqError(Exception):
    """Raised when Groq returns a non-retriable error."""


class GroqClient:
    """Async chat-completions client for Groq."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        *,
        client: httpx.AsyncClient | None = None,
    ):
        if not api_key:
            raise ValueError("Groq API key is empty; set GROQ_API_KEY")
        self.api_key = api_key
        self.model = model
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "GroqClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        json_object: bool = False,
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        assert self._client is not None
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if json_object:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{GROQ_API_BASE}/chat/completions"

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.post(url, headers=headers, json=body)
            except httpx.HTTPError as e:
                last_exc = e
                log.warning("groq request error attempt=%d: %s", attempt, e)
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue

            if resp.status_code in TRANSIENT_STATUSES:
                log.warning(
                    "groq transient %s attempt=%d: %s",
                    resp.status_code,
                    attempt,
                    resp.text[:200],
                )
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue

            if resp.status_code >= 400:
                raise GroqError(f"groq error {resp.status_code}: {resp.text[:500]}")

            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return ChatCompletion(
                content=choice["message"]["content"],
                model=data.get("model", self.model),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

        raise GroqError(f"groq failed after {MAX_RETRIES} attempts: {last_exc}")
