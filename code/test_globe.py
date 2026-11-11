"""Tests for the globe: public/globe.js, public/data/surface_1deg.json and the page wiring.
Run from anywhere: python3 code/test_globe.py

Four kinds of check:
  1. The data file: its shape, known values, that land and ocean are where they should be (so
     the globe cannot be flipped or mirrored), and that what the page says about the data is
     true. Compared with the raw World Ocean Atlas files too, when the real ones are here.
  2. The JavaScript maths, run for real (with node, or with jsc, the engine built into
     macOS) and compared with an independent Python version written a different way.
  3. The page code, run in a pretend web page (code/globe_harness.js): dragging, buttons,
     layers, readouts, screen-reader announcements, and what happens when the data fails.
  4. The page itself: the globe's elements exist, and it loads nothing from other websites.
"""

import csv
import html
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
GLOBE_JS = PUBLIC / "globe.js"
DATA_JSON = PUBLIC / "data" / "surface_1deg.json"
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
NLON, NLAT = 360, 180


def close(a, b, tol, name):
    assert abs(a - b) <= tol, f"{name}: got {a}, expected {b} (tol {tol})"
    print(f"ok  {name}: {a:.4g}")


# =====================================================================================
# 1. The data file
# =====================================================================================
data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
T, S, SCALE = data["temperature_c"], data["salinity_psu"], data["scale"]
assert data["grid"] == {"rows": 180, "cols": 360, "first_lat": -89.5, "first_lon": -179.5, "step": 1,
                        "order": "south to north, then west to east"}, data["grid"]
assert SCALE == 0.01 and len(T) == len(S) == NLON * NLAT
print(f"ok  data file: {NLAT} x {NLON} grid, both layers, scale {SCALE}")


def cell(layer, lat, lon):
    """Value at the cell centered on (lat, lon), e.g. (22.5, -158.5), or None."""
    v = layer[int(lat + 89.5) * NLON + int(lon + 179.5)]
    return None if v is None else v * SCALE


def valid(layer):
    return [v * SCALE for v in layer if v is not None]


t_all, s_all = valid(T), valid(S)
assert 40000 < len(t_all) < 41000 and 39700 < len(s_all) < 40600, (len(t_all), len(s_all))
assert -2.5 <= min(t_all) and max(t_all) <= 31, (min(t_all), max(t_all))
assert 0 <= min(s_all) and max(s_all) <= 41, (min(s_all), max(s_all))
print(f"ok  data file: {len(t_all)} temperature cells in {min(t_all):.1f}..{max(t_all):.1f} C, "
      f"{len(s_all)} salinity cells in {min(s_all):.1f}..{max(s_all):.1f}")

# Known values, read from the World Ocean Atlas files (cell centers)
for name, lat, lon, t, s in [("Hawaii", 22.5, -158.5, 24.91, 35.06),
                             ("Mediterranean", 35.5, 18.5, 20.35, 38.38),
                             ("Arctic, north of Norway", 80.5, -0.5, -1.62, 31.89),
                             ("equatorial Atlantic", 0.5, -30.5, 27.15, 35.96),
                             ("Southern Ocean, 60 S", -60.5, 0.5, -0.66, 34.07)]:
    close(cell(T, lat, lon), t, 0.005, f"{name}: temperature")
    close(cell(S, lat, lon), s, 0.005, f"{name}: salinity")

# Land is empty, ocean is not, and no pair of mirror images is the same: this catches a grid
# that is flipped north-south or east-west.
for name, lat, lon in [("Sahara", 25.5, 10.5), ("central Asia", 45.5, 90.5), ("Antarctic interior", -85.5, 0.5),
                       ("Germany", 50.5, 10.5), ("Siberia", 60.5, 100.5), ("Uganda", 0.5, 30.5)]:
    assert cell(T, lat, lon) is None and cell(S, lat, lon) is None, f"{name} should be land"
for name, lat, lon in [("South Atlantic, mirror of Germany", -50.5, 10.5), ("Southern Ocean, mirror of Siberia", -60.5, 100.5),
                       ("Atlantic, mirror of Uganda", 0.5, -30.5)]:
    assert cell(T, lat, lon) is not None and cell(S, lat, lon) is not None, f"{name} should be ocean"
print("ok  land and ocean are where they should be (no north-south or east-west flip)")


def band_mean(layer, lo, hi):
    vals = [v * SCALE for row in range(NLAT) if lo <= row - 89.5 < hi
            for v in layer[row * NLON:(row + 1) * NLON] if v is not None]
    return sum(vals) / len(vals)


warm, cold = band_mean(T, -10, 10), band_mean(T, 60, 90)
assert warm - cold > 20, (warm, cold)
print(f"ok  tropics ({warm:.1f} C) are much warmer than the far north ({cold:.1f} C)")

# Ocean in the Arctic that has no 0 m value but does have a 5 m or 10 m one is filled in, not left as "land"
close(cell(T, 89.5, 177.5), -1.72, 0.005, "Arctic cell with only a 10 m value: temperature")
assert cell(S, 89.5, 177.5) is not None
print("ok  ocean cells whose 0 m value is blank use the 5 m or 10 m value")


def cells(layer, lat_lo, lat_hi, lon_lo=-180, lon_hi=180):
    return [(row - 89.5, col - 179.5, v * SCALE) for row in range(NLAT) for col, v in enumerate(layer[row * NLON:(row + 1) * NLON])
            if v is not None and lat_lo <= row - 89.5 < lat_hi and lon_lo <= col - 179.5 < lon_hi]


# What the descriptions on the page say, checked against the data
hottest = max(cells(T, -90, 90), key=lambda c: c[2])
assert 28.5 < hottest[2] < 30.5 and 90 < hottest[1] < 180, hottest                 # "about 29 C, in the western Pacific"
assert min(c[2] for c in cells(T, -90, 90)) < -1.8                                 # "down to about -2 C"
mean = lambda cs: sum(c[2] for c in cs) / len(cs)
subtropics = mean(cells(S, 20, 30) + cells(S, -30, -20))
equator, subpolar = mean(cells(S, -5, 5)), mean(cells(S, 50, 70) + cells(S, -70, -50))
assert subtropics > equator + 0.5 and subtropics > subpolar + 1.5, (subtropics, equator, subpolar)   # "saltiest open water is in the subtropics"
assert max(c[2] for c in cells(S, 12, 30, 32, 45)) > 38.5                          # Red Sea "up to about 40"
assert max(c[2] for c in cells(S, 30, 38, -6, 36)) > 38                            # Mediterranean
assert cell(S, 58.5, 19.5) < 10 and mean(cells(S, 75, 90)) < 33.5                  # Baltic Sea, Arctic: "freshest"
print(f"ok  the page's wording about the data is true: warmest {hottest[2]:.1f} C at {hottest[0]}N {hottest[1]}E, "
      f"subtropics {subtropics:.1f} > equator {equator:.1f} and subpolar {subpolar:.1f} PSU, Red Sea over 38.5, Baltic under 10")

# Against the raw atlas files, when the real ones are here (on GitHub they are empty stubs).
# If they live somewhere else, set WOA_SOURCES to that folder.
SOURCES = Path(os.environ.get("WOA_SOURCES", ROOT / "sources"))
raw = {}
for layer, names in (("temperature", ("woa23_decav_t00mn01.csv", "woa23_temp.csv")),
                     ("salinity", ("woa23_decav_s00mn01.csv", "woa23_salinity.csv"))):
    for n in names:
        if (SOURCES / n).exists() and (SOURCES / n).stat().st_size > 1_000_000:
            raw[layer] = SOURCES / n
