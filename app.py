import os
import json
import pandas as pd
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

_store = {}   # holds the loaded DataFrame


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


if __name__ == '__main__':
    app.run(port=5004, debug=False)
