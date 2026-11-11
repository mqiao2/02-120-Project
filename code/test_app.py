"""Tests for ../app.py and ../public/index.html. Run: python3 test_app.py   (needs flask)

Expected pH and aragonite omega values come from PyCO2SYS 1.8.3, an
independent implementation: Lueker 2000 constants, total alkalinity
2300 umol/kg, sulfate and fluoride off, input as dry-air xCO2 in ppm. The API
returns the unrounded values.
"""

import itertools
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Vercel only looks for these at the top level of the repo. If one is moved, the
# website silently stops deploying, so fail here first with a clear message.
for name in ("app.py", "requirements.txt", ".python-version", "public/index.html"):
    assert (ROOT / name).is_file(), f"{name} must stay at the top level of the repo (Vercel looks for it there)"
assert "flask" in (ROOT / "requirements.txt").read_text().lower(), "requirements.txt must list flask"
print("ok  Vercel's files are at the top level: app.py, requirements.txt, .python-version, public/index.html")

sys.path.insert(0, str(ROOT))
import app as web  # noqa: E402

client = web.app.test_client()
TOL = 0.0005          # pH
TOL_OMEGA = 0.001     # aragonite omega (runs from about 0.4 to 5.8 in the allowed box)


def close(a, b, tol, name):
    assert abs(a - b) <= tol, f"{name}: got {a}, expected {b} (tol {tol})"
    print(f"ok  {name}: {a:.4f}")


