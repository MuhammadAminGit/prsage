# Examples

A companion repo, [prsage-demo](https://github.com/MuhammadAminGit/prsage-demo), exists as a target for prsage to review. The `main` branch of that repo is a clean Python baseline. The `feature/buggy-changes` branch deliberately introduces issues for prsage to flag.

## What's in `feature/buggy-changes`

### `app/users.py`

- SQL injection via string concatenation in `get_user` (`"... WHERE id = " + str(user_id)`)
- SQL injection via f-string in `get_user_by_email`
- Missing `None` check on `row` before accessing `row[0]`
- Bare `except` swallowing all errors in `delete_all_users`
- Type hints removed from function signatures

### `app/notify.py`

- Hardcoded API key inline (security)
- No error handling around the `requests.post` call
- No retry logic or status-code check before parsing JSON
- Sequential `send_bulk` instead of any kind of concurrency
- Removed the prior input validation on the recipient address

## Reproducing locally

1. Install prsage on the prsage-demo repo (or a fork).
2. Open a PR from `feature/buggy-changes` into `main`.
3. Within seconds, prsage should post inline review comments on the lines above.

If a comment is missing or off-target, that's useful feedback. The reviewer prompt in `app/review/prompts.py` is the lever to tune.
