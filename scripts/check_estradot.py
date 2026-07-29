#!/usr/bin/env python3
"""
Estradot nationwide stock tracker
----------------------------------
Runs on a schedule (via GitHub Actions), checks pharmacy stock across
Sweden for all Estradot strengths using Fass.se's public pharmacy API,
compares against the previous run, sends push notifications via ntfy.sh
when something new comes into stock, and renders a static HTML page.

This is meant to be run non-interactively (cron/CI), not by hand -- for
manual/ad-hoc checks with more CLI options, see check_estradot_availability.py.

ENVIRONMENT VARIABLES
    NTFY_TOPIC   (optional) -- a personal *base* string (not a literal
                 topic name) used to derive several topics:
                     {NTFY_TOPIC}                         -- catch-all, every event
                     {NTFY_TOPIC}-{strength}mcg-all        -- one strength, anywhere in Sweden
                     {NTFY_TOPIC}-{strength}mcg-{region}   -- one strength, one region
                 The live page has an interactive panel that builds these
                 topic names for you based on picks you make there.
                 If unset, notifications are skipped (page still updates).

OUTPUTS
    docs/index.html               -- the live status page (published via GitHub Pages)
    docs/data/latest.json         -- raw current results, for reference/debugging
    docs/data/status_values.json -- every distinct raw stock-status value seen, for auditing
    state/previous.json           -- internal state, used to detect new-stock events
"""

import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "previous.json"
HTML_FILE = DOCS_DIR / "index.html"
JSON_FILE = DOCS_DIR / "data" / "latest.json"

BASE = "https://fass.se/api/content"

PRODUCT_IDS = {
    "25": "20040113100574",
    "37.5": "20011130100489",
    "50": "20011130100502",
    "75": "20011130100526",
    "100": "20011130100564",
}

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en;q=0.9,sv;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/26.5.2 Safari/605.1.15"
    ),
    "Referer": "https://fass.se/product/20011130000260/stock-status",
    "Origin": "https://fass.se",
}

