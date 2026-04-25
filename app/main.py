from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.webhooks.github import router as github_webhook_router

settings = get_settings()

app = FastAPI(
    title="prsage",
    description="AI code reviewer for GitHub pull requests.",
    version=__version__,
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
