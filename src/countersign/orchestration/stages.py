"""The six stages, the provider each one leans on, and the keys it cannot run without.

A missing credential is a property of one provider, so it costs one stage. The
run continues with that stage marked skipped and the reason naming the variable,
because a partial assessment that says which part is missing is worth more than
a crash that says nothing.

Each requirement is a tuple of interchangeable variable names: Foxit accepts an
already issued access token in place of the client credentials, and Doctavian's
bearer has a second accepted name, so satisfying any member satisfies the
requirement.

The check describes the deployment, not the call, so it runs even when the stage
has been handed an injected seam. A run that substitutes a port still needs the
environment of the stages it wants to reach, which keeps one answer to "why was
this stage omitted" rather than two that can disagree.
"""

import os
from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.agents.document_extractor_model import LOCATION_ENV, PROJECT_ENV
from countersign.schemas.evidence import Provider
from countersign.tools import (
    doctavian_client,
    foxit_esign_client,
    foxit_pdf,
    namecom_client,
    xano,
)
from countersign.tools.nutrient_client import PROCESSOR_KEY_ENV
from countersign.tools.serpapi_client import SERPAPI_API_KEY_ENV

PRODUCTION = namecom_client.NamecomEnvironment.PRODUCTION


class Stage(StrEnum):
    INGEST = "ingest"
    IDENTITY = "identity"
    DOMAIN = "domain"
    RISK = "risk"
    GENERATION = "generation"
    DELIVERY = "delivery"
    PERSISTENCE = "persistence"


class StageStatus(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    FAILED = "failed"


STAGE_PROVIDER: dict[Stage, Provider] = {
    Stage.INGEST: Provider.NUTRIENT,
    Stage.IDENTITY: Provider.SERPAPI,
    Stage.DOMAIN: Provider.NAMECOM,
    Stage.RISK: Provider.NUTRIENT,
    Stage.GENERATION: Provider.DOCTAVIAN,
    Stage.DELIVERY: Provider.FOXIT,
    Stage.PERSISTENCE: Provider.XANO,
}

STAGE_CREDENTIALS: dict[Stage, tuple[tuple[str, ...], ...]] = {
    Stage.INGEST: ((PROCESSOR_KEY_ENV,), (PROJECT_ENV,), (LOCATION_ENV,)),
    Stage.IDENTITY: ((SERPAPI_API_KEY_ENV,), (PROJECT_ENV,), (LOCATION_ENV,)),
    Stage.DOMAIN: (
        (namecom_client.USERNAME_ENV[PRODUCTION],),
        (namecom_client.TOKEN_ENV[PRODUCTION],),
    ),
    Stage.RISK: ((PROJECT_ENV,), (LOCATION_ENV,)),
    Stage.GENERATION: (
        (
            doctavian_client.ENV_API_KEY,
            foxit_pdf.ENV_CLIENT_ID,
        ),
        (
            doctavian_client.ENV_ACCESS_TOKEN,
            doctavian_client.ENV_ACCESS_TOKEN_FALLBACK,
            foxit_pdf.ENV_CLIENT_SECRET,
        ),
    ),
    Stage.DELIVERY: (
        (foxit_esign_client.ENV_ACCESS_TOKEN, foxit_esign_client.ENV_CLIENT_ID),
        (foxit_esign_client.ENV_ACCESS_TOKEN, foxit_esign_client.ENV_CLIENT_SECRET),
    ),
    Stage.PERSISTENCE: (
        (xano.TOKEN_ENV,),
        (xano.DOMAIN_ENV,),
        (xano.WORKSPACE_ENV,),
        (xano.AUDIT_TABLE_ENV,),
    ),
}


class SkippedStage(StrictBaseModel):
    """One stage the run could not attempt, and exactly why."""

    stage: Stage
    provider: Provider
    reason: str = Field(min_length=1)
    missing_variables: list[str] = Field(default_factory=list)


class StageOutcome(StrictBaseModel):
    """What happened at one stage, whether or not it produced anything."""

    stage: Stage
    status: StageStatus
    detail: str = ""
    errors: list[str] = Field(default_factory=list)


def _is_set(variable: str) -> bool:
    return bool(os.environ.get(variable, "").strip())


def missing_credentials(stage: Stage) -> list[str]:
    """The first accepted name of every requirement this stage cannot satisfy."""
    return [
        alternatives[0]
        for alternatives in STAGE_CREDENTIALS.get(stage, ())
        if not any(_is_set(name) for name in alternatives)
    ]


def credential_skip(stage: Stage) -> SkippedStage | None:
    """Turn a missing key into a skipped stage, or None when the stage may run."""
    missing = missing_credentials(stage)
    if not missing:
        return None
    return SkippedStage(
        stage=stage,
        provider=STAGE_PROVIDER[stage],
        reason=(
            f"{STAGE_PROVIDER[stage].value} is unconfigured: {', '.join(missing)} "
            "unset, so this stage is omitted and the run continues"
        ),
        missing_variables=missing,
    )


def skipped(stage: Stage, reason: str) -> SkippedStage:
    """A stage omitted for a reason that is not a credential."""
    return SkippedStage(stage=stage, provider=STAGE_PROVIDER[stage], reason=reason)


__all__ = [
    "STAGE_CREDENTIALS",
    "STAGE_PROVIDER",
    "SkippedStage",
    "Stage",
    "StageOutcome",
    "StageStatus",
    "credential_skip",
    "missing_credentials",
    "skipped",
]
