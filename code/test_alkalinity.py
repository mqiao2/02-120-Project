"""Tests for local alkalinity: the GLODAP data file, the Alkalinity layer on the globe, and the
calculator's "Use local alkalinity" box. Run from anywhere: python3 code/test_alkalinity.py
(needs numpy; JavaScript runs in node, or jsc on macOS). If the GLODAP files are here, set
GLODAP_DIR to their folder to also check the data file against them.

  1. The data file: its grid, its range (inside what the calculator allows), and that what the
     page says about it (where data is missing, where alkalinity is high and low) is true.
  2. The maths: chem.js with an alkalinity matches ocean_chem.py; the globe's Ω grid with local
     alkalinity matches ocean_chem.py cell by cell and marks cells with no alkalinity; the smoothing
     and the drawing keep "no alkalinity data" apart from real values and from "too fresh".
  3. The page: the Alkalinity button, the box, the calculator's slider, and what the text under the
     globe says, including when the alkalinity file is slow or missing.
  4. The page itself: the elements, the striped key matching the globe, and the notes.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
import ocean_chem as oc  # noqa: E402

PUBLIC = ROOT / "public"
CHEM_JS, GLOBE_JS, HARNESS = PUBLIC / "chem.js", PUBLIC / "globe.js", ROOT / "code" / "globe_harness.js"
DATA_JSON, ALK_JSON = PUBLIC / "data" / "surface_1deg.json", PUBLIC / "data" / "alkalinity_1deg.json"
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
NLAT, NLON = 180, 360


# ---------------------------------------------------------------- 1. the data file
alk_data = json.loads(ALK_JSON.read_text(encoding="utf-8"))
surface = json.loads(DATA_JSON.read_text(encoding="utf-8"))
assert alk_data["grid"] == surface["grid"] and alk_data["unit"] == "µmol/kg", alk_data["grid"]
assert "GLODAPv2.2016b" in alk_data["source"] and "CC BY 4.0" in alk_data["source"]
A = np.array([np.nan if v is None else v for v in alk_data["alkalinity_umol_kg"]], float).reshape(NLAT, NLON)
T = np.array([np.nan if v is None else v * surface["scale"] for v in surface["temperature_c"]]).reshape(NLAT, NLON)
S = np.array([np.nan if v is None else v * surface["scale"] for v in surface["salinity_psu"]]).reshape(NLAT, NLON)
assert all(v is None or isinstance(v, int) for v in alk_data["alkalinity_umol_kg"]), "whole µmol/kg"
has = ~np.isnan(A)
assert has.sum() == 41223 and np.nanmin(A) == 1070 and np.nanmax(A) == 2636, (has.sum(), np.nanmin(A), np.nanmax(A))
assert 1000 <= np.nanmin(A) and np.nanmax(A) <= 2700, "every value fits the calculator's alkalinity slider (1000-2700)"
print(f"ok  alkalinity file: 180 x 360 like the globe's, {has.sum()} cells, {np.nanmin(A):.0f}-{np.nanmax(A):.0f} µmol/kg "
      "(inside the calculator's 1000-2700)")

lat = np.arange(-89.5, 90)
lon = np.arange(-179.5, 180)
ocean = ~np.isnan(T) | ~np.isnan(S)                       # what the globe calls ocean
gap = ocean & ~has


def region(la, lo):
    return np.ix_((lat >= la[0]) & (lat <= la[1]), (lon >= lo[0]) & (lon <= lo[1]))


def gap_share(la, lo):
    m = region(la, lo)
    return gap[m].sum() / ocean[m].sum()


# The layer's description and the page's note say where data is missing; check each claim.
shares = {name: gap_share(*box) for name, box in {
    "Hudson Bay": ((51, 65), (-95, -76)), "Gulf of Mexico": ((18, 30), (-98, -81)), "Red Sea": ((13, 28), (32, 43)),
    "Caribbean": ((9, 22), (-88, -60)), "Beaufort Sea": ((69, 76), (-160, -125)), "near the North Pole": ((84, 90), (-180, 180)),
    "Black Sea": ((41.5, 47.5), (27.5, 41.5)), "Baltic Sea": ((53.5, 65.5), (13.5, 30.5)), "Persian Gulf": ((23.5, 30.5), (47.5, 56.5)),
    "Mediterranean": ((30, 40), (-5, 36)), "Barents Sea": ((68, 80), (20, 60))}.items()}
assert shares["Hudson Bay"] == 1 and shares["Red Sea"] == 1 and shares["Gulf of Mexico"] > 0.95, shares   # "no values for", "most of"
assert 0.4 < shares["Caribbean"] < 0.6 and 0.4 < shares["Beaufort Sea"] < 0.6, shares                     # "about half"
assert 0.2 < shares["near the North Pole"] < 0.3, shares                                                    # "a quarter"
assert shares["Black Sea"] == shares["Baltic Sea"] == shares["Persian Gulf"] == 1, shares   # hardly measured: left out
assert shares["Mediterranean"] == 0 and shares["Barents Sea"] == 0, shares
assert gap.sum() == 1234, gap.sum()            # ocean (temperature or salinity) with no alkalinity
print("ok  missing data is where the page says: " + ", ".join(f"{k} {v:.0%}" for k, v in shares.items()))

med = A[region((30, 46), (-5, 36))]
assert np.nanmax(med) == np.nanmax(A) > 2600, "the highest values are in the Mediterranean"
low = np.unravel_index(np.nanargmin(A), A.shape)
assert (lat[low[0]], lon[low[1]]) == (71.5, 131.5), "the lowest value is off the Lena River delta"
subtropics = A[region((20, 30), (-60, -30))]
assert np.nanmedian(subtropics) > np.nanmedian(A) + 100, "the salty subtropics are high"
print(f"ok  the description holds: Mediterranean up to {np.nanmax(med):.0f}, lowest {np.nanmin(A):.0f} off the Lena, "
      f"subtropical Atlantic {np.nanmedian(subtropics):.0f} vs median {np.nanmedian(A):.0f}")

glodap = os.environ.get("GLODAP_DIR")
if glodap:
    from build_alkalinity_data import MASKS, apply_masks, encode, read_surface
    talk = Path(glodap) / "GLODAPv2.2016b.TAlk.nc"
    raw, inputs = read_surface(talk), np.nan_to_num(read_surface(talk, "Input_N"))
    assert encode(apply_masks(raw)) == alk_data["alkalinity_umol_kg"], "the data file is what the build script makes"
    masked = ~np.isnan(raw) & ~has
    assert masked.sum() == 121 and inputs[masked].astype(bool).sum() == 3, (masked.sum(), inputs[masked].astype(bool).sum())
    assert np.all(raw[masked] > 2200), "the masked seas were filled in with open-sea values (2200-2600), not their real ones"
    print(f"ok  the data file matches GLODAPv2.2016b.TAlk.nc at 0 m, cell by cell, except the {masked.sum()} cells of "
          f"{', '.join(MASKS)}, where only 3 cells had any measurements")
else:
    print("skip  comparison with the raw GLODAP file (set GLODAP_DIR to run it)")

# ---------------------------------------------------------------- JavaScript
runtime = shutil.which("node") and ("node", shutil.which("node")) or (Path(JSC).exists() and ("jsc", JSC)) or None
if runtime is None:
    print("skip  JavaScript checks: no node or jsc found (macOS has jsc)")
    sys.exit(0)


def run_js(body):
    kind, path = runtime
    c, g, d, a, h = (json.dumps(str(x)) for x in (CHEM_JS, GLOBE_JS, DATA_JSON, ALK_JSON, HARNESS))
    if kind == "jsc":
        setup = (f"load({c}); load({h});"
                 f" var sources = {{ globeJs: read({g}), data: JSON.parse(read({d})), alk: JSON.parse(read({a})) }};")
        show = "print(JSON.stringify(__r));"
    else:
        setup = ("const vm = require('vm'), fs = require('fs');"
                 f"vm.runInThisContext(fs.readFileSync({c}, 'utf8')); vm.runInThisContext(fs.readFileSync({h}, 'utf8'));"
                 f"var sources = {{ globeJs: fs.readFileSync({g}, 'utf8'), data: JSON.parse(fs.readFileSync({d}, 'utf8')),"
                 f" alk: JSON.parse(fs.readFileSync({a}, 'utf8')) }};")
        show = "console.log(JSON.stringify(__r));"
    done = subprocess.run([path, "-e", setup + "var __r = (function () { " + body + " })();" + show],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0 and done.stdout.strip(), f"{kind} failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- 2. the maths
points = [(co2, t, s, a) for co2 in (280, 425, 1100) for t in (-2, 10, 30) for s in (20, 33, 40) for a in (1000, 2150, 2300, 2700)]
J = run_js("""
  return %s.map(function (p) { var r = OceanChem.carbonate(p[0], p[1], p[2], p[3] * 1e-6); return [r.pH, r.omega]; })
    .concat([[OceanChem.carbonate(425, 15, 35).omega, OceanChem.carbonate(425, 15, 35, 2300e-6).omega]]);
