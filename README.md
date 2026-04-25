# prsage

AI code reviewer that runs on your GitHub pull requests. Installs as a GitHub App, reads the diff, and posts inline review comments using an LLM.

> Status: early development. Building in public toward a v0.1.

## What it does

You install prsage on a repo. Someone opens a pull request. Within a few seconds, prsage reads the diff, runs it through an LLM, and posts inline comments on the lines it has thoughts about. Bugs, security issues, missing tests, style smells, the kind of stuff a senior reviewer would flag if they had time.

You stay in control. The bot comments, never approves or rejects. Humans still do the merging.

## How it works

1. PR opens or gets new commits.
2. GitHub fires a webhook to the prsage server.
3. prsage fetches the diff via the GitHub API.
4. The diff goes to an LLM with a tuned review prompt.
5. The LLM returns structured review comments (file, line, severity, body).
6. prsage posts each comment back to the PR via the GitHub Reviews API.

End to end, this should run in 3 to 8 seconds for small PRs.

## Features

**In progress for v0.1:**
- GitHub App with webhook handler for `pull_request` events
- Diff fetcher and parser
- LLM-driven review (Groq, Llama 3.3 70B by default)
- Inline comments posted back to the PR
- One review style, well-tuned out of the box
- Postgres persistence for review history
- Live demo on a deployed instance
- Demo repo with intentional issues to test the bot on

**Planned for later:**
- Multiple reviewer personas (strict, kind mentor, security-focused)
- Repo-level config file for rules and ignores
- Conversation with the bot in PR comments
- Token-cost tracking and analytics
- Multi-tenant billing
- CLI mode for local pre-push review

## Stack

- Python 3.12 + FastAPI for the server
- Groq (Llama 3.3 70B) for the LLM by default; provider is pluggable
- httpx for the GitHub API client
- PyJWT for GitHub App authentication
- Postgres in production, SQLite in local dev
- Hosted on Railway (server) and Vercel (landing page)

## Quick start (local dev)

```bash
git clone https://github.com/MuhammadAminGit/prsage.git
cd prsage

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# fill in GITHUB_APP_ID, GITHUB_APP_WEBHOOK_SECRET, GROQ_API_KEY, etc.

uvicorn app.main:app --reload
```

Hit `http://localhost:8000/health` to confirm it's up.

To test the full webhook flow locally, you'll need a public tunnel like `ngrok` or `smee.io`. The setup walkthrough lives in `scripts/bootstrap_github_app.md` (coming soon).

## Roadmap

- [x] Project scaffold
- [ ] GitHub App authentication (JWT + installation tokens)
- [ ] Webhook handler with signature verification
- [ ] Diff fetcher and parser
- [ ] LLM review pipeline
- [ ] Inline comment posting
- [ ] Persistence layer (Postgres)
- [ ] Landing page
- [ ] Public deploy
- [ ] Tag v0.1.0

## License

MIT. See [LICENSE](./LICENSE).
