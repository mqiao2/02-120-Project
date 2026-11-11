"""Tests for the CO2 graph: public/co2chart.js, public/data/co2_yearly.json and the page wiring.
Run from anywhere: python3 code/test_co2.py

  1. The data file: full years only, rising every year, and (when the raw Mauna Loa file is
     here) recomputed from it independently.
  2. The JavaScript, run for real (node, or jsc on macOS): the drawing maths, and the page code
     in a small pretend page: picking a year sets the calculator's CO2, clicking the graph picks
     the nearest year, a failed download says so, moving the CO2 slider by hand clears the year.
  3. The page: the graph sits beside the globe, and nothing is loaded from other websites.
"""

import csv
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
CHART_JS = PUBLIC / "co2chart.js"
DATA_JSON = PUBLIC / "data" / "co2_yearly.json"
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"

# ---------------------------------------------------------------- 1. the data file
data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
years, ppm = data["years"], data["ppm"]
assert len(years) == len(ppm) >= 60 and years == sorted(years) and years[0] == 1959 and years[-1] >= 2024, years
assert 1958 not in years and 1964 not in years, "years with missing months must be left out"
assert all(b > a for a, b in zip(ppm, ppm[1:])), "yearly CO2 at Mauna Loa has risen every year"
# NOAA's published yearly means. Ours are plain averages of the daily record and since the 1980s run
# 0.2-0.54 ppm below NOAA's (the page says so), so allow 0.6 ppm.
for year, noaa in ((1959, 315.98), (1990, 354.45), (2000, 369.71), (2024, 424.61)):
    got = ppm[years.index(year)]
    assert abs(got - noaa) < 0.6, (year, got, noaa)
print(f"ok  data file: {len(years)} full years {years[0]}-{years[-1]}, {ppm[0]} to {ppm[-1]} ppm, rising every year, close to NOAA's published means")

raw = next((p for p in (ROOT / "sources/mauna_loa_co2.csv", ROOT / "sources/mauna_loa_CO2.csv")
            if p.exists() and p.stat().st_size > 100_000), None)
if raw:
    monthly = defaultdict(list)
    with open(raw, newline="") as f:
        for row in csv.DictReader(f):
            monthly[(int(row["date"][:4]), int(row["date"][5:7]))].append(float(row["value"]))
    by_year = defaultdict(list)
    for (y, m), vals in sorted(monthly.items()):
        by_year[y].append(sum(vals) / len(vals))
    expected = {y: round(sum(v) / 12, 2) for y, v in by_year.items() if len(v) == 12}
    assert expected == dict(zip(years, ppm)), "co2_yearly.json does not match the raw Mauna Loa file"
    print(f"ok  every yearly value matches an independent recomputation from {raw.name}")
else:
    print("skip  the raw Mauna Loa file is not here")

# ---------------------------------------------------------------- 2. the JavaScript
runtime = shutil.which("node") and ("node", shutil.which("node")) or (Path(JSC).exists() and ("jsc", JSC)) or None