""" % json.dumps(points))
for (co2, t, s, a), (ph, om) in zip(points, J):
    py = oc.carbonate_system(co2, t, s, alk=a * 1e-6)
    assert abs(ph - py["pH"]) < 1e-9 and abs(om - py["omega"]) / py["omega"] < 1e-9, (co2, t, s, a, ph, om, py)
assert J[-1][0] == J[-1][1], "leaving alkalinity out is the fixed 2300"
print(f"ok  chem.js with an alkalinity matches ocean_chem.py at {len(points)} points, alkalinity 1000-2700")

G = run_js("""
  var d = sources.data, n = d.temperature_c.length, api = makeEnv(sources, { canvasWidth: 240 }).api;
  function grid(list, scale) { var a = new Float32Array(n); for (var i = 0; i < n; i++) a[i] = list[i] === null ? NaN : list[i] * scale; return a; }
  var T = grid(d.temperature_c, d.scale), S = grid(d.salinity_psu, d.scale), ocean = new Float32Array(n);
  for (var i = 0; i < n; i++) ocean[i] = (T[i] === T[i] || S[i] === S[i]) ? 1 : NaN;
  var alk = api.alkalinityGrid(sources.alk.alkalinity_umol_kg, ocean);
  function out(a) { return Array.prototype.map.call(a, function (v) { return v === v ? v : null; }); }
  return { alk: out(alk), marks: [api.FRESH, api.NO_ALK],
           runs: [425, 1089].map(function (co2) { var o = api.omegaGrid(co2, T, S, OceanChem, alk);
             return { co2: co2, share: o.corrosiveShare, local: o.local, grid: out(o.grid) }; }),
           fixedShare: api.omegaGrid(1089, T, S, OceanChem).corrosiveShare };
