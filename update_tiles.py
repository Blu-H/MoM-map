#!/usr/bin/env python3
"""
Checks for a new Final_Attributes CSV at the MoM output server.
If found: joins with watershed shapefile, regenerates data/watersheds.pmtiles.

Usage:
    python update_tiles.py          # run indefinitely (default interval 1800s)
    python update_tiles.py --once   # run once and exit
    python update_tiles.py --interval 3600  # custom interval in seconds
"""

import argparse
import json
import os
import re
import sys
import time
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

import pandas as pd
import geopandas as gpd
import requests
from osgeo import gdal, ogr

# ── Paths ─────────────────────────────────────────────────────────────────────

load_dotenv()

REPO_DIR = Path(__file__).parent.resolve()
SHP_PATH = REPO_DIR / "data" / "watershed_shp" / "Watershed_pfaf_id.shp"
OUT_DIR = REPO_DIR / "data" / "tiles"
PMTILES_OUT = OUT_DIR / "watersheds.pmtiles"
GEOJSON_TMP = OUT_DIR / "watersheds.geojson"
METADATA = OUT_DIR / "metadata.json"

if not os.path.exists(OUT_DIR):
    os.mkdir(OUT_DIR)

# ── Config ────────────────────────────────────────────────────────────────────

_csv_url = os.getenv("MOM_CSV_URL")
if not _csv_url:
    print("ERROR: MOM_CSV_URL environment variable is not set.")
    sys.exit(1)
CSV_BASE_URL: str = _csv_url
ALERT_RANK = {"Warning": 3, "Watch": 2, "Advisory": 1, "Information": 0}
MINZOOM = 2
MAXZOOM = 6

# ── CSV discovery ─────────────────────────────────────────────────────────────


def fetch_latest_csv_info():
    max_retries = 5
    retry_delay = 2  # seconds
    r = None

    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(CSV_BASE_URL, timeout=30)
            r.raise_for_status()
            break  # Success, exit the loop
        except Exception as e:
            if attempt < max_retries:
                wait_time = retry_delay * attempt
                print(
                    f"  CSV fetch attempt {attempt} failed: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                print(f"  CSV fetch failed after {max_retries} attempts: {e}")
                raise

    # Parse response
    names = re.findall(r'href="(Final_Attributes_[^"]+\.csv)"', r.text)
    if not names:
        return None
    name = sorted(names, reverse=True)[0]
    return {"name": name, "download_url": CSV_BASE_URL + name}


def parse_date_from_filename(name):
    m = re.search(r"Final_Attributes_(\d{4})(\d{2})(\d{2})(\d{2})", name)
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:00 UTC" if m else name


# ── CSV processing ────────────────────────────────────────────────────────────


def load_csv(url):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    try:
        text = r.content.decode("utf-8")
    except UnicodeDecodeError:
        text = r.content.decode("windows-1252")
    return pd.read_csv(StringIO(text))


def process_csv(df):
    """Dedup by pfaf_id: pick highest-alert row, merge country/region names."""
    groups = {}
    for _, row in df.iterrows():
        pfaf = str(row.get("pfaf_id", "") or "")
        if pfaf:
            groups.setdefault(pfaf, []).append(row)

    records = []
    for pfaf, rows in groups.items():
        base = max(rows, key=lambda r: ALERT_RANK.get(r.get("Alert", ""), -1))
        countries = ", ".join(
            sorted({str(r["name"]) for r in rows if pd.notna(r.get("name"))})
        )
        regions = ", ".join(
            sorted({str(r["name_1"]) for r in rows if pd.notna(r.get("name_1"))})
        )
        records.append(
            {
                "pfaf_id": int(float(pfaf)),
                "alert": base.get("Alert") if pd.notna(base.get("Alert")) else None,
                "status": base.get("Status") if pd.notna(base.get("Status")) else None,
                "name": countries or None,
                "regions": regions or None,
                "days_until_peak": (
                    int(base["Days_until_peak"])
                    if pd.notna(base.get("Days_until_peak"))
                    else None
                ),
            }
        )
    return pd.DataFrame(records)


# ── PMTiles generation ────────────────────────────────────────────────────────


def regenerate_pmtiles(alert_df, csv_name):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if ogr.GetDriverByName("PMTiles") is None:
        print(
            "ERROR: GDAL PMTiles driver not available. Ensure GDAL >= 3.7 is installed."
        )
        sys.exit(1)

    print("  Loading shapefile...")
    gdf = gpd.read_file(SHP_PATH)
    gdf["pfaf_id"] = pd.to_numeric(gdf["pfaf_id"], errors="coerce").astype("Int64")
    alert_df["pfaf_id"] = alert_df["pfaf_id"].astype("Int64")

    print("  Joining alert data...")
    merged = gdf.merge(alert_df, on="pfaf_id", how="left")

    # Fix any invalid geometries before tiling
    merged.geometry = merged.geometry.buffer(0)

    print("  Writing GeoJSON...")
    merged.to_file(str(GEOJSON_TMP), driver="GeoJSON")

    tmp_out = PMTILES_OUT.with_suffix(".tmp.pmtiles")
    print(f"  Generating PMTiles (zoom {MINZOOM}–{MAXZOOM})...")
    options = gdal.VectorTranslateOptions(
        format="PMTiles",
        layerName="watersheds",
        datasetCreationOptions=[
            f"MINZOOM={MINZOOM}",
            f"MAXZOOM={MAXZOOM}",
            "SIMPLIFICATION=10",
            "SIMPLIFICATION_MAX_ZOOM=2",  # preserve more detail at max zoom
        ],
    )
    result = gdal.VectorTranslate(str(tmp_out), str(GEOJSON_TMP), options=options)
    if result is None:
        raise RuntimeError(
            "gdal.VectorTranslate failed — check GDAL error output above"
        )
    result = None  # flush/close

    Path(tmp_out).replace(PMTILES_OUT)
    GEOJSON_TMP.unlink(missing_ok=True)

    alert_levels = sorted(
        alert_df["alert"].dropna().unique().tolist(),
        key=lambda a: ALERT_RANK.get(a, -1),
        reverse=True,
    )
    METADATA.write_text(
        json.dumps(
            {
                "updated_at": parse_date_from_filename(csv_name),
                "csv": csv_name,
                "alert_levels": alert_levels,
                "generated": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )

    print(f"  Done → {PMTILES_OUT}")


# ── Main loop ─────────────────────────────────────────────────────────────────


def run_once():
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}] Checking for new CSV...")
    try:
        info = fetch_latest_csv_info()
    except Exception as e:
        print(f"  CSV fetching error: {e}")
        return

    if not info:
        print("  No CSV found.")
        return

    last = ""
    if METADATA.exists():
        try:
            last = json.loads(METADATA.read_text()).get("csv", "")
        except Exception:
            pass
    if info["name"] == last and PMTILES_OUT.exists():
        print(f'  No update (latest: {info["name"]})')
        return

    print(f'  New CSV: {info["name"]}')
    try:
        df = load_csv(info["download_url"])
        alert_df = process_csv(df)
        regenerate_pmtiles(alert_df, info["name"])
    except Exception as e:
        print(f"  Error: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Check interval in seconds (default: 1800)",
    )
    args = parser.parse_args()

    run_once()
    if not args.once:
        print(f"Watching for updates every {args.interval}s. Ctrl+C to stop.")
        while True:
            time.sleep(args.interval)
            run_once()
