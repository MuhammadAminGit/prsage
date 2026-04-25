# Architecture

prsage is a small async FastAPI service plus a static landing page. This doc explains how the pieces fit and the trade-offs behind a few non-obvious choices.

## High level

```
GitHub --webhook--> [FastAPI receiver] --bg task--> [reviewer]
                          |                              |
                          v                              v
                    verify HMAC               fetcher -> Groq -> parser
                                                             |
                                                             v
                                                   filter_to_reviewable_lines
                                                             |
                                                             v
                                                  GitHub Reviews API
                                                             |
                                                             v
                                                       Postgres
```

Three things happen on every PR:

1. **Receive.** GitHub fires a webhook. We verify its HMAC signature against the configured secret, parse the event, and queue work.
2. **Review.** A background task fetches the PR's files via the GitHub API, builds a prompt, calls Groq, parses the JSON response, and filters out comments that point at lines that weren't actually added.
3. **Post.** The filtered comments go back to GitHub via the Reviews API. Everything we did is persisted to Postgres.

## Modules

### `app/main.py`

FastAPI entrypoint. Sets up the lifespan that creates DB tables on first boot, configures logging, and mounts the webhook router.

### `app/config.py`

`Settings` (pydantic-settings) loads everything from env vars or `.env`. Cached singleton via `get_settings()`. Tests clear the cache between runs.

### `app/db.py` and `app/models.py`

SQLAlchemy 2.0 async. Two tables:

- `reviews` — one row per review attempt, with status, model, token usage, duration, summary, error
- `review_comments` — the inline comments that got posted

We default to a local SQLite file in dev (`sqlite+aiosqlite:///./prsage.db`) and Postgres in prod (`postgresql+asyncpg://...`).

No Alembic. Schema is created via `Base.metadata.create_all` at startup. Cheap, idempotent, fine for a single-table-set MVP.

### `app/github/auth.py`

Two auth layers:

- **App JWT.** RS256-signed token identifying the GitHub App itself. Lifetime ≤ 10 minutes (we use 9). Cached in-process so we don't regenerate on every webhook.
- **Installation token.** Bearer token scoped to a specific installation (a repo or org that installed the app). Fetched by exchanging the App JWT. Lifetime ~1 hour. Cached per-installation.

Both caches are pure in-memory dicts. Fine for one process; would need Redis for horizontal scale.

### `app/github/client.py`

Async HTTP client wrapping the GitHub REST API. Three methods we actually use:

- `get_pull_request(repo, pr_number)`
- `get_pull_request_files(repo, pr_number)` — returns each file with its `patch` (unified diff hunks)
- `post_review(repo, pr_number, ...)` — posts a review with multiple inline comments at once

Retries on 429 / 5xx with exponential backoff (1s, 3s, 7s).

### `app/webhooks/signature.py`

HMAC-SHA256 verification using `hmac.compare_digest` (constant-time). Anything without a valid signature gets a 401 before its body is parsed.

### `app/webhooks/github.py`

The receiver. Reads raw body, verifies the signature, parses JSON, and dispatches by `X-GitHub-Event`. For `pull_request` events with `action in {opened, synchronize, reopened, ready_for_review}`, it queues `run_review` as a FastAPI BackgroundTask and returns 202 immediately.

Why BackgroundTasks instead of Celery: it's the smallest moving part that satisfies the constraint "GitHub needs a 2xx fast." For multi-instance scale, swap to Celery + Redis.

### `app/review/`

The actual review pipeline:

- `fetcher.py` — `fetch_reviewable_pr(...)` calls the client, drops files we shouldn't review (lockfiles, binaries, oversized patches), returns a `ReviewablePR`.
- `diff.py` — parses the unified-diff `patch` text into hunks with proper line numbers on both sides. `render_for_llm` formats the diff with NEW-side line numbers shown in a column the LLM can refer to.
- `prompts.py` — `build_system_prompt()` returns the base prompt plus any `REVIEW_STYLE_NOTES`. `build_user_prompt(pr, files)` assembles the per-PR text.
- `output.py` — strips markdown fences, parses the JSON, validates severity, and `filter_to_reviewable_lines` drops comments that don't refer to a line that was actually added in the diff.
- `reviewer.py` — orchestrator. Builds the prompt, calls Groq, parses, filters, returns a `ReviewRun` (result + token usage + duration).
- `runner.py` — top-level `run_review` that the webhook hands off to. Handles persistence: a `Review` row is inserted up front (`status=running`) and updated with the outcome (`posted`, `skipped`, `failed`).

### `app/llm/groq_client.py`

Async chat-completions client for Groq's OpenAI-compatible endpoint. Why direct HTTP instead of the SDK: we already use `httpx` and the surface is small; one fewer dependency. Retries on 429 / 5xx with exponential backoff. Supports `response_format={"type":"json_object"}`.

## A reviewable comment

The trickiest invariant: a posted comment must refer to a line that was actually added in this PR. GitHub will reject comments otherwise.

We enforce this in two places:

1. The system prompt tells the LLM only to comment on lines marked `+` in the rendered diff.
2. `filter_to_reviewable_lines` re-checks the LLM's output: for each comment, we look up `added_line_numbers(parse_patch(file.patch))` and drop the comment if its line isn't in that set.

This guards against hallucinated files, off-by-one mistakes, and the LLM commenting on context lines.

## Trade-offs and what we'd do differently with more time

- **No queue.** BackgroundTasks runs in-process. A crashed worker loses queued reviews. Celery + Redis fixes this; not worth the complexity at v0.1.
- **In-memory caches.** App JWT and installation tokens are per-process. Multi-instance deployments would re-auth more often than necessary. Redis fixes this.
- **One LLM provider.** The reviewer code is provider-aware (it imports `GroqClient`). Swapping to OpenAI/Anthropic is a 30-line change but not currently abstracted behind an interface.
- **Single review style.** Configurable via `REVIEW_STYLE_NOTES` but only one base prompt. Per-repo style would need a `prsage.yml` config in target repos.
- **No PR diff truncation.** Files over 30KB of patch text are skipped entirely instead of summarized. Big PRs lose visibility.
- **No conversation.** The bot can't reply to a "no, this isn't a bug" comment. Would need to subscribe to `pull_request_review_comment` events and thread context through.
