# Estradot stock tracker

Checks Fass.se's public pharmacy stock data for all Estradot strengths
(25 / 37.5 / 50 / 75 / 100 mikrogram) across ~105 towns covering all of
Sweden, classifies every pharmacy into one of the 21 regions (län), and
publishes a live status page. It runs automatically 10 times a day
(06:00–00:00, every 2 hours, Stockholm time) and can email and/or push-notify
you when a strength/region combo you care about newly comes into stock.

**Unofficial tool.** Not affiliated with Fass.se, Sveriges Apoteksförening,
or any pharmacy chain. It works by replicating the same requests your
browser makes when you use Fass.se's own "Lagerstatus" search — see
`scripts/check_estradot.py` for how that was reverse-engineered.

---

## One-time setup

### 1. Create the repository
1. Create a free account at [github.com](https://github.com) if you don't have one.
2. Create a **new repository**. Pick any name — it doesn't need to mention
   the medication if you'd rather keep it generic (see the Privacy section
   below for why that might matter).
3. Upload all the files in this folder, preserving the folder structure
   (`.github/workflows/check.yml`, `scripts/`, `docs/`, `state/`). Easiest
   way: "Add file" → "Upload files" and drag in the *contents* of the
   folder (not the folder itself — dragging the folder itself creates an
   extra unwanted level of nesting). Note that `.github` is a hidden
   folder on a Mac — press **Cmd+Shift+.** in Finder to reveal it before
   dragging, or use `git` locally instead:
   ```
   cd estradot-tracker
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
   git push -u origin main
   ```

### 2. Enable GitHub Pages
1. **Settings → Pages**.
2. Under "Build and deployment" → "Source", choose **Deploy from a branch**.
3. Branch: `main`, folder: `/docs`. Save.
4. Note: on GitHub's free plan, Pages only works with a **public** repo —
   see the Privacy section below for what that does and doesn't expose.
5. Your live URL will be `https://YOUR-USERNAME.github.io/YOUR-REPO/` —
   can take a minute or two to go live the first time.