CITIES = {
    "Stockholm": (59.3293, 18.0686), "Göteborg": (57.7089, 11.9746),
    "Malmö": (55.6050, 13.0038), "Uppsala": (59.8586, 17.6389),
    "Västerås": (59.6099, 16.5448), "Örebro": (59.2741, 15.2066),
    "Linköping": (58.4108, 15.6214), "Helsingborg": (56.0465, 12.6945),
    "Jönköping": (57.7826, 14.1618), "Norrköping": (58.5877, 16.1924),
    "Lund": (55.7047, 13.1910), "Umeå": (63.8258, 20.2630),
    "Gävle": (60.6749, 17.1413), "Borås": (57.7210, 12.9401),
    "Södertälje": (59.1955, 17.6252), "Eskilstuna": (59.3706, 16.5077),
    "Halmstad": (56.6745, 12.8570), "Växjö": (56.8777, 14.8091),
    "Karlstad": (59.3793, 13.5036), "Sundsvall": (62.3908, 17.3069),
    "Trollhättan": (58.2837, 12.2886), "Östersund": (63.1792, 14.6357),
    "Borlänge": (60.4858, 15.4342), "Falun": (60.6065, 15.6355),
    "Skövde": (58.3911, 13.8458), "Kalmar": (56.6634, 16.3567),
    "Kristianstad": (56.0294, 14.1567), "Karlskrona": (56.1612, 15.5869),
    "Skellefteå": (64.7507, 20.9528), "Luleå": (65.5842, 22.1547),
    "Uddevalla": (58.3498, 11.9423), "Varberg": (57.1057, 12.2503),
    "Visby": (57.6349, 18.2948), "Motala": (58.5378, 15.0367),
    "Landskrona": (55.8708, 12.8300), "Kiruna": (67.8558, 20.2253),
    "Gällivare": (67.1667, 20.6667), "Haparanda": (65.8378, 24.1358),
    "Piteå": (65.3172, 21.4794), "Boden": (65.8256, 21.6889),
    "Kalix": (65.8531, 23.1614), "Arvidsjaur": (65.5928, 19.1753),
    "Lycksele": (64.6014, 18.6714), "Vilhelmina": (64.6136, 16.6547),
    "Storuman": (65.0997, 17.1092), "Åre": (63.3986, 13.0817),
    "Härnösand": (62.6328, 17.9382), "Örnsköldsvik": (63.2909, 18.7153),
    "Sollefteå": (63.1667, 17.2667), "Kramfors": (62.9333, 17.7833),
    "Hudiksvall": (61.7281, 17.1058), "Söderhamn": (61.3036, 17.0575),
    "Bollnäs": (61.3486, 16.3931), "Sandviken": (60.6167, 16.7833),
    "Hofors": (60.5486, 16.2792), "Ludvika": (60.1500, 15.1833),
    "Avesta": (60.1450, 16.1697), "Hedemora": (60.2789, 15.9814),
    "Fagersta": (59.9986, 15.7947), "Sala": (59.9247, 16.6067),
    "Enköping": (59.6367, 17.0775), "Katrineholm": (58.9958, 16.2064),
    "Nyköping": (58.7531, 17.0089), "Oxelösund": (58.6733, 17.1067),
    "Flen": (59.0578, 16.5836), "Strängnäs": (59.3775, 17.0300),
    "Mariestad": (58.7089, 13.8236), "Lidköping": (58.5039, 13.1575),
    "Skara": (58.3856, 13.4356), "Vänersborg": (58.3808, 12.3222),
    "Alingsås": (57.9300, 12.5333), "Kungsbacka": (57.4875, 12.0761),
    "Falkenberg": (56.9058, 12.4914), "Ängelholm": (56.2428, 12.8617),
    "Ystad": (55.4297, 13.8203), "Trelleborg": (55.3753, 13.1567),
    "Eslöv": (55.8397, 13.3033), "Hässleholm": (56.1589, 13.7664),
    "Simrishamn": (55.5514, 14.3547), "Nässjö": (57.6531, 14.6947),
    "Vetlanda": (57.4275, 15.0806), "Värnamo": (57.1833, 14.0333),
    "Ljungby": (56.8317, 13.9425), "Oskarshamn": (57.2647, 16.4486),
    "Västervik": (57.7594, 16.6386), "Vimmerby": (57.6653, 15.8578),
    "Nybro": (56.7439, 15.9089), "Emmaboda": (56.6247, 15.5417),
    "Karlshamn": (56.1697, 14.8639), "Sölvesborg": (56.0522, 14.5761),
    "Ronneby": (56.2117, 15.2761), "Olofström": (56.2769, 14.5289),
    "Åmål": (59.0500, 12.7000), "Arvika": (59.6553, 12.5892),
    "Kristinehamn": (59.3103, 14.1097), "Filipstad": (59.7139, 14.1739),
    "Torsby": (60.1333, 12.9833), "Hagfors": (60.0333, 13.7000),
    "Säffle": (59.1333, 12.9167), "Karlskoga": (59.3267, 14.5250),
    "Lindesberg": (59.5936, 15.2325), "Nora": (59.5122, 14.9819),
    "Kumla": (59.1258, 15.1381), "Hallsberg": (59.0644, 15.1050),
    "Askersund": (58.8794, 14.9042),
}

DELAY = 0.4  # seconds between requests, to be a polite/low-impact scraper

# The 21 Swedish regions (län), each with a representative coordinate
# (its capital/residence city) used to classify each pharmacy into a
# region by nearest-center distance. This is an approximation -- Sweden's
# elongated shape means simple lat/lon distance isn't perfectly accurate
# right at län borders -- but it's more than good enough for grouping
# pharmacies for notification purposes.
REGIONS = [
    ("Stockholm", "stockholm", 59.3293, 18.0686),
    ("Uppsala", "uppsala", 59.8586, 17.6389),
    ("Södermanland", "sodermanland", 58.7531, 17.0089),
    ("Östergötland", "ostergotland", 58.4108, 15.6214),
    ("Jönköping", "jonkoping", 57.7826, 14.1618),
    ("Kronoberg", "kronoberg", 56.8777, 14.8091),
    ("Kalmar", "kalmar", 56.6634, 16.3567),
    ("Gotland", "gotland", 57.6349, 18.2948),
    ("Blekinge", "blekinge", 56.1612, 15.5869),
    ("Skåne", "skane", 55.6050, 13.0038),
    ("Halland", "halland", 56.6745, 12.8570),
    ("Västra Götaland", "vastra-gotaland", 57.7089, 11.9746),
    ("Värmland", "varmland", 59.3793, 13.5036),
    ("Örebro", "orebro", 59.2741, 15.2066),
    ("Västmanland", "vastmanland", 59.6099, 16.5448),
    ("Dalarna", "dalarna", 60.6065, 15.6355),
    ("Gävleborg", "gavleborg", 60.6749, 17.1413),
    ("Västernorrland", "vasternorrland", 62.6328, 17.9382),
    ("Jämtland", "jamtland", 63.1792, 14.6357),
    ("Västerbotten", "vasterbotten", 63.8258, 20.2630),
    ("Norrbotten", "norrbotten", 65.5842, 22.1547),
]


