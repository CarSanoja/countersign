"""The model seam.

The synthesiser takes its client as an argument so the rejection rule can be
exercised without a network and without an ADC. The Vertex client is built
lazily, at call time: a missing variable is reported by name and never raised
from an import, because a credential that is not there yet must not be able to
stop the module from loading.
"""

import os
from typing import Any, Protocol

from autocurricula.agents.base import AgentResponseError

FLASH_MODEL = "gemini-3.5-flash"
LITE_MODEL = "gemini-3.5-flash-lite"

PROJECT_VAR = "GOOGLE_CLOUD_PROJECT"
LOCATION_VAR = "GOOGLE_CLOUD_LOCATION"
VERTEX_FLAG_VAR = "GOOGLE_GENAI_USE_VERTEXAI"
REQUIRED_VARS = (PROJECT_VAR, LOCATION_VAR, VERTEX_FLAG_VAR)

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_TEMPERATURE = 0.0


class VerdictModel(Protocol):
    """Prompt in, raw text out. Anything that satisfies this can be injected."""

    async def __call__(self, prompt: str) -> str: ...


class MissingCredentialsError(RuntimeError):
    """Raised at call time, naming the variables that are not set."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"unset environment variable(s): {', '.join(missing)}")
        self.missing = missing


def missing_vertex_env() -> list[str]:
    """Which variables a caller still has to set. Checkable without a call."""
    return [name for name in REQUIRED_VARS if not os.environ.get(name, "").strip()]


def vertex_model(
    model_name: str = FLASH_MODEL,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> VerdictModel:
    """A VerdictModel backed by Gemini on Vertex, with an explicit timeout.

    Temperature is zero because two runs over the same evidence that disagree in
    wording are two verdicts an auditor has to reconcile.
    """

    async def call(prompt: str) -> str:
        missing = missing_vertex_env()
        if missing:
            raise MissingCredentialsError(missing)
        client, config = _client_and_config(timeout_seconds, temperature)
        response = await client.aio.models.generate_content(
            model=model_name, contents=prompt, config=config
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise AgentResponseError("the model returned no text", raw=str(response))
        return text

    return call


def _client_and_config(timeout_seconds: float, temperature: float) -> tuple[Any, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=os.environ[PROJECT_VAR],
        location=os.environ[LOCATION_VAR],
        http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
    )
    config = types.GenerateContentConfig(
        temperature=temperature, response_mime_type="application/json"
    )
    return client, config
