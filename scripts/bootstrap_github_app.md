# Bootstrap a GitHub App for prsage

This walks you through creating your own GitHub App so you can run prsage locally and have it review real PRs on a repo you control. Takes about 10 minutes.

## 1. Create the App

Go to https://github.com/settings/apps → **New GitHub App**.

Fill in:

| Field | Value |
|---|---|
| Name | `prsage-dev` (or any unique name) |
| Homepage URL | https://github.com/MuhammadAminGit/prsage |
| Webhook URL | placeholder for now, we'll fix it in step 4 |
| Webhook secret | a random 32+ char string (use `python3 -c "import secrets; print(secrets.token_hex(32))"`) |

## 2. Permissions

Under **Repository permissions**, set:

- **Pull requests**: Read & Write
- **Contents**: Read-only
- **Metadata**: Read-only (defaults to this anyway)

Leave everything else as "No access."

## 3. Events

Under **Subscribe to events**, check:

- [x] **Pull request**

That's the only event prsage cares about for now.

Click **Create GitHub App** at the bottom.

## 4. Grab the credentials

After the app is created you'll be on its settings page. Note these down:

- **App ID** at the top (a number like `3499025`)
- Scroll to the bottom and click **Generate a private key**. A `.pem` file downloads. Move it to your prsage project root and rename it `private-key.pem`.

## 5. Populate `.env`

Copy `.env.example` to `.env` if you haven't:

```bash
cp .env.example .env
```

Fill in:

```
GITHUB_APP_ID=3499025
GITHUB_APP_WEBHOOK_SECRET=<the random secret from step 1>
GITHUB_APP_PRIVATE_KEY_PATH=./private-key.pem
GROQ_API_KEY=<from https://console.groq.com>
```

Both `.env` and `*.pem` are in `.gitignore` so they won't get committed.

## 6. Run the server

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

You should see the server start on `http://localhost:8000`. Hit `/health` to confirm.

## 7. Tunnel for webhooks

GitHub needs a public URL to send webhooks to. Two free options:

### Option A: ngrok (recommended for one-off testing)

```bash
brew install ngrok
ngrok http 8000
```

Copy the `https://...ngrok-free.app` URL.

### Option B: smee.io (recommended for ongoing dev)

```bash
brew install smee-client    # or: npm install -g smee-client
# create a channel at https://smee.io and start the client:
smee --url https://smee.io/<your-channel> --target http://localhost:8000/webhooks/github
```

Either way, you now have a public URL that forwards to your local server.

## 8. Update the webhook URL in GitHub

Back on the GitHub App settings page, set the **Webhook URL** to:

- ngrok: `https://<random>.ngrok-free.app/webhooks/github`
- smee: `https://smee.io/<your-channel>`

Save the page.

## 9. Install the App on a test repo

On the App's left sidebar, click **Install App** and pick a repo you own. (Recommendation: create a throwaway repo like `prsage-demo` so you can break things freely.)

## 10. Test the round trip

In your test repo, push a branch and open a PR. You should see:

- A `pull_request` webhook delivery in **App settings → Advanced** → Recent Deliveries
- Logs in your local server like `received delivery=... event=pull_request action=opened`
- A 202 response back to GitHub

If you see that, your local prsage instance is wired up correctly. From here, the actual review pipeline (Day 4) takes over.

## Troubleshooting

- **401 in your logs:** webhook secret mismatch. Double-check the secret in GitHub App settings vs your `.env`.
- **No deliveries arriving:** check the **Advanced** tab on the App page. The "Recent Deliveries" view shows what GitHub tried to send and any errors.
- **`File not found: private-key.pem`:** the `.pem` file isn't where `GITHUB_APP_PRIVATE_KEY_PATH` says it is.
- **400 Invalid JSON:** something is munging the body before it reaches the server. Make sure no proxy is rewriting the request.
