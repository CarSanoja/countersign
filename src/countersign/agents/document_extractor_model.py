"""The model seam, narrow on purpose: one prompt in, one string out.

Injected rather than constructed inside the agent, so the mapping can be exercised
with a fake and the agent never depends on a live credential to be testable.
"""

import os
from typing import Any, Final, Protocol, runtime_checkable

from autocurricula.tools.base import ToolResult

PROJECT_ENV: Final[str] = "GOOGLE_CLOUD_PROJECT"
LOCATION_ENV: Final[str] = "GOOGLE_CLOUD_LOCATION"
GENERATION_TIMEOUT_SECONDS: Final[float] = 60.0
JSON_MIME_TYPE: Final[str] = "application/json"


@runtime_checkable
class TextModel(Protocol):
    """Everything this agent is allowed to ask a model for."""

    async def generate_text(self, prompt: str, *, model: str) -> str: ...


class VertexTextModel:
    """google-genai on Vertex, wrapped so the agent never sees the SDK's shape."""

    def __init__(self, client: Any, *, temperature: float = 0.0) -> None:
        self._client = client
        self._temperature = temperature

    async def generate_text(self, prompt: str, *, model: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "temperature": self._temperature,
                "response_mime_type": JSON_MIME_TYPE,
            },
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("the model returned no text")
        return text


def vertex_text_model(
    *, timeout_seconds: float = GENERATION_TIMEOUT_SECONDS
) -> VertexTextModel | ToolResult:
    """Build the live client, or name the variable that is missing.

    Never raises at import time and never at call time for a configuration fault: a
    missing credential is a result the caller can read, like any other failure.
    """
    for variable in (PROJECT_ENV, LOCATION_ENV):
        if not os.environ.get(variable, "").strip():
            return ToolResult.failure(f"{variable} is unset; the Vertex client cannot be built")
    try:
        from google import genai
    except ImportError as error:
        return ToolResult.failure(f"google-genai is not importable: {error}")
    try:
        client = genai.Client(
            vertexai=True,
            project=os.environ[PROJECT_ENV].strip(),
            location=os.environ[LOCATION_ENV].strip(),
            http_options={"timeout": int(timeout_seconds * 1000)},
        )
    except Exception as error:
        return ToolResult.failure(f"vertex client refused construction: {type(error).__name__}")
    return VertexTextModel(client)
