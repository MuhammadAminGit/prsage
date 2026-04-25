import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.db import engine
from app.logging_config import configure_logging
from app.models import Base
from app.webhooks.github import router as github_webhook_router

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("prsage.startup")


def _write_pem_if_inline() -> None:
    """If GITHUB_APP_PRIVATE_KEY_PEM is set, materialize it to disk.

    Lets us deploy on hosts that only support env vars (Railway, Fly).
    """
    pem = settings.github_app_private_key_pem.strip()
    if not pem:
        return
    target = Path(settings.github_app_private_key_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pem if pem.endswith("\n") else pem + "\n")
    target.chmod(0o600)
    log.info("wrote inline GitHub App key to %s", target)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _write_pem_if_inline()
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