def get_result(co2, temp, sal):
    response = client.get(f"/api/ph?co2={co2}&temp={temp}&sal={sal}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def get_ph(co2, temp, sal):
    return get_result(co2, temp, sal)["pH"]


def get_omega(co2, temp, sal):
    return get_result(co2, temp, sal)["omega"]


def rejects(args, word):
    """read_inputs must raise ValueError and its message must contain word."""
    try:
        web.read_inputs(args)
    except ValueError as err:
        assert word in str(err), f"{args}: message {err!r} lacks {word!r}"
    else:
        raise AssertionError(f"accepted {args}")


GOOD = {"co2": "425", "temp": "15", "sal": "35"}

# 1. read_inputs: ordinary case gives floats
assert web.read_inputs(GOOD) == {"co2": 425.0, "temp": 15.0, "sal": 35.0}
assert all(isinstance(v, float) for v in web.read_inputs(GOOD).values())
print("ok  read_inputs: valid input -> floats")

# 2. read_inputs: both edges of every range are allowed, just outside is not
for name, (low, high) in web.LIMITS.items():
    for edge in (low, high):
        assert web.read_inputs({**GOOD, name: str(edge)})[name] == edge
    rejects({**GOOD, name: str(low - 0.01)}, name)
    rejects({**GOOD, name: str(high + 0.01)}, name)
print("ok  read_inputs: edges accepted, just-outside rejected (all 3 inputs)")

# 3. read_inputs: missing, empty, junk, nan and inf are all rejected
for name in web.LIMITS:
    rejects({k: v for k, v in GOOD.items() if k != name}, name)
    for junk in ("", "abc", "4 2 5", "nan", "inf", "-inf"):
        rejects({**GOOD, name: junk}, name)
print("ok  read_inputs: missing / empty / junk / nan / inf rejected")

# 4. API matches the independent values: default, one slider at a time, all three
close(get_ph(425, 15, 35), 8.0302, TOL, "default (425 ppm, 15 C, 35)")
close(get_ph(280, 15, 35), 8.1824, TOL, "CO2 only (280 ppm)")
close(get_ph(425, -2, 35), 8.0065, TOL, "temperature only (-2 C)")
close(get_ph(425, 15, 30), 8.0457, TOL, "salinity only (30)")
close(get_ph(700, 5, 30), 7.8328, TOL, "all three moved")
close(get_omega(425, 15, 35), 2.3417, TOL_OMEGA, "omega: default (425 ppm, 15 C, 35)")
close(get_omega(280, 15, 35), 3.1089, TOL_OMEGA, "omega: CO2 only (280 ppm)")
close(get_omega(425, -2, 35), 1.2075, TOL_OMEGA, "omega: temperature only (-2 C)")
close(get_omega(425, 15, 30), 2.2306, TOL_OMEGA, "omega: salinity only (30)")
close(get_omega(700, 5, 30), 0.9887, TOL_OMEGA, "omega: all three moved (just corrosive)")

# 5. Every corner of the allowed box: (pH, omega)
corners = {
    (250, -2, 20): (8.2705, 1.4658), (250, -2, 42): (8.2041, 1.9743),
    (250, 35, 20): (8.2887, 5.7712), (250, 35, 42): (8.1758, 5.7623),
    (1000, -2, 20): (7.7012, 0.4262), (1000, -2, 42): (7.6530, 0.6241),
    (1000, 35, 20): (7.7926, 2.3507), (1000, 35, 42): (7.7102, 2.6995),
}
assert set(corners) == set(itertools.product(*[(lo, hi) for lo, hi in web.LIMITS.values()]))
for point, (ph, omega) in corners.items():
    close(get_ph(*point), ph, TOL, f"corner {point} pH")
    close(get_omega(*point), omega, TOL_OMEGA, f"corner {point} omega")

# 6. Physics direction: more CO2 -> strictly lower pH and omega;
#    warmer water (same CO2 and salinity) -> strictly higher omega
phs = [get_ph(x, 15, 35) for x in (250, 425, 700, 1000)]
assert all(a > b for a, b in zip(phs, phs[1:])), phs
print(f"ok  more CO2 -> lower pH: {[round(p, 3) for p in phs]}")
omegas = [get_omega(x, 15, 35) for x in (250, 425, 700, 1000)]
assert all(a > b for a, b in zip(omegas, omegas[1:])), omegas
print(f"ok  more CO2 -> lower omega: {[round(o, 3) for o in omegas]}")
warm = [get_omega(425, t, 35) for t in (-2, 5, 15, 25, 35)]
assert all(a < b for a, b in zip(warm, warm[1:])), warm
print(f"ok  warmer -> higher omega: {[round(o, 3) for o in warm]}")

# 7. The response has pH and omega and echoes the inputs it used
data = client.get("/api/ph?co2=700&temp=5&sal=30").get_json()
assert set(data) == {"pH", "omega", "co2", "temp", "sal"}, data
assert (data["co2"], data["temp"], data["sal"]) == (700.0, 5.0, 30.0), data
print("ok  response has pH, omega and echoes co2, temp, sal")

# 8. Bad requests get a 400 with a JSON error, not a crash
for query, word in [("", "co2"), ("co2=425&temp=15", "sal"), ("co2=abc&temp=15&sal=35", "co2"),
                    ("co2=425&temp=99&sal=35", "temp"), ("co2=425&temp=15&sal=nan", "sal")]:
    response = client.get("/api/ph?" + query)
    assert response.status_code == 400, (query, response.status_code)
    assert word in response.get_json()["error"], (query, response.get_json())
assert client.post("/api/ph?" + "co2=425&temp=15&sal=35").status_code == 405
print("ok  bad input -> 400 with message; POST -> 405")

# 9. Only the page, the API and the files in public/ are served: no repo files leak,
#    and no path can climb out of public/
for path in ("/app.py", "/code/ocean_chem.py", "/requirements.txt", "/journal/x.jsonl",
             "/sources/mauna_loa_co2.csv", "/static/index.html", "/public/index.html",
             "/../app.py", "/data/../../app.py", "/%2e%2e/app.py", "/data/%2e%2e/%2e%2e/app.py",
             "/data/", "/data/nope.json"):
    response = client.get(path)
    assert response.status_code == 404, (path, response.status_code)
    response.close()
print("ok  repo files are not served; paths that climb out of public/ are refused")

# 9b. Like Vercel, locally the files in public/ are served from the site root (the globe needs these)
for path, kind in (("/globe.js", "javascript"), ("/data/surface_1deg.json", "json")):
    response = client.get(path)
    assert response.status_code == 200 and kind in response.headers["Content-Type"], (path, response.headers)
    assert len(response.get_data()) > 1000, path
    response.close()
print("ok  /globe.js and /data/surface_1deg.json are served")

# 10. The home page is served and has the three sliders and the assumption note
home = client.get("/")
page = home.get_data(as_text=True)
home.close()
assert home.status_code == 200 and '<input id="co2"' in page and "2300" in page
assert 'id="ph"' in page and 'id="omega"' in page and 'id="saturation"' in page
assert "data.omega" in page          # the script shows the omega the API returns
print("ok  home page served, with pH and omega readouts")


class SliderFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sliders = {}
        self.label_for = set()   # ids that a <label for=...> points at
        self.in_label = 0
        self.nested = []         # form controls found inside a <label> (invalid HTML)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "label":
            self.in_label += 1
            self.label_for.add(attrs.get("for"))
        elif self.in_label and tag in ("input", "output", "select", "textarea", "button"):
            self.nested.append(tag)
        if tag == "input" and attrs.get("type") == "range":
            self.sliders[attrs["id"]] = attrs

    def handle_endtag(self, tag):
        if tag == "label":
            self.in_label -= 1


finder = SliderFinder()
finder.feed((ROOT / "public" / "index.html").read_text(encoding="utf-8"))

# 11. Page sliders and API limits agree (a slider must never offer a value the API refuses)
# The calculator's sliders (the CO2 graph's year picker is a slider too, but not a calculator input)
assert set(finder.sliders) == set(web.LIMITS) | {"co2-year"}, finder.sliders.keys()
for name, (low, high) in web.LIMITS.items():
    s = finder.sliders[name]
    assert (float(s["min"]), float(s["max"])) == (low, high), (name, s)
    assert low <= float(s["value"]) <= high and float(s["step"]) > 0, (name, s)
print("ok  slider min/max match API limits")

# 12. Page defaults give the default pH shown in test 4
defaults = {name: s["value"] for name, s in finder.sliders.items() if name in web.LIMITS}
assert defaults == {"co2": "425", "temp": "15", "sal": "35"}, defaults
print("ok  slider defaults are 425 ppm, 15 C, salinity 35")

# 13. Valid label markup: every slider has a label, and no form control sits inside a label
assert set(finder.sliders) <= finder.label_for, (finder.sliders.keys(), finder.label_for)
assert finder.nested == [], finder.nested
print("ok  every slider has a label; no form control nested inside a label")

# 14. A favicon is declared, so browsers don't request /favicon.ico from the Python function
assert 'rel="icon"' in page
print("ok  favicon declared")

print("\nAll tests passed.")