def run_js(body):
    """Run `body` with `chartSource` (the text of co2chart.js) and `chartData` defined; return its result."""
    kind, path = runtime
    c, d = json.dumps(str(CHART_JS)), json.dumps(str(DATA_JSON))
    if kind == "jsc":
        setup = f"var chartSource = read({c}); var chartData = JSON.parse(read({d}));"
        show = "print(JSON.stringify(__r));"
    else:
        setup = f"const fs = require('fs'); var chartSource = fs.readFileSync({c}, 'utf8'); var chartData = JSON.parse(fs.readFileSync({d}, 'utf8'));"
        show = "console.log(JSON.stringify(__r));"
    done = subprocess.run([path, "-e", setup + "var __r = (function () { " + body + " })();" + show],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and done.stdout.strip(), f"{kind} failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])


# A pretend page, just big enough for co2chart.js: the graph, the year picker, the messages and the
# calculator's CO2 slider. Everything happens at once (no real waiting).
PRETEND_PAGE = r"""
function SyncPromise(run) {
  var self = this; this.state = "pending"; this.waiters = [];
  function settle(state, value) {
    if (self.state !== "pending") return;
    if (state === "ok" && value && typeof value.then === "function") { value.then(function (v) { settle("ok", v); }, function (e) { settle("bad", e); }); return; }
    self.state = state; self.value = value; self.waiters.splice(0).forEach(function (w) { w(); });
  }
  this.then = function (ok, bad) {
    return new SyncPromise(function (resolve, reject) {
      function go() { var h = self.state === "ok" ? ok : bad; if (typeof h !== "function") { (self.state === "ok" ? resolve : reject)(self.value); return; }
                      try { resolve(h(self.value)); } catch (e) { reject(e); } }
      if (self.state === "pending") self.waiters.push(go); else go();
    });
  };
  this["catch"] = function (bad) { return this.then(undefined, bad); };
  try { run(function (v) { settle("ok", v); }, function (e) { settle("bad", e); }); } catch (e) { settle("bad", e); }
}
function makePage(options) {
  options = options || {};
  var errors = [], byId = {};
  function El(id) { this.id = id; this.listeners = {}; this.attrs = {}; this.textContent = ""; this.innerHTML = ""; this.inputEvents = 0; }
  El.prototype.addEventListener = function (t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); };
  El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
  El.prototype.getAttribute = function (k) { return this.attrs[k]; };
  El.prototype.dispatchEvent = function (ev) {
    var el = this; if (ev.type === "input") el.inputEvents++;
    (el.listeners[ev.type] || []).forEach(function (fn) { try { fn.call(el, ev); } catch (e) { errors.push(String(e)); } });
  };
  El.prototype.getBoundingClientRect = function () { return { left: 10, top: 20, width: 300, height: 170 }; };
  function add(id) { return (byId[id] = new El(id)); }
  var page = { svg: add("co2-chart"), picker: add("co2-year"), out: add("co2-year-out"), message: add("co2-pick"), status: add("co2-status"),
              estimate: add("co2-pick-estimate"), link: add("co2-pick-link"), errors: errors };
  page.link.hidden = true;
  var winListeners = {};
  page.told = [];                                                     // what the graph told the rest of the page
  var window = { addEventListener: function (t, fn) { (winListeners[t] = winListeners[t] || []).push(fn); },
                 dispatchEvent: function (ev) { if (ev.type === "co2year") page.told.push({ detail: ev.detail, co2Then: page.co2 ? page.co2.value : null }); } };
  function CustomEv(type, init) { this.type = type; this.detail = init ? init.detail : undefined; }
  page.calculatorSays = function (detail) { (winListeners.estimate || []).forEach(function (fn) { fn({ detail: detail }); }); };
  page.status.textContent = "Loading CO₂ data…"; page.picker.disabled = true;
  if (!options.noCalculator) {
    var co2 = page.co2 = add("co2"), current = "425";
    co2.min = "250"; co2.max = "1000"; co2.step = "1";
    Object.defineProperty(co2, "value", { get: function () { return current; },
      set: function (v) { var n = Math.max(250, Math.min(1000, Math.round(Number(v)))); current = String(n); } });
  }
  function Ev(type, init) { this.type = type; this.bubbles = !!(init && init.bubbles); }
  var document = { getElementById: function (id) { return byId[id] || null; } };
  function fetch() {
    var mode = options.fetch || "ok";
    if (mode === "reject") return new SyncPromise(function (res, rej) { rej(new TypeError("offline")); });
    if (mode === "404") return new SyncPromise(function (res) { res({ ok: false, status: 404 }); });
    var body = mode === "short" ? { years: [2000], ppm: [370] }
             : mode === "nan" ? { years: [2000, 2001], ppm: [370, null] }
             : mode === "unsorted" ? { years: [2001, 2000], ppm: [371, 370] } : chartData;
    return new SyncPromise(function (res) { res({ ok: true, json: function () { return new SyncPromise(function (r) { r(body); }); } }); });
  }
  var factory = new Function("document", "fetch", "Event", "window", "CustomEvent", chartSource + "\n;return Co2Chart;");
  try { page.api = factory(document, fetch, Ev, window, CustomEv); } catch (e) { page.loadError = String(e); }
  page.pick = function (i) { page.picker.value = String(i); page.picker.dispatchEvent(new Ev("input")); };
  page.clickAtYear = function (year) {        // a click on the graph above a year, in screen pixels
    var x = page.api.scales(chartData.years).x(year) / page.api.W * 300 + 10;
    page.svg.dispatchEvent({ type: "click", clientX: x, clientY: 100 });
  };
  page.press = function (key) { page.picker.dispatchEvent({ type: "keydown", key: key }); };
  page.change = function () { page.picker.dispatchEvent(new Ev("change")); };
  page.userMovesCo2 = function (v) { page.co2.value = v; page.co2.dispatchEvent(new Ev("input")); };
  return page;
}
"""

if runtime is None:
    print("skip  JavaScript checks: no node or jsc found (macOS has jsc)")
else:
    # -- the drawing maths
    m = run_js("""
      var C = (new Function(chartSource + "\\n;return Co2Chart;"))();
      var s = C.scales(chartData.years), last = chartData.years.length - 1;
      return { x0: s.x(chartData.years[0]), x1: s.x(chartData.years[last]), yPre: s.y(280), yTop: s.y(C.Y_MAX), yBottom: s.y(C.Y_MIN),
               back: s.yearAt(s.x(1990)), near1964: chartData.years[C.nearestIndex(chartData.years, 1964.2)],
               near2100: chartData.years[C.nearestIndex(chartData.years, 2100)], none: C.svgMarkup(chartData, -1),
               one: C.svgMarkup(chartData, chartData.years.indexOf(1990)), lastOne: C.svgMarkup(chartData, last),
               W: C.W, H: C.H, PAD: C.PAD };
    """)
    pad, W, H = m["PAD"], m["W"], m["H"]
    assert abs(m["x0"] - pad["left"]) < 1e-9 and abs(m["x1"] - (W - pad["right"])) < 1e-9
    assert abs(m["yTop"] - pad["top"]) < 1e-9 and abs(m["yBottom"] - (H - pad["bottom"])) < 1e-9 and m["yTop"] < m["yPre"] < m["yBottom"]
    assert abs(m["back"] - 1990) < 1e-9 and m["near1964"] in (1963, 1965) and m["near2100"] == years[-1]
    print("ok  the graph's axes map years and CO2 onto the drawing and back; a missing year picks its neighbor")
    path = re.search(r'<path class="line" d="([^"]+)"', m["none"]).group(1).split()
    pts = [tuple(map(float, p[1:].split(","))) for p in path]
    assert len(pts) == len(years) and all(b[0] > a[0] and b[1] < a[1] for a, b in zip(pts, pts[1:])), "the line should go right and up"
    assert 'class="preindustrial"' in m["none"] and "Preindustrial ≈ 280 ppm" in m["none"] and 'class="marker"' not in m["none"]
    assert 'class="marker"' in m["one"] and f"1990: {ppm[years.index(1990)]:.1f} ppm" in m["one"]
    label = re.search(r'<text class="marker-label" x="([\d.]+)"[^>]*text-anchor="(\w+)"', m["lastOne"])
    assert label.group(2) == "end", "the last year's label must sit to the left of its point, inside the graph"
    ly = float(re.search(r'<text class="marker-label"[^>]* y="([\d.]+)"', m["one"]).group(1))
    cy = float(re.search(r'<circle class="marker"[^>]* cy="([\d.]+)"', m["one"]).group(1))
    assert ly > cy + 15, "for a left-side year the label goes under the rising line, not across it"
    print(f"ok  the line has {len(pts)} points going up and to the right, a dashed preindustrial line, and a marker with its label kept inside")

    # -- the page code
    P = run_js(PRETEND_PAGE + """
      var out = {};
      var p = makePage();
      out.loaded = { status: p.status.textContent, disabled: p.picker.disabled, min: p.picker.min, max: p.picker.max, value: p.picker.value,
                     out: p.out.textContent, co2: p.co2.value, co2Events: p.co2.inputEvents, drawn: p.svg.innerHTML.length > 1000,
                     aria: p.svg.getAttribute("aria-label"), errors: p.errors.slice(), loadError: p.loadError || null };
      var i1990 = chartData.years.indexOf(1990);
      p.pick(i1990);
      out.picked = { co2: p.co2.value, co2Events: p.co2.inputEvents, message: p.message.textContent, out: p.out.textContent,
                     valuetext: p.picker.getAttribute("aria-valuetext"), marker: p.svg.innerHTML.indexOf('class="marker"') >= 0 };
      out.pickedExtra = { link: p.link.hidden, estimate: p.estimate.textContent };
      p.calculatorSays({ co2: 354, pH: 8.1234, omega: 2.345 });
      out.pickedExtra.shown = p.estimate.textContent;
      p.calculatorSays({ co2: 500, pH: 8.0, omega: 2.0 });            // not this year's CO2: ignored
      out.pickedExtra.other = p.estimate.textContent;
      p.calculatorSays({ error: true });
      out.pickedExtra.error = p.estimate.textContent;
      p.clickAtYear(2000.3);
      out.clicked = { co2: p.co2.value, picker: p.picker.value, message: p.message.textContent };
      p.userMovesCo2(600);
      out.clearedExtra = { link: p.link.hidden, estimate: p.estimate.textContent, valuetext: p.picker.getAttribute("aria-valuetext") };
      var k = makePage(); var lastIdx = String(chartData.years.length - 1);
      out.loadedValuetext = k.picker.getAttribute("aria-valuetext");
      k.press("Enter"); out.enter = { co2: k.co2.value, picker: k.picker.value };
      var c = makePage(); c.change(); out.change = { co2: c.co2.value, events: c.co2.inputEvents };
      c.change(); out.change.again = c.co2.inputEvents;                // already picked: no second event
      out.told = p.told.slice();
      out.cleared = { message: p.message.textContent, out: p.out.textContent, marker: p.svg.innerHTML.indexOf('class="marker"') >= 0, co2: p.co2.value };
      out.failures = ["reject", "404", "short", "nan", "unsorted"].map(function (mode) {
        var f = makePage({ fetch: mode }); f.pick(3);
        return { status: f.status.textContent, disabled: f.picker.disabled, co2: f.co2.value, errors: f.errors };
      });
      var n = makePage({ noCalculator: true }); n.pick(2);
      out.noCalculator = { message: n.message.textContent, errors: n.errors };
      return out;
    """)
    ld = P["loaded"]
    assert ld["loadError"] is None and ld["errors"] == [] and ld["status"] == "" and ld["disabled"] is False and ld["drawn"], ld
    assert (ld["min"], ld["max"], ld["value"]) == ("0", str(len(years) - 1), str(len(years) - 1)), ld
    assert ld["out"] == "Pick a year" and ld["co2"] == "425" and ld["co2Events"] == 0, ld          # loading changes nothing
    assert ld["aria"] == f"Graph of yearly CO₂ at Mauna Loa: {years[0]}: {ppm[0]:.1f} ppm, rising every year to {years[-1]}: {ppm[-1]:.1f} ppm.", ld["aria"]
    v1990 = ppm[years.index(1990)]
    pk = P["picked"]
    assert pk["co2"] == str(round(v1990)) and pk["co2Events"] == 1 and pk["marker"], pk
    assert pk["message"] == f"The calculator now uses {round(v1990)} ppm CO₂, the 1990 average at Mauna Loa ({v1990:.1f} ppm).", pk["message"]
    assert pk["out"] == pk["valuetext"] == f"1990: {v1990:.1f} ppm", pk
    print(f"ok  picking 1990 sets the calculator's CO2 to {round(v1990)} ppm with one 'input' event, as a drag would, and says so")
    ck = P["clicked"]
    assert ck["co2"] == str(round(ppm[years.index(2000)])) and ck["picker"] == str(years.index(2000)), ck
    px = P["pickedExtra"]
    assert px["link"] is False and px["estimate"] == "" and px["shown"] == "Result: pH 8.123, Ω 2.35." and px["other"] == px["shown"], px
    assert px["error"] == "The calculator couldn't get an estimate; pick the year again to retry.", px
    print("ok  after picking a year, the graph shows the calculator's pH and Ω and a link to the calculator")
    assert P["clearedExtra"] == {"link": True, "estimate": "", "valuetext": "No year picked"}, P["clearedExtra"]
    assert P["loadedValuetext"] == "No year picked", P["loadedValuetext"]
    assert P["enter"] == {"co2": str(round(ppm[-1])), "picker": str(len(years) - 1)}, P["enter"]
    assert P["change"] == {"co2": str(round(ppm[-1])), "events": 1, "again": 1}, P["change"]
    print("ok  Enter or a click on the thumb picks the latest year, which moving the thumb can't")
    print("ok  clicking the graph above 2000 picks 2000 and moves the year picker there")
    assert P["cleared"] == {"message": "", "out": "Pick a year", "marker": False, "co2": "600"}, P["cleared"]
    v2000 = ppm[years.index(2000)]
    assert P["told"] == [{"detail": {"year": 1990, "ppm": v1990}, "co2Then": "425"},
                         {"detail": {"year": 2000, "ppm": v2000}, "co2Then": str(round(v1990))},
                         {"detail": None, "co2Then": "600"}], P["told"]
    print("ok  moving the CO2 slider by hand clears the year")
    print("ok  the graph tells the page (the globe) each picked year before moving the CO2 slider, and null when it's cleared")
    for row in P["failures"]:
        assert row["status"] == "Couldn't load the CO₂ data. Reload the page to try again." and row["disabled"] is True, row
        assert row["co2"] == "425" and row["errors"] == [], row
    assert P["noCalculator"] == {"message": "The calculator isn't on this page.", "errors": []}, P["noCalculator"]
    print("ok  if the data fails, a message says so and the picker stays off; without a calculator it says so")

# ---------------------------------------------------------------- 3. the page
page = (PUBLIC / "index.html").read_text(encoding="utf-8")
js = CHART_JS.read_text(encoding="utf-8")
for element in ("co2-chart", "co2-year", "co2-year-out", "co2-pick", "co2-status", "co2-title"):
    assert f'id="{element}"' in page, element
assert 'id="co2-pick-estimate"' in page and re.search(r'<a id="co2-pick-link" href="#calculator" hidden>', page)
assert '<a href="#co2-title">Go to the graph</a>' in page and "0.5 ppm below NOAA" in page
explore = page[page.index('<div class="explore">'):]
assert explore.index('class="card globe-card"') < explore.index('class="card co2-card"'), "the globe comes first (left), the graph second (right)"
assert re.search(r"@media \(min-width: [\d.]+rem\) \{ \.explore \{ grid-template-columns: 1fr 1fr; max-width: none; \} \}", page), "two columns on wide screens"
assert re.search(r'<script src="/co2chart\.js" defer onerror="[^"]+"></script>', page)
W_js, H_js = (int(re.search(rf'var W = (\d+), H = (\d+);', js).group(k)) for k in (1, 2))
assert f'viewBox="0 0 {W_js} {H_js}"' in page, "the page's graph size must match co2chart.js"
assert page.index('src="/co2chart.js"') > page.index('id="co2-status"')
assert not re.search(r"https?://", page + js), "nothing should be loaded from other websites"
print("ok  the page puts the globe on the left and the CO2 graph on the right (stacked on narrow screens), and loads co2chart.js")

print("\nAll tests passed.")
