"""The demo surface: one renderer, reached either with a real run or with the fixture.

The runner is a separate piece of work, so nothing here imports it. POST a
finished `AssessmentResult` and get the page back; GET the demo route and the
same code renders the bundled example.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from countersign.api.dossier_page import render_dossier
from countersign.api.dossier_sample import SampleUnavailable, cached_sample
from countersign.orchestration.result import AssessmentResult

dossier_router = APIRouter(tags=["dossier"])

NO_STORE = {"Cache-Control": "no-store"}


def html(markup: str) -> HTMLResponse:
    return HTMLResponse(content=markup, headers=NO_STORE)


def demo_result() -> AssessmentResult:
    try:
        return cached_sample()
    except SampleUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


@dossier_router.post("/dossier", response_class=HTMLResponse)
async def dossier_page(result: AssessmentResult) -> HTMLResponse:
    """Render a finished run. The body is the whole contract with the pipeline."""
    return html(render_dossier(result))


@dossier_router.get("/demo", response_class=HTMLResponse)
async def demo_page() -> HTMLResponse:
    """The fixed example, for the walkthrough."""
    return html(render_dossier(demo_result()))


@dossier_router.get("/demo.json", response_model=AssessmentResult)
async def demo_payload() -> AssessmentResult:
    """The same example as data, so it can be posted straight back to /dossier."""
    return demo_result()


__all__ = ["demo_page", "demo_payload", "demo_result", "dossier_page", "dossier_router"]
