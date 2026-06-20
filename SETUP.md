# MoM Map Viewer — Setup

Interactive flood alert map: watershed polygons colored by alert level, served as PMTiles, alert data fetched from the MoMOutputStream GitHub repo every 30 minutes.

Two deployment options:

| Option | Infra needed | Update mechanism |
|--------|-------------|-----------------|
| **GitHub Pages** | None (serverless) | GitHub Action (4×/day) |
| **Linux server** | Ubuntu VPS + nginx | systemd timer |

---

## Option A — GitHub Pages (serverless)

> **Requirement:** GitHub Pages for private repos requires **GitHub Pro** (personal) or **GitHub Team / Enterprise** (org). Free plans only support public repos.

### How it works

```
GitHub Action (01:30, 06:30, 13:30, 18:30 UTC)
    ↓ checks for new Final_Attributes CSV
    ↓ joins with shapefile via GDAL
    → gh-pages branch: index.html + data/watersheds.pmtiles + data/metadata.json

Browser → GitHub Pages (CDN)
    ├── /           → index.html (map.html)
    └── /data/      → watersheds.pmtiles + metadata.json
```

### Setup

**1. Enable GitHub Pages**

Repo → **Settings → Pages**:
- Source: **Deploy from a branch**
- Branch: `gh-pages` / `/ (root)`

(The `gh-pages` branch is created automatically on the first Action run.)

**2. Add the workflow**

Copy `map_viewer/update-tiles.yml` to `.github/workflows/update-tiles.yml` in the repo root. No edits needed.

**3. Trigger the first run**

**Actions → Update map tiles → Run workflow**. This generates the initial tiles and creates the `gh-pages` branch.

**4. Find your URL**

After the first deploy, **Settings → Pages** shows the public URL:
`https://<owner>.github.io/<repo>/`

---

## Option B — Linux server

### Prerequisites

- Ubuntu 22.04+ (or Debian 12+)
- The watershed shapefile at `data/watershed_shp/Watershed_pfaf_id.shp` (part of the repo)
- Port 80 open in the firewall

### Setup

```bash
cd ~/MoMProduction/map_viewer
chmod +x setup.sh
./setup.sh --url http://YOUR_IP_OR_DOMAIN
```

If `--url` is omitted, the script auto-detects the server's public IP.

The script:
1. Installs system packages (`nginx`, `git`, `wget`)
2. Installs Miniconda if not present
3. Creates the `mom-map` conda environment from `environment.yml`
4. Runs `update_tiles.py --once` to generate the initial `data/watersheds.pmtiles`
5. Installs a systemd timer that runs `update_tiles.py --once` every 30 minutes
6. Writes and enables an nginx site config (serves PMTiles + map page statically)

### After setup

```bash
# Check timer status
sudo systemctl status mom-map.timer
sudo systemctl list-timers mom-map.timer

# View update logs
sudo journalctl -u mom-map.service -f

# Trigger a manual tile update
python ~/MoMProduction/map_viewer/update_tiles.py --once
```

Logs: `/var/log/mom-map/`

### Updating

```bash
cd ~/MoMProduction && git pull
cd map_viewer && ./setup.sh --url http://YOUR_IP_OR_DOMAIN
```

### HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
```

---

## Local development (Windows)

**Step 1 — generate tiles:**

```powershell
cd map_viewer
python update_tiles.py --once
```

**Step 2 — serve the map:**

```powershell
python serve.py
```

Open `http://localhost:8080/map.html`.

> `python -m http.server` does **not** work — PMTiles requires HTTP Range requests, which Python's built-in server doesn't support. `serve.py` handles this with no extra dependencies.

**Step 3 — watch for CSV updates** (optional, checks every 30 min):

```powershell
python update_tiles.py
```

`map_viewer/data/` is gitignored — do not commit the generated files.

---

## Files

| File | Purpose |
|------|---------|
| `map.html` | Map page (served directly) |
| `update_tiles.py` | Checks GitHub for new CSV and regenerates PMTiles |
| `update-tiles.yml` | GitHub Actions workflow — copy to `.github/workflows/` |
| `serve.py` | Local dev server with Range request support |
| `environment.yml` | Conda env: gdal, geopandas, pandas, nodejs |
| `setup.sh` | One-shot Linux server setup (Option B) |
| `data/watersheds.pmtiles` | Generated — do not commit |
| `data/metadata.json` | Generated — do not commit |

---

## Troubleshooting

**Map loads but no watersheds visible** — PMTiles file missing or empty:
```bash
ls -lh map_viewer/data/watersheds.pmtiles
python map_viewer/update_tiles.py --once
```

**GitHub Action fails on GDAL / PMTiles** — conda solve failed or GDAL version mismatch; check the Action log. Re-running usually fixes transient conda errors.

**Tile update failed (Linux):**
```bash
sudo journalctl -u mom-map.service -n 50
cat /var/log/mom-map/update.log
```

**Shapefile not found:**
```bash
ls ~/MoMProduction/data/watershed_shp/Watershed_pfaf_id.shp
```
