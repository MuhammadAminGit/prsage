"""GitHub webhook receiver.

Verifies the HMAC signature, dispatches by event type, and (for now) logs the
events we care about. Actual review work gets wired up in a later step.

Returning 2xx fast is important here: GitHub will retry if we hang or fail.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from app.config import get_settings
from app.review.runner import run_review
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
    background_tasks: BackgroundTasks,
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

        if not installation_id or not repo.get("full_name") or not pr.get("number"):
            log.warning("missing fields in pull_request payload, ignoring")
            return {"status": "ignored"}

        log.info(
            "queueing review repo=%s pr=#%s action=%s installation=%s",
            repo["full_name"],
            pr["number"],
            action,
            installation_id,
        )
        background_tasks.add_task(
            run_review,
            installation_id=int(installation_id),
            repo_full_name=repo["full_name"],
            pr_number=int(pr["number"]),
        )
        return {"status": "queued"}

    return {"status": "ignored"}
