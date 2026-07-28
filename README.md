# Estradot stock tracker

Checks Fass.se's public pharmacy stock data for all Estradot strengths
(25/37.5/50/75/100 mikrogram) across ~105 towns covering all of Sweden,
every 30 minutes, publishes a live status page, and sends a push
notification (via [ntfy.sh](https://ntfy.sh)) whenever a pharmacy that
wasn't previously in stock becomes in stock.

**Unofficial tool.** Not affiliated with Fass.se, Sveriges Apoteksförening,
or any pharmacy chain. It works by replicating the same requests your
browser makes when you use Fass.se's own "Lagerstatus" search — see
`scripts/check_estradot.py` for how that was reverse-engineered.

---

## One-time setup (~10 minutes)

### 1. Create the repository
1. Create a free account at [github.com](https://github.com) if you don't have one.
2. Create a **new repository** (the "+" icon top right → "New repository").
   Public or private both work. Pick any name — it doesn't need to mention
   the medication if you'd rather keep it generic, since the published page
   URL will be visible to anyone with the link (though not searchable or
   listed anywhere).
3. Upload all the files in this folder to that repository, preserving the
   folder structure (`.github/workflows/check.yml`, `scripts/`, `docs/`,
   `state/`). Easiest way: on the repo's page, use "Add file" → "Upload
   files" and drag the whole folder in, or use `git` locally if you're
   comfortable with it:
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
1. In your repo, go to **Settings → Pages**.
2. Under "Build and deployment" → "Source", choose **Deploy from a branch**.
3. Branch: `main`, folder: `/docs`. Save.
4. GitHub will show you the live URL (something like
   `https://YOUR-USERNAME.github.io/YOUR-REPO/`) — it can take a minute or
   two to go live the first time.

### 3. Allow the workflow to commit results back
1. Go to **Settings → Actions → General**.
2. Scroll to "Workflow permissions".
3. Select **"Read and write permissions"**. Save.
   (Without this, the workflow can run the check but will fail to publish
   the updated page, since it won't be allowed to push its results.)

### 4. Set up push notifications (optional but recommended)
1. Install the **ntfy** app — free, on [iOS App Store](https://apps.apple.com/app/ntfy/id1625396347)
   or [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy),
   or just use [ntfy.sh](https://ntfy.sh) in a browser tab if you'd rather
   not install anything.
2. Pick a **topic name** — this acts like a private channel name. Anyone
   who knows the exact name could subscribe to it too, so make it long and
   random rather than something guessable, e.g. `estradot-alerts-x7k2m9qp`.
3. In the app (or on ntfy.sh), **subscribe** to that exact topic name.
4. Back in your GitHub repo: **Settings → Secrets and variables → Actions
   → New repository secret**.
   - Name: `NTFY_TOPIC`
   - Value: the topic name you picked
   - Save.

If you skip this step, everything else still works — you'll just need to
check the page yourself rather than getting pushed a notification.

### 5. Run it once manually to confirm it works
1. Go to the **Actions** tab in your repo.
2. Click "Check Estradot stock" in the left sidebar.
3. Click **"Run workflow"** (dropdown on the right) → "Run workflow".
4. Wait ~2-3 minutes, then check the run's logs. If it succeeded, refresh
   your GitHub Pages URL from step 2 — it should now show live data.

After this, it runs automatically every 30 minutes (at :07 and :37 past
each hour) with no further action needed.

---

## If something breaks

- **Workflow fails at the "Commit and push" step** → almost always the
  workflow permissions from step 3 above; double check that setting.
- **Workflow fails at "Run stock check" with request errors** → Fass.se
  may have changed something on their end, or is rate-limiting the
  automated requests. Check the error message in the Actions log; if it's
  a batch-size rejection the script already retries with smaller batches
  automatically, so a persistent failure likely means something upstream
  changed and the script needs an update.
- **No notification arrives even though the page shows new stock** →
  double-check the `NTFY_TOPIC` secret is spelled identically to what
  you subscribed to in the app (case-sensitive).
- **Page shows 404** → GitHub Pages can take a couple of minutes after
  first enabling it; also double-check Settings → Pages source is set to
  `main` / `/docs`.

## Files

- `scripts/check_estradot.py` — the actual checker; safe to run locally too
  (`pip install requests && python scripts/check_estradot.py`) for testing.
- `.github/workflows/check.yml` — the schedule/automation definition.
- `docs/index.html` — the published page (auto-generated, don't edit by hand — it gets overwritten every run).
- `state/previous.json` — internal memory of the last run's results, used to detect *new* stock events (auto-generated).
