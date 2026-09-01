"""Small response shapes that are not part of the dossier itself."""

from autocurricula.schemas.common import StrictBaseModel


class HealthResponse(StrictBaseModel):
    status: str = "ok"


__all__ = ["HealthResponse"]