if len(raw) == 2:
    for layer, grid in (("temperature", T), ("salinity", S)):
        expected = [None] * (NLON * NLAT)
        with open(raw[layer], newline="") as f:
            for row in csv.reader(line for line in f if not line.startswith("#")):
                top = next((c.strip() for c in row[2:5] if c.strip()), "")      # 0 m, else 5 m, else 10 m
                if top:
                    i = int(float(row[0]) + 90) * NLON + int(float(row[1]) + 180)
                    expected[i] = int(round(float(top) / SCALE))
        assert expected == grid, f"{layer}: public/data/surface_1deg.json does not match {raw[layer].name}"
    print("ok  data file matches the raw World Ocean Atlas files exactly, cell by cell")
else:
    print("skip  raw World Ocean Atlas files are not on this computer (GitHub holds empty stubs)")

# The script that builds the file (needs pandas, so only where that is installed)
try:
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(ROOT / "code"))
    import build_globe_data as bgd
except ImportError:
    print("skip  build_globe_data.py checks (needs pandas)")
else:
    idx = pd.MultiIndex.from_tuples([(-89.5, -179.5), (0.5, 0.5), (89.5, 179.5), (10.5, 20.5)], names=["lat", "lon"])
    grid = bgd.to_grid(pd.Series([1.234, 2.5, np.nan, -1.8], index=idx))
    assert grid.shape == (180, 360) and grid[0, 0] == 1.234 and grid[90, 180] == 2.5 and grid[100, 200] == -1.8
    assert np.isnan(grid[179, 359]) and np.isnan(grid).sum() == 180 * 360 - 3
    enc = bgd.encode(grid)
    assert enc[0] == 123 and enc[90 * 360 + 180] == 250 and enc[100 * 360 + 200] == -180 and enc[179 * 360 + 359] is None
    print("ok  build_globe_data: cells land in the right rows and columns, values are stored x100")
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        sample = Path(folder) / "sample.csv"
        sample.write_text("#WOA23 test file\n#COMMA SEPARATED LATITUDE, LONGITUDE, AND VALUES AT DEPTHS (M):0,5,10,15,\n"
                          "10.5,20.5,2.0,3.0,4.0,5.0\n"             # has a 0 m value: use it
                          "11.5,20.5,,3.5,4.5,5.5\n"                # no 0 m: use 5 m
                          "12.5,20.5,,,4.75,5.5\n"                  # no 0 m or 5 m: use 10 m
                          "13.5,20.5,,,,5.5\n")                     # nothing in the top 10 m: no data
        series, at_surface = bgd.load_top_10m(sample)
    assert series.tolist()[:3] == [2.0, 3.5, 4.75] and np.isnan(series.iloc[3]) and at_surface == 1, (series.tolist(), at_surface)
    print("ok  build_globe_data: uses the 0 m value, else 5 m, else 10 m")

# =====================================================================================
# 2. The JavaScript maths, run for real and compared with independent Python
# =====================================================================================
runtime = shutil.which("node") and ("node", shutil.which("node")) or (Path(JSC).exists() and ("jsc", JSC)) or None


