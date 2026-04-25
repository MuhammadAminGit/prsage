from fastapi import FastAPI

from app import __version__

app = FastAPI(
    title="prsage",
    description="AI code reviewer for GitHub pull requests.",
    version=__version__,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "prsage", "version": __version__}
