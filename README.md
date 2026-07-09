# MoM Map Viewer — Setup

Interactive flood alert map: watershed polygons colored by alert level, served as PMTiles, alert data fetched in real time.

### Setup

yml workflow is regularly updating the data

### Local development (Windows)

Steps 1-3 are only needed if you want to generate tiles locally.

1. Set up venv calling .\setup.ps1
2. Create .env file with MOM_CSV_URL=...
3. Generate tiles: 
```powershell
python update_tiles.py
```

4. Serve the map:
```powershell
python serve.py
```

Open `http://localhost:8080/index.html`.

> `python -m http.server` doesn't work — PMTiles requires HTTP Range requests, which Python's built-in server doesn't support. `serve.py` handles this with no extra dependencies.
