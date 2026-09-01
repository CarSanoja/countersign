"""The model behind the hard judgement, injected rather than imported.

The verifier never constructs a Vertex client of its own: it takes anything that
can turn a prompt into text, so the disambiguation logic can be exercised in a
test without an ADC, a project or a quota.

The client stays deliberately dumb. It carries no response schema, because the
schema belongs to the prompt that the verifier writes, and a client that knew
about counterparties could not be reused by the other four agents that call a
model.
"""

import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

MODEL_ENV = "COUNTERSIGN_VERIFIER_MODEL"
PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
LOCATION_ENV = "GOOGLE_CLOUD_LOCATION"
VERTEX_FLAG_ENV = "GOOGLE_GENAI_USE_VERTEXAI"

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_LOCATION = "global"
REQUEST_TIMEOUT_MS = 90_000
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 8192


class CounterpartyModelError(RuntimeError):
    """The judgement could not be obtained.

    Raised rather than returned so that no caller can mistake a missing
    judgement for a clean one.
    """


@runtime_checkable
class CounterpartyModelClient(Protocol):
    async def complete(self, *, system: str, user: str) -> str:
        """Return the model's raw answer, expected to be one JSON object."""
        ...


def configured_model() -> str:
    return os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL


@dataclass(frozen=True)
class VertexCounterpartyModel:
    """gemini-3.5-flash on Vertex through google-genai.

    Every import and every credential read happens inside the call, so a missing
    variable becomes a named failure at judgement time and never an import error
    that takes the whole service down.
    """

    model: str = ""
    timeout_ms: int = REQUEST_TIMEOUT_MS
    temperature: float = TEMPERATURE

    async def complete(self, *, system: str, user: str) -> str:
        client, types = self._client()
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
        )
        try:
            response = await client.aio.models.generate_content(
                model=self.model or configured_model(), contents=user, config=config
            )
        except Exception as error:
            raise CounterpartyModelError(
                f"vertex call failed: {type(error).__name__}: {error}"
            ) from error
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise CounterpartyModelError("the model returned an empty response")
        return text

    def _client(self) -> tuple[Any, Any]:
        project = os.environ.get(PROJECT_ENV, "").strip()
        if not project:
            raise CounterpartyModelError(
                f"environment variable {PROJECT_ENV} is not set or is empty; "
                "the counterparty verifier needs a Vertex project to reach "
                f"{configured_model()}"
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise CounterpartyModelError(
                f"google-genai is not installed: {error}"
            ) from error
        os.environ.setdefault(VERTEX_FLAG_ENV, "True")
        location = os.environ.get(LOCATION_ENV, "").strip() or DEFAULT_LOCATION
        client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(timeout=self.timeout_ms),
        )
        return client, types