""")
FRESH, NO_ALK = G["marks"]
assert (FRESH, NO_ALK) == (-1, -2)
got_alk = np.array([np.nan if v is None else v for v in G["alk"]]).reshape(NLAT, NLON)
assert np.array_equal(got_alk[has], A[has]) and np.all(got_alk[gap] == NO_ALK) and np.all(np.isnan(got_alk[~has & ~ocean]))
print(f"ok  the globe's alkalinity grid: GLODAP's values, {gap.sum()} ocean cells marked 'no data', land empty")
rows = np.repeat(np.arange(NLAT), NLON).reshape(NLAT, NLON)
w = np.cos(np.radians(rows - 89.5))
for run in G["runs"]:
    got = np.array([np.nan if v is None else v for v in run["grid"]]).reshape(NLAT, NLON)
    both = ~np.isnan(T) & ~np.isnan(S)
    fresh = both & (S < 20)
    noalk = both & ~fresh & ~has
    ok = both & ~fresh & has
    assert run["local"] is True and np.array_equal(np.isnan(got), ~both)
    assert np.all(got[fresh] == FRESH) and np.all(got[noalk] == NO_ALK) and noalk.sum() > 500, noalk.sum()
    want = oc.carbonate_system(run["co2"], T[ok].astype(np.float32).astype(float), S[ok].astype(np.float32).astype(float),
                               alk=A[ok] * 1e-6)["omega"]
    assert np.max(np.abs(got[ok] - want) / want) < 1e-6
    share = w[ok][want < 1].sum() / w[ok].sum()
    assert abs(run["share"] - share) < 1e-6, (run["share"], share)
    print(f"ok  at {run['co2']} ppm with local alkalinity the globe's Ω matches ocean_chem.py in all {ok.sum()} cells, "
          f"marks {noalk.sum()} without alkalinity; {share:.2%} of the ocean below Ω = 1")
assert G["runs"][1]["share"] != G["fixedShare"]

D = run_js("""
  var api = makeEnv(sources, { canvasWidth: 240 }).api, N = api.NO_ALK, F = api.FRESH;
  var g = new Float32Array(360 * 180).fill(NaN);
  function at(lat, lon) { return Math.floor(lat + 90) * 360 + Math.floor(lon + 180); }
  g[at(10.5, 0.5)] = 2300; g[at(10.5, 1.5)] = N; g[at(11.5, 0.5)] = N; g[at(11.5, 1.5)] = N;      // mostly no data
  g[at(20.5, 0.5)] = 2200; g[at(20.5, 1.5)] = 2400; g[at(21.5, 0.5)] = N; g[at(21.5, 1.5)] = 2300; // one gap: left out of the blend
  g[at(30.5, 0.5)] = F; g[at(30.5, 1.5)] = F; g[at(31.5, 0.5)] = N; g[at(31.5, 1.5)] = 2;          // fresh outweighs the gap
  g[at(40.5, 0.5)] = N; g[at(40.5, 1.5)] = N; g[at(41.5, 0.5)] = F; g[at(41.5, 1.5)] = 2;          // the gap outweighs fresh
  var picture = function (fill) {
    var grid = new Float32Array(360 * 180).fill(fill), size = 40, px = new Uint32Array(size * size), colors = {};
    api.renderGlobe(px, size, 0, 0, 1, grid, "omega");
    for (var i = 0; i < px.length; i++) if (px[i]) colors[px[i] & 0xFFFFFF] = 1;
    return Object.keys(colors).length;
  };
  return { mostlyGap: api.sampleSmooth(g, 11, 1, true), oneGap: api.sampleSmooth(g, 21, 1, true),
           freshWins: api.sampleSmooth(g, 31, 1, true), gapWins: api.sampleSmooth(g, 41, 1, true),
           stripedTones: picture(N), freshTones: picture(F), stripes: api.NO_ALK_STRIPES,
           lowColor: api.colorAt("alkalinity", 1070), highColor: api.colorAt("alkalinity", 2636),
           layer: api.LAYERS.alkalinity, fmt: api.formatValue(2287.4, api.LAYERS.alkalinity) };