### 3. Allow the workflow to commit results back
1. **Settings → Actions → General**.
2. Under "Workflow permissions", select **"Read and write permissions"**. Save.
   (Without this, the workflow runs the check but can't publish the
   updated page, since it isn't allowed to push its results.)

### 4. Set up notifications (either or both — optional but recommended)

**Email** (via Gmail):
1. Turn on 2-Step Verification on your Google account, if not already on.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   → create an app password (name it anything) → copy the 16-character code.
   This is *not* your normal Gmail password, and can be revoked independently
   at any time without affecting your real account password.
3. **Settings → Secrets and variables → Actions → New repository secret**,
   add these:
   - `SMTP_USERNAME` → your Gmail address
   - `SMTP_PASSWORD` → the app password from step 2
   - `NOTIFY_EMAIL` → where alerts should go (can be the same address)

**Push notifications** (via [ntfy](https://ntfy.sh), no account needed):
1. Install the free ntfy app ([iOS](https://apps.apple.com/app/ntfy/id1625396347) /
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)),
   or just use ntfy.sh in a browser tab.
2. Pick a personal base string — long and random, e.g. `estradot-x7k2m9qp`
   (this seeds several topic names derived from it, so keep it private-ish).
3. Add it as a repository secret named `NTFY_TOPIC`.
4. Subscribe to that exact string in the app for a catch-all feed of every
   event, or use the live page's "Get notified" panel to get specific
   `{base}-{strength}mcg-{region}` topic names for just what you care about.

If you skip both, everything else still works — you'll just need to check
the page yourself.

### 5. Filter notifications by strength/region (optional)
1. Open your live page → scroll to **"Get notified"**.
2. Tick the strength(s) and region(s) you want (or "All of Sweden").
3. Click **"Show my config"** — it displays two values.
4. Add them as repository secrets:
   - `NOTIFY_STRENGTHS` (controls email filtering)
   - `NOTIFY_REGIONS` (controls email filtering)

   Leave `NOTIFY_REGIONS` **unset entirely** for "all of Sweden" — GitHub
   won't let you save a truly blank secret value, so just don't create it
   rather than trying to leave it empty.

   (ntfy filtering works differently — see step 4 above; it's based on
   which topic name(s) you subscribe to, not these two secrets.)

Without these two secrets, email notifications include every new-stock
event with no filtering.

### 6. Run it once manually to confirm it works
1. **Actions** tab → "Check Estradot stock" → **"Run workflow"**.
2. Manual runs always execute regardless of the schedule/time gate.
3. Wait a few minutes, check for a green checkmark, then refresh your
   GitHub Pages URL — it should show live data instead of the placeholder.

After this, it runs itself automatically — no further action needed.

---

## How the schedule works

The workflow technically runs every hour, but a "Check if this is one of
the scheduled hours" step first checks the actual current time in the
`Europe/Stockholm` timezone and skips everything else unless it's exactly
06:00, 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00, or 00:00
local time. This (rather than a fixed UTC cron schedule) is what keeps it
correctly aligned through the March/October daylight-saving changes with
no manual adjustment ever needed. Manually triggering a run from the
Actions tab always runs immediately, bypassing this check.

---

## Privacy

On GitHub's free plan, Pages only works from a **public** repository —
there's no way around this without upgrading to GitHub Pro (private repos)
or GitHub Enterprise Cloud (actually-private published sites; Pro alone
still leaves the *published page* public, just not the source code).

What being public actually exposes:
- The source code, README, and Actions run logs/history
- The live tracker page (this is *always* publicly reachable by URL
  regardless of repo visibility or plan — a fundamental property of how
  GitHub Pages works, not something specific to this project)
- Your GitHub username being associated with a repo about this medication

What it does **not** expose:
- Your email address or notification preferences — these live only as
  encrypted GitHub secrets, are never printed anywhere in logs, and
  GitHub automatically redacts secret values from log output as an
  extra safety net even if code ever accidentally tried to print one
- Anything about *you* personally in the tracked data itself — the
  published stock/pharmacy information is the same public data anyone
  can already get directly from Fass.se

If you'd rather your GitHub username not be so directly associable with
this specific medication:
- Rename the repository to something generic (Settings → General → rename)
- Consider a separate GitHub account not linked to your identity elsewhere
- Check **github.com/settings/emails** → make sure **"Keep my email
  addresses private"** is turned on, so any commits you make through
  GitHub's website show a placeholder email instead of your real one
  (this only protects commits made *after* turning it on — check your
  existing commit history if you're curious whether anything's already
  exposed)

---

## If something breaks

- **Workflow fails at "Commit and push"** → almost always the workflow
  permissions from setup step 3; double-check that setting.
- **Workflow fails at "Run stock check"** → Fass.se may have changed
  something, or is rate-limiting automated requests. Check the Actions
  log for the actual error message; batch-size rejections are already
  retried automatically with smaller batches, so a persistent failure
  likely means something upstream changed and the script needs updating.
- **No notification arrives despite the page showing new stock** →
  double-check secret names/values are spelled exactly right
  (case-sensitive), and that `NOTIFY_STRENGTHS`/`NOTIFY_REGIONS` (if set)
  actually match the event that occurred.
- **Page shows 404** → GitHub Pages can take a couple of minutes after
  first enabling it; confirm Settings → Pages source is `main` / `/docs`.
- **"Fill out this field" error when saving a secret** → GitHub won't
  accept a blank value; just skip creating that secret entirely instead
  of trying to save it empty.

## Files

- `scripts/check_estradot.py` — the actual checker; safe to run locally
  too (`pip install requests && python scripts/check_estradot.py`) for
  testing, though notifications and the live page still require the
  secrets described above to be set as environment variables locally.
- `.github/workflows/check.yml` — the schedule/automation definition.
- `docs/index.html` — the published page (auto-generated — don't edit by
  hand, it gets overwritten every run).
- `docs/data/latest.json` — raw current results, for reference/debugging.
- `docs/data/status_values.json` — every distinct raw stock-status value
  Fass has returned, with an example pharmacy for each — useful for
  auditing the in-stock/out-of-stock classification logic.
- `state/previous.json` — internal memory of the last run's results, used
  to detect *new* stock events (auto-generated).

---

*Built with help from Claude (Anthropic).*
