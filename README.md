# Place Visualiser

A browser-based geospatial visualisation tool for CSV and JSON/JSONL datasets. Upload any file with latitude/longitude columns and explore records on an interactive OpenStreetMap background, with confidence-based progressive zoom filtering and emoji icons per POI category.

## Features

- **File upload** — CSV, JSON, JSONL/NDJSON (up to 500 MB / 200 000 rows)
- **Auto-detection** — lat/lng/confidence/category columns detected from column names
- **OSM map background** — Leaflet.js with standard pan/zoom controls
- **Confidence-based zoom filtering** — records with confidence = 100 always visible; lower-confidence records revealed progressively as you zoom in
- **Emoji icons** — derived from a category field via keyword matching (~30 POI types)
- **Feature filter** — checkbox list per category value (All / None toggles)
- **Feature labels** — any column rendered as black text labels above icons, with grid-based deduplication to prevent crowding
- **Hover tooltip** — configurable fields shown on mouse-over
- **High performance** — typed arrays + viewport culling handles 100k+ records smoothly

## Quick Start

```bash
pip install flask pandas
python3 app.py
```

Then open [http://localhost:5004](http://localhost:5004) in your browser.

## Usage

1. Upload a CSV or JSON/JSONL file using the **Data Source** panel
2. Confirm or adjust the **Column Mapping** (lat, lng, confidence, category)
3. Optionally pick a **Label** field and configure **Tooltip Fields**
4. Click **Visualise** — the map zooms to fit the data
5. Use the **Feature Filter** checkboxes to show/hide categories
6. Zoom in to progressively reveal lower-confidence records

## Confidence Scoring

The zoom threshold formula is:

```
threshold = 100 / 2^((currentZoom − baseZoom) / 2)
```

Every 2 Leaflet zoom levels zoomed in, the visible confidence threshold halves. Confidence values are auto-normalised: `[0,1]` → ×100, `>100` → min-max scaled to `[0,100]`.

## File Formats

| Format | Notes |
|--------|-------|
| `.csv` | Standard comma-separated, first 200 000 rows |
| `.json` | Standard JSON array |
| `.jsonl` / `.ndjson` | Newline-delimited JSON, one object per line |

## Stack

- **Backend**: Python 3, Flask, pandas
- **Frontend**: Leaflet.js 1.9.4, HTML5 Canvas, vanilla JS
- **Port**: 5004
