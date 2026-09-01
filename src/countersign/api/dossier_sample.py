"""The fixed example the demo route renders.

Kept as JSON on disk rather than as Python so the same bytes can be posted back
to the live endpoint: the demo page and a real run go through one renderer, and
the fixture cannot drift into a shape the API would reject.
"""

from functools import lru_cache
from pathlib import Path

from countersign.orchestration.result import AssessmentResult

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_NAME = "dossier.json"


class SampleUnavailable(RuntimeError):
    """The bundled example is missing or no longer matches the contract."""


def sample_path() -> Path:
    return SAMPLES_DIR / SAMPLE_NAME


def load_sample(path: Path | None = None) -> AssessmentResult:
    """Read and validate the example. Raises rather than serving half a page."""
    target = path or sample_path()
    if not target.is_file():
        raise SampleUnavailable(f"the demo dossier is not bundled at {target}")
    try:
        return AssessmentResult.model_validate_json(target.read_text(encoding="utf-8"))
    except ValueError as error:
        raise SampleUnavailable(f"the demo dossier no longer validates: {error}") from error


@lru_cache(maxsize=1)
def cached_sample() -> AssessmentResult:
    """Parsed once per process. The file never changes while the app is up."""
    return load_sample()


__all__ = [
    "SAMPLES_DIR",
    "SAMPLE_NAME",
    "SampleUnavailable",
    "cached_sample",
    "load_sample",
    "sample_path",
]
