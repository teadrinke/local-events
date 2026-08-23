from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.providers.jambase import JamBaseProvider
from app.services.distance import HaversineCalculator
from app.services.event_service import EventService

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        # Provider registry: adding a source is one entry here.
        providers = [JamBaseProvider(client)]
        app.state.event_service = EventService(providers, HaversineCalculator())
        yield


app = FastAPI(title="Local Events API", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
