"""Ocean pH estimator website: a Flask app that Vercel runs as a function.

GET /api/ph?co2=425&temp=15&sal=35 returns the surface-ocean pH and the
aragonite saturation state (omega) as JSON, along with the inputs it used.
The page with the sliders is public/index.html.

Keep app.py, requirements.txt, .python-version and public/ at the top level of
the repo: Vercel only looks for them there (code/test_app.py checks this).

Run locally: flask --app app run --port 5055
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "code"))
import ocean_chem as oc  # noqa: E402

# Allowed (min, max) for each input. The sliders in public/index.html match.
LIMITS = {"co2": (250, 1100), "temp": (-2, 35), "sal": (20, 42)}

app = Flask(__name__, static_folder=None)


def read_inputs(args):
    """Check the query-string values and return them as floats.

    Raises ValueError with a plain message if one is missing, is not a
    number, or is outside LIMITS.
    """
    values = {}
    for name, (low, high) in LIMITS.items():
        if name not in args:
            raise ValueError(f"missing '{name}'")
        try:
            value = float(args[name])
        except ValueError:
            raise ValueError(f"'{name}' must be a number") from None
        if not low <= value <= high:      # also rejects nan and inf
            raise ValueError(f"'{name}' must be between {low} and {high}")
        values[name] = value
    return values


@app.get("/api/ph")
def api_ph():
    try:
        values = read_inputs(request.args)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    result = oc.carbonate_system(values["co2"], values["temp"], values["sal"])
    return jsonify(pH=float(result["pH"]), omega=float(result["omega"]), **values)


@app.get("/")
def home():
    # On Vercel, public/index.html is served directly; this does the same locally.
    return send_from_directory(ROOT / "public", "index.html")


@app.get("/<path:filename>")
def public_file(filename):
    # Likewise for the rest of public/ (globe.js, data/...). Only files inside public/ can
    # be reached: send_from_directory refuses paths that climb out of it.
    return send_from_directory(ROOT / "public", filename)
