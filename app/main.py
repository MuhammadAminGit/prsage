from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.db import engine
from app.models import Base
from app.webhooks.github import router as github_webhook_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables on startup. Cheap on every boot, idempotent.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="prsage",
    description="AI code reviewer for GitHub pull requests.",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(github_webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "prsage",
        "version": __version__,
        "model": settings.groq_model,
    }
