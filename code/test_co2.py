"""Tests for the CO2 graph: public/co2chart.js, public/data/co2_yearly.json and the page wiring.
Run from anywhere: python3 code/test_co2.py

  1. The data file: full years only, rising every year, and (when the raw Mauna Loa file is
     here) recomputed from it independently.
  2. The JavaScript, run for real (node, or jsc on macOS): the drawing maths, and the page code
     in a small pretend page: picking a year sets the calculator's CO2, clicking the graph picks
     the nearest year, a failed download says so, moving the CO2 slider by hand clears the year.
  3. The page: the graph sits beside the globe, and nothing is loaded from other websites.
  Also the future pathways (public/data/ssp_co2.json): checked against the source CSV, drawn to
  2100 with the picked one highlighted, colored green (lowest) to red (highest).
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
SSP_JSON = PUBLIC / "data" / "ssp_co2.json"
SSP_CSV = ROOT / "atmospheric-concentrations-of-carbon-dioxide.filtered" / "atmospheric-concentrations-of-carbon-dioxide.csv"
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

# ---------------------------------------------------------------- 1b. the future pathways file
ssp = json.loads(SSP_JSON.read_text(encoding="utf-8"))
assert [p["id"] for p in ssp["pathways"]] == ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"], ssp["pathways"]
assert all(p["years"] == [2005, 2010] + list(range(2020, 2101, 10)) for p in ssp["pathways"])
end = {p["id"]: p["ppm"][-1] for p in ssp["pathways"]}
assert end == {"SSP1": 608.35, "SSP2": 789.85, "SSP3": 834.34, "SSP4": 718.37, "SSP5": 1088.97}, end
assert all(b > a for p in ssp["pathways"] for a, b in zip(p["ppm"], p["ppm"][1:])), "every baseline pathway keeps rising"
assert "baseline" in ssp["source"].lower() and "Riahi" in ssp["source"]
if SSP_CSV.exists():
    by = defaultdict(dict)
    with open(SSP_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by[row["Entity"].split(" ")[0]][int(row["Year"])] = round(float(row["CO2 concentration - Region: global"]), 2)
    assert {p["id"]: dict(zip(p["years"], p["ppm"])) for p in ssp["pathways"]} == dict(by), "ssp_co2.json does not match the source CSV"
    print("ok  pathways file: SSP1-SSP5, 2005-2100, matches the source CSV; 2100 ranges from 608 (SSP1) to 1089 ppm (SSP5)")
else:
    print("skip  the source SSP CSV is not here")
RANK_LOW_TO_HIGH = sorted(end, key=end.get)            # SSP1, SSP4, SSP2, SSP3, SSP5

# ---------------------------------------------------------------- 2. the JavaScript
runtime = shutil.which("node") and ("node", shutil.which("node")) or (Path(JSC).exists() and ("jsc", JSC)) or None


def run_js(body):
    """Run `body` with `chartSource` (the text of co2chart.js) and `chartData` defined; return its result."""
    kind, path = runtime
    c, d, e = json.dumps(str(CHART_JS)), json.dumps(str(DATA_JSON)), json.dumps(str(SSP_JSON))
    if kind == "jsc":
        setup = f"var chartSource = read({c}); var chartData = JSON.parse(read({d})); var sspData = JSON.parse(read({e}));"
        show = "print(JSON.stringify(__r));"
    else:
        setup = (f"const fs = require('fs'); var chartSource = fs.readFileSync({c}, 'utf8'); var chartData = JSON.parse(fs.readFileSync({d}, 'utf8'));"
                 f" var sspData = JSON.parse(fs.readFileSync({e}, 'utf8'));")
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
  function El(id) { this.id = id; this.listeners = {}; this.attrs = {}; this.textContent = ""; this.innerHTML = ""; this.inputEvents = 0; this.children = []; }
  El.prototype.appendChild = function (child) { this.children.push(child); return child; };
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
  if (!options.noPathwayBox) { page.ssp = add("co2-ssp"); page.ssp.disabled = true; page.ssp.value = ""; page.sspInfo = add("co2-ssp-info"); }
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
  var document = { getElementById: function (id) { return byId[id] || null; }, createElement: function (tag) { return new El(tag); } };
  page.fetched = [];
  function fetch(url) {
    page.fetched.push(url);
    if (url === "/data/ssp_co2.json") {
      var sm = options.sspFetch || "ok";
      if (sm === "reject") return new SyncPromise(function (res, rej) { rej(new TypeError("offline")); });
      var sb = sm === "four" ? { pathways: sspData.pathways.slice(0, 4) } : sspData;
      return new SyncPromise(function (res) { res({ ok: true, json: function () { return new SyncPromise(function (r) { r(sb); }); } }); });
    }
    var mode = options.fetch || "ok";
    if (mode === "reject") return new SyncPromise(function (res, rej) { rej(new TypeError("offline")); });
    if (mode === "404") return new SyncPromise(function (res) { res({ ok: false, status: 404 }); });
    var body = mode === "short" ? { years: [2000], ppm: [370] }
             : mode === "nan" ? { years: [2000, 2001], ppm: [370, null] }
             : mode === "unsorted" ? { years: [2001, 2000], ppm: [371, 370] } : chartData;
    return new SyncPromise(function (res) { res({ ok: true, json: function () { return new SyncPromise(function (r) { r(body); }); } }); });
  }
  page.frames = []; page.timers = [];
  var raf = options.frames ? function (fn) { page.frames.push(fn); } : undefined;
  var timeout = options.frames ? function (fn, ms) { page.timers.push(fn); } : undefined;
  page.runFrames = function (times) { times.forEach(function (t) { var now = page.frames.splice(0); now.forEach(function (fn) { fn(t); }); }); };
  page.runTimers = function () { page.timers.splice(0).forEach(function (fn) { fn(); }); };
  page.xTicks = function () { return (page.svg.innerHTML.match(/>((19|20|21)\d\d)<\/text>/g) || []).map(function (t) { return t.slice(1, 5); }).join(","); };
  var factory = new Function("document", "fetch", "Event", "window", "CustomEvent", "requestAnimationFrame", "setTimeout", chartSource + "\n;return Co2Chart;");
  try { page.api = factory(document, fetch, Ev, window, CustomEv, raf, timeout); } catch (e) { page.loadError = String(e); }
  page.pick = function (i) { page.picker.value = String(i); page.picker.dispatchEvent(new Ev("input")); };
  page.clickAtYear = function (year) {        // a click on the graph above a year, in screen pixels
    var x = page.api.scales(chartData.years).x(year) / page.api.W * 300 + 10;
    page.svg.dispatchEvent({ type: "click", clientX: x, clientY: 100 });
  };
  page.press = function (key) { page.picker.dispatchEvent({ type: "keydown", key: key }); };
  page.change = function () { page.picker.dispatchEvent(new Ev("change")); };
  page.choosePathway = function (id) { page.ssp.value = id; page.ssp.dispatchEvent(new Ev("change")); };
  page.clickAt = function (x) { page.svg.dispatchEvent({ type: "click", clientX: x / page.api.W * 300 + 10, clientY: 100 }); };   // x in drawing units
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
    path = re.search(r'<path class="line"[^>]* d="([^"]+)"', m["none"]).group(1).split()
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

    # -- the future pathways: drawing
    F = run_js("""
      var C = (new Function(chartSource + "\\n;return Co2Chart;"))();
      var mv = C.measuredView(chartData.years), fv = C.futureView(chartData.years);
      var sm = C.scales(mv), sf = C.scales(fv);
      return { ranks: C.ranks(sspData.pathways), valid: C.validSsp(sspData), validFour: C.validSsp({ pathways: sspData.pathways.slice(0, 4) }),
               validBadYear: C.validSsp({ pathways: sspData.pathways.map(function (p, i) { return i ? p : { id: p.id, name: p.name, years: [2020, 2050], ppm: [415, 500] }; }) }),
               mEnd: sm.x(chartData.years[chartData.years.length - 1]), f2024: sf.x(2024), f2100: sf.x(2100), fy1100: sf.y(1100),
               half: C.between(mv, fv, 0.5), mv: mv, fv: fv,
               spread: C.spreadLabels([100, 101, 102, 150, 300], 17, 30, 260), spreadLow: C.spreadLabels([255, 256, 257], 17, 30, 260),
               measuredOnly: C.svgMarkup(chartData, -1, { view: mv, ssp: sspData, pathway: "SSP5" }),
               none: C.svgMarkup(chartData, -1, { view: fv, ssp: sspData, pathway: "" }),
               five: C.svgMarkup(chartData, -1, { view: fv, ssp: sspData, pathway: "SSP5" }),
               one: C.svgMarkup(chartData, chartData.years.indexOf(1990), { view: fv, ssp: sspData, pathway: "SSP1" }),
               every: chartData.years.map(function (y, i) { return C.svgMarkup(chartData, i, { view: fv, ssp: sspData, pathway: "SSP3" }); }),
               x2020: sf.x(C.FUTURE_FROM), W: C.W, H: C.H, PAD: C.PAD };
    """)
    def lines(markup):
        return re.findall(r'<path class="(ssp[^"]*)"[^>]* d="([^"]+)"', markup)

    def box(markup, cls, size):           # a text's rough box: x from the anchor, about 0.58 of the font size per character
        m = re.search(rf'<text class="{cls}" x="([\d.]+)" y="([\d.]+)"(?: text-anchor="(\w+)")?>([^<]+)</text>', markup)
        x, y, anchor, text = float(m.group(1)), float(m.group(2)), m.group(3) or "start", m.group(4)
        w = len(text) * size * 0.58
        left = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        return left, y - size * 0.75, left + w, y + size * 0.2
    axis_y = F["H"] - F["PAD"]["bottom"]
    for year, markup in zip(years, F["every"]):
        a, b = box(markup, "marker-label", 17), box(markup, "note-label", 15)
        assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1], (year, a, b)       # never on the preindustrial label
        assert a[3] < axis_y and a[0] >= 0 and a[2] <= F["W"], (year, a)                    # above the axis, inside the drawing
        for _, d in lines(markup):                                                           # and clear of every pathway line
            pts = [tuple(map(float, q[1:].split(","))) for q in d.split()]
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                for k in range(21):
                    x, y = xa + (xb - xa) * k / 20, ya + (yb - ya) * k / 20
                    assert not (a[0] - 2 <= x <= a[2] + 2 and a[1] - 2 <= y <= a[3] + 2), (year, a, x, y)
    expect_rank = {pid: RANK_LOW_TO_HIGH.index(pid) for pid in end}
    assert F["ranks"] == [expect_rank[f"SSP{i}"] for i in range(1, 6)] == [0, 2, 3, 1, 4], F["ranks"]
    assert F["valid"] is True and F["validFour"] is False and F["validBadYear"] is False, F
    assert abs(F["mEnd"] - (F["W"] - F["PAD"]["right"])) < 1e-9 and abs(F["f2100"] - (F["W"] - F["fv"]["padRight"])) < 1e-9
    assert F["f2024"] < F["W"] * 0.55, "with the pathways shown, today's CO2 moves to the left part of the graph"
    assert F["fy1100"] > F["PAD"]["top"] + 10, "SSP5's 1,089 ppm fits under the top"
    assert all(abs(F["half"][k] - (F["mv"][k] + F["fv"][k]) / 2) < 1e-9 for k in F["mv"]), F["half"]
    assert F["spread"] == [100, 117, 134, 151, 260], F["spread"]       # pushed apart downward, and the last kept above the bottom
    lo = F["spreadLow"]; assert max(lo) <= 260 and all(b - a >= 17 - 1e-9 for a, b in zip(sorted(lo), sorted(lo)[1:])), lo
    assert 'class="ssp' not in F["measuredOnly"], "in the measured view no pathway is drawn"
    assert len(lines(F["none"])) == 5 and not any("ssp-dull" in c or "ssp-on" in c for c, _ in lines(F["none"]))
    five = lines(F["five"])
    assert [c for c, _ in five].count("ssp ssp-r4 ssp-on") == 1 and sum("ssp-dull" in c for c, _ in five) == 4, five
    assert five[-1][0] == "ssp ssp-r4 ssp-on", "the highlighted line is drawn last, on top"
    first_x = {float(d.split()[0][1:].split(",")[0]) for _, d in five}
    assert len(first_x) == 1 and all(len(d.split()) == 9 for _, d in five), "each pathway starts at 2020 and has 2020-2100 every 10 years"
    labels = re.findall(r'<text class="(ssp-label[^"]*)" x="[\d.]+" y="([\d.]+)">(SSP\d)</text>', F["five"])
    assert sorted(l[2] for l in labels) == ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"]
    assert [l[2] for l in labels if "ssp-label-on" in l[0]] == ["SSP5"]
    ys = sorted(float(l[1]) for l in labels); assert all(b - a >= 17 - 0.06 for a, b in zip(ys, ys[1:])), ys
    by_label = {l[2]: float(l[1]) for l in labels}
    assert by_label["SSP5"] < by_label["SSP3"] < by_label["SSP2"] < by_label["SSP4"] < by_label["SSP1"], by_label
    assert re.findall(r'<text class="tick"[^>]*>(\d+)</text>', F["five"])[:9] == [str(v) for v in range(300, 1101, 100)]
    assert "2100</text>" in F["five"] and "2040</text>" in F["five"] and "1990</text>" not in F["five"]
    assert 'class="marker"' in F["one"] and lines(F["one"])[-1][0] == "ssp ssp-r0 ssp-on", lines(F["one"])   # SSP1, picked, on top
    print("ok  with the pathways shown, every picked year's label stays clear of the preindustrial label and the axis")
    print("ok  pathways: ranked green (SSP1) to red (SSP5) by 2100 CO2; the picked one is thick and on top, the others dull; "
          "all start at 2020, labels never overlap, and today's CO2 moves to the left")

    # -- the future pathways: the page
    Q = run_js(PRETEND_PAGE + """
      var out = {}, p = makePage();
      out.loaded = { disabled: p.ssp.disabled, options: p.ssp.children.map(function (o) { return o.value + "=" + o.textContent; }),
                     fetched: p.fetched.slice(), info: p.sspInfo.textContent };
      p.choosePathway("SSP5");
      out.ssp5 = { info: p.sspInfo.textContent, aria: p.svg.getAttribute("aria-label"), on: (p.svg.innerHTML.match(/ssp-on|ssp-label-on/g) || []).length,
                   has2100: p.svg.innerHTML.indexOf(">2100<") >= 0, errors: p.errors.slice() };
      var co2Before = p.co2.value;
      p.clickAt(p.api.W - 70);                                                  // the future part of the graph
      out.futureClick = { co2: p.co2.value, before: co2Before, message: p.message.textContent };
      p.clickAt(p.api.scales(p.api.futureView(chartData.years)).x(1990));       // the measured part still picks a year
      out.pastClick = { co2: p.co2.value, ssp: p.svg.innerHTML.indexOf('class="ssp') >= 0 };
      p.choosePathway("SSP1"); out.ssp1 = p.sspInfo.textContent;
      p.choosePathway("SSP2"); out.ssp2 = p.sspInfo.textContent;
      p.choosePathway("SSP9"); out.unknown = { info: p.sspInfo.textContent, ssp: p.svg.innerHTML.indexOf('class="ssp') >= 0, aria: p.svg.getAttribute("aria-label") };
      p.choosePathway("");
      out.none = { info: p.sspInfo.textContent, ssp: p.svg.innerHTML.indexOf('class="ssp') >= 0, has2100: p.svg.innerHTML.indexOf(">2100<") >= 0,
                   aria: p.svg.getAttribute("aria-label") };
      var f = makePage({ sspFetch: "reject" });
      out.sspFailed = { disabled: f.ssp.disabled, info: f.sspInfo.textContent, drawn: f.svg.innerHTML.length > 1000, status: f.status.textContent };
      var g = makePage({ sspFetch: "four" }); out.sspFour = { disabled: g.ssp.disabled, info: g.sspInfo.textContent };
      var h = makePage({ fetch: "404" }); out.mainFailed = h.fetched.slice();
      var a = makePage({ frames: true }); a.choosePathway("SSP5");
      out.anim = { before: a.xTicks() };
      a.runFrames([1000, 1300]); out.anim.middle = a.xTicks();
      a.runFrames([1600]); out.anim.end = a.xTicks(); out.anim.framesLeft = a.frames.length;
      a.runTimers(); out.anim.afterTimer = a.xTicks();
      a.choosePathway("SSP2"); a.runFrames([2000]); a.choosePathway(""); a.runFrames([2050, 2650, 2700]); a.runTimers();   // the old slide must not win
      out.anim.back = { ticks: a.xTicks(), ssp: a.svg.innerHTML.indexOf('class="ssp') >= 0 };
      var b = makePage({ frames: true }); b.choosePathway("SSP1"); b.runFrames([0, 100]); b.runTimers();   // frames stop: the timer finishes
      out.anim.stalled = b.xTicks(); b.runFrames([5000, 5100]); out.anim.stalledLater = b.xTicks();
      var k = makePage({ noPathwayBox: true }); out.noBox = { fetched: k.fetched.slice(), errors: k.errors };
      return out;
    """)
    ld = Q["loaded"]
    assert ld["disabled"] is False and ld["fetched"] == ["/data/co2_yearly.json", "/data/ssp_co2.json"] and ld["info"] == "", ld
    assert ld["options"] == ["SSP1=SSP1: Sustainability", "SSP2=SSP2: Middle of the Road", "SSP3=SSP3: Regional Rivalry",
                             "SSP4=SSP4: Inequality", "SSP5=SSP5: Fossil-fueled Development"], ld["options"]
    s5 = Q["ssp5"]
    assert s5["info"] == "SSP5, Fossil-fueled Development (Taking the Highway): CO₂ reaches 560 ppm by 2050 and 1,089 ppm by 2100, the highest of the five by then.", s5["info"]
    assert s5["on"] == 2 and s5["has2100"] and s5["errors"] == [], s5        # the line and its label
    assert s5["aria"].endswith("Future pathways to 2100: SSP1 608 ppm, SSP2 790 ppm, SSP3 834 ppm, SSP4 718 ppm, SSP5 1089 ppm; SSP5 is highlighted."), s5["aria"]
    assert Q["futureClick"]["co2"] == Q["futureClick"]["before"] and Q["futureClick"]["message"] == "", Q["futureClick"]
    assert Q["pastClick"] == {"co2": str(round(ppm[years.index(1990)])), "ssp": True}, Q["pastClick"]
    assert Q["ssp1"].endswith("608 ppm by 2100, the lowest of the five by then.") and Q["ssp2"] == "SSP2, Middle of the Road: CO₂ reaches 511 ppm by 2050 and 790 ppm by 2100.", (Q["ssp1"], Q["ssp2"])
    assert Q["none"]["info"] == "" and Q["none"]["ssp"] is False and Q["none"]["has2100"] is False and "Future" not in Q["none"]["aria"], Q["none"]
    assert Q["unknown"]["info"] == "" and Q["unknown"]["ssp"] is False and "Future" not in Q["unknown"]["aria"], Q["unknown"]
    assert Q["sspFailed"] == {"disabled": True, "info": "Couldn't load the future pathways. Reload the page to try again.", "drawn": True, "status": ""}, Q["sspFailed"]
    assert Q["sspFour"]["disabled"] is True and Q["sspFour"]["info"].startswith("Couldn't load"), Q["sspFour"]
    an = Q["anim"]; future_ticks = ",".join(str(y) for y in range(1960, 2101, 20)); measured_ticks = ",".join(str(y) for y in range(1960, 2021, 10))
    assert an["before"] == measured_ticks and an["middle"] not in (measured_ticks, future_ticks), an     # it moves gradually
    assert an["end"] == an["afterTimer"] == future_ticks and an["framesLeft"] == 0, an
    assert an["back"] == {"ticks": measured_ticks, "ssp": False}, an["back"]                          # a quick change of mind ends in the right place
    assert an["stalled"] == an["stalledLater"] == future_ticks, an
    print("ok  the graph slides to 2100 and back over several frames; a newer pick takes over, and if frames stop a timer finishes the move")
    assert Q["mainFailed"] == ["/data/co2_yearly.json"] and Q["noBox"] == {"fetched": ["/data/co2_yearly.json"], "errors": []}, (Q["mainFailed"], Q["noBox"])
    print("ok  the pathway box lists SSP1-SSP5, describes the pick, extends the graph to 2100 and back; clicks in the future part "
          "change nothing; a failed pathways file leaves the box off and the graph working")

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
assert re.search(r'<select id="co2-ssp" disabled>\s*<option value="">None: measured CO₂ only</option>\s*</select>', page)
assert page.index('id="co2-year"') < page.index('id="co2-ssp"') < page.index('id="co2-ssp-info"'), "the pathway box sits under the Year slider"
light = re.search(r":root \{ (--ssp0: #\w+; --ssp1: #\w+; --ssp2: #\w+; --ssp3: #\w+; --ssp4: #\w+;) \}", page)
dark = re.search(r"prefers-color-scheme: dark\) \{ :root \{ (--ssp0[^}]+) \} \}", page)
assert light and dark, "five pathway colors, for light and dark mode"
def hue(hexcolor):
    import colorsys
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360
for block in (light.group(1), dark.group(1)):
    hues = [hue(h) for h in re.findall(r"#[0-9a-f]{6}", block)]
    assert 100 < hues[0] < 160 and (hues[4] < 15 or hues[4] > 345) and hues == sorted(hues, reverse=True), hues   # green ... red
assert "baseline" in page and "Riahi et al. (2017)" in page
print("ok  the pathway box sits under the Year slider, with green-to-red colors for light and dark mode and the baseline caveat")
print("ok  the page puts the globe on the left and the CO2 graph on the right (stacked on narrow screens), and loads co2chart.js")

print("\nAll tests passed.")
