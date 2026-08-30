# code-agent — Telegram coding agent (OpenRouter)

Send a coding task from Telegram. It edits a fresh checkout of `origin/main`,
runs the test suite, and pushes an `agent/*` branch for you to review.

It **never pushes to `main`** and **never merges**. Your merge is the deploy.

## Why it is a separate service

The obvious move — let the agent work inside `btc-executor` — is the one to
avoid. That container holds `HL_SECRET_KEY`, which can sign trades against
real money, and `EXEC_TOKEN`. An LLM driven from a chat app has
attacker-reachable input by definition: anything it reads (a file, a log, a
forwarded message) can try to steer it. Putting one next to a trading key
hands signing authority to a prompt.

It also would not work. Render containers are ephemeral — edits made inside
one vanish on the next deploy — and there is no repo of record in there. The
deploy path is already `push to main → Render rebuilds`, so the agent's job
is git, not ssh.

## The gates

`app/guard.py`. Every one refuses by raising; none return a boolean a caller
can forget to check. The model is not the security boundary — these are.

| gate | refuses |
|---|---|
| `assert_pushable` | any branch that is not `agent/*`; `main`/`master`/`HEAD` in any casing |
| `assert_paths_allowed` | `render.yaml` (could grant itself the trading keys), `code-agent/**` (could delete these gates), `.github/workflows/**` (CI has its own creds), `.env`, and the `CLAUDE.md`/`AGENTS.md`/`.cursorrules` convention files |
| `scan_diff_for_secrets` | a diff that **adds** a line matching a key shape — wallet hex, PEM, `sk-`, Telegram token, AWS, GitHub. Added lines only: this repo's own docs quote key shapes, and refusing to edit a file because a neighbouring line looks like a key would make the agent useless where the money is |
| `assert_tests_passed` | any push on a red suite. The suite is the merge gate everywhere else here; it is the push gate |
| `assert_environment_isolated` | **booting at all** while holding a trading credential |

Order is the design (`runner.do_task`): paths before the diff, diff before
tests, tests before the remote, and the branch re-checked at the push itself.
Each gate assumes the previous ones may have been wrong.

`aider` runs with `--no-auto-commits` on purpose: the change stays in the
working tree so the gates see a diff they can still refuse. An agent that
commits before it is checked has already done the thing being prevented.

## Setup

1. **Fine-grained** GitHub token — this repo only, Contents: read+write.
   Not a classic PAT: a classic token carries every repo the account can
   reach, and blast radius is the only thing between a bad edit and the rest
   of the account.
2. Render dashboard → `code-agent` → set `GITHUB_TOKEN`, `OPENROUTER_API_KEY`,
   `CODE_MODEL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
   **Do not add any trading variable** — the service refuses to boot with one.
3. Register the webhook (the secret is derived from the bot token):
   ```
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://code-agent.onrender.com/telegram/<secret>"
   ```
   Get `<secret>` from `python -c "from app.main import webhook_secret; print(webhook_secret())"`
   with `TELEGRAM_BOT_TOKEN` set, or from the service logs at boot.

Use a **different bot** from the alerts/canary one, or its messages will be
read as coding tasks.

## Limits, stated

- One task at a time; a second is told the agent is busy.
- It only knows what `aider` maps from the repo. It cannot see live venue
  state, and it holds no token to ask for any.
- It does not review its own work. The branch is the deliverable; the review
  is yours.
- A refusal is an answer, not an error. If a gate says no, the fix is a human
  making that change — not loosening the gate.
