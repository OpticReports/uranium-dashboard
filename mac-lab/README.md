# mac-lab — the Tier-0 training box (`mac-mini-lab`)

A Mac mini (M4, 24 GB, arm64) that trains models on our research data and
**cannot place a trade**. Built 2026-09-16/17.

## Why it exists, and the law it runs under

`CLAUDE.md` already says strategy engines are keyless decision brains and
credentials live only in executors. This box extends that one tier further
out:

```
  TIER 0 — LAB               TIER 1 — DATA/BRAINS        TIER 2 — EXECUTORS
  ┌──────────────────┐       ┌──────────────────┐        ┌─────────────────┐
  │ mac-mini-lab     │ pull  │ genomics-tracker │        │ btc-executor    │
  │ Unsloth Studio   │ ────> │ barbell-lab      │        │ ibkr-executor   │
  │ MLX / Metal      │ HTTPS │ btc-paper-engine │ ────>  │                 │
  │                  │ read  │ treasury-canary  │ EXEC_  │ TRADE KEYS      │
  │ ZERO credentials │ only  │                  │ TOKEN  │ DRY_RUN gates   │
  └──────────────────┘       └──────────────────┘        └─────────────────┘
         ▲                                                       ▲
         │ Tailscale, ACL-scoped                     no token, no key, no code
    ┌─────────┐                                      path from the lab to here
    │ laptop  │
    └─────────┘
```

**Invariants.** Break any of these and the box stops being safe:

1. No exchange credential of any kind on this machine — no `CB_API_*`, no
   `HL_SECRET_KEY`, no IBKR session, no `EXEC_TOKEN`, no `READ_TOKEN`.
2. It **pulls**. Nothing on Render pushes to it, schedules work on it, or
   receives anything from it automatically.
3. A trained model's output is a file. It becomes a signal only via
   git → review → paper engine → executor, with the existing ramp gates.
   Never lab → executor.
4. Not signed into Casey's primary iCloud. Keychain sync would replicate
   trading passwords onto a box running third-party training code.

## Access

| Thing | Value |
|---|---|
| Tailnet name | `mac-mini-lab` |
| Tailscale IP | `100.93.59.14` |
| macOS user | `aibot` |
| From the laptop | `ssh lab` |
| Studio UI | `http://100.93.59.14:8888` (user `unsloth`) |

No port forwarding on the home router, ever. The box is reachable only from
the tailnet, and the tailnet ACL narrows that to the laptop.

### The ACL gotcha — read this before debugging connectivity

`optic.capital` runs a **custom** tailnet policy, not the default allow-all.
A new node joins the tailnet and is still unreachable, because no rule names
it as a destination. The symptom is diagnostic poison:

- `tailscale ping <node>` → **pong** (WireGuard layer, bypasses ACL)
- `ping` / `ssh` → **timeout** (blocked by ACL)

Everything on the host looks perfect — `sshd` listening, firewall off, `utun`
holding the right address — and it still fails. The fix is in
`https://login.tailscale.com/admin/acls`, not on the Mac:

```json
{
	"action": "accept",
	"src":    ["ally@optic.capital"],
	"dst":    ["100.93.59.14:*"],
}
```

`:*` rather than `:22` so the Studio port works without another edit.
`src` is the explicit user, not `autogroup:owner` — the tailnet has two
users and `autogroup:owner` matches only one of them.

## Build, from scratch

### 1. Tailscale — CLI daemon, not the GUI app

The macOS GUI app runs in a login session, so after a power cut the box stays
dark until someone logs in at the keyboard. The open-source daemon starts at
boot.

```
brew install tailscale
sudo brew services start tailscale
sudo /opt/homebrew/bin/tailscale up --accept-dns=true --hostname=mac-mini-lab
```

`sudo` on `brew services` matters — it installs to `/Library/LaunchDaemons`
(system, boots without login) rather than `~/Library/LaunchAgents`.
Full path on `tailscale up` because `sudo` resets `PATH`.

Then in the admin console: **Disable key expiry** on this node. A lapsed key
drops the box off the tailnet, and re-auth needs a browser *on the mini* —
which is exactly what you don't have when it matters.

### 2. Always-on

```
sudo pmset -a sleep 0 disksleep 0 autorestart 1
```

`autorestart 1` brings it back after a power cut.

### 3. SSH — key only

Remote Login can't be toggled from the terminal without granting Terminal
Full Disk Access; use the GUI instead:
**System Settings → General → Sharing → Remote Login**, ⓘ → *Only these
users* → `aibot`, "full disk access for remote users" **off**.

On the laptop:

```
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_lab -C "laptop to mac-mini-lab"
ssh-copy-id -i ~/.ssh/id_ed25519_lab.pub aibot@100.93.59.14
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_lab
```

`~/.ssh/config`:

```
Host lab
  HostName 100.93.59.14
  User aibot
  IdentityFile ~/.ssh/id_ed25519_lab
  AddKeysToAgent yes
  UseKeychain yes
  ForwardAgent no
```

