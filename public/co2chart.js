/* CO2 graph: yearly CO2 at Mauna Loa, with a year picker that sets the calculator's CO2, and
   a box to show the future pathways (SSP1-SSP5) to 2100.

   The data is public/data/co2_yearly.json, built by code/build_co2_data.py, and
   public/data/ssp_co2.json, built by code/build_ssp_data.py. The graph is
   plain SVG built as text; there are no libraries. The first part of this file is maths and
   drawing that need no web page (code/test_co2.py tests it); start() connects it to the page.
*/

var Co2Chart = (function () {
  "use strict";

  var DATA_URL = "/data/co2_yearly.json";
  var SSP_URL = "/data/ssp_co2.json";
  var FUTURE_FROM = 2020;                               // pathways are drawn from here; the measured line covers earlier years
  var FUTURE_TO = 2100;
  var PREINDUSTRIAL = 280;                              // ppm, before about 1750
  var W = 480, H = 300;                                 // the drawing's own units; it scales to fit the page
  var PAD = { left: 50, right: 12, top: 24, bottom: 40 };
  var Y_MIN = 270, Y_MAX = 430;

  // What part of the graph is shown: years `from`-`to`, CO2 `yMin`-`yMax`, and space on the right for labels.
  // The measured view fits the Mauna Loa record; the future view runs to 2100 so the measured years move left.
  function measuredView(years) { return { from: years[0], to: years[years.length - 1], yMin: Y_MIN, yMax: Y_MAX, padRight: PAD.right }; }
  function futureView(years) { return { from: years[0], to: FUTURE_TO, yMin: 250, yMax: 1150, padRight: 60 }; }
  function between(a, b, t) {                          // a view part way from a (t = 0) to b (t = 1)
    var v = {};
    for (var k in a) v[k] = a[k] + (b[k] - a[k]) * t;
    return v;
  }

  // Where a year and a CO2 value go on the drawing, and back. Takes a view, or a list of years for the measured view.
  function scales(view) {
    if (Array.isArray(view)) view = measuredView(view);
    var plotW = W - PAD.left - view.padRight, plotH = H - PAD.top - PAD.bottom;
    return {
      x: function (year) { return PAD.left + (year - view.from) / (view.to - view.from) * plotW; },
      y: function (ppm) { return PAD.top + (view.yMax - ppm) / (view.yMax - view.yMin) * plotH; },
      yearAt: function (x) { return view.from + (x - PAD.left) / plotW * (view.to - view.from); }
    };
  }

  // The pathways ranked by their 2100 CO2, lowest first: rank 0 is drawn green, rank 4 red.
  function ranks(pathways) {
    var order = pathways.map(function (p, i) { return i; });
    order.sort(function (a, b) { return last(pathways[a].ppm) - last(pathways[b].ppm); });
    var rank = [];
    order.forEach(function (i, r) { rank[i] = r; });
    return rank;
  }
  function last(list) { return list[list.length - 1]; }

  // A pathway's CO2 in `year`, a straight line between its data points (2020, 2030, ... 2100).
  function pathwayAt(p, year) {
    for (var i = 1; i < p.years.length; i++) {
      if (year <= p.years[i]) {
        var a = p.years[i - 1], b = p.years[i];
        return p.ppm[i - 1] + (p.ppm[i] - p.ppm[i - 1]) * (year - a) / (b - a);
      }
    }
    return last(p.ppm);
  }

  // The years the Year slider can pick: the measured years, then (with a pathway) every year to 2100 on that pathway.
  // `measured` is how many of them are measured.
  function timeline(data, p) {
    var years = data.years.slice(), ppm = data.ppm.slice(), measured = years.length;
    if (p) for (var y = last(data.years) + 1; y <= FUTURE_TO; y++) { years.push(y); ppm.push(pathwayAt(p, y)); }
    return { years: years, ppm: ppm, measured: measured, pathway: p ? p.id : "" };
  }

  // Label heights for the line ends: each wants `want[i]`; push them apart so none are closer than `gap`.
  function spreadLabels(want, gap, low, high) {
    var order = want.map(function (y, i) { return i; }).sort(function (a, b) { return want[a] - want[b]; });
    var at = want.slice();
    for (var k = 1; k < order.length; k++) at[order[k]] = Math.max(at[order[k]], at[order[k - 1]] + gap);
    var n = order.length;                              // then from the bottom up, so none runs past `high`
    at[order[n - 1]] = Math.min(at[order[n - 1]], high);
    for (k = n - 2; k >= 0; k--) at[order[k]] = Math.min(at[order[k]], at[order[k + 1]] - gap);
    order.forEach(function (i) { at[i] = Math.max(low, at[i]); });
    return at;
  }

  // The index of the year closest to `year` (some years, like 1964, have no full-year average).
  function nearestIndex(years, year) {
    var best = 0;
    for (var i = 1; i < years.length; i++) {
      if (Math.abs(years[i] - year) < Math.abs(years[best] - year)) best = i;
    }
    return best;
  }

  // True if `d` looks like the pathways file: SSP1-SSP5, each with whole increasing years and numbers for ppm.
  function validSsp(d) {
    if (!d || !Array.isArray(d.pathways) || d.pathways.length !== 5) return false;
    return d.pathways.every(function (p, i) {
      return p && p.id === "SSP" + (i + 1) && typeof p.name === "string" && valid(p) && p.years[p.years.length - 1] === FUTURE_TO &&
             p.years.indexOf(FUTURE_FROM) >= 0;
    });
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
  // `options` (all optional): view (the part shown), ssp (the pathways data) and pathway (the highlighted id, or "").
  function svgMarkup(data, selected, options) {
    options = options || {};
    var view = options.view || measuredView(data.years);
    var s = scales(view), parts = [];
    var x0 = PAD.left, x1 = W - view.padRight, y0 = PAD.top, y1 = H - PAD.bottom;
    var yStep = view.yMax - view.yMin > 300 ? 100 : 20, xStep = view.to - view.from > 90 ? 20 : 10;
    for (var v = Math.ceil((view.yMin + 5) / yStep) * yStep; v <= view.yMax - 10; v += yStep) {   // grid lines and CO2 labels
      parts.push('<line class="grid" x1="' + x0 + '" x2="' + f1(x1) + '" y1="' + f1(s.y(v)) + '" y2="' + f1(s.y(v)) + '"/>');
      parts.push('<text class="tick" x="' + (x0 - 8) + '" y="' + f1(s.y(v) + 4) + '" text-anchor="end">' + v + '</text>');
    }
    for (var yr = 1960; yr <= view.to + 0.5; yr += xStep) {   // year labels
      parts.push('<text class="tick" x="' + f1(s.x(yr)) + '" y="' + (y1 + 18) + '" text-anchor="middle">' + yr + '</text>');
    }
    parts.push('<line class="axis" x1="' + x0 + '" x2="' + f1(x1) + '" y1="' + y1 + '" y2="' + y1 + '"/>');
    parts.push('<line class="preindustrial" x1="' + x0 + '" x2="' + f1(x1) + '" y1="' + f1(s.y(PREINDUSTRIAL)) + '" y2="' + f1(s.y(PREINDUSTRIAL)) + '"/>');
    parts.push('<text class="note-label" x="' + f1(x1 - 4) + '" y="' + f1(s.y(PREINDUSTRIAL) - 6) + '" text-anchor="end">Preindustrial ≈ 280 ppm</text>');
    parts.push('<text class="axis-label" x="' + (x0 - 8) + '" y="' + (PAD.top - 8) + '" text-anchor="end">ppm</text>');   // the unit, above the CO2 labels
    var d = data.years.map(function (year, i) {
      return (i === 0 ? "M" : "L") + f1(s.x(year)) + "," + f1(s.y(data.ppm[i]));
    }).join(" ");
    parts.push('<clipPath id="co2-plot"><rect x="' + x0 + '" y="' + y0 + '" width="' + f1(x1 - x0) + '" height="' + (y1 - y0) + '"/></clipPath>');
    if (options.ssp && view.to > data.years[data.years.length - 1] + 1) parts.push(pathwayMarkup(options.ssp, options.pathway || "", s, x1, y0, y1));
    parts.push('<path class="line" clip-path="url(#co2-plot)" d="' + d + '"/>');
    var pts = options.points || timeline(data, null);
    if (selected >= 0 && selected < pts.years.length) {
      var px = s.x(pts.years[selected]), py = s.y(pts.ppm[selected]);
      var label = pts.years[selected] + ": " + pts.ppm[selected].toFixed(1) + " ppm";   // the highlighted line shows which pathway
      var future = view.to > data.years[data.years.length - 1] + 1;
      // Measured view: under the rising line, or left of the point near the right edge. Future view: the measured
      // line lies low and flat under the preindustrial label, so the label goes to the empty top of the dashed
      // marker line, beside it (left of it for later years).
      var right = future ? px > 200 : px > W - 160;
      var ly = future ? y0 + 22 : right ? py - 10 : py + 24;
      parts.push('<line class="marker-line" x1="' + f1(px) + '" x2="' + f1(px) + '" y1="' + y0 + '" y2="' + y1 + '"/>');
      parts.push('<circle class="marker" cx="' + f1(px) + '" cy="' + f1(py) + '" r="6"/>');
      parts.push('<text class="marker-label" x="' + f1(right ? px - 10 : px + 10) + '" y="' + f1(ly) + '" text-anchor="' +
                 (right ? "end" : "start") + '">' + label + '</text>');
    }
    return parts.join("");
  }

  // The five future pathways from 2020: the highlighted one bright and thick, the others dull, each labeled at its end.
  function pathwayMarkup(ssp, highlight, s, xEnd, yTop, yBottom) {
    var rank = ranks(ssp.pathways), lines = [], labels = [];
    var want = ssp.pathways.map(function (p) { return s.y(last(p.ppm)) + 5; });
    var at = spreadLabels(want, 17, yTop + 5, yBottom);
    ssp.pathways.forEach(function (p, i) {
      var d = [];
      p.years.forEach(function (year, j) { if (year >= FUTURE_FROM) d.push((d.length ? "L" : "M") + f1(s.x(year)) + "," + f1(s.y(p.ppm[j]))); });
      var on = p.id === highlight;
      var cls = "ssp ssp-r" + rank[i] + (on ? " ssp-on" : highlight ? " ssp-dull" : "");
      lines[on ? 5 : i] = '<path class="' + cls + '" clip-path="url(#co2-plot)" d="' + d.join(" ") + '"/>';   // the highlighted line on top
      labels.push('<text class="ssp-label' + (on ? " ssp-label-on" : "") + '" x="' + f1(xEnd + 6) + '" y="' + f1(at[i]) + '">' + p.id + '</text>');
    });
    return lines.filter(Boolean).join("") + labels.join("");
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
    var sspBox = document.getElementById("co2-ssp");
    var sspInfo = document.getElementById("co2-ssp-info");
    if (!svg || !picker) return;
    var data = null, selected = -1, applying = false;
    var ssp = null, pathway = "", view = null, animation = 0;
    var points = null;           // the years the Year slider picks from (see timeline)

    function draw() {
      if (!view) view = measuredView(data.years);
      svg.innerHTML = svgMarkup(data, selected, { view: view, ssp: ssp, pathway: pathway, points: points });
    }

    function describe(i) {
      return points.years[i] + ": " + points.ppm[i].toFixed(1) + " ppm" + (i >= points.measured ? " (" + points.pathway + ")" : "");
    }

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
      var year = points.years[i], value = points.ppm[i], future = i >= points.measured;
      var wanted = Math.round(value);
      var set = Math.max(Number(co2.min), Math.min(Number(co2.max), wanted));
      tellPage({ year: year, ppm: value, pathway: future ? points.pathway : null });   // before the calculator's new estimate comes back
      applying = true;
      try {
        co2.value = String(set);
        co2.dispatchEvent(new Event("input", { bubbles: true }));
      } finally {
        applying = false;
      }
      if (!future) {
        messageEl.textContent = "The calculator now uses " + co2.value + " ppm CO₂, the " + year +
          " average at Mauna Loa (" + value.toFixed(1) + " ppm).";
      } else {
        var decade = Math.floor(year / 10) * 10;
        messageEl.textContent = "The calculator now uses " + co2.value + " ppm CO₂, the " + points.pathway + " pathway's value for " +
          year + " (" + value.toFixed(1) + " ppm" + (year % 10 ? ", between its " + decade + " and " + (decade + 10) + " values" : "") + ")." +
          (Number(co2.value) !== wanted ? " That is as high as the calculator goes." : "");
      }
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
      var year = scales(view || measuredView(data.years)).yearAt(x);
      if (year > last(points.years) + 1.5) return;     // past the last year there is CO2 for (the future, with no pathway picked)
      choose(nearestIndex(points.years, year));
    });

    // Moving the CO2 slider by hand means the calculator no longer shows that year.
    var co2Slider = document.getElementById("co2");
    if (co2Slider) co2Slider.addEventListener("input", function () {
      if (applying || selected < 0) return;
      clearPick();
    });

    // ---- the future pathways ----
    var reduceMotion = typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Slide the graph to `target` over about half a second (at once if motion is reduced or there is no animation frame).
    function moveTo(target) {
      var startView = view, startTime = null, run = ++animation;
      if (reduceMotion || typeof requestAnimationFrame !== "function") { view = target; draw(); return; }
      requestAnimationFrame(function step(now) {
        if (run !== animation) return;                  // a newer choice took over
        if (startTime === null) startTime = now;
        var t = Math.min(1, (now - startTime) / 600);
        view = between(startView, target, t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t));
        draw();
        if (t < 1) requestAnimationFrame(step); else animation++;
      });
      setTimeout(function () {                           // if the browser skips frames (a hidden tab), still finish
        if (run !== animation) return;
        animation++; view = target; draw();
      }, 800);
    }

    function describePathway(p) {
      var rank = ranks(ssp.pathways)[ssp.pathways.indexOf(p)];
      var at = function (year) { return Math.round(p.ppm[p.years.indexOf(year)]).toLocaleString("en-US") + " ppm"; };
      return p.id + ", " + p.name + (p.tagline ? " (" + p.tagline + ")" : "") + ": CO₂ reaches " + at(2050) + " by 2050 and " +
             at(FUTURE_TO) + " by " + FUTURE_TO + (rank === 0 ? ", the lowest of the five by then." : rank === 4 ? ", the highest of the five by then." : ".");
    }

    function choosePathway(id) {
      if (!data || !ssp) return;
      var p = ssp.pathways.filter(function (q) { return q.id === id; })[0] || null;
      pathway = p ? p.id : "";
      var pickedYear = selected >= 0 ? points.years[selected] : null, wasFuture = selected >= points.measured;
      points = timeline(data, p);
      picker.max = String(points.years.length - 1);
      if (Number(picker.value) > points.years.length - 1) picker.value = String(points.measured - 1);
      if (wasFuture && p) choose(points.years.indexOf(pickedYear));   // the same year, on the new pathway
      else if (wasFuture) clearPick();                 // no pathway: no CO2 for that year (the thumb was moved back above)
      if (sspInfo) sspInfo.textContent = p ? describePathway(p) : "";
      describeGraph();
      moveTo(p ? futureView(data.years) : measuredView(data.years));
    }

    function describeGraph() {
      var text = "Graph of yearly CO₂ at Mauna Loa: " + describe(0) + ", rising every year to " + describe(data.years.length - 1) + ".";
      if (pathway) {
        text += " Future pathways to " + FUTURE_TO + ": " + ssp.pathways.map(function (p) {
          return p.id + " " + Math.round(last(p.ppm)) + " ppm";
        }).join(", ") + "; " + pathway + " is highlighted.";
      }
      svg.setAttribute("aria-label", text);
    }

    if (sspBox) sspBox.addEventListener("change", function () { choosePathway(sspBox.value); });

    fetch(DATA_URL)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (d) {
        if (!valid(d)) throw new Error("unexpected data");
        data = d;
        points = timeline(d, null);
        picker.min = "0"; picker.max = String(d.years.length - 1); picker.step = "1";
        picker.value = String(d.years.length - 1);          // the thumb starts at the latest year, but nothing is changed yet
        picker.setAttribute("aria-valuetext", "No year picked");
        picker.disabled = false;
        yearOut.textContent = "Pick a year";
        statusEl.textContent = "";
        describeGraph();
        draw();
        if (sspBox) loadPathways();
      })
      .catch(function () {
        statusEl.textContent = "Couldn't load the CO₂ data. Reload the page to try again.";
      });

    // The pathways load after the measured data, so the graph never waits for them.
    function loadPathways() {
      fetch(SSP_URL)
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return response.json();
        })
        .then(function (d) {
          if (!validSsp(d)) throw new Error("unexpected data");
          ssp = d;
          d.pathways.forEach(function (p) {
            var option = document.createElement("option");
            option.value = p.id;
            option.textContent = p.id + ": " + p.name;
            sspBox.appendChild(option);
          });
          sspBox.value = "";                               // always start with None, even if the browser kept an older choice
          sspBox.disabled = false;
        })
        .catch(function () {
          if (sspInfo) sspInfo.textContent = "Couldn't load the future pathways. Reload the page to try again.";
        });
    }
  }

  if (typeof document !== "undefined") {
    try { start(); } catch (err) {
      var s = document.getElementById("co2-status");
      if (s) s.textContent = "The CO₂ graph could not start. Reload the page to try again.";
    }
  }

  return { W: W, H: H, PAD: PAD, PREINDUSTRIAL: PREINDUSTRIAL, Y_MIN: Y_MIN, Y_MAX: Y_MAX,
           FUTURE_FROM: FUTURE_FROM, FUTURE_TO: FUTURE_TO, measuredView: measuredView, futureView: futureView, between: between,
           scales: scales, nearestIndex: nearestIndex, svgMarkup: svgMarkup, valid: valid, validSsp: validSsp,
           ranks: ranks, spreadLabels: spreadLabels, pathwayAt: pathwayAt, timeline: timeline };
})();