def run_js(body):
    """Load public/globe.js, run `body` (JavaScript that returns a value), give back that value."""
    script = "var __result = (function () { " + body + " })();"
    kind, path = runtime
    if kind == "jsc":
        code = f"load({json.dumps(str(GLOBE_JS))}); {script} print(JSON.stringify(__result));"
    else:
        code = ("const vm = require('vm'), fs = require('fs');"
                f"vm.runInThisContext(fs.readFileSync({json.dumps(str(GLOBE_JS))}, 'utf8'));"
                f"{script} console.log(JSON.stringify(__result));")
    done = subprocess.run([path, "-e", code], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and done.stdout.strip(), f"{kind} failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])


def ref_view_to_latlon(x, y, lat0, lon0):
    """The same question answered with rotation matrices instead of the page's formula."""
    if x * x + y * y > 1:
        return None
    z = math.sqrt(1 - x * x - y * y)
    X, Y, Z = z, x, y                                  # toward us, to the right, up
    p0, l0 = math.radians(lat0), math.radians(lon0)
    X, Z = X * math.cos(p0) - Z * math.sin(p0), X * math.sin(p0) + Z * math.cos(p0)   # undo the tilt
    X, Y = X * math.cos(l0) - Y * math.sin(l0), X * math.sin(l0) + Y * math.cos(l0)   # undo the spin
    return math.degrees(math.asin(Z)), math.degrees(math.atan2(Y, X))


def lon_gap(a, b):
    return abs((a - b + 180) % 360 - 180)


def ref_sample(values, lat, lon):
    lon = (lon + 180) % 360 - 180
    gx, gy = lon + 179.5, lat + 89.5
    x0, y0 = math.floor(gx), math.floor(gy)
    fx, fy = gx - x0, gy - y0
    total = weight = 0.0
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        v = values[min(NLAT - 1, max(0, y0 + dy)) * NLON + (x0 + dx) % NLON]
        if v is not None:
            total += w * v
            weight += w
    return total / weight if weight >= 0.5 else None


# Independent copies of the two color scales (ColorBrewer RdYlBu from cold to warm; viridis, 10 steps)
RDYLBU_COLD_TO_WARM = ["#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8", "#ffffbf",
                       "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"]
VIRIDIS_10 = ["#440154", "#482878", "#3e4a89", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6dcd59", "#b4de2c", "#fde725"]


def rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def ref_color(stops, p):
    p = min(1.0, max(0.0, p)) * (len(stops) - 1)
    k = min(int(p), len(stops) - 2)
    return [round(a + (b - a) * (p - k)) for a, b in zip(rgb(stops[k]), rgb(stops[k + 1]))]


if runtime is None:
    print("skip  JavaScript checks: no node or jsc found (macOS has jsc)")
else:
    random.seed(7)
    # -- the projection, both directions
    cases = [(random.uniform(-1.05, 1.05), random.uniform(-1.05, 1.05), random.uniform(-90, 90), random.uniform(-180, 180))
             for _ in range(400)]
    got = run_js(f"var c = {json.dumps(cases)}; return c.map(function (a) {{ return OceanGlobe.viewToLatLon(a[0], a[1], a[2], a[3]); }});")
    worst = 0.0
    for (x, y, lat0, lon0), g in zip(cases, got):
        want = ref_view_to_latlon(x, y, lat0, lon0)
        assert (want is None) == (g is None), (x, y, lat0, lon0, want, g)
        if want:
            worst = max(worst, abs(want[0] - g["lat"]), lon_gap(want[1], g["lon"]) * math.cos(math.radians(want[0])))
    assert worst < 1e-7, worst
    print(f"ok  JavaScript viewToLatLon agrees with the rotation-matrix version at 400 points (worst {worst:.1e} degrees)")

    center = run_js("return OceanGlobe.viewToLatLon(0, 0, 33.3, -120.5);")
    close(center["lat"], 33.3, 1e-9, "the middle of the view shows the chosen latitude")
    close(center["lon"], -120.5, 1e-9, "the middle of the view shows the chosen longitude")
    east, north = run_js("return [OceanGlobe.viewToLatLon(0.5, 0, 0, 0), OceanGlobe.viewToLatLon(0, 0.5, 0, 0)];")
    assert east["lon"] > 0 and abs(east["lat"]) < 1e-9 and north["lat"] > 0 and abs(north["lon"]) < 1e-9
    print("ok  to the right is east and up is north")

    pts = [(random.uniform(-89, 89), random.uniform(-180, 180), random.uniform(-80, 80), random.uniform(-180, 180)) for _ in range(300)]
    back = run_js(f"var c = {json.dumps(pts)}; return c.map(function (a) {{ var v = OceanGlobe.latLonToView(a[0], a[1], a[2], a[3]); "
                  f"var b = v.z > 0 ? OceanGlobe.viewToLatLon(v.x, v.y, a[2], a[3]) : null; return [v.z, b]; }});")
    seen = 0
    for (lat, lon, *_), (z, b) in zip(pts, back):
        if z > 0:
            seen += 1
            assert abs(b["lat"] - lat) < 1e-6 and lon_gap(b["lon"], lon) < 1e-6, (lat, lon, b)
    assert seen > 100
    print(f"ok  latLonToView and viewToLatLon undo each other ({seen} visible points)")

    # -- reading the grid
    spots = [(random.uniform(-90, 90), random.uniform(-190, 190)) for _ in range(300)]
    idx = run_js(f"var c = {json.dumps(spots)}; return c.map(function (a) {{ return OceanGlobe.cellIndex(a[0], a[1]); }});")
    for (lat, lon), i in zip(spots, idx):
        w = ((lon + 180) % 360) - 180
        assert i == min(179, max(0, math.floor(lat + 90))) * NLON + min(359, math.floor(w + 180)), (lat, lon, i)
    print("ok  cellIndex finds the right 1-degree cell, including past 180 degrees and at the poles")

    grid = [None if random.random() < 0.35 else random.uniform(-2, 30) for _ in range(NLON * NLAT)]
    for k in range(0, NLON * NLAT, 997):                # make some wholly empty and some wholly full areas too
        grid[k] = None
    spots = [(random.uniform(-90, 90), random.uniform(-180, 180)) for _ in range(600)] + \
            [(89.9, 179.9), (-89.9, -179.9), (0.0, 180.0), (0.0, -180.0), (45.0, 179.99), (45.0, -179.99)]
    smooth = run_js(f"var g = new Float32Array({json.dumps(grid)}.map(function (v) {{ return v === null ? NaN : v; }})); "
                    f"var c = {json.dumps(spots)}; return c.map(function (a) {{ var v = OceanGlobe.sampleSmooth(g, a[0], a[1]); return v === v ? v : null; }});")
    none = 0
    for (lat, lon), g in zip(spots, smooth):
        want = ref_sample(grid, lat, lon)
        assert (want is None) == (g is None), (lat, lon, want, g)
        if want is None:
            none += 1
        else:
            assert abs(want - g) < 1e-3, (lat, lon, want, g)
    assert 20 < none < len(spots) - 20
    print(f"ok  sampleSmooth matches an independent blend at {len(spots)} spots ({none} with too little data)")

    # -- colors
    layers = run_js("return OceanGlobe.LAYERS;")
    assert layers["temperature"]["stops"] == RDYLBU_COLD_TO_WARM and layers["salinity"]["stops"] == VIRIDIS_10
    assert (layers["temperature"]["min"], layers["temperature"]["max"]) == (-2, 30)
    assert (layers["salinity"]["min"], layers["salinity"]["max"]) == (31, 38)
    print("ok  color scales are ColorBrewer RdYlBu (cold blue to warm red) and viridis (fresh purple to salty yellow)")
    for name, stops in (("temperature", RDYLBU_COLD_TO_WARM), ("salinity", VIRIDIS_10)):
        lo, hi = layers[name]["min"], layers[name]["max"]
        values = [lo - 5, lo, hi, hi + 5] + [random.uniform(lo, hi) for _ in range(60)]
        got = run_js(f"var v = {json.dumps(values)}; return v.map(function (x) {{ return OceanGlobe.colorAt({json.dumps(name)}, x); }});")
        for v, g in zip(values, got):
            want = ref_color(stops, (v - lo) / (hi - lo))
            assert max(abs(a - b) for a, b in zip(want, g)) <= 1, (name, v, want, g)
        assert got[1] == rgb(stops[0]) and got[2] == rgb(stops[-1]) and got[0] == got[1] and got[3] == got[2]
    print("ok  colorAt blends between the stops like the independent version, and clamps outside the range")

    # -- the picture itself
    pic = run_js("""
      var size = 64, out = new Uint32Array(size * size), warm = new Float32Array(360 * 180);
      for (var i = 0; i < warm.length; i++) warm[i] = 15;
      OceanGlobe.renderGlobe(out, size, 20, -160, 1, warm, "temperature");
      var inside = 0; for (var i = 0; i < out.length; i++) if (out[i] !== 0) inside++;
      var none = new Float32Array(360 * 180); for (var i = 0; i < none.length; i++) none[i] = NaN;
      var out2 = new Uint32Array(size * size); OceanGlobe.renderGlobe(out2, size, 20, -160, 1, none, "temperature");
      var out3 = new Uint32Array(size * size); OceanGlobe.renderGlobe(out3, size, 20, -160, 1, warm, null);
      var latGrid = new Float32Array(360 * 180); for (var r = 0; r < 180; r++) for (var c = 0; c < 360; c++) latGrid[r * 360 + c] = r - 89.5;
      var out4 = new Uint32Array(size * size); OceanGlobe.renderGlobe(out4, size, 0, 0, 1, latGrid, "temperature");
      function px(a, x, y) { var v = a[y * size + x]; return [v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255]; }
      return { inside: inside, size: size, corner: out[0], center: px(out, 32, 32), edgeish: px(out, 32, 4),
               land: px(out2, 32, 32), plain: px(out3, 32, 32), north: px(out4, 32, 10), south: px(out4, 32, 54),
               landColor: OceanGlobe.LAND, plainColor: OceanGlobe.PLAIN_OCEAN,
               tempNorth: OceanGlobe.colorAt("temperature", 22), tempSouth: OceanGlobe.colorAt("temperature", -22) };""")
    expected_inside = math.pi * (0.94 * 32) ** 2
    assert abs(pic["inside"] - expected_inside) / expected_inside < 0.03, (pic["inside"], expected_inside)
    assert pic["corner"] == 0
    want15 = ref_color(RDYLBU_COLD_TO_WARM, (15 + 2) / 32)
    assert max(abs(a - b) for a, b in zip(want15, pic["center"][:3])) <= 2 and pic["center"][3] == 255, (want15, pic["center"])
    assert all(c < w for c, w in zip(pic["edgeish"][:3], pic["center"][:3]) if w > 20), "the edge should be shaded darker"
    assert max(abs(a - b) for a, b in zip(pic["land"][:3], pic["landColor"])) <= 2
    assert max(abs(a - b) for a, b in zip(pic["plain"][:3], pic["plainColor"])) <= 2
    assert pic["north"][0] > pic["south"][0], "a latitude grid should read higher (warmer, redder) toward the top"
    print(f"ok  renderGlobe draws a disc ({pic['inside']} pixels), colors it from the data, shades the edge, "
          "and puts north at the top")

    labels = run_js("return [OceanGlobe.formatLat(22.54), OceanGlobe.formatLat(-0.04), OceanGlobe.formatLat(-33.26), "
                    "OceanGlobe.formatLon(-158.46), OceanGlobe.formatLon(190), OceanGlobe.formatLon(180)];")
    assert labels == ["22.5°N", "0.0°N", "33.3°S", "158.5°W", "170.0°W", "180.0°W"], labels
    print("ok  latitude and longitude labels")

    values = run_js("var t = OceanGlobe.LAYERS.temperature, s = OceanGlobe.LAYERS.salinity; "
                    "return [OceanGlobe.formatValue(24.91, t), OceanGlobe.formatValue(-0.02, t), OceanGlobe.formatValue(-1.62, t), "
                    "OceanGlobe.formatValue(35.056, s), t.minLabel, t.maxLabel, s.minLabel, s.maxLabel];")
    assert values == ["24.9 °C", "0.0 °C", "-1.6 °C", "35.06 PSU", "≤ −2", "30", "≤ 31", "≥ 38"], values
    print("ok  values are shown with their units, never as -0.0, and the legend ends say 'at most' and 'at least'")

# =====================================================================================
# 3. The page code, run in a pretend web page
# =====================================================================================
HARNESS = ROOT / "code" / "globe_harness.js"


def run_page(body):
    """Run `body` (JavaScript that can use makeEnv(sources, options) and returns something JSON-able)."""
    kind, path = runtime
    h, g, d = (json.dumps(str(x)) for x in (HARNESS, GLOBE_JS, DATA_JSON))
    if kind == "jsc":
        setup = f"load({h}); var sources = {{ globeJs: read({g}), data: JSON.parse(read({d})) }};"
        show = "print(JSON.stringify(__result));"
    else:
        setup = ("const vm = require('vm'), fs = require('fs');"
                 f"vm.runInThisContext(fs.readFileSync({h}, 'utf8'));"
                 f"var sources = {{ globeJs: fs.readFileSync({g}, 'utf8'), data: JSON.parse(fs.readFileSync({d}, 'utf8')) }};")
        show = "console.log(JSON.stringify(__result));"
    done = subprocess.run([path, "-e", setup + "var __result = (function () { " + body + " })();" + show],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0 and done.stdout.strip(), f"{kind} failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])


PAGE_SCENARIOS = r"""
var out = {};
function loaded(options) { var env = makeEnv(sources, options || { canvasWidth: 240 }); env.start(); env.run(); return env; }
function middle(env) { var r = env.canvas.rect; return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }
function drag(env, dx, dy) {                       // press, move slowly, wait, let go: a drag with no coasting
  var m = middle(env);
  env.pointer("pointerdown", m.x, m.y); env.advance(300);
  env.pointer("pointermove", m.x + dx, m.y + dy); env.advance(300);
  env.pointer("pointerup", m.x + dx, m.y + dy); env.run();
  return env.view();
}

// canvas sizes, including 300 device pixels, which is also the size a new canvas starts at
out.sizes = [[300, 1], [301, 1], [246, 1], [374, 1], [502, 2], [150, 2], [240, 1.25], [200, 1.5]].map(function (c) {
  var env = makeEnv(sources, { canvasWidth: c[0], dpr: c[1] }); env.start(); env.run();
  return { css: c[0], dpr: c[1], width: env.canvas.width, height: env.canvas.height, drawn: env.drawImageCalls.length,
           errors: env.errors, loadError: env.loadError || null };
});

// the data does not arrive, or is wrong
out.failures = ["reject", "404", "badjson", "shape", "short"].map(function (mode) {
  var env = makeEnv(sources, { fetch: mode, canvasWidth: 240 }); env.start();
  env.press("west"); env.pick("salinity"); env.advance(500); env.run();
  return { mode: mode, status: env.status.textContent, hidden: env.status.hidden, errors: env.errors, drawn: env.drawImageCalls.length };
});

// nothing is drawn before the data arrives; the loading message goes when it does
var slow = makeEnv(sources, { fetch: "manual", canvasWidth: 240 }); slow.start();
var early = { status: slow.status.textContent, hidden: slow.status.hidden, drawn: slow.drawImageCalls.length };
slow.press("east"); slow.pick("plain"); slow.run();
var early2 = { drawn: slow.drawImageCalls.length, errors: slow.errors, legendHidden: slow.legend.hidden };
slow.releaseData(); slow.run();
out.slow = { early: early, early2: early2, status: slow.status.textContent, hidden: slow.status.hidden, drawn: slow.drawImageCalls.length, errors: slow.errors };

// dragging
out.dragRight = drag(loaded(), 60, 0);
out.dragUp = drag(loaded(), 0, -60);
out.dragFarUp = drag(loaded(), 0, -5000);
out.dragFarDown = drag(loaded(), 0, 5000);
out.dragFarLeft = drag(loaded(), -4000, 0);
var afterDrag = loaded(); drag(afterDrag, 60, 0);
out.readoutAfterDrag = afterDrag.readout.textContent;

// pointer input that should not turn the globe
(function () {
  var a = loaded(), m = middle(a);
  a.pointer("pointerdown", m.x, m.y, { button: 2 }); a.pointer("pointermove", m.x + 80, m.y, { buttons: 2 });
  a.pointer("pointerup", m.x + 80, m.y, { button: 2 }); a.run(); out.rightButton = a.view();
  var b = loaded(); b.pointer("pointerdown", m.x, m.y, { ctrlKey: true }); b.pointer("pointermove", m.x + 80, m.y);
  b.pointer("pointerup", m.x + 80, m.y); b.run(); out.ctrlClick = b.view();
  var c = loaded(); c.pointer("pointerdown", m.x, m.y);
  c.pointer("pointerdown", m.x + 10, m.y, { pointerId: 2, pointerType: "touch" }); c.advance(300);
  c.pointer("pointermove", m.x + 80, m.y, { pointerId: 2, pointerType: "touch" });
  c.pointer("pointerup", m.x + 80, m.y, { pointerId: 2, pointerType: "touch" }); c.run(); out.secondPointer = c.view();
  var d = loaded(); d.pointer("pointerdown", m.x, m.y); d.advance(300);
  d.pointer("pointermove", m.x + 80, m.y, { buttons: 0 }); d.run(); out.releasedElsewhere = d.view();
  var e = loaded({ canvasWidth: 240, captureThrows: true }); out.captureThrows = { view: drag(e, 60, 0), errors: e.errors };
})();

// a tap reads the value; a small wobble is still a tap
(function () {
  var a = loaded(), h = a.spot(22.5, -158.5);
  a.pointer("pointerdown", h.x, h.y); a.pointer("pointerup", h.x, h.y); out.tap = a.readout.textContent;
  var b = loaded(); b.pointer("pointerdown", h.x, h.y); b.pointer("pointermove", h.x + 2, h.y + 1); b.pointer("pointerup", h.x + 2, h.y + 1);
  out.wobble = b.readout.textContent;
})();

// coasting after a flick
function flick(options) {
  var f = loaded(options), m = middle(f);
  f.pointer("pointerdown", m.x, m.y);
  for (var i = 1; i <= 5; i++) { f.advance(8); f.pointer("pointermove", m.x + 12 * i, m.y); }
  f.pointer("pointerup", m.x + 60, m.y);
  return f;
}
(function () {
  var a = flick(); var ra = a.run(); out.flick = { frames: ra.frames, pending: ra.stillPending, view: a.view(), errors: a.errors };
  var b = flick({ canvasWidth: 240, reduceMotion: true }); var rb = b.run(); out.flickReduced = { frames: rb.frames, view: b.view() };
  var c = flick(); c.frame(16, -60); var base = c.view(); c.frame(16); out.negativeTime = { base: base, after: c.view() };
})();

// the buttons
(function () {
  var b = loaded();
  b.press("west"); b.run(); var west = b.view();
  b.press("east"); b.press("east"); b.run(); var east = b.view();
  b.press("north"); b.run(); var north = b.view();
  for (var i = 0; i < 10; i++) b.press("north"); b.run(); var northCap = b.view();
  for (var i = 0; i < 25; i++) b.press("south"); b.run(); var southCap = b.view();
  b.press("zoom-in"); b.press("zoom-in"); b.run(); var zoomed = b.zoom();
  b.press("reset"); b.run();
  out.buttons = { west: west, east: east, north: north, northCap: northCap, southCap: southCap, zoomed: zoomed,
                  reset: b.view(), resetZoom: b.zoom(), errors: b.errors };
  var z = loaded(); for (var i = 0; i < 8; i++) z.press("zoom-in"); z.run(); var most = z.zoom();
  for (var i = 0; i < 20; i++) z.press("zoom-out"); z.run(); out.zoom = { most: most, least: z.zoom() };
})();

// what a screen reader is told
(function () {
  var a = loaded();
  a.press("east"); a.press("east"); a.press("east"); var before = a.announceWrites; a.advance(500);
  var first = a.announce.textContent, writes = a.announceWrites;
  a.pick("salinity"); a.advance(500);
  a.press("zoom-in"); a.press("zoom-in"); a.press("zoom-in"); a.advance(500);
  out.announce = { before: before, writes: writes, first: first, afterLayer: null, zoomed: a.announce.textContent };
  var l = loaded(); l.pick("salinity"); l.advance(500); out.announce.afterLayer = l.announce.textContent;
  var q = loaded(); out.announce.atLoad = q.announce.textContent;
})();

// layers
(function () {
  var l = loaded(); l.hover(22.5, -158.5);
  l.pick("salinity"); l.run();
  out.salinity = { aria: l.canvas.getAttribute("aria-label"), title: l.legendTitle.textContent,
                   ticks: l.legendTicks.children.map(function (c) { return c.textContent; }),
                   legendHidden: l.legend.hidden, desc: l.description.textContent, readout: l.readout.textContent,
                   bar: l.legendBar.style.background.slice(0, 80) };
  l.pick("plain"); l.run();
  out.plain = { aria: l.canvas.getAttribute("aria-label"), legendHidden: l.legend.hidden, desc: l.description.textContent,
                center: l.center.textContent };
  l.pick("temperature"); l.run();
  out.temperature = { aria: l.canvas.getAttribute("aria-label"), title: l.legendTitle.textContent,
                      ticks: l.legendTicks.children.map(function (c) { return c.textContent; }), legendHidden: l.legend.hidden,
                      desc: l.description.textContent, center: l.center.textContent, errors: l.errors };
})();

// readouts
(function () {
  var r = loaded();
  out.readTemperature = r.hover(22.5, -158.5);
  r.pick("salinity"); r.run(); out.readSalinity = r.hover(22.5, -158.5);
  r.pick("plain"); r.run(); out.readPlain = r.hover(22.5, -158.5); out.readPlainLand = r.hover(36.5, -121.5);
  var m = r.canvas.rect; r.pointer("pointermove", m.left + 1, m.top + 1, { buttons: 0 }); out.readOutside = r.readout.textContent;
  r.pointer("pointerleave", m.left + 1, m.top + 1, { buttons: 0 }); out.readLeave = r.readout.textContent;
  var s = loaded(); for (var i = 0; i < 17; i++) s.press("east"); s.run();
  out.saharaView = s.view(); out.saharaCenter = s.center.textContent; out.readLand = s.hover(20, 10);
})();

// the mouse wheel
(function () {
  var w = loaded();
  var plain = w.wheel(-100, { ctrlKey: false }); w.run(); var z0 = w.zoom();
  var ctrl = w.wheel(-100, { ctrlKey: true }); w.run(); var z1 = w.zoom();
  w.wheel(-3, { ctrlKey: true, deltaMode: 1 }); w.run(); var z2 = w.zoom();
  w.wheel(-5000, { ctrlKey: true }); w.run(); var z3 = w.zoom();
  w.wheel(5000, { ctrlKey: true }); w.run(); var z4 = w.zoom();
  out.wheel = { plainPrevented: plain.defaultPrevented, ctrlPrevented: ctrl.defaultPrevented, z0: z0, z1: z1, z2: z2, z3: z3, z4: z4 };
})();

// no key handling on the globe itself (so the browser's own shortcuts are never taken over)
out.canvasListeners = Object.keys(loaded().canvas.listeners).sort();

// drawing is batched: many moves in one animation frame make one draw
(function () {
  var b = loaded(), m = middle(b);
  b.pointer("pointerdown", m.x, m.y); var before = b.drawImageCalls.length;
  for (var i = 1; i <= 30; i++) b.pointer("pointermove", m.x + i * 2, m.y);
  b.frame(16); out.batch = b.drawImageCalls.length - before;
})();

// unusual browsers
(function () {
  var a = makeEnv(sources, { noContext: true }); a.start(); a.run();
  out.noContext = { status: a.status.textContent, hidden: a.status.hidden, errors: a.errors, loadError: a.loadError || null, drawn: a.drawImageCalls.length };
  var b = makeEnv(sources, { noResizeObserver: true, canvasWidth: 240 }); b.start(); b.run();
  out.noResizeObserver = { listener: !!(b.windowListeners && b.windowListeners.resize), errors: b.errors, drawn: b.drawImageCalls.length };
  var c = loaded(); c.canvas.clientWidth = 400; c.canvas.rect = { left: 100, top: 50, width: 400, height: 400 };
  c.resizeObserver.callback([{}]); c.run(); out.resize = { width: c.canvas.width, height: c.canvas.height, errors: c.errors };
})();

// clicking the globe sends the spot to the calculator
function arcsPerDraw(env) { var n = env.arcs; env.resizeObserver.callback([{}]); env.frame(0); return env.arcs - n; }   // one draw's circles
function msg(env) { return { text: env.pickText.textContent, est: env.pickEstimate.textContent, linkHidden: env.pickLink.hidden }; }
(function () {
  var plainDraw = arcsPerDraw(loaded());
  var a = loaded(), sl = a.sliders, start = { co2: sl.co2.value, temp: sl.temp.value, sal: sl.sal.value };
  a.tap(22.5, -158.5); a.run();
  var hawaii = { co2: sl.co2.value, temp: sl.temp.value, sal: sl.sal.value, tempEvents: sl.temp.inputEvents, salEvents: sl.sal.inputEvents,
                 co2Events: sl.co2.inputEvents, msg: msg(a), errors: a.errors.slice() };
  var marker = arcsPerDraw(a);
  a.estimate({ co2: 425, temp: 24.9, sal: 35.1, pH: 8.0312, omega: 3.4567 }); var e1 = msg(a);
  a.userMoves("co2", 800); a.estimate({ co2: 800, temp: 24.9, sal: 35.1, pH: 7.7999, omega: 2.128 }); var e2 = msg(a);
  var ringAfterCo2 = arcsPerDraw(a);
  a.estimate({ error: true }); var e3 = msg(a);
  out.pickHawaii = { start: start, hawaii: hawaii, plainDraw: plainDraw, markerDraw: marker, e1: e1, e2: e2, e3: e3, ringAfterCo2: ringAfterCo2 };
  for (var i = 0; i < 18; i++) a.press("east"); a.run();
  out.pickFarSide = arcsPerDraw(a);
  for (var i = 0; i < 18; i++) a.press("west"); a.run();
  a.userMoves("temp", 10);
  out.pickCleared = { msg: msg(a), ring: arcsPerDraw(a) };
  var b = loaded(); b.tap(22.5, -158.5);
  b.estimate({ co2: 425, temp: 20, sal: 35.1, pH: 7.9, omega: 1.1 });
  out.pickOtherInputs = msg(b);
})();

(function () {
  var a = loaded(), sl = a.sliders;
  for (var i = 0; i < 17; i++) a.press("east"); a.run();                              // the Sahara
  a.useCenter.dispatch("click", {});
  out.pickLand = { temp: sl.temp.value, sal: sl.sal.value, events: sl.temp.inputEvents + sl.sal.inputEvents, msg: msg(a) };
  var c = loaded(); c.tap(22.5, -158.5); c.run();
  for (var i = 0; i < 17; i++) c.press("east"); c.run();
  c.useCenter.dispatch("click", {}); var landMsg = msg(c);
  c.estimate({ co2: 425, temp: 24.9, sal: 35.1, pH: 8, omega: 3 });
  out.pickLandThenEstimate = { before: landMsg, after: msg(c), temp: c.sliders.temp.value };
})();

(function () {
  var a = loaded(), sl = a.sliders;
  for (var i = 0; i < 18; i++) a.press("east"); for (var i = 0; i < 4; i++) a.press("north"); a.run();       // the Baltic Sea, 60 N 20 E
  a.useCenter.dispatch("click", {});
  out.pickBaltic = { temp: sl.temp.value, sal: sl.sal.value, events: sl.temp.inputEvents + sl.sal.inputEvents, msg: msg(a) };
  /*LOWSPOT*/
  var w = loaded(), ws = w.sliders;
  for (var i = 0; i < LOW[0]; i++) w.press("north"); for (var i = 0; i < LOW[1]; i++) w.press("east"); w.run();
  w.useCenter.dispatch("click", {});
  out.pickLowSalinity = { view: w.view(), temp: ws.temp.value, sal: ws.sal.value, msg: msg(w) };
})();

(function () {
  var edited = JSON.parse(JSON.stringify(sources.data)); edited.salinity_psu[112 * 360 + 21] = null;             // Hawaii loses its salinity
  var a = makeEnv({ globeJs: sources.globeJs, data: edited }, { canvasWidth: 240 }); a.start(); a.run();
  a.tap(22.5, -158.5);
  out.pickOneMissing = { temp: a.sliders.temp.value, sal: a.sliders.sal.value, events: a.sliders.temp.inputEvents + a.sliders.sal.inputEvents, msg: msg(a) };
  var n = loaded({ canvasWidth: 240, noCalculator: true }); n.tap(22.5, -158.5);
  out.pickNoCalculator = { msg: msg(n), errors: n.errors };
  var slow = makeEnv(sources, { fetch: "manual", canvasWidth: 240 }); slow.start(); slow.useCenter.dispatch("click", {});
  out.pickNotLoaded = slow.pickText.textContent;
  var failed = makeEnv(sources, { fetch: "reject", canvasWidth: 240 }); failed.start(); failed.useCenter.dispatch("click", {});
  out.pickLoadFailed = failed.pickText.textContent;
  var d = loaded(), m = middle(d); drag(d, 60, 0);
  d.pointer("pointerdown", m.x, m.y, { button: 2 }); d.pointer("pointerup", m.x, m.y, { button: 2 }); d.hover(20, -190);
  d.pointer("pointerdown", m.x, m.y); d.pointer("pointercancel", m.x, m.y);
  out.pickNotFromDragHoverRightClickOrCancel = { events: d.sliders.temp.inputEvents + d.sliders.sal.inputEvents + d.sliders.co2.inputEvents, text: d.pickText.textContent };
})();
return out;
"""

if runtime is None:
    print("skip  page-code checks: no node or jsc found (macOS has jsc)")
else:
    Tf = [None if v is None else v * SCALE for v in T]
    Sf = [None if v is None else v * SCALE for v in S]
    low_spot = next((la, lo) for la in (70, 80, 60) for lo in range(-180, 180, 10)
                    if ref_sample(Sf, la, lo) is not None and ref_sample(Tf, la, lo) is not None and 21 <= ref_sample(Sf, la, lo) <= 29)
    presses = ((low_spot[0] - 20) // 10, ((low_spot[1] + 160) % 360) // 10)
    page_run = run_page(PAGE_SCENARIOS.replace("/*LOWSPOT*/", f"var LOW = [{presses[0]}, {presses[1]}];"))
    P = page_run

    def near(view, lat, lon, tol=0.15):
        assert view is not None and abs(view["lat"] - lat) <= tol and lon_gap(view["lon"], lon) <= tol, (view, lat, lon)

    # the globe is drawn at the right size, whatever the screen: 300 device pixels used to crash it
    for row in P["sizes"]:
        full = max(200, int(row["css"] * min(row["dpr"], 2) + 0.5))
        assert row["loadError"] is None and row["errors"] == [], row
        assert row["width"] == row["height"] == full and row["drawn"] >= 1, (row, full)
    print("ok  the globe draws without errors, on a square canvas, at every size (including exactly 300 device pixels)")

    for row in P["failures"]:
        assert row["status"] == "Couldn't load the ocean data. Reload the page to try again." and row["hidden"] is False, row
        assert row["errors"] == [] and row["drawn"] == 0, row
    print("ok  if the data is missing, broken or the wrong shape, a message says so and nothing else breaks")

    slow = P["slow"]
    assert slow["early"] == {"status": "Loading ocean data…", "hidden": False, "drawn": 0}, slow["early"]
    assert slow["early2"]["drawn"] == 0 and slow["early2"]["errors"] == [] and slow["early2"]["legendHidden"] is True, slow["early2"]
    assert slow["status"] == "" and slow["hidden"] is True and slow["drawn"] > 0 and slow["errors"] == [], slow
    print("ok  nothing is drawn before the data arrives (buttons still work); the loading message goes when it does")

    # dragging: a drag of dx pixels turns the globe dx / radius radians, to the west when dragged right
    per_pixel = math.degrees(1 / (0.94 * 240 / 2))
    near(P["dragRight"], 20, -160 - 60 * per_pixel)
    near(P["dragUp"], 20 - 60 * per_pixel, -160)
    assert P["dragFarUp"]["lat"] == -90.0 and P["dragFarDown"]["lat"] == 90.0, (P["dragFarUp"], P["dragFarDown"])
    assert -180 <= P["dragFarLeft"]["lon"] < 180
    assert P["readoutAfterDrag"] == "Hover for a value. Click or tap a spot to use it in the calculator."
    print(f"ok  dragging right turns the globe west and dragging up turns it south ({per_pixel:.3f} degrees per pixel), "
          "stopping at the poles and wrapping around the dateline")

    for key in ("rightButton", "ctrlClick", "secondPointer", "releasedElsewhere"):
        near(P[key], 20, -160)
    assert P["captureThrows"]["errors"] == []
    near(P["captureThrows"]["view"], 20, -160 - 60 * per_pixel)                    # still drags if capturing the pointer fails
    print("ok  right-clicks, ctrl-clicks, a second finger and a button let go elsewhere do not turn the globe")

    assert P["tap"] == "24.9 °C at 22.5°N, 158.5°W", P["tap"]
    assert re.fullmatch(r"-?[\d.]+ °C at [\d.]+°N, [\d.]+°W", P["wobble"]), P["wobble"]
    print("ok  tapping reads the value there; a wobble of a pixel or two is still a tap")

    assert P["flick"]["pending"] == 0 and P["flick"]["frames"] < 1500 and P["flick"]["errors"] == []
    assert 0 < P["flick"]["view"]["lon"] < 169.4, P["flick"]               # coasted on past a plain drag (169.5 E)
    assert P["flickReduced"]["frames"] <= 6, P["flickReduced"]
    near(P["flickReduced"]["view"], 20, -160 - 60 * per_pixel)                    # exactly where the finger left it
    moved = (P["negativeTime"]["after"]["lon"] - P["negativeTime"]["base"]["lon"] + 540) % 360 - 180   # shortest signed turn, across the dateline too
    assert moved <= 0.05, P["negativeTime"]                                      # coasting after a drag to the right never turns back east
    print(f"ok  a flick coasts and always stops ({P['flick']['frames']} frames); reduced motion skips it; time never runs backwards")

    b = P["buttons"]
    near(b["west"], 20, -170); near(b["east"], 20, -150); near(b["north"], 30, -150)
    assert b["northCap"]["lat"] == 90.0 and b["southCap"]["lat"] == -90.0 and b["errors"] == []
    assert abs(b["zoomed"] - 1.5625) < 0.01 and b["resetZoom"] == 1.0, b
    near(b["reset"], 20, -160)
    assert abs(P["zoom"]["most"] - 4.0) < 0.01 and abs(P["zoom"]["least"] - 1.0) < 0.01, P["zoom"]
    print("ok  the turn buttons move the view 10 degrees (stopping at the poles), zoom stays between 1 and 4, reset goes home")

    a = P["announce"]
    assert a["atLoad"] == "" and a["before"] == 0 and a["writes"] == 1, a             # one announcement, a moment after the last press
    assert re.fullmatch(r"Sea surface temperature\. Center of the view: 20\.0°N, 130\.0°W, [\d.-]+ °C\.", a["first"]), a["first"]
    assert a["afterLayer"].startswith("Sea surface salinity. Center of the view: 20.0°N, 160.0°W, ") and a["afterLayer"].endswith(" PSU."), a["afterLayer"]
    assert "Zoom 2.0 times." in a["zoomed"] or "Zoom 1.9 times." in a["zoomed"], a["zoomed"]
    print("ok  screen-reader announcements: one, after the last button press, naming the layer, the center and its value")

    layers_js = run_js("return OceanGlobe.LAYERS;")
    sal, plain, temp = P["salinity"], P["plain"], P["temperature"]
    assert sal["aria"] == "Globe colored by sea surface salinity" and sal["title"] == "Sea surface salinity (PSU)", sal
    assert sal["ticks"] == ["≤ 31", "33", "35", "≥ 38"] and sal["legendHidden"] is False and sal["desc"] == layers_js["salinity"]["description"], sal
    assert sal["readout"] == "Hover for a value. Click or tap a spot to use it in the calculator." and sal["bar"].startswith("linear-gradient(to right, #440154"), sal
    assert plain["legendHidden"] is True and plain["aria"].startswith("Globe colored by nothing") and plain["center"].endswith(", ocean"), plain
    assert temp["aria"] == "Globe colored by sea surface temperature" and temp["ticks"] == ["≤ −2", "10", "20", "30"], temp
    assert temp["desc"] == layers_js["temperature"]["description"] and temp["legendHidden"] is False and temp["errors"] == [], temp
    print("ok  each layer sets the canvas label, legend, text description and readout")

    assert P["readTemperature"] == "24.9 °C at 22.5°N, 158.5°W", P["readTemperature"]
    assert P["readSalinity"] == "35.06 PSU at 22.5°N, 158.5°W", P["readSalinity"]
    assert P["readPlain"] == "Ocean at 22.5°N, 158.5°W" and P["readPlainLand"].startswith("Land or no data at "), (P["readPlain"], P["readPlainLand"])
    assert P["readOutside"] == "Hover for a value. Click or tap a spot to use it in the calculator." == P["readLeave"]
    near(P["saharaView"], 20, 10)
    assert P["saharaCenter"] == "Center of the view: 20.0°N, 10.0°E, land or no data" and P["readLand"] == "Land or no data at 20.0°N, 10.0°E"
    print("ok  readouts: value and unit, ocean, 'land or no data' (the legend's own words), and the hint off the globe")

    w = P["wheel"]
    assert w["plainPrevented"] is False and w["ctrlPrevented"] is True and w["z0"] == 1.0, w
    assert abs(w["z1"] - 1.25) < 0.01 and abs(w["z2"] - 1.25 * 1.25 ** 0.99) < 0.01 and abs(w["z3"] - w["z2"] * 1.25) < 0.02 and w["z4"] < w["z3"], w
    print("ok  ctrl + scroll zooms one step per notch in any unit; plain scrolling is left alone")

    assert "keydown" not in P["canvasListeners"], P["canvasListeners"]
    print(f"ok  the globe takes no keyboard shortcuts (it listens for: {', '.join(P['canvasListeners'])})")

    assert P["batch"] == 1, P["batch"]
    print("ok  thirty pointer moves in one animation frame cost one draw")

    nc, nr, rs = P["noContext"], P["noResizeObserver"], P["resize"]
    assert nc["status"] == "Your browser can't draw the globe." and nc["hidden"] is False and nc["errors"] == [] and nc["loadError"] is None and nc["drawn"] == 0, nc
    assert nr["listener"] is True and nr["errors"] == [] and nr["drawn"] >= 1, nr
    assert rs["width"] == rs["height"] == 400 and rs["errors"] == [], rs
    print("ok  without a canvas context there is a message; without ResizeObserver it still resizes; resizing redraws")


    # clicking the globe sends the spot to the calculator
    k = P["pickHawaii"]; h = k["hawaii"]
    assert k["start"] == {"co2": "425", "temp": "15", "sal": "35"}, k["start"]
    assert (h["temp"], h["sal"], h["co2"]) == ("24.9", "35.1", "425"), h               # the data at Hawaii; carbon dioxide untouched
    assert (h["tempEvents"], h["salEvents"], h["co2Events"]) == (1, 1, 0) and h["errors"] == [], h   # one 'input' event each, as for a drag
    base = "The calculator now uses 24.9 °C and 35.1 PSU from 22.5°N, 158.5°W (CO₂ unchanged)."
    assert h["msg"] == {"text": base, "est": "", "linkHidden": False}, h["msg"]
    assert k["markerDraw"] == k["plainDraw"] + 2, (k["markerDraw"], k["plainDraw"])    # a ring (two circles) is drawn on the spot
    assert k["e1"] == {"text": base, "est": "At 425 ppm CO₂: pH 8.031, Ω 3.46.", "linkHidden": False}, k["e1"]
    assert k["e2"]["est"] == "At 800 ppm CO₂: pH 7.800, Ω 2.13." and k["e2"]["text"] == base, k["e2"]   # follows the CO2 slider
    assert k["ringAfterCo2"] == k["plainDraw"] + 2
    assert k["e3"]["est"] == "The calculator couldn't get an estimate; click the spot again to retry.", k["e3"]
    assert P["pickFarSide"] == k["plainDraw"], "the ring should not show on the far side of the globe"
    assert P["pickCleared"] == {"msg": {"text": "", "est": "", "linkHidden": True}, "ring": k["plainDraw"]}, P["pickCleared"]
    assert P["pickOtherInputs"] == {"text": base, "est": "", "linkHidden": False}, P["pickOtherInputs"]
    print("ok  clicking sets temperature and salinity to the data there (CO₂ untouched), tells the calculator as a drag would, "
          "draws a ring, follows the estimate (also when CO₂ moves, or fails), and clears itself if you move a slider")

    ld = P["pickLand"]
    assert (ld["temp"], ld["sal"], ld["events"]) == ("15", "35", 0) and ld["msg"]["linkHidden"] is True, ld
    assert ld["msg"]["text"] == "Land or no data at 20.0°N, 10.0°E, so the calculator was not changed.", ld
    lt = P["pickLandThenEstimate"]
    assert lt["before"] == lt["after"] and lt["after"]["est"] == "" and lt["temp"] == "24.9", lt   # a late estimate does not rewrite it
    om = P["pickOneMissing"]
    assert (om["temp"], om["sal"], om["events"]) == ("15", "35", 0), om
    assert om["msg"]["text"] == "No salinity data at 22.5°N, 158.5°W, so the calculator was not changed.", om
    assert P["pickNoCalculator"]["msg"]["text"] == "The calculator isn't on this page." and P["pickNoCalculator"]["errors"] == []
    assert P["pickNotLoaded"] == "The ocean data hasn't loaded yet."
    assert P["pickLoadFailed"] == "The ocean data couldn't be loaded, so the calculator was not changed. Reload the page to try again."
    assert P["pickNotFromDragHoverRightClickOrCancel"] == {"events": 0, "text": ""}, P["pickNotFromDragHoverRightClickOrCancel"]
    print("ok  land, a missing layer, a missing calculator and missing data change nothing and say why; "
          "dragging, hovering, right-clicking and a cancelled touch never change the calculator")

    bs = ref_sample(Sf, 60.0, 20.0)
    bal = P["pickBaltic"]
    assert bs < 20 and (bal["temp"], bal["sal"], bal["events"]) == ("15", "35", 0), (bs, bal)
    assert bal["msg"]["text"] == f"Salinity at 60.0°N, 20.0°E is {bs:.2f} PSU, outside this calculator's range (20 to 42 PSU), so the calculator was not changed.", bal
    lw = P["pickLowSalinity"]; ls_, lt_ = ref_sample(Sf, *low_spot), ref_sample(Tf, *low_spot)
    assert abs(float(lw["sal"]) - ls_) <= 0.06 and abs(float(lw["temp"]) - lt_) <= 0.06, (lw, ls_, lt_)
    assert "Below 30 PSU the real alkalinity is probably lower than the model's 2300 µmol/kg" in lw["msg"]["text"], lw
    print(f"ok  brackish water ({bs:.1f} PSU in the Baltic) leaves the calculator alone; low-salinity Arctic water "
          f"({ls_:.1f} PSU at {low_spot[0]}N {low_spot[1]}E) is used with a what-if warning")

# =====================================================================================
# 4. The page itself
# =====================================================================================
page = (PUBLIC / "index.html").read_text(encoding="utf-8")
js = GLOBE_JS.read_text(encoding="utf-8")
for element in ("globe", "globe-status", "globe-readout", "globe-center", "globe-description", "globe-announce",
                "globe-use-center", "globe-pick", "globe-pick-link", "calculator", "temp", "sal", "co2",
                "globe-legend", "legend-title", "legend-bar", "legend-ticks", "globe-west", "globe-east", "globe-north",
                "globe-south", "globe-zoom-in", "globe-zoom-out", "globe-reset",
                "layer-temperature", "layer-salinity", "layer-plain"):
    assert f'id="{element}"' in page, f"index.html has no element with id {element}"
canvas_tag = re.search(r'<canvas id="globe".*?>', page, re.S).group(0)
assert 'role="img"' in canvas_tag and 'aria-describedby="globe-description"' in canvas_tag and "tabindex" not in canvas_tag, canvas_tag
assert 'name="layer"' in page and "<noscript>" in page
tag = re.search(r'<script src="/globe\.js" defer[^>]*></script>', page)
assert tag and "onerror=" in tag.group(0), "globe.js needs a script tag with an onerror message"
assert page.index(tag.group(0)) > page.index('id="globe-status"'), "the script tag must come after the globe section (its onerror looks for it)"
if runtime:                                           # the message shown if globe.js cannot be loaded at all
    handler = html.unescape(re.search(r'onerror="([^"]*)"', tag.group(0)).group(1))
    shown = run_js("var status = { hidden: true, textContent: '' }; "
                   "var document = { getElementById: function (id) { return id === 'globe-status' ? status : null; } }; "
                   f"(function () {{ {handler} }})(); return status;")
    assert shown == {"hidden": False, "textContent": "The globe could not be loaded. Reload the page to try again."}, shown
    print("ok  if globe.js cannot be loaded, the page's own onerror message appears")
for key in ('getElementById("globe")', "pointerdown", "pointermove"):
    assert key in js, key
assert "keydown" not in js, "the globe should not take keyboard shortcuts"
print("ok  the page has the globe (a labelled image, not a focus trap), the layer buttons, the turn and zoom buttons, "
      "the legend, a no-JavaScript message and a load-failure message")

assert not re.search(r"https?://", page + js), "the page should not load anything from other websites"
print("ok  nothing is loaded from other websites")

# The globe finds the calculator's sliders by id and reads their limits from the page; the page must announce each estimate
assert re.search(r'<input id="temp" type="range" min="-2" max="35" step="0\.1"', page), "the temperature slider must step by 0.1"
assert re.search(r'<input id="sal" type="range" min="20" max="42" step="0\.1"', page), "the salinity slider must step by 0.1"
assert 'id="calculator"' in page and 'href="#calculator"' in page and 'id="globe-title"' in page and 'href="#globe-title"' in page
assert 'new CustomEvent("estimate", {detail: data})' in page, "the calculator must announce each estimate to the globe"
assert 'new CustomEvent("estimate", {detail: {error: true}})' in page, "the calculator must tell the globe when an estimate fails"
assert 'id="globe-pick-estimate"' in page and not re.search(r'id="globe-pick-estimate"[^>]*role=', page), "the estimate must not be a second live region"
assert 'window.addEventListener("estimate"' in js and 'new Event("input", { bubbles: true })' in js
print("ok  the calculator's sliders step by 0.1 (so a clicked value fits), it announces each estimate, and the link to it works")

# Every local file the page asks for exists, with exactly the right capital letters (Vercel's servers care; a Mac does not)
on_disk = {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob("*") if p.is_file()}
assert not any(p.is_symlink() for p in PUBLIC.rglob("*")), "no symlinks in public/"
data_url = re.search(r'DATA_URL = "(/[^"]+)"', js).group(1)
asked = {data_url.lstrip("/")} | {u.lstrip("/") for u in re.findall(r'(?:src|href)="(/[^"]+)"', page)}
assert asked <= on_disk, (asked - on_disk, on_disk)
print(f"ok  every file the page asks for exists in public/ with the exact name: {', '.join(sorted(asked))}")

print("\nAll tests passed.")