`ForwardAgent no` is not optional. With agent forwarding on, anything running
on the mini can use the laptop's keys — including GitHub push access to this
repo, which deploys to Render, which holds the trade keys. That is the one
realistic path from "training box" to "someone touched the trading stack".

Only after key login works:

```
sudo sed -i '' 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo launchctl kickstart -k system/com.openssh.sshd
```

Verify from a *second* laptop tab before closing the first.

### 4. Unsloth Studio

```
curl -fsSL https://unsloth.ai/install.sh | sh
unsloth studio reset-password        # set BEFORE first run; see below
```

The installer detects `Apple Silicon (Metal, unified memory)` and takes the
**MLX** path — newer and rougher than Unsloth's CUDA path, so expect missing
kernels on exotic configs.

Studio refuses to sit unauthenticated on a routable bind: started without a
password it generates one and **shuts down after 1 hour**. Set the password
first, keep it in the password manager.

Then install the service (`ai.unsloth.studio.plist` in this directory):

```
sudo cp mac-lab/ai.unsloth.studio.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/ai.unsloth.studio.plist
sudo chmod 644 /Library/LaunchDaemons/ai.unsloth.studio.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/ai.unsloth.studio.plist
```

It binds `100.93.59.14`, not `0.0.0.0` — tailnet only, never the LAN.
`KeepAlive` covers the boot race: if Tailscale hasn't brought the address up
yet, the bind fails and launchd retries every 15s.

Metal **does** work from a LaunchDaemon with no GUI session — verified:

```
grep -i "hardware detected" ~/.unsloth/studio/logs/launchd.out.log
# Hardware detected: MLX — Apple Silicon (arm64)
```

### 5. Verify the whole thing

```
sudo reboot
# ~90s later, from the LAPTOP:
curl -sS http://100.93.59.14:8888/api/health
```

A healthy response with nobody logged in at the mini is the acceptance test.

## Data

The mini holds **no market-data API key**. It pulls allow-listed research
tables from `barbell-lab` over `/api/export/*`, guarded by `LAB_READ_TOKEN`
(`X-Lab-Token` header). See `barbell-lab/src/barbell/web/export.py`; the
merge-blocking gates are in `barbell-lab/tests/test_export.py`.

Default-closed: unset `LAB_READ_TOKEN` means every export route 404s.

```
./pull.sh                 # incremental, writes ~/lab/data/<table>.ndjson
./pull.sh --full          # ignore watermarks, re-pull everything
```

Install the nightly schedule (`com.optic.labpull.plist`, 05:20 local):

```
cp mac-lab/pull.sh ~/lab/bin/pull.sh && chmod 700 ~/lab/bin/pull.sh
cp mac-lab/com.optic.labpull.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.optic.labpull.plist
```

The token lives in `~/lab/.lab_read_token`, mode `600`, never in git and
never in a shell history line.

### What can and cannot leave Render

Exportable: `prices`, `fred`, `bot_pnl`, `trials`, `regime_log`,
`portfolio_metrics`, `validation_log`.

Never exportable: `chat_conversations`, `chat_messages`, `chat_memory`.
These carry conversation content. `test_export.py` fails the build if any of
them is added to the allow-list, and asserts seeded conversation text is
unreachable through every route.

The allow-list is explicit, never a prefix match — a table added to the
schema later is *not* exportable until someone adds it here on purpose.

## What fits on 24 GB

| Job | Verdict |
|---|---|
| LoRA/QLoRA, 4B–8B, 4-bit, seq 2048 | sweet spot |
| LoRA, 14B 4-bit, short seq + grad checkpointing | tight but works |
| Inference 7–14B 4-bit | easy; 32B 4-bit runs slowly |
| Full fine-tune ≥7B, or training ≥30B | no |

macOS caps GPU-wired memory near 75% of RAM (~18 GB here). The
`iogpu.wired_limit_mb` knob can raise it; starving macOS into swap is worse
than a smaller batch. Hours per run, not minutes — the mini is for iterating
and small LoRAs, a rented GPU is for the run that ships.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `tailscale ping` pongs, `ssh`/`ping` time out | tailnet ACL, not the host | add the `dst` rule above |
| `command not found: tailscale` | GUI app, CLI is inside the bundle | use the Homebrew daemon build instead |
| `setremotelogin: requires Full Disk Access` | macOS TCC | use the Sharing GUI toggle |
| Studio dies ~1h after start | booted on the auto-generated password | `unsloth studio reset-password` |
| Studio gone after reboot | plist not bootstrapped, or bind raced Tailscale | check `launchd.err.log`; `KeepAlive` should retry |
| `ssh lab` → `could not resolve hostname lab` | you're already ON the mini | `lab` only exists in the laptop's config |
| zsh drops to `quote>` pasting commands | zsh has no `interactive_comments`; an apostrophe in a `#` comment opened a quote | Ctrl-C, paste without comments |

Session log of the original build: the ACL discovery took the longest and is
the single least reproducible-from-memory step. Start there next time.
