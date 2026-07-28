#!/usr/bin/env python3
"""
Estradot nationwide stock tracker
----------------------------------
Runs on a schedule (via GitHub Actions), checks pharmacy stock across
Sweden for all Estradot strengths using Fass.se's public pharmacy API,
compares against the previous run, sends a push notification via ntfy.sh
if something new comes into stock, and renders a static HTML page.

This is meant to be run non-interactively (cron/CI), not by hand -- for
manual/ad-hoc checks with more CLI options, see check_estradot_availability.py.

ENVIRONMENT VARIABLES
    NTFY_TOPIC   (optional) -- if set, posts a notification to
                 https://ntfy.sh/<NTFY_TOPIC> when new stock is found.
                 If unset, notifications are skipped (page still updates).

OUTPUTS
    docs/index.html        -- the live status page (published via GitHub Pages)
    docs/data/latest.json  -- raw current results, for reference/debugging
    state/previous.json    -- internal state, used to detect new-stock events
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


def is_in_stock(entry):
       return entry.get("stockInformation") is True


def run_all_checks(session, gln_list):
    """Returns {strength: {gln: bool_in_stock}}"""
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
                    stock_by_gln[gln] = is_in_stock(entry)
            time.sleep(DELAY)
        hits = sum(1 for v in stock_by_gln.values() if v)
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
    """Return list of (strength, gln, pharmacy_name, city) that are newly in stock."""
    events = []
    prev_stock = previous.get("stock", {})
    for strength, gln_map in current.items():
        prev_map = prev_stock.get(strength, {})
        for gln, in_stock in gln_map.items():
            was_in_stock = prev_map.get(gln, False)
            if in_stock and not was_in_stock:
                p = pharmacies.get(gln, {})
                addr = p.get("visitingAddress", {})
                events.append((strength, gln, p.get("name", gln), addr.get("city", "")))
    return events


def send_ntfy_notification(events):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log("NTFY_TOPIC not set, skipping notification.")
        return
    if not events:
        return
    lines = [f"• {strength} mcg at {name} ({city})" for strength, _, name, city in events]
    message = "New Estradot stock found:\n" + "\n".join(lines)
    title = f"Estradot: {len(events)} new stock hit(s)"
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tags": "pill"},
            timeout=15,
        )
        log(f"Sent ntfy notification ({len(events)} event(s)) to topic '{topic}'.")
    except requests.RequestException as e:
        log(f"[!] Failed to send ntfy notification: {e}")


def render_html(current, pharmacies, generated_at, events_history):
    strengths = list(PRODUCT_IDS.keys())

    rows_html = []
    combined = {}
    for strength in strengths:
        for gln, in_stock in current[strength].items():
            combined.setdefault(gln, {})[strength] = in_stock

    any_hits = []
    for gln, per_strength in combined.items():
        if any(per_strength.values()):
            p = pharmacies.get(gln, {})
            addr = p.get("visitingAddress", {})
            in_stock_strengths = [s for s, v in per_strength.items() if v]
            any_hits.append({
                "name": p.get("name", ""),
                "street": addr.get("streetAddress", ""),
                "city": addr.get("city", ""),
                "postal_code": addr.get("postalCode", ""),
                "phone": p.get("phoneNumber", ""),
                "strengths": in_stock_strengths,
            })
    any_hits.sort(key=lambda r: (r["city"], r["name"]))

    for h in any_hits:
        strength_badges = " ".join(
            f'<span class="badge">{s} mcg</span>' for s in h["strengths"]
        )
        rows_html.append(f"""
        <tr>
          <td>{h['name']}</td>
          <td>{h['street']}, {h['city']} ({h['postal_code']})</td>
          <td>{h['phone']}</td>
          <td>{strength_badges}</td>
        </tr>""")

    summary_html = "".join(
        f'<div class="stat"><div class="stat-num">{sum(1 for v in current[s].values() if v)}</div>'
        f'<div class="stat-label">{s} mcg</div></div>'
        for s in strengths
    )

    history_html = ""
    if events_history:
        items = "".join(
            f"<li>{e['timestamp']}: {e['strength']} mcg at {e['name']} ({e['city']})</li>"
            for e in events_history[:30]
        )
        history_html = f"<h2>Recent new-stock events</h2><ul class='history'>{items}</ul>"

    table_html = (
        "<table><thead><tr><th>Pharmacy</th><th>Address</th><th>Phone</th><th>In stock</th></tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table>"
        if any_hits else "<p class='none'>No pharmacies currently report any strength in stock.</p>"
    )

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
  .history {{ color: var(--muted); font-size: 0.85rem; padding-left: 18px; }}
  footer {{ margin-top: 40px; color: var(--muted); font-size: 0.8rem; border-top: 1px solid var(--border); padding-top: 16px; }}
  a {{ color: var(--accent); }}
</style>
</head>
<body>
  <h1>Estradot® stock tracker — Sweden</h1>
  <p class="subtitle">Last checked: {generated_at} UTC · Data via Fass.se / Sveriges Apoteksförening</p>

  <div class="stats">{summary_html}</div>

  <h2>Currently in stock</h2>
  {table_html}

  {history_html}

  <footer>
    Unofficial tool, not affiliated with Fass.se or Sveriges Apoteksförening.
    Always confirm with the pharmacy before travelling — stock snapshots can change quickly.
  </footer>
</body>
</html>"""
    return html


def main():
    session = requests.Session()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    previous = load_previous_state()
    pharmacies = collect_pharmacies(session)
    gln_list = list(pharmacies.keys())

    current = run_all_checks(session, gln_list)

    events = find_new_stock_events(previous, current, pharmacies)
    if events:
        log(f"New stock events: {len(events)}")
        for strength, gln, name, city in events:
            log(f"  + {strength} mcg at {name} ({city})")
    send_ntfy_notification(events)

    history = previous.get("history", [])
    for strength, gln, name, city in events:
        history.insert(0, {"timestamp": generated_at, "strength": strength, "name": name, "city": city})
    history = history[:100]

    new_state = {"stock": current, "history": history, "last_run": generated_at}
    save_state(new_state)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "data").mkdir(parents=True, exist_ok=True)

    html = render_html(current, pharmacies, generated_at, history)
    HTML_FILE.write_text(html, encoding="utf-8")

    JSON_FILE.write_text(json.dumps({
        "generated_at": generated_at,
        "pharmacies_checked": len(pharmacies),
        "stock": current,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    log("Done. Wrote docs/index.html and docs/data/latest.json.")


if __name__ == "__main__":
    main()