def assign_region(lat, lon):
    """Return (region_name, region_slug) for a coordinate, by nearest
    regional center. Falls back to ("Unknown", "unknown") if lat/lon
    are missing or unparseable.
    """
    if lat is None or lon is None:
        return ("Unknown", "unknown")
    best = None
    best_dist = None
    for name, slug, rlat, rlon in REGIONS:
        d = (lat - rlat) ** 2 + (lon - rlon) ** 2
        if best_dist is None or d < best_dist:
            best_dist = d
            best = (name, slug)
    return best


def pharmacy_latlon(p):
    """Parse a pharmacy's lat/lon (Fass returns them as strings) into floats."""
    try:
        return float(p.get("latitude")), float(p.get("longitude"))
    except (TypeError, ValueError):
        return None, None


def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


def fetch_pharmacies_near(session, lat, lon, limit=60):
    inner = f"https://cms.fass.se/api/patient/pharmacy?longitude={lon}&latitude={lat}&limit={limit}"
    url = f"{BASE}?endpoint={urllib.parse.quote(inner, safe='')}"
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_stock(session, product_id, gln_codes):
    inner = f"https://cms.fass.se/api/patient/pharmacy/stock/{product_id}"
    url = f"{BASE}?endpoint={urllib.parse.quote(inner, safe='')}"
    resp = session.post(
        url,
        headers={**HEADERS, "Content-Type": "text/plain;charset=UTF-8"},
        data=json.dumps(gln_codes),
        timeout=20,
    )
    if not resp.ok:
        raise requests.HTTPError(f"{resp.status_code} {resp.reason}: {resp.text[:300]!r}", response=resp)
    return resp.json()


def fetch_stock_with_retry(session, product_id, gln_codes, min_chunk=5):
    try:
        return fetch_stock(session, product_id, gln_codes)
    except requests.HTTPError:
        if len(gln_codes) <= min_chunk:
            raise
        mid = len(gln_codes) // 2
        left = fetch_stock_with_retry(session, product_id, gln_codes[:mid], min_chunk)
        right = fetch_stock_with_retry(session, product_id, gln_codes[mid:], min_chunk)
        return left + right


def collect_pharmacies(session):
    all_pharmacies = {}
    log(f"Searching pharmacies near {len(CITIES)} towns...")
    for city, (lat, lon) in CITIES.items():
        try:
            pharmacies = fetch_pharmacies_near(session, lat, lon)
        except requests.RequestException as e:
            log(f"  [!] {city}: {e}")
            continue
        if isinstance(pharmacies, list):
            for p in pharmacies:
                gln = p.get("glnCode")
                if gln:
                    all_pharmacies[gln] = p
        time.sleep(DELAY)
    log(f"Collected {len(all_pharmacies)} unique pharmacies.")
    return all_pharmacies


def is_in_stock(raw_status):
    """Classify a raw stockInformation value as in-stock or not.

    CONFIRMED FROM REAL DATA (via docs/data/status_values.json across
    the full ~1247-pharmacy x 5-strength dataset): Fass uses exactly
    four distinct values for this field:
        "NOT_IN_STOCK_SHORTAGE_INFO"  -> not in stock
        "NO_SERVICE"                  -> pharmacy doesn't report stock
        "IN_STOCK"                    -> genuinely in stock
        "FEW_IN_STOCK"                -> genuinely in stock, low quantity
    No ambiguous "orderable but not in stock" status actually exists --
    that was a reasonable worry given the "Beställningsvara" label seen
    on the Fass website, but the real API data doesn't bear it out.

    This is now an explicit allow-list (safer than the earlier
    exclusion-based version): only values known to mean "in stock"
    count as such. If Fass ever introduces a new status we haven't seen,
    it will correctly fall on the "not confirmed in stock" side rather
    than being assumed positive by default.
    """
    return raw_status in ("IN_STOCK", "FEW_IN_STOCK")


