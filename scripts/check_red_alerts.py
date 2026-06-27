#!/usr/bin/env python3
"""
Check the latest MoM Final_Attributes feed for top-level ("red") flood alerts.

Reads the same feed update_tiles.py uses (MOM_CSV_URL). Treats watersheds whose
`Alert` is in ALERT_LEVELS (default "Warning") as "red". De-dupes against the
previous run's state so the workflow only emails when NEW watersheds go red.

Outputs (for the workflow):
  $STATE_DIR/last_red.json   persisted state (cached between runs)
  red_summary.md / .html     email body (only the NEW reds)
  GitHub Actions outputs:    red_count, new_count, csv_name
"""
import os, re, csv, io, json, sys, html
import urllib.request
from datetime import datetime, timezone

BASE = os.getenv("MOM_CSV_URL")
LEVELS = {x.strip() for x in os.getenv("ALERT_LEVELS", "Warning").split(",") if x.strip()}
STATE_DIR = os.getenv("STATE_DIR", ".alert-state")
os.makedirs(STATE_DIR, exist_ok=True)
STATE_FILE = os.path.join(STATE_DIR, "last_red.json")


def gh_output(**kv):
    p = os.getenv("GITHUB_OUTPUT")
    if not p:
        return
    with open(p, "a") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "blu-h-mom-alert/1.0"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def latest_csv_name(index_html):
    names = re.findall(r'href="(Final_Attributes_[^"]+\.csv)"', index_html)
    return sorted(names, reverse=True)[0] if names else None


def main():
    if not BASE:
        print("MOM_CSV_URL not set — skipping.")
        gh_output(red_count=0, new_count=0, csv_name="")
        return 0
    try:
        idx = fetch(BASE).decode("utf-8", "replace")
        name = latest_csv_name(idx)
        if not name:
            print("No Final_Attributes CSV found at feed.")
            gh_output(red_count=0, new_count=0, csv_name="")
            return 0
        raw = fetch(BASE + name)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("windows-1252")
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception as e:
        print(f"Feed error: {e!r} — skipping (no alert).")
        gh_output(red_count=0, new_count=0, csv_name="")
        return 0

    # collect "red" watersheds, keyed by pfaf_id
    reds = {}
    for r in rows:
        if (r.get("Alert") or "").strip() in LEVELS:
            pid = str(r.get("pfaf_id") or "").strip()
            if pid:
                reds[pid] = {
                    "pfaf_id": pid,
                    "country": (r.get("name") or "").strip(),
                    "region": (r.get("name_1") or "").strip(),
                    "alert": (r.get("Alert") or "").strip(),
                }

    # diff against previous state
    prev = set()
    if os.path.exists(STATE_FILE):
        try:
            prev = set(json.load(open(STATE_FILE)).get("red_pfaf_ids", []))
        except Exception:
            prev = set()
    new_ids = [p for p in reds if p not in prev]

    # persist current state for next run
    json.dump(
        {"csv": name, "checked": datetime.now(timezone.utc).isoformat(),
         "red_pfaf_ids": sorted(reds.keys())},
        open(STATE_FILE, "w"), indent=2,
    )

    print(f"csv={name} red={len(reds)} new={len(new_ids)}")
    gh_output(red_count=len(reds), new_count=len(new_ids), csv_name=name)

    if not new_ids:
        return 0

    # build email body for the NEW reds
    new = [reds[p] for p in new_ids]
    new.sort(key=lambda x: (x["country"], x["region"]))
    when = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    lines = [f"- **{n['country'] or '—'} / {n['region'] or '—'}** "
             f"(watershed {n['pfaf_id']}) — {n['alert']}" for n in new]
    md = (f"# 🔴 MoM Flood Alert\n\n"
          f"{len(new)} watershed(s) newly at **{'/'.join(sorted(LEVELS))}** level "
          f"(total currently red: {len(reds)}).\n\n"
          + "\n".join(lines)
          + f"\n\nSource: `{name}` · checked {when}\n"
          f"Map: https://mom-map.blu-h.org\n\n"
          f"_Automated alert. MoM is a prototype decision-support tool, "
          f"not an official emergency warning system._\n")
    open("red_summary.md", "w").write(md)
    body = "".join(
        f"<li><strong>{html.escape(n['country'] or '—')} / "
        f"{html.escape(n['region'] or '—')}</strong> "
        f"(watershed {html.escape(n['pfaf_id'])}) — {html.escape(n['alert'])}</li>"
        for n in new)
    open("red_summary.html", "w").write(
        f"<h2>🔴 MoM Flood Alert</h2>"
        f"<p>{len(new)} watershed(s) newly at <strong>{'/'.join(sorted(LEVELS))}</strong> "
        f"level (total currently red: {len(reds)}).</p><ul>{body}</ul>"
        f"<p>Source: <code>{html.escape(name)}</code> · checked {when}<br>"
        f"Map: <a href='https://mom-map.blu-h.org'>mom-map.blu-h.org</a></p>"
        f"<p style='color:#888;font-size:12px'>Automated alert. MoM is a prototype "
        f"decision-support tool, not an official emergency warning system.</p>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