""")
assert D["mostlyGap"] == NO_ALK and D["freshWins"] == FRESH and D["gapWins"] == NO_ALK, D
assert abs(D["oneGap"] - 2300) < 1e-3, "a gap next door is left out of the blend, not averaged in as -2"
assert D["stripedTones"] > D["freshTones"], "no-alkalinity cells are drawn in stripes; too-fresh cells in one gray"
assert sum(D["lowColor"]) > 600 and D["highColor"][2] > D["highColor"][0] + 60, (D["lowColor"], D["highColor"])
L = D["layer"]
assert (L["min"], L["max"], L["marked"], L["unit"]) == (2000, 2450, True, "µmol/kg") and D["fmt"] == "2287 µmol/kg", (L, D["fmt"])
assert all(L["min"] < t < L["max"] for t in L["ticks"])
print("ok  smoothing keeps 'no alkalinity data' apart from values and from 'too fresh'; it is drawn as stripes; "
      "colors run from light (low) to dark blue (high)")

# ---------------------------------------------------------------- 3. the page
# Spots to click, chosen from the data: a cell with no alkalinity whose neighbors have none either (and
# with temperature and salinity the calculator accepts); a measured cell; a brackish but usable measured cell.
def usable(i, j, need_alk):
    box = (slice(i - 1, i + 2), slice(j - 1, j + 2))
    ok_ts = np.all(~np.isnan(T[box])) and np.all((S[box] >= 21) & (S[box] <= 41)) and np.all((T[box] > -1.9) & (T[box] < 34))
    return ok_ts and (np.all(has[box]) if need_alk else np.all(gap[box]))


def find(need_alk, lat_range, lon_range, extra=lambda i, j: True):
    for i in range(NLAT):
        for j in range(NLON):
            if lat_range[0] <= lat[i] <= lat_range[1] and lon_range[0] <= lon[j] <= lon_range[1] and usable(i, j, need_alk) and extra(i, j):
                return float(lat[i]), float(lon[j])
    raise AssertionError("no spot found")


gap_spot = find(False, (18, 30), (-98, -81))                               # the Gulf of Mexico
measured_spot = find(True, (30, 40), (10, 30))                             # the Mediterranean
brackish_spot = find(True, (55, 80), (-180, 180), lambda i, j: S[i, j] < 29)
pole_note = "Polar surface water usually holds less CO₂ than the air would put in it, which makes the real Ω higher than the model's."


def view_for(spot):
    """Presses (north, east) from the home view (20 N, 160 W) to look straight at a spot."""
    return [round((spot[0] - 20) / 10), round(((spot[1] + 160) % 360) / 10)]


P = run_js("""
  var GAP = %s, MEAS = %s, BRACK = %s, VG = %s, VM = %s, VB = %s;
  function go(e, v) { for (var i = 0; i < Math.abs(v[0]); i++) e.press(v[0] > 0 ? "north" : "south"); for (var i = 0; i < v[1]; i++) e.press("east"); e.run(); }
  function msg(e) { return { text: e.pickText.textContent, est: e.pickEstimate.textContent }; }
  function page(options) { var e = makeEnv(sources, options || { canvasWidth: 240 }); e.start(); e.run(); return e; }
  var out = {};

  var a = page();
  out.buttons = { alkEnabled: !a.radio("alkalinity").disabled, noAlkHidden: a.noAlk.hidden, fetched: a.fetchUrls.slice() };
  a.pick("alkalinity"); a.run();
  out.layer = { title: a.legendTitle.textContent, desc: a.description.textContent, noAlk: a.noAlk.hidden, fresh: a.tooFresh.hidden,
                aria: a.canvas.getAttribute("aria-label"), errors: a.errors.slice() };
  go(a, VG); out.hoverGap = a.hover(GAP[0], GAP[1]);
  var m = page(); m.pick("alkalinity"); go(m, VM); out.hoverMeasured = m.hover(MEAS[0], MEAS[1]);

  var o = page(); o.pick("omega"); o.run();
  out.omegaFixed = { title: o.legendTitle.textContent, noAlk: o.noAlk.hidden };
  o.tick(true); o.run();
  out.omegaLocal = { title: o.legendTitle.textContent, desc: o.description.textContent, noAlk: o.noAlk.hidden };
  go(o, VG); out.omegaHoverGap = o.hover(GAP[0], GAP[1]);
  o.tick(false); o.run();
  out.omegaBack = { title: o.legendTitle.textContent, noAlk: o.noAlk.hidden, desc: o.description.textContent.slice(0, 40) };

  var p = page(); go(p, VM); p.tap(MEAS[0], MEAS[1]);
  out.pickUnticked = { msg: msg(p), alk: p.sliders.alk.value, alkEvents: p.sliders.alk.inputEvents };
  p.tick(true);                                                    // ticking re-sends the picked spot, with its alkalinity
  out.pickTicked = { msg: msg(p), alk: p.sliders.alk.value };
  var alkNow = Number(p.sliders.alk.value);
  p.estimate({ co2: 425, temp: Number(p.sliders.temp.value), sal: Number(p.sliders.sal.value), alk: 2300, pH: 8, omega: 3 });
  out.wrongAlkIgnored = msg(p).est;
  p.estimate({ co2: 425, temp: Number(p.sliders.temp.value), sal: Number(p.sliders.sal.value), alk: alkNow, pH: 8.1234, omega: 3.456 });
  out.rightAlkShown = msg(p).est;
  p.sliders.alk.value = 2300; p.tick(false);                       // (the page's script resets the slider first; tested below)
  out.pickUntickedAgain = { msg: msg(p), alk: p.sliders.alk.value };
  p.tick(true); p.userMoves("alk", 2000);
  out.handMoved = msg(p);

  var g = page({ canvasWidth: 240, useAlk: true }); go(g, VG); g.tap(GAP[0], GAP[1]);
  out.pickGap = { msg: msg(g), alk: g.sliders.alk.value };
  var b = page({ canvasWidth: 240, useAlk: true }); go(b, VB); b.tap(BRACK[0], BRACK[1]);
  out.pickBrackish = { msg: msg(b), alk: b.sliders.alk.value };
  var bf = page(); go(bf, VB); bf.tap(BRACK[0], BRACK[1]); out.pickBrackishFixed = msg(bf).text;

  var early = makeEnv(sources, { canvasWidth: 240, alkFetch: "manual", useAlk: true }); early.start(); early.run();
  go(early, VM); early.tap(MEAS[0], MEAS[1]);
  out.early = { before: msg(early).text, alkBefore: early.sliders.alk.value };
  early.releaseAlk(); early.run();
  out.early.after = msg(early).text; out.early.alkAfter = early.sliders.alk.value;
  var early2 = makeEnv(sources, { canvasWidth: 240, alkFetch: "manual", useAlk: true }); early2.start(); early2.run();
  go(early2, VM); early2.tap(MEAS[0], MEAS[1]); early2.sliders.alk.value = 2300; early2.tick(false); early2.releaseAlk(); early2.run();
  out.early2 = { text: msg(early2).text, alk: early2.sliders.alk.value };                   // unticked meanwhile: left alone

  var slow = makeEnv(sources, { canvasWidth: 240, alkFetch: "manual", useAlk: true }); slow.start(); slow.run();
  out.slowButton = slow.radio("alkalinity").disabled; out.slowPickRefused = slow.pick("alkalinity");
  slow.pick("omega"); slow.run(); out.slowDesc = slow.description.textContent;
  slow.releaseAlk(); slow.run();
  out.slowAfter = { desc: slow.description.textContent, title: slow.legendTitle.textContent, button: slow.radio("alkalinity").disabled, errors: slow.errors };
  var gone = makeEnv(sources, { canvasWidth: 240, alkFetch: "reject", useAlk: true }); gone.start(); gone.run();
  gone.pick("omega"); gone.run(); go(gone, VM); gone.tap(MEAS[0], MEAS[1]);
  out.gone = { button: gone.radio("alkalinity").disabled, desc: gone.description.textContent, msg: msg(gone).text, alk: gone.sliders.alk.value, errors: gone.errors };
  var bad = makeEnv(sources, { canvasWidth: 240, alkFetch: "shape" }); bad.start(); bad.run();
  out.badShape = { button: bad.radio("alkalinity").disabled, errors: bad.errors };
  var late = makeEnv(sources, { canvasWidth: 240, fetch: "manual" }); late.start(); late.releaseData(); late.run();   // alkalinity first, then the ocean data
  out.alkFirst = { button: late.radio("alkalinity").disabled, errors: late.errors };

  out.restored = (function () {                                      // a browser brings back "Alkalinity" as checked after a reload
    var env = makeEnv(sources, { canvasWidth: 240, checkedLayer: "alkalinity" }); env.start(); env.run();
    return { alkChecked: env.radio("alkalinity").checked, tempChecked: env.radio("temperature").checked, title: env.legendTitle.textContent, errors: env.errors };
  })();
  var none = makeEnv(sources, { canvasWidth: 240, noAlkControls: true }); none.start(); none.run(); go(none, VM); none.tap(MEAS[0], MEAS[1]);
  out.noControls = { msg: msg(none).text, errors: none.errors };
  return out;
