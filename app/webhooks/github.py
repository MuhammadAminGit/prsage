"""GitHub webhook receiver.

Verifies the HMAC signature, dispatches by event type, and (for now) logs the
events we care about. Actual review work gets wired up in a later step.

Returning 2xx fast is important here: GitHub will retry if we hang or fail.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import get_settings
from app.webhooks.signature import (
    InvalidSignatureError,
    SIGNATURE_HEADER,
    verify_signature,
)

log = logging.getLogger("prsage.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Pull request actions that should trigger a review.
REVIEWABLE_PR_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias=SIGNATURE_HEADER),
) -> dict[str, str]:
    settings = get_settings()
    body = await request.body()

    try:
        verify_signature(settings.github_app_webhook_secret, body, x_hub_signature_256)
    except InvalidSignatureError as e:
        log.warning("rejected webhook delivery=%s: %s", x_github_delivery, e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    event = x_github_event or "unknown"
    action = payload.get("action", "")

    log.info(
        "received delivery=%s event=%s action=%s",
        x_github_delivery,
        event,
        action,
    )

    if event == "ping":
        return {"status": "pong"}

    if event == "pull_request" and action in REVIEWABLE_PR_ACTIONS:
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        installation_id = payload.get("installation", {}).get("id")
        log.info(
            "pull_request review-worthy: repo=%s pr=#%s action=%s installation=%s",
            repo.get("full_name"),
            pr.get("number"),
            action,
            installation_id,
        )
        # TODO: enqueue review job (Day 4)
        return {"status": "queued"}

    return {"status": "ignored"}
