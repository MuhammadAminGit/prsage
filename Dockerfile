FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime deps first for better layer caching.
COPY pyproject.toml ./
RUN pip install \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "pydantic-settings>=2.6" \
        "httpx>=0.28" \
        "pyjwt[crypto]>=2.10" \
        "sqlalchemy[asyncio]>=2.0" \
        "aiosqlite>=0.20" \
        "asyncpg>=0.30"

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