def run_all_checks(session, gln_list):
    """Returns {strength: {gln: raw_stockInformation_value}}.

    Deliberately stores the *raw* value (not just a bool) so we can
    audit exactly what Fass returns and catch misclassifications --
    see main()'s status-value summary output.
    """
    results = {}
    for strength, product_id in PRODUCT_IDS.items():
        log(f"Checking {strength} mikrogram...")
        stock_by_gln = {}
        chunk_size = 40
        for i in range(0, len(gln_list), chunk_size):
            chunk = gln_list[i:i + chunk_size]
            try:
                entries = fetch_stock_with_retry(session, product_id, chunk)
            except requests.RequestException as e:
                log(f"  [!] batch at {i} failed: {e}")
                continue
            for entry in entries:
                gln = entry.get("glnCode")
                if gln:
                    stock_by_gln[gln] = entry.get("stockInformation")
            time.sleep(DELAY)
        hits = sum(1 for v in stock_by_gln.values() if is_in_stock(v))
        log(f"  -> {hits} in stock")
        results[strength] = stock_by_gln
    return results


def load_previous_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def find_new_stock_events(previous, current, pharmacies):
    """Return list of dicts describing pharmacies newly in stock, including
    which region each falls into (needed to route notifications)."""
    events = []
    prev_stock = previous.get("stock", {})
    for strength, gln_map in current.items():
        prev_map = prev_stock.get(strength, {})
        for gln, raw_status in gln_map.items():
            in_stock = is_in_stock(raw_status)
            was_in_stock = is_in_stock(prev_map.get(gln))
            if in_stock and not was_in_stock:
                p = pharmacies.get(gln, {})
                addr = p.get("visitingAddress", {})
                lat, lon = pharmacy_latlon(p)
                region_name, region_slug = assign_region(lat, lon)
                events.append({
                    "strength": strength,
                    "gln": gln,
                    "name": p.get("name", gln),
                    "city": addr.get("city", ""),
                    "region_name": region_name,
                    "region_slug": region_slug,
                })
    return events


def send_notifications(events):
    """Route each new-stock event to the right ntfy.sh topic(s).

    NTFY_TOPIC is now used as a personal *base* string (not a literal
    topic name). For each event we derive:
        {base}-{strength}mcg-{region_slug}   -- subscribers wanting just this strength+region
        {base}-{strength}mcg-all             -- subscribers wanting this strength anywhere in Sweden
        {base}                               -- catch-all, everything (kept for backward compatibility
                                                 with whoever already subscribed to the bare base topic)
    Only one HTTP request is sent per distinct topic per run, with all
    matching events combined into one message, rather than one request
    per event.
    """
    base = os.environ.get("NTFY_TOPIC")
    if not base:
        log("NTFY_TOPIC not set, skipping notifications.")
        return
    if not events:
        return

    # topic -> list of event dicts
    topic_events = {}

    def add(topic, event):
        topic_events.setdefault(topic, []).append(event)

    for e in events:
        add(base, e)  # catch-all
        add(f"{base}-{e['strength']}mcg-all", e)
        add(f"{base}-{e['strength']}mcg-{e['region_slug']}", e)

    for topic, evs in topic_events.items():
        lines = [f"• {e['strength']} mcg at {e['name']} ({e['city']}, {e['region_name']})" for e in evs]
        message = "New Estradot stock found:\n" + "\n".join(lines)
        title = f"Estradot: {len(evs)} new stock hit(s)"
        try:
            requests.post(
                f"https://ntfy.sh/{topic}",
                data=message.encode("utf-8"),
                headers={"Title": title, "Priority": "high", "Tags": "pill"},
                timeout=15,
            )
            log(f"Sent ntfy notification ({len(evs)} event(s)) to topic '{topic}'.")
        except requests.RequestException as ex:
            log(f"[!] Failed to send ntfy notification to '{topic}': {ex}")


