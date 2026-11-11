/* CO2 graph: yearly CO2 at Mauna Loa, with a year picker that sets the calculator's CO2.

   The data is public/data/co2_yearly.json, built by code/build_co2_data.py. The graph is
   plain SVG built as text; there are no libraries. The first part of this file is maths and
   drawing that need no web page (code/test_co2.py tests it); start() connects it to the page.
*/

var Co2Chart = (function () {
  "use strict";

  var DATA_URL = "/data/co2_yearly.json";
  var PREINDUSTRIAL = 280;                              // ppm, before about 1750
  var W = 480, H = 300;                                 // the drawing's own units; it scales to fit the page
  var PAD = { left: 50, right: 12, top: 24, bottom: 40 };
  var Y_MIN = 270, Y_MAX = 430;

  // Where a year and a CO2 value go on the drawing, and back.
  function scales(years) {
    var first = years[0], last = years[years.length - 1];
    var plotW = W - PAD.left - PAD.right, plotH = H - PAD.top - PAD.bottom;
    return {
      x: function (year) { return PAD.left + (year - first) / (last - first) * plotW; },
      y: function (ppm) { return PAD.top + (Y_MAX - ppm) / (Y_MAX - Y_MIN) * plotH; },
      yearAt: function (x) { return first + (x - PAD.left) / plotW * (last - first); }
    };
  }

  // The index of the year closest to `year` (some years, like 1964, have no full-year average).
  function nearestIndex(years, year) {
    var best = 0;
    for (var i = 1; i < years.length; i++) {
      if (Math.abs(years[i] - year) < Math.abs(years[best] - year)) best = i;
    }
    return best;
  }

  // True if `d` looks like the data file: matching lists, whole increasing years, numbers for ppm (JSON has no NaN).
  function valid(d) {
    if (!d || !Array.isArray(d.years) || !Array.isArray(d.ppm) || d.years.length < 2 || d.years.length !== d.ppm.length) return false;
    for (var i = 0; i < d.years.length; i++) {
      if (!Number.isInteger(d.years[i]) || typeof d.ppm[i] !== "number") return false;
      if (i > 0 && d.years[i] <= d.years[i - 1]) return false;
    }
    return true;
  }

  function f1(n) { return (Math.round(n * 10) / 10).toFixed(1); }

  // The whole graph as SVG text. `selected` is the index of the chosen year, or -1 for none.
  function svgMarkup(data, selected) {
    var s = scales(data.years), parts = [];
    var x0 = PAD.left, x1 = W - PAD.right, y0 = PAD.top, y1 = H - PAD.bottom;
    for (var v = 280; v <= 420; v += 20) {             // horizontal grid lines and CO2 labels
      parts.push('<line class="grid" x1="' + x0 + '" x2="' + x1 + '" y1="' + f1(s.y(v)) + '" y2="' + f1(s.y(v)) + '"/>');
      parts.push('<text class="tick" x="' + (x0 - 8) + '" y="' + f1(s.y(v) + 4) + '" text-anchor="end">' + v + '</text>');
    }
    for (var yr = 1960; yr <= data.years[data.years.length - 1]; yr += 10) {   // year labels
      parts.push('<text class="tick" x="' + f1(s.x(yr)) + '" y="' + (y1 + 18) + '" text-anchor="middle">' + yr + '</text>');
    }
    parts.push('<line class="axis" x1="' + x0 + '" x2="' + x1 + '" y1="' + y1 + '" y2="' + y1 + '"/>');
    parts.push('<line class="preindustrial" x1="' + x0 + '" x2="' + x1 + '" y1="' + f1(s.y(PREINDUSTRIAL)) + '" y2="' + f1(s.y(PREINDUSTRIAL)) + '"/>');
    parts.push('<text class="note-label" x="' + (x1 - 4) + '" y="' + f1(s.y(PREINDUSTRIAL) - 6) + '" text-anchor="end">Preindustrial ≈ 280 ppm</text>');
    parts.push('<text class="axis-label" x="' + (x0 - 8) + '" y="' + (PAD.top - 8) + '" text-anchor="end">ppm</text>');   // the unit, above the CO2 labels
    var d = data.years.map(function (year, i) {
      return (i === 0 ? "M" : "L") + f1(s.x(year)) + "," + f1(s.y(data.ppm[i]));
    }).join(" ");
    parts.push('<path class="line" d="' + d + '"/>');
    if (selected >= 0) {
      var px = s.x(data.years[selected]), py = s.y(data.ppm[selected]);
      var label = data.years[selected] + ": " + data.ppm[selected].toFixed(1) + " ppm";
      var right = px > W - 160;                          // keep the label inside the drawing
      var ly = right ? py - 10 : py + 24;                // left of the end, the label goes under the rising line
      parts.push('<line class="marker-line" x1="' + f1(px) + '" x2="' + f1(px) + '" y1="' + y0 + '" y2="' + y1 + '"/>');
      parts.push('<circle class="marker" cx="' + f1(px) + '" cy="' + f1(py) + '" r="6"/>');
      parts.push('<text class="marker-label" x="' + f1(right ? px - 10 : px + 10) + '" y="' + f1(ly) + '" text-anchor="' +
                 (right ? "end" : "start") + '">' + label + '</text>');
    }
    return parts.join("");
  }

  // ---------- the page ----------
  function start() {
    var svg = document.getElementById("co2-chart");
    var picker = document.getElementById("co2-year");
    var yearOut = document.getElementById("co2-year-out");
    var messageEl = document.getElementById("co2-pick");
    var statusEl = document.getElementById("co2-status");
    var estimateEl = document.getElementById("co2-pick-estimate");
    var linkEl = document.getElementById("co2-pick-link");
    if (!svg || !picker) return;
    var data = null, selected = -1, applying = false;

    function draw() { svg.innerHTML = svgMarkup(data, selected); }

    function describe(i) { return data.years[i] + ": " + data.ppm[i].toFixed(1) + " ppm"; }

    // Set the calculator's CO2 slider, telling the calculator with the same "input" event a drag sends.
    function choose(i) {
      selected = i;
      picker.value = String(i);
      picker.setAttribute("aria-valuetext", describe(i));
      yearOut.textContent = describe(i);
      draw();
      var co2 = document.getElementById("co2");
      if (!co2) { messageEl.textContent = "The calculator isn't on this page."; return; }
      if (estimateEl) estimateEl.textContent = "";
      var wanted = Math.round(data.ppm[i]);
      var set = Math.max(Number(co2.min), Math.min(Number(co2.max), wanted));
      tellPage({ year: data.years[i], ppm: data.ppm[i] });   // before the calculator's new estimate comes back
      applying = true;
      try {
        co2.value = String(set);
        co2.dispatchEvent(new Event("input", { bubbles: true }));
      } finally {
        applying = false;
      }
      messageEl.textContent = "The calculator now uses " + co2.value + " ppm CO₂, the " + data.years[i] +
        " average at Mauna Loa (" + data.ppm[i].toFixed(1) + " ppm).";
      if (linkEl) linkEl.hidden = false;
    }

    // Tell the rest of the page (the globe) which year the calculator's CO2 comes from, or null for none.
    function tellPage(detail) {
      if (typeof window !== "undefined" && window.dispatchEvent) window.dispatchEvent(new CustomEvent("co2year", { detail: detail }));
    }

    function clearPick() {
      selected = -1; messageEl.textContent = ""; yearOut.textContent = "Pick a year";
      picker.setAttribute("aria-valuetext", "No year picked");
      if (estimateEl) estimateEl.textContent = "";
      if (linkEl) linkEl.hidden = true;
      draw();
      tellPage(null);
    }

    // The calculator reports each estimate; while it still uses the picked year's CO2, show it here,
    // because the calculator itself may be off screen.
    window.addEventListener("estimate", function (e) {
      var d = e.detail, co2 = document.getElementById("co2");
      if (selected < 0 || !d || !estimateEl || !co2) return;
      if (d.error) { estimateEl.textContent = "The calculator couldn't get an estimate; pick the year again to retry."; return; }
      if (typeof d.pH !== "number" || Math.round(d.co2) !== Number(co2.value)) return;
      estimateEl.textContent = "Result: pH " + d.pH.toFixed(3) + ", Ω " + d.omega.toFixed(2) + ".";
    });

    picker.addEventListener("input", function () { if (data) choose(Number(picker.value)); });
    // The thumb starts on the latest year, so moving it can't pick that year; Enter or a click on the thumb can.
    picker.addEventListener("change", function () { if (data && selected !== Number(picker.value)) choose(Number(picker.value)); });
    picker.addEventListener("keydown", function (e) { if (data && e.key === "Enter") choose(Number(picker.value)); });

    // Clicking the graph picks the nearest year.
    svg.addEventListener("click", function (e) {
      if (!data) return;
      var rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      var x = (e.clientX - rect.left) / rect.width * W;    // into the drawing's own units
      choose(nearestIndex(data.years, scales(data.years).yearAt(x)));
    });

    // Moving the CO2 slider by hand means the calculator no longer shows that year.
    var co2Slider = document.getElementById("co2");
    if (co2Slider) co2Slider.addEventListener("input", function () {
      if (applying || selected < 0) return;
      clearPick();
    });

    fetch(DATA_URL)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (d) {
        if (!valid(d)) throw new Error("unexpected data");
        data = d;
        picker.min = "0"; picker.max = String(d.years.length - 1); picker.step = "1";
        picker.value = String(d.years.length - 1);          // the thumb starts at the latest year, but nothing is changed yet
        picker.setAttribute("aria-valuetext", "No year picked");
        picker.disabled = false;
        yearOut.textContent = "Pick a year";
        statusEl.textContent = "";
        svg.setAttribute("aria-label", "Graph of yearly CO₂ at Mauna Loa: " + describe(0) + ", rising every year to " +
                         describe(d.years.length - 1) + ".");
        draw();
      })
      .catch(function () {
        statusEl.textContent = "Couldn't load the CO₂ data. Reload the page to try again.";
      });
  }

  if (typeof document !== "undefined") {
    try { start(); } catch (err) {
      var s = document.getElementById("co2-status");
      if (s) s.textContent = "The CO₂ graph could not start. Reload the page to try again.";
    }
  }

  return { W: W, H: H, PAD: PAD, PREINDUSTRIAL: PREINDUSTRIAL, Y_MIN: Y_MIN, Y_MAX: Y_MAX,
           scales: scales, nearestIndex: nearestIndex, svgMarkup: svgMarkup, valid: valid };
})();
