"""The demo application.

Deliberately thin: no container, no settings, no store. The one thing this
service does is render a dossier, and a judge pasting the bare URL lands on the
example rather than on a 404.
"""

from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse

from countersign.api.dossier import dossier_router
from countersign.api.responses import HealthResponse

APP_TITLE = "Countersign"
APP_VERSION = "0.1.0"
DEMO_PATH = "/demo"

health_router = APIRouter(tags=["health"])


@health_router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse()


@health_router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """The bare URL is what gets pasted. Answer it with the demo."""
    return RedirectResponse(DEMO_PATH)


def create_app() -> FastAPI:
    application = FastAPI(title=APP_TITLE, version=APP_VERSION)
    application.include_router(health_router)
    application.include_router(dossier_router)
    return application


app = create_app()

__all__ = ["APP_TITLE", "APP_VERSION", "DEMO_PATH", "app", "create_app", "healthz", "root"]