""" % tuple(json.dumps(x) for x in (gap_spot, measured_spot, brackish_spot, view_for(gap_spot), view_for(measured_spot), view_for(brackish_spot))))


def cell(grid, spot):
    return grid[int(spot[0] + 89.5), int(spot[1] + 179.5)]


bt = P["buttons"]
assert bt == {"alkEnabled": True, "noAlkHidden": True, "fetched": ["/data/surface_1deg.json", "/data/alkalinity_1deg.json"]}, bt
ly = P["layer"]
assert ly["title"] == "Surface total alkalinity (µmol/kg)" and ly["noAlk"] is False and ly["fresh"] is True and ly["errors"] == [], ly
assert ly["desc"].startswith("Alkalinity is seawater's capacity to neutralize acid") and "Striped gray: no data" in ly["desc"], ly
assert ly["aria"] == "Globe colored by surface total alkalinity", ly
assert P["hoverGap"].startswith("No alkalinity data at "), P["hoverGap"]
hm = re.fullmatch(r"(\d+) µmol/kg at .*", P["hoverMeasured"])
assert hm and abs(int(hm.group(1)) - cell(A, measured_spot)) < 25, (P["hoverMeasured"], cell(A, measured_spot))
print(f"ok  the Alkalinity layer: its legend, the striped key, its description; hover reads a value ({P['hoverMeasured']}) "
      f"or 'No alkalinity data' ({gap_spot})")

assert P["omegaFixed"] == {"title": "Aragonite saturation Ω at 425 ppm CO₂", "noAlk": True}, P["omegaFixed"]
ol = P["omegaLocal"]
assert ol["title"] == "Aragonite saturation Ω at 425 ppm CO₂, GLODAP alkalinity" and ol["noAlk"] is False, ol
assert ol["desc"].startswith("At 425 ppm CO₂ with each spot's own alkalinity (GLODAP), ") and ol["desc"].endswith(
    "Gray water is too fresh for this model (salinity below 20). Striped gray: no alkalinity data, so no Ω."), ol
assert "below about 30" not in ol["desc"], "with local alkalinity, the low-salinity caveat is already in the map"
assert P["omegaHoverGap"].startswith("No alkalinity data, so no Ω at "), P["omegaHoverGap"]
assert P["omegaBack"] == {"title": "Aragonite saturation Ω at 425 ppm CO₂", "noAlk": True, "desc": "At 425 ppm CO₂, less than 0.1% of the oc"}, P["omegaBack"]
print("ok  ticking the box switches the Ω layer to measured alkalinity (title, key, description, readout); clearing it switches back")

pu = P["pickUnticked"]
assert pu["alk"] == "2300" and pu["alkEvents"] == 0 and "alkalinity" not in pu["msg"]["text"], pu
pt = P["pickTicked"]
assert abs(int(pt["alk"]) - cell(A, measured_spot)) < 25, (pt, cell(A, measured_spot))
assert f"GLODAP alkalinity there is {pt['alk']} µmol/kg." in pt["msg"]["text"], pt
assert P["wrongAlkIgnored"] == "" and P["rightAlkShown"] == "Result: pH 8.123, Ω 3.46.", (P["wrongAlkIgnored"], P["rightAlkShown"])
pa = P["pickUntickedAgain"]
assert pa["alk"] == "2300" and "alkalinity" not in pa["msg"]["text"] and pa["msg"]["text"], pa
assert P["handMoved"] == {"text": "", "est": ""}, P["handMoved"]
print(f"ok  with the box ticked, clicking a spot sets the alkalinity slider ({pt['alk']} µmol/kg in the Mediterranean); ticking "
      "after a click re-sends the spot; an estimate for another alkalinity is ignored; moving the slider by hand clears the spot")

pg = P["pickGap"]
assert pg["alk"] == "2300" and "There is no alkalinity data for this spot (striped gray on the Alkalinity map), so the calculator uses 2300 µmol/kg." in pg["msg"]["text"], pg
pb = P["pickBrackish"]
assert "Below 30 PSU" not in pb["msg"]["text"] and "GLODAP alkalinity there is" in pb["msg"]["text"] and pole_note in pb["msg"]["text"], pb
assert "Below 30 PSU the real alkalinity is probably lower" in P["pickBrackishFixed"], P["pickBrackishFixed"]
print(f"ok  a spot with no data ({gap_spot}) uses 2300 and says so; brackish water ({brackish_spot}, salinity "
      f"{cell(S, brackish_spot):.1f}) with measured alkalinity drops the 'Below 30 PSU' warning, and polar spots add the disequilibrium note")

ea = P["early"]
assert "The alkalinity data is still loading, so for now the calculator uses 2300 µmol/kg." in ea["before"] and ea["alkBefore"] == "2300", ea
assert ea["after"] == ea["before"].replace("The alkalinity data is still loading, so for now the calculator uses 2300 µmol/kg.",
                                          f"GLODAP alkalinity there is {ea['alkAfter']} µmol/kg.") and ea["alkAfter"] == pt["alk"], ea
assert "alkalinity" not in P["early2"]["text"] and P["early2"]["alk"] == "2300", P["early2"]
print("ok  a spot clicked while the alkalinity file loads says so, and gets its value when the file arrives (unless the box was cleared)")
assert P["slowButton"] is True and P["slowPickRefused"] is False
assert P["slowDesc"].endswith(" The alkalinity data is still loading, so for now this uses the fixed 2300 µmol/kg."), P["slowDesc"]
sa = P["slowAfter"]
assert sa["desc"].startswith("At 425 ppm CO₂ with each spot's own alkalinity (GLODAP)") and sa["title"].endswith(", GLODAP alkalinity"), sa
assert sa["button"] is False and sa["errors"] == [], sa
gn = P["gone"]
assert gn["button"] is True and gn["errors"] == [] and gn["alk"] == "2300", gn
assert gn["desc"].endswith(" The alkalinity data couldn't be loaded, so this uses the fixed 2300 µmol/kg."), gn
assert "The alkalinity data couldn't be loaded, so the calculator uses 2300 µmol/kg." in gn["msg"], gn
assert P["badShape"] == {"button": True, "errors": []} and P["alkFirst"] == {"button": False, "errors": []}, (P["badShape"], P["alkFirst"])
rs = P["restored"]
assert rs == {"alkChecked": False, "tempChecked": True, "title": "Sea surface temperature (°C)", "errors": []}, rs
assert P["noControls"]["errors"] == [] and "alkalinity" not in P["noControls"]["msg"], P["noControls"]
print("ok  while the alkalinity file loads, or if it fails, the button stays off and the Ω layer and calculator say they use 2300; "
      "a remembered 'Alkalinity' choice falls back to temperature; a page without the box still works")

# ---------------------------------------------------------------- 4. the page itself
page = (PUBLIC / "index.html").read_text(encoding="utf-8")
js = GLOBE_JS.read_text(encoding="utf-8")
assert '<input id="layer-alkalinity" type="radio" name="layer" value="alkalinity" disabled>' in page
assert '<label for="layer-alkalinity">Alkalinity</label>' in page
assert page.index('id="layer-omega"') < page.index('id="layer-alkalinity"') < page.index('id="layer-plain"')
assert '<input id="use-alk" type="checkbox"' in page and '<label for="use-alk">Use local alkalinity</label>' in page
assert re.search(r'<input id="alk" type="range" min="1000" max="2700" step="1" value="2300"[^>]* disabled>', page)
assert 'id="legend-no-alk" hidden' in page
stripes = json.loads(re.search(r"NO_ALK_STRIPES = (\[\[.*?\]\])", js).group(1))
want_css = "repeating-linear-gradient(45deg, #%02x%02x%02x 0 3px, #%02x%02x%02x 3px 6px)" % tuple(stripes[0] + stripes[1])
assert f".swatch-no-alk {{ background: {want_css};" in page, want_css
assert page.index(".swatch {") < page.index(".swatch-no-alk {")
alk_url = re.search(r'ALK_URL = "(/[^"]+)"', js).group(1)
assert (PUBLIC / alk_url.lstrip("/")).is_file(), alk_url
for words in ("GLODAPv2.2016b mapped climatology (Lauvset et al., 2016; CC BY 4.0)", "Hudson Bay", "Gulf of Mexico", "Red Sea",
              "half of the Caribbean and the Beaufort Sea", "a quarter of the water around the North Pole",
              "The Black Sea, the Baltic and the Persian Gulf are left out", "about 25% less CO₂", "about 12%",
              "about 0.3 too low in the Arctic", "(about 0.45)", "0.27 down to 0.23",
              "code/compare_glodap.py"):
    assert words in " ".join(page.split()), words
print("ok  the page has the Alkalinity button, the box and slider (off at 2300), the striped key matching the globe, "
      "and the notes on missing data and on polar water")

if glodap:   # the numbers in the note come from compare_glodap.py
    done = subprocess.run([sys.executable, str(ROOT / "code" / "compare_glodap.py"), "--glodap-dir", glodap],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    rows = {line[:32].strip(): line[32:].split() for line in done.stdout.splitlines() if "(" in line and line[:32].strip()}
    arctic, south, tropics = rows["Arctic (north of 66°N)"], rows["Southern Ocean (south of 60°S)"], rows["Tropics, 30°S-30°N"]
    assert arctic[1] == "(-0.33)" and arctic[3] == "(-0.45)" and arctic[4] == "0.75" and south[4] == "0.88", (arctic, south)
    assert tropics[0] == "0.27" and tropics[2] == "0.23", tropics
    print("ok  the note's numbers match code/compare_glodap.py")

# The calculator's own script (inline in index.html): run it in a tiny pretend page and work the box.
inline = re.search(r"<script>\n(.*?)</script>", page, re.S).group(1)
C = run_js("""
  var els = {}, requests = [], timers = [];
  function el(id, props) { var e = { id: id, listeners: {}, attrs: {}, value: "", disabled: false, checked: false, textContent: "", className: "",
      addEventListener: function (t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
      setAttribute: function (k, v) { this.attrs[k] = String(v); },
      fire: function (t) { (this.listeners[t] || []).forEach(function (f) { f({ target: e }); }); } };
    for (var k in props) e[k] = props[k]; els[id] = e; return e; }
  el("co2", { value: "425" }); el("temp", { value: "15" }); el("sal", { value: "35" }); el("alk", { value: "2300", disabled: true });
  ["co2-out", "temp-out", "sal-out", "alk-out", "ph", "omega", "saturation", "error"].forEach(function (id) { el(id); });
  el("use-alk");
  var document = { getElementById: function (id) { return els[id] || null; } };
  var window = { dispatchEvent: function () {} };
  function CustomEvent() {}
  function AbortController() { this.signal = {}; this.abort = function () {}; }
  function URLSearchParams() { var parts = []; this.set = function (k, v) { parts.push(k + "=" + v); }; this.toString = function () { return parts.join("&"); }; }
  function fetch(url) { requests.push(url); return new Promise(function () {}); }
  function setTimeout(f) { timers.push(f); return timers.length; }
  function clearTimeout() {}
  function flush() { var t = timers.splice(0); t.forEach(function (f) { f(); }); }
  (function () { %s })();
  var a = els.alk, out = {};
  function snap() { return { disabled: a.disabled, value: a.value, readout: els["alk-out"].textContent, aria: a.attrs["aria-valuetext"], last: requests[requests.length - 1] }; }
  out.start = snap();
  els["use-alk"].checked = true; els["use-alk"].fire("change"); flush(); out.ticked = snap();
  a.value = "2150"; a.fire("input"); flush(); out.moved = snap();
  els["use-alk"].checked = false; els["use-alk"].fire("change"); flush(); out.unticked = snap();
  return out;
""" % inline)
assert C["start"] == {"disabled": True, "value": "2300", "readout": "2300 µmol/kg (fixed)", "aria": "2300 µmol/kg (fixed)",
                      "last": "/api/ph?co2=425&temp=15&sal=35"}, C["start"]
assert C["ticked"] == {"disabled": False, "value": "2300", "readout": "2300 µmol/kg", "aria": "2300 µmol/kg",
                       "last": "/api/ph?co2=425&temp=15&sal=35&alk=2300"}, C["ticked"]
assert C["moved"]["readout"] == "2150 µmol/kg" and C["moved"]["last"].endswith("&alk=2150"), C["moved"]
assert C["unticked"] == {"disabled": True, "value": "2300", "readout": "2300 µmol/kg (fixed)", "aria": "2300 µmol/kg (fixed)",
                         "last": "/api/ph?co2=425&temp=15&sal=35"}, C["unticked"]
print("ok  the calculator's box: off, the slider is locked at '2300 µmol/kg (fixed)' and alk is not sent; ticked, it unlocks "
      "and alk is sent; cleared, it goes back to 2300 and asks again without alk")

print("\nAll tests passed.")
