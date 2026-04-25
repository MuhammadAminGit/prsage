# Deploying prsage

Two pieces ship separately:

- The **backend** (FastAPI app + webhook handler) on Railway
- The **landing page** (`landing/`) on Vercel

Both have free tiers that fit prsage's traffic comfortably.

## Backend — Railway

### Prereqs

- A Railway account: https://railway.app
- The Railway CLI: `brew install railway` (or `npm i -g @railway/cli`)
- The project pushed to GitHub (it is)

### Steps

1. Log in:
   ```bash
   railway login
   ```

2. From the prsage repo root, create a Railway project:
   ```bash
   railway init
   ```

3. Add a Postgres database (Railway provisions it for you):
   ```bash
   railway add --plugin postgresql
   ```
   This sets `DATABASE_URL` automatically. To use the async driver, override
   it in the next step.

4. Set the env vars Railway will inject at runtime:
   ```bash
   railway variables set GITHUB_APP_ID="<your-app-id>"
   railway variables set GITHUB_APP_WEBHOOK_SECRET="<your-secret>"
   railway variables set GROQ_API_KEY="<your-groq-key>"
   railway variables set GROQ_MODEL="llama-3.3-70b-versatile"
   railway variables set LOG_LEVEL="info"
   # Override the auto-generated DATABASE_URL with the asyncpg variant:
   railway variables set DATABASE_URL='${{Postgres.DATABASE_URL}}'
   ```

   The private key is multiline and harder to set via CLI. Easiest path:
   - Open the Railway dashboard, your service, **Variables** tab
   - Add `GITHUB_APP_PRIVATE_KEY` with the full PEM contents
   - Then set `GITHUB_APP_PRIVATE_KEY_PATH=/tmp/private-key.pem`
   - Add a small startup hook to write the env var to that path. (For
     simplicity in v0.1 we read directly from a path; v0.2 will accept the
     PEM inline.)

5. Deploy:
   ```bash
   railway up
   ```

6. Once the deploy is healthy, grab the public URL:
   ```bash
   railway domain
   ```

7. Update the GitHub App's **Webhook URL** to:
   ```
   https://<your-railway-domain>/webhooks/github
   ```

That's it. Push to `main` (or trigger via CLI) and Railway redeploys.

### Sanity check

```bash
curl https://<your-railway-domain>/health
# -> {"status":"ok","version":"0.1.0"}
```

## Landing page — Vercel

### Prereqs

- A Vercel account: https://vercel.com
- The Vercel CLI: `npm i -g vercel`

### Steps

1. Log in:
   ```bash
   vercel login
   ```

2. From the prsage repo root, deploy the `landing/` directory:
   ```bash
   cd landing
   vercel --prod
   ```

3. Vercel auto-detects the static site, deploys, and gives you a public URL
   like `prsage.vercel.app`.

4. Optional: point a custom domain (`prsage.dev`?) at the Vercel deployment
   from the Vercel dashboard.

## After both are live

- Update the README with both URLs (replacing the placeholders).
- Open a PR on the demo repo and watch the bot post inline comments.
