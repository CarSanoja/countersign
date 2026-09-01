"""One concrete Vertex client that satisfies every agent's model protocol.

Each agent declares its own narrow Protocol so it can be tested without a
network. Nothing implemented them, so this is the single adapter the whole
fleet shares: three call shapes over one client, and one place to change when
the model or the region does.
"""

import asyncio
import os
from typing import Any

FLASH = "gemini-3.5-flash-lite"
PRO = "gemini-3.5-flash"

_TIMEOUT_SECONDS = 90.0


class VertexUnavailable(RuntimeError):
    pass


def _client() -> Any:
    try:
        from google import genai
    except ImportError as exc:
        raise VertexUnavailable("google-genai is not installed") from exc
    for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        if not os.environ.get(name):
            raise VertexUnavailable(f"missing environment variable {name}")
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    return genai.Client()


class VertexModel:
    """Satisfies TextModel, CounterpartyModelClient and VerdictModel at once."""

    def __init__(self, *, default_model: str = FLASH, client: Any | None = None) -> None:
        self._client = client if client is not None else _client()
        self._default_model = default_model

    def _blocking(self, model: str, prompt: str) -> str:
        response = self._client.models.generate_content(model=model, contents=prompt)
        text = getattr(response, "text", None)
        if not text:
            raise VertexUnavailable(f"{model} returned no text")
        return text

    async def _generate(self, prompt: str, model: str) -> str:
        return await asyncio.wait_for(
            asyncio.to_thread(self._blocking, model, prompt), timeout=_TIMEOUT_SECONDS
        )

    async def generate_text(self, prompt: str, *, model: str) -> str:
        return await self._generate(prompt, model or self._default_model)

    async def complete(self, *, system: str, user: str) -> str:
        return await self._generate(f"{system}\n\n{user}", self._default_model)

    async def __call__(self, prompt: str) -> str:
        return await self._generate(prompt, self._default_model)


def flash() -> VertexModel:
    return VertexModel(default_model=FLASH)


def pro() -> VertexModel:
    return VertexModel(default_model=PRO)
