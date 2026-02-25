import os
import json
import pandas as pd
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

_store = {}       # holds the loaded DataFrame
_area_store = {}  # holds the loaded GeoJSON features


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['file']
    name = (f.filename or '').lower()

    try:
        if name.endswith('.csv'):
            df = pd.read_csv(f, nrows=200_000)
        elif name.endswith(('.json', '.jsonl', '.ndjson')):
            raw = f.read().decode('utf-8')
            lines = [l for l in raw.strip().splitlines() if l.strip()]
            if lines and lines[0].strip().startswith('{'):
                records = []
                for line in lines[:200_000]:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
                df = pd.DataFrame(records)
            else:
                df = pd.read_json(raw)
                if len(df) > 200_000:
                    df = df.head(200_000)
        else:
            return jsonify({'error': f'Unsupported format. Use CSV or JSON/JSONL.'}), 400

        _store['df'] = df
        cols = list(df.columns)

        def guess(keywords):
            return next(
                (c for c in cols if any(k in c.lower() for k in keywords)),
                None
            )

        return jsonify({
            'columns': cols,
            'row_count': len(df),
            'guesses': {
                'lat': guess(['lat', 'latitude']),
                'lng': guess(['lng', 'lon', 'longitude']),
                'confidence': guess(['confidence', 'conf', 'score', 'quality', 'accuracy']),
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_data', methods=['POST'])
def get_data():
    if 'df' not in _store:
        return jsonify({'error': 'No data loaded'}), 400

    body = request.json or {}
    lat_col  = body.get('lat')
    lng_col  = body.get('lng')
    conf_col = body.get('confidence')
    extras   = [c for c in (body.get('extra_fields') or []) if c]

    df = _store['df']

    if not lat_col or lat_col not in df.columns:
        return jsonify({'error': f'Latitude column not found: {lat_col}'}), 400
    if not lng_col or lng_col not in df.columns:
        return jsonify({'error': f'Longitude column not found: {lng_col}'}), 400

    cols = [c for c in ([lat_col, lng_col, conf_col] + extras) if c and c in df.columns]
    sub = df[cols].copy()
    sub = sub.dropna(subset=[lat_col, lng_col])

    MAX_ROWS = 150_000
    truncated = len(sub) > MAX_ROWS
    if truncated:
        sub = sub.head(MAX_ROWS)

    # Auto-normalise confidence to 0-100 if needed
    if conf_col and conf_col in sub.columns:
        conf_vals = pd.to_numeric(sub[conf_col], errors='coerce')
        cmax = conf_vals.max()
        cmin = conf_vals.min()
        if cmax <= 1.0 and cmin >= 0.0:
            sub[conf_col] = conf_vals * 100
        elif cmax > 100:
            sub[conf_col] = (conf_vals - cmin) / (cmax - cmin) * 100

    records = []
    for _, row in sub.iterrows():
        try:
            x = float(row[lng_col])
            y = float(row[lat_col])
            if x != x or y != y:   # NaN check
                continue
            c = 100.0
            if conf_col and conf_col in row:
                v = row[conf_col]
                if v == v and v is not None:
                    c = float(v)
            rec = {'x': x, 'y': y, 'c': c}
            for col in extras:
                if col in row:
                    val = row[col]
                    rec[col] = None if (val != val) else val
            records.append(rec)
        except (ValueError, TypeError):
            continue

    return jsonify({
        'records': records,
        'total': len(records),
        'truncated': truncated,
    })


@app.route('/upload_areas', methods=['POST'])
def upload_areas():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['file']
    name = (f.filename or '').lower()
    try:
        if name.endswith('.csv'):
            df = pd.read_csv(f, nrows=50_000)
        else:
            return jsonify({'error': 'Unsupported format. Use CSV with a WKT geometry column.'}), 400

        cols = list(df.columns)
        _area_store['df'] = df

        wkt_keywords = ['geometry', 'wkt', 'geom', 'shape', 'polygon', 'multipolygon', 'the_geom']
        wkt_guess = next(
            (c for kw in wkt_keywords for c in cols if kw in c.lower()),
            None
        )

        return jsonify({
            'row_count': len(df),
            'columns': cols,
            'wkt_guess': wkt_guess,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_areas', methods=['POST'])
def get_areas():
    if 'df' not in _area_store:
        return jsonify({'error': 'No area data loaded'}), 400

    body = request.json or {}
    wkt_col = body.get('wkt_col')
    df = _area_store['df']

    if not wkt_col or wkt_col not in df.columns:
        return jsonify({'error': f'WKT column not found: {wkt_col}'}), 400

    try:
        from shapely import wkt as shapely_wkt
        from shapely.geometry import mapping
    except ImportError:
        return jsonify({'error': 'shapely is required. Install with: pip install shapely'}), 500

    prop_cols = [c for c in df.columns if c != wkt_col]
    valid = df.dropna(subset=[wkt_col])
    MAX = 10_000
    truncated = len(valid) > MAX
    rows = valid.head(MAX)

    features = []
    for _, row in rows.iterrows():
        try:
            geom = shapely_wkt.loads(str(row[wkt_col]))
            props = {}
            for col in prop_cols:
                val = row[col]
                props[col] = None if (val != val) else val  # NaN → None
            features.append({'type': 'Feature', 'geometry': mapping(geom), 'properties': props})
        except Exception:
            continue

    return jsonify({
        'type': 'FeatureCollection',
        'features': features,
        'truncated': truncated,
        'total': len(valid),
    })


if __name__ == '__main__':
    app.run(port=5004, debug=False)
