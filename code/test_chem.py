"""Tests for the saturation (Ω) layer on the globe: public/chem.js and the Ω parts of public/globe.js.
Run from anywhere: python3 code/test_chem.py   (needs numpy; JavaScript runs in node, or jsc on macOS)

  1. chem.js gives the same numbers as code/ocean_chem.py (the calculator's model), constant by
     constant and for pH and Ω across the calculator's whole range.
  2. The globe's Ω grid matches ocean_chem.py cell by cell for the real data, marks water too
     fresh for the model, and its "share of the ocean below Ω = 1" matches an area-weighted count.
  3. Drawing: the color scale splits at Ω = 1 (red below, neutral at 1, blue above), and the
     smoothing never blends "too fresh" cells into fake low values.
  4. The page: the layer follows the calculator's CO2, says how much ocean is corrosive, reads
     "too fresh" water correctly, and is switched off if chem.js fails to load.
"""

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
import ocean_chem as oc  # noqa: E402

PUBLIC = ROOT / "public"
CHEM_JS, GLOBE_JS = PUBLIC / "chem.js", PUBLIC / "globe.js"
DATA_JSON, HARNESS = PUBLIC / "data" / "surface_1deg.json", ROOT / "code" / "globe_harness.js"
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
runtime = shutil.which("node") and ("node", shutil.which("node")) or (Path(JSC).exists() and ("jsc", JSC)) or None
if runtime is None:
    print("skip  all checks: no node or jsc found (macOS has jsc)")
    sys.exit(0)