def render_html(current, pharmacies, generated_at):
    strengths = list(PRODUCT_IDS.keys())

    rows_html = []
    combined = {}
    for strength in strengths:
        for gln, raw_status in current[strength].items():
            combined.setdefault(gln, {})[strength] = is_in_stock(raw_status)

    any_hits = []
    for gln, per_strength in combined.items():
        if any(per_strength.values()):
            p = pharmacies.get(gln, {})
            addr = p.get("visitingAddress", {})
            lat, lon = pharmacy_latlon(p)
            region_name, _ = assign_region(lat, lon)
            in_stock_strengths = [s for s, v in per_strength.items() if v]
            any_hits.append({
                "name": p.get("name", ""),
                "street": addr.get("streetAddress", ""),
                "city": addr.get("city", ""),
                "postal_code": addr.get("postalCode", ""),
                "region": region_name,
                "phone": p.get("phoneNumber", ""),
                "strengths": in_stock_strengths,
            })
    any_hits.sort(key=lambda r: (r["region"], r["city"], r["name"]))

    for h in any_hits:
        strength_badges = " ".join(
            f'<span class="badge">{s} mcg</span>' for s in h["strengths"]
        )
        rows_html.append(f"""
        <tr>
          <td>{h['name']}</td>
          <td>{h['street']}, {h['city']} ({h['postal_code']})</td>
          <td>{h['region']}</td>
          <td>{h['phone']}</td>
          <td>{strength_badges}</td>
        </tr>""")

    summary_html = "".join(
        f'<div class="stat"><div class="stat-num">{sum(1 for v in current[s].values() if is_in_stock(v))}</div>'
        f'<div class="stat-label">{s} mcg</div></div>'
        for s in strengths
    )

    table_html = (
        "<table><thead><tr><th>Pharmacy</th><th>Address</th><th>Region</th><th>Phone</th><th>In stock</th></tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table>"
        if any_hits else "<p class='none'>No pharmacies currently report any strength in stock.</p>"
    )

    strength_checkboxes_html = "".join(
        f'<label><input type="checkbox" class="strengthCb" value="{s}"> {s} mcg</label>'
        for s in strengths
    )
    region_checkboxes_html = "".join(
        f'<label><input type="checkbox" class="regionCb" value="{slug}"> {name}</label>'
        for name, slug, _, _ in REGIONS
    )

    # Built as a plain (non f-) string so the JS's own { } don't need escaping.
    notif_panel_html = """
  <h2>Get notified</h2>
  <p class="subtitle">
    Pick a strength and an area below, and this shows you the exact
    <a href="https://ntfy.sh" target="_blank" rel="noopener">ntfy</a> topic
    name(s) to subscribe to for just that combination -- no account or
    sign-up on this site, your picks are only remembered in this browser.
  </p>
  <div class="notif-panel">
    <label class="secret-label" for="baseSecret">Your personal code (any long random string -- keep it private, it's what makes these topics yours alone):</label>
    <input id="baseSecret" type="text" placeholder="e.g. river-lamp-92-owl" autocomplete="off">

    <fieldset>
      <legend>Strength</legend>
      <div class="cb-grid">__STRENGTH_CHECKBOXES__</div>
    </fieldset>

    <fieldset>
      <legend>Area</legend>
      <div class="cb-grid">
        <label><input type="checkbox" id="allSwedenCb"> <strong>All of Sweden</strong></label>
      </div>
      <div class="cb-grid region-grid">__REGION_CHECKBOXES__</div>
    </fieldset>

    <button id="generateBtn">Show my topics</button>
    <div id="topicResults"></div>
  </div>

  <script>
    (function() {
      var STORAGE_KEY = "estradot_notif_prefs_v1";

      function saved() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
        catch (e) { return {}; }
      }
      function save(prefs) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs)); }
        catch (e) {}
      }

      var prefs = saved();
      var secretEl = document.getElementById("baseSecret");
      if (prefs.secret) secretEl.value = prefs.secret;

      document.querySelectorAll(".strengthCb").forEach(function(cb) {
        if (prefs.strengths && prefs.strengths.indexOf(cb.value) !== -1) cb.checked = true;
      });
      document.querySelectorAll(".regionCb").forEach(function(cb) {
        if (prefs.regions && prefs.regions.indexOf(cb.value) !== -1) cb.checked = true;
      });
      var allSwedenEl = document.getElementById("allSwedenCb");
      if (prefs.allSweden) allSwedenEl.checked = true;

      document.getElementById("generateBtn").addEventListener("click", function() {
        var secret = secretEl.value.trim();
        var resultsEl = document.getElementById("topicResults");
        resultsEl.innerHTML = "";

        if (!secret) {
          resultsEl.innerHTML = '<p class="warn">Enter a personal code first.</p>';
          return;
        }

        var strengths = Array.prototype.slice.call(document.querySelectorAll(".strengthCb:checked")).map(function(cb) { return cb.value; });
        var regions = Array.prototype.slice.call(document.querySelectorAll(".regionCb:checked")).map(function(cb) { return cb.value; });
        var allSweden = allSwedenEl.checked;

        save({ secret: secret, strengths: strengths, regions: regions, allSweden: allSweden });

        if (strengths.length === 0 || (!allSweden && regions.length === 0)) {
          resultsEl.innerHTML = '<p class="warn">Pick at least one strength and at least one area (or "All of Sweden").</p>';
          return;
        }

        var topics = [];
        strengths.forEach(function(s) {
          if (allSweden) topics.push(secret + "-" + s + "mcg-all");
          regions.forEach(function(r) { topics.push(secret + "-" + s + "mcg-" + r); });
        });

        var html = '<p>Subscribe to ' + (topics.length === 1 ? "this topic" : "these topics") + ' in the ntfy app (or tap to open in browser):</p><ul class="topic-list">';
        topics.forEach(function(t) {
          html += '<li><code>' + t + '</code> ' +
                  '<a href="https://ntfy.sh/' + t + '" target="_blank" rel="noopener">open</a> ' +
                  '<button type="button" class="copyBtn" data-topic="' + t + '">copy</button></li>';
        });
        html += '</ul>';
        resultsEl.innerHTML = html;

        resultsEl.querySelectorAll(".copyBtn").forEach(function(btn) {
          btn.addEventListener("click", function() {
            navigator.clipboard.writeText(btn.getAttribute("data-topic")).then(function() {
              btn.textContent = "copied!";
              setTimeout(function() { btn.textContent = "copy"; }, 1500);
            });
          });
        });
      });
    })();
  </script>
""".replace("__STRENGTH_CHECKBOXES__", strength_checkboxes_html).replace("__REGION_CHECKBOXES__", region_checkboxes_html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Estradot stock tracker — Sweden</title>
<style>
  :root {{
    --bg: #0f1115; --panel: #171a21; --border: #2a2f3a; --text: #e8eaed;
    --muted: #9aa0ac; --accent: #4ade80; --accent-dim: #1f3d2c;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 900px; margin: 0 auto; padding: 32px 20px 60px;
    line-height: 1.5;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1.2rem; margin-top: 36px; }}
  .subtitle {{ color: var(--muted); margin-top: 0; font-size: 0.95rem; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 24px 0; }}
  .stat {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 18px; min-width: 90px; text-align: center;
  }}
  .stat-num {{ font-size: 1.6rem; font-weight: 700; }}
  .stat-label {{ color: var(--muted); font-size: 0.8rem; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
  th {{ color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }}
  .badge {{
    display: inline-block; background: var(--accent-dim); color: var(--accent);
    border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; margin-right: 4px;
  }}
  .none {{ color: var(--muted); padding: 20px 0; }}
  footer {{ margin-top: 40px; color: var(--muted); font-size: 0.8rem; border-top: 1px solid var(--border); padding-top: 16px; }}
  a {{ color: var(--accent); }}

  .notif-panel {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; margin-top: 12px;
  }}
  .notif-panel input[type="text"] {{
    display: block; width: 100%; margin: 6px 0 18px; padding: 10px 12px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    color: var(--text); font-size: 0.9rem;
  }}
  .secret-label {{ font-size: 0.85rem; color: var(--muted); }}
  fieldset {{ border: 1px solid var(--border); border-radius: 8px; margin-bottom: 16px; padding: 12px 14px; }}
  legend {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; padding: 0 6px; }}
  .cb-grid {{ display: flex; flex-wrap: wrap; gap: 10px 18px; }}
  .region-grid {{ margin-top: 10px; }}
  .cb-grid label {{ font-size: 0.9rem; white-space: nowrap; }}
  button#generateBtn {{
    background: var(--accent); color: #06210f; border: none; border-radius: 8px;
    padding: 10px 18px; font-size: 0.9rem; font-weight: 600; cursor: pointer;
  }}
  .topic-list {{ padding-left: 0; list-style: none; margin-top: 12px; }}
  .topic-list li {{
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 12px; margin-bottom: 8px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  }}
  .topic-list code {{ font-size: 0.85rem; }}
  .copyBtn {{
    background: transparent; border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 10px; font-size: 0.8rem; cursor: pointer;
  }}
  .warn {{ color: #f4a261; }}
</style>
</head>
<body>
  <h1>Estradot® stock tracker — Sweden</h1>
  <p class="subtitle">Last checked: {generated_at} UTC · Data via Fass.se / Sveriges Apoteksförening</p>

  <div class="stats">{summary_html}</div>

  <h2>Currently in stock</h2>
  {table_html}

  {notif_panel_html}

  <footer>
    Unofficial tool, not affiliated with Fass.se or Sveriges Apoteksförening.
    Always confirm with the pharmacy before travelling — stock snapshots can change quickly.
  </footer>
</body>
</html>"""
    return html


def build_status_value_summary(current, pharmacies):
    """Collect every distinct raw stockInformation value seen this run,
    with a count and one example pharmacy, so we can verify our
    is_in_stock() classification against real evidence instead of
    guessing. Written to docs/data/status_values.json (public, so it's
    easy to inspect without needing dev tools again).
    """
    summary = {}  # raw_value (as string key) -> {count, example, classified_as_in_stock}
    for strength, gln_map in current.items():
        for gln, raw_status in gln_map.items():
            key = repr(raw_status)  # distinguishes True (bool) from "True" (string) etc.
            if key not in summary:
                p = pharmacies.get(gln, {})
                addr = p.get("visitingAddress", {})
                summary[key] = {
                    "raw_value": raw_status,
                    "count": 0,
                    "classified_as_in_stock": is_in_stock(raw_status),
                    "example_pharmacy": p.get("name", gln),
                    "example_city": addr.get("city", ""),
                    "example_strength": strength,
                }
            summary[key]["count"] += 1
    return summary


def main():
    session = requests.Session()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    previous = load_previous_state()
    pharmacies = collect_pharmacies(session)
    gln_list = list(pharmacies.keys())

    current = run_all_checks(session, gln_list)

    status_summary = build_status_value_summary(current, pharmacies)
    log("Distinct stockInformation values seen this run:")
    for key, info in sorted(status_summary.items(), key=lambda kv: -kv[1]["count"]):
        log(f"  {info['raw_value']!r} -> classified in_stock={info['classified_as_in_stock']}, "
            f"count={info['count']}, e.g. {info['example_pharmacy']} ({info['example_city']}, {info['example_strength']}mcg)")

    events = find_new_stock_events(previous, current, pharmacies)
    if events:
        log(f"New stock events: {len(events)}")
        for e in events:
            log(f"  + {e['strength']} mcg at {e['name']} ({e['city']}, {e['region_name']})")
    send_notifications(events)

    history = previous.get("history", [])
    for e in events:
        history.insert(0, {
            "timestamp": generated_at, "strength": e["strength"],
            "name": e["name"], "city": e["city"], "region": e["region_name"],
        })
    history = history[:100]  # kept in state for internal bookkeeping; not shown on the page

    new_state = {"stock": current, "history": history, "last_run": generated_at}
    save_state(new_state)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "data").mkdir(parents=True, exist_ok=True)

    html = render_html(current, pharmacies, generated_at)
    HTML_FILE.write_text(html, encoding="utf-8")

    JSON_FILE.write_text(json.dumps({
        "generated_at": generated_at,
        "pharmacies_checked": len(pharmacies),
        "stock": current,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    (DOCS_DIR / "data" / "status_values.json").write_text(
        json.dumps(status_summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    log("Done. Wrote docs/index.html, docs/data/latest.json, docs/data/status_values.json.")


if __name__ == "__main__":
    main()