def run_js(body):
    """Run `body` with OceanChem, OceanGlobe (via the pretend page in globe_harness.js), `sources` and `chemSource` defined."""
    kind, path = runtime
    c, g, d, h = (json.dumps(str(x)) for x in (CHEM_JS, GLOBE_JS, DATA_JSON, HARNESS))
    if kind == "jsc":
        setup = (f"load({c}); load({h}); var chemSource = read({c});"
                 f" var sources = {{ globeJs: read({g}), data: JSON.parse(read({d})) }};")
        show = "print(JSON.stringify(__r));"
    else:
        setup = ("const vm = require('vm'), fs = require('fs');"
                 f"vm.runInThisContext(fs.readFileSync({c}, 'utf8')); vm.runInThisContext(fs.readFileSync({h}, 'utf8'));"
                 f"var chemSource = fs.readFileSync({c}, 'utf8');"
                 f"var sources = {{ globeJs: fs.readFileSync({g}, 'utf8'), data: JSON.parse(fs.readFileSync({d}, 'utf8')) }};")
        show = "console.log(JSON.stringify(__r));"
    done = subprocess.run([path, "-e", setup + "var __r = (function () { " + body + " })();" + show],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0 and done.stdout.strip(), f"{kind} failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- 1. chem.js == ocean_chem.py
points = [(co2, t, s) for co2 in (250, 280, 425, 700, 1000, 1100) for t in (-2, 0, 5, 15, 25, 35) for s in (20, 30, 35, 42)]
J = run_js("""
  var pts = %s, C = OceanChem;
  return pts.map(function (p) {
    var r = C.carbonate(p[0], p[1], p[2]);
    return [r.pH, r.omega, r.dic, r.co3, C.k0(p[1], p[2]), C.k1(p[1], p[2]), C.k2(p[1], p[2]), C.kb(p[1], p[2]), C.kw(p[1], p[2]),
            C.kspAragonite(p[1], p[2]), C.xco2ToFco2(p[0], p[1], p[2])];
  });
""" % json.dumps(points))
worst = {}
for (co2, t, s), js in zip(points, J):
    py = oc.carbonate_system(co2, t, s)
    want = [py["pH"], py["omega"], py["dic"], py["co3"], oc.k0(t, s), oc.k1(t, s), oc.k2(t, s), oc.kb(t, s), oc.kw(t, s),
            oc.ksp_aragonite(t, s), oc.xco2_to_fco2(co2, t, s)]
    for name, a, b in zip(["pH", "omega", "dic", "co3", "k0", "k1", "k2", "kb", "kw", "ksp", "fco2"], js, want):
        rel = abs(a - float(b)) / abs(float(b))
        worst[name] = max(worst.get(name, 0), rel)
assert all(v < 1e-9 for v in worst.values()), worst
print(f"ok  chem.js matches ocean_chem.py at {len(points)} points across the calculator's range "
      f"(worst relative difference {max(worst.values()):.1e}, in {max(worst, key=worst.get)})")

# ---------------------------------------------------------------- 2. the globe's Ω grid
data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
T = np.array([np.nan if v is None else v * data["scale"] for v in data["temperature_c"]], dtype=np.float32).astype(float)
S = np.array([np.nan if v is None else v * data["scale"] for v in data["salinity_psu"]], dtype=np.float32).astype(float)
G = run_js("""
  var d = sources.data, n = d.temperature_c.length;
  function grid(list) { var a = new Float32Array(n); for (var i = 0; i < n; i++) a[i] = list[i] === null ? NaN : list[i] * d.scale; return a; }
  var T = grid(d.temperature_c), S = grid(d.salinity_psu), api = makeEnv(sources, { canvasWidth: 240 }).api;
  return [425, 1089].map(function (co2) {
    var o = api.omegaGrid(co2, T, S, OceanChem);
    return { co2: o.co2, share: o.corrosiveShare, grid: Array.prototype.map.call(o.grid, function (v) { return v === v ? v : null; }) };
  }).concat([{ salMin: api.SAL_MIN }]);
""")
sal_min = G[-1]["salMin"]
assert sal_min == 20
rows = np.arange(T.size) // 360
weights = np.cos(np.radians(rows - 89.5))
for res in G[:-1]:
    got = np.array([np.nan if v is None else v for v in res["grid"]])
    has = ~np.isnan(T) & ~np.isnan(S)
    fresh = has & (S < sal_min)
    ok = has & ~fresh
    assert np.array_equal(np.isnan(got), ~has), "Ω only where there is temperature and salinity"
    assert np.all(got[fresh] == -1) and fresh.sum() == 250, "water fresher than 20 is marked -1, not given an Ω"
    want = oc.carbonate_system(res["co2"], T[ok], S[ok])["omega"]
    assert np.max(np.abs(got[ok] - want) / want) < 1e-6, np.max(np.abs(got[ok] - want) / want)   # float32 storage
    share = weights[ok][want < 1].sum() / weights[ok].sum()
    assert abs(res["share"] - share) < 1e-9, (res["share"], share)
    print(f"ok  at {res['co2']} ppm the globe's Ω matches ocean_chem.py in all {ok.sum()} cells; "
          f"{share * 100:.2f}% of the ocean surface (by area) is below Ω = 1")
assert G[0]["share"] < 0.001 < 0.2 < G[1]["share"], "today almost none, at SSP5's 2100 CO2 a large part"

# ---------------------------------------------------------------- 3. colors and smoothing
D = run_js("""
  var api = makeEnv(sources, { canvasWidth: 240 }).api, L = api.LAYERS.omega;
  var g = new Float32Array(360 * 180).fill(NaN);
  function at(lat, lon) { return Math.floor(lat + 90) * 360 + Math.floor(lon + 180); }
  g[at(10.5, 0.5)] = 2.0; g[at(10.5, 1.5)] = -1; g[at(11.5, 0.5)] = -1; g[at(11.5, 1.5)] = -1;   // 3 fresh cells, 1 ocean
  g[at(20.5, 0.5)] = 2.0; g[at(20.5, 1.5)] = 3.0; g[at(21.5, 0.5)] = -1; g[at(21.5, 1.5)] = 4.0; // 1 fresh cell
  g[at(30.5, 0.5)] = -1;                                                                         // one lone fresh cell
  return { stops: L.stops, min: L.min, max: L.max, c0: api.colorAt("omega", 0), c1: api.colorAt("omega", 1), c45: api.colorAt("omega", 4.5),
           c09: api.colorAt("omega", 0.9), c11: api.colorAt("omega", 1.1),
           mostlyFresh: api.sampleSmooth(g, 11, 1, true), someFresh: api.sampleSmooth(g, 21, 1, true),
           someFreshUnmarked: api.sampleSmooth(g, 21, 1, false), loneEdge: api.sampleSmooth(g, 30.6, 0.6, true), loneFar: api.sampleSmooth(g, 30.9, 0.9, true),
           landOnly: api.sampleSmooth(g, 50, 50, true),
           striped: (function () {                       // every other column fresh, the rest Ω 2: drawn blue, not red
             var st = new Float32Array(360 * 180); for (var i = 0; i < st.length; i++) st[i] = i % 2 ? -1 : 2.0;
             var px = new Uint32Array(9 * 9); api.renderGlobe(px, 9, 0, 0.0, 1, st, "omega");
             var c = px[4 * 9 + 4]; return [c & 255, (c >> 8) & 255, (c >> 16) & 255];
           })(),
           temperatureStillNegative: api.sampleSmooth(new Float32Array(360 * 180).fill(-1.5), 0, 0, false),
           fmt: api.formatValue(2.345, L), fmtT: api.formatValue(25.61, api.LAYERS.temperature),
           describe: [0, 0.0004, 0.0123, 0.2834].map(function (s) { return api.describeOmega({ co2: 1089.4, corrosiveShare: s }); }) };
""")
assert len(D["stops"]) == 10 and (D["max"] - D["min"]) / 9 == 0.5, "stops 0.5 apart, so the third sits at Ω = 1"
r, g_, b = D["c1"]
assert max(r, g_, b) - min(r, g_, b) <= 2, D["c1"]                          # neutral at exactly Ω = 1
assert D["c0"][0] > D["c0"][2] + 80 and D["c09"][0] > D["c09"][2], (D["c0"], D["c09"])   # red below 1
assert D["c45"][2] > D["c45"][0] + 80 and D["c11"][2] > D["c11"][0], (D["c45"], D["c11"])  # blue above 1
print("ok  Ω colors: red below 1, neutral at exactly 1, blue above, on a fixed 0-4.5 scale")
assert D["mostlyFresh"] == -1, D["mostlyFresh"]
assert abs(D["someFresh"] - 3.0) < 1e-6 and D["someFreshUnmarked"] < 2.1, (D["someFresh"], D["someFreshUnmarked"])
assert D["loneEdge"] == -1 and D["loneFar"] is None and D["landOnly"] is None, (D["loneEdge"], D["loneFar"], D["landOnly"])   # the coast rule still applies
assert D["striped"][2] > D["striped"][0] + 40, D["striped"]                  # the drawing uses the same fresh-aware blend
assert abs(D["temperatureStillNegative"] + 1.5) < 1e-6, "other layers still blend negative values (cold water)"
print("ok  smoothing: mostly-fresh spots read 'too fresh', a fresh neighbor is left out of the blend instead of dragging Ω down, "
      "and temperature below 0 still blends normally")
assert D["fmt"] == "Ω 2.35" and D["fmtT"] == "25.6 °C", (D["fmt"], D["fmtT"])
end = (" of the ocean surface has Ω below 1 (red), where seawater dissolves aragonite shells. Ω is lowest in cold polar water "
       "and highest in the warm tropics. Gray water is too fresh for this model (salinity below 20); below about 30 the real Ω is likely lower than shown.")
assert D["describe"] == ["At 1089 ppm CO₂, none" + end, "At 1089 ppm CO₂, less than 0.1%" + end,
                         "At 1089 ppm CO₂, 1.2%" + end, "At 1089 ppm CO₂, 28%" + end], D["describe"]
print("ok  the description gives the corrosive share sensibly from none to 28%")

# ---------------------------------------------------------------- 4. the page
P = run_js("""
  var out = {}, e = makeEnv(sources, { canvasWidth: 240 }); e.start(); e.run();
  out.before = { legendTooFresh: e.tooFresh.hidden, radioDisabled: e.radios[2].disabled || false };
  e.pick("omega"); e.run();
  out.omega = { title: e.legendTitle.textContent, description: e.description.textContent, tooFresh: e.tooFresh.hidden,
                center: e.center.textContent, aria: e.canvas.getAttribute("aria-label"), errors: e.errors.slice() };
  e.userMoves("co2", 1089); e.run();
  out.high = { title: e.legendTitle.textContent, description: e.description.textContent };
  out.hoverHawaii = e.hover(22.5, -158.5);
  for (var i = 0; i < 18; i++) e.press("east"); for (var i = 0; i < 2; i++) e.press("north"); e.run();   // the Caspian Sea, about 42 N 50 E
  out.caspian = e.hover(42.5, 50.5);
  e.pick("temperature"); e.run();
  out.back = { title: e.legendTitle.textContent, tooFresh: e.tooFresh.hidden, description: e.description.textContent.slice(0, 10) };
  e.userMoves("co2", 500); e.run(); out.backTitle = e.legendTitle.textContent;   // other layers ignore CO2
  return out;
""")
assert P["before"] == {"legendTooFresh": True, "radioDisabled": False}, P["before"]
om = P["omega"]
assert om["errors"] == [] and om["title"] == "Aragonite saturation Ω at 425 ppm CO₂" and om["tooFresh"] is False, om
assert om["description"].startswith("At 425 ppm CO₂, less than 0.1% of the ocean surface has Ω below 1"), om["description"]
assert om["aria"] == "Globe colored by aragonite saturation" and om["center"].startswith("Center of the view: 20.0°N, 160.0°W, Ω "), om
hi = P["high"]
assert hi["title"] == "Aragonite saturation Ω at 1089 ppm CO₂" and hi["description"].startswith("At 1089 ppm CO₂, 2"), hi
want_hawaii = oc.carbonate_system(1089, *[float(np.float32(v)) for v in (24.9, 35.1)])["omega"]   # roughly; the readout blends 4 cells
assert P["hoverHawaii"].startswith("Ω ") and abs(float(P["hoverHawaii"][2:6]) - want_hawaii) < 0.15, (P["hoverHawaii"], want_hawaii)
assert P["caspian"].startswith("Too fresh to estimate Ω at 42.5°N, 50.5°E"), P["caspian"]
assert P["back"] == {"title": "Sea surface temperature (°C)", "tooFresh": True, "description": "Warm water"}, P["back"]
assert P["backTitle"] == "Sea surface temperature (°C)"
print("ok  the Ω layer follows the calculator's CO2 (title, description, readout), reads the Caspian as too fresh, "
      "and switching back to temperature hides the gray key")

N = run_js("""
  delete this.OceanChem; var saved = OceanChem; OceanChem = undefined;
  var e = makeEnv(sources, { canvasWidth: 240 }); e.start(); e.run();
  OceanChem = saved;
  return { disabled: !!e.radios[2].disabled, errors: e.errors.slice(), status: e.status.textContent };
""")
assert N == {"disabled": True, "errors": [], "status": ""}, N
print("ok  if chem.js fails to load, the Ω option is switched off and the rest of the globe works")

page = (PUBLIC / "index.html").read_text(encoding="utf-8")
assert '<input id="layer-omega" type="radio" name="layer" value="omega">' in page and '<label for="layer-omega">Saturation (Ω)</label>' in page
assert page.index('src="/chem.js"') < page.index('src="/globe.js"'), "chem.js loads before globe.js"
assert 'id="legend-too-fresh" hidden' in page and ".swatch-fresh { background: #8c8c8c;" in page
assert page.index(".swatch {") < page.index(".swatch-fresh {"), "the gray swatch rule must come after .swatch to win"
import re  # noqa: E402
gray = re.search(r"tooFresh: \[(\d+), (\d+), (\d+)\]", GLOBE_JS.read_text(encoding="utf-8"))
assert gray and ".swatch-fresh { background: #%02x%02x%02x;" % tuple(int(x) for x in gray.groups()) in page, "the key matches the globe's gray"
print("ok  the page has the Saturation (Ω) option, loads chem.js first, and has the gray 'too fresh' key")

print("\nAll tests passed.")
