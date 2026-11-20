/* Ocean globe: a draggable Earth colored by sea surface temperature, salinity, total alkalinity,
   or aragonite saturation (Ω, worked out in the browser by public/chem.js for the calculator's CO2).

   The data is public/data/surface_1deg.json, built by code/build_globe_data.py from NOAA's
   World Ocean Atlas 2023, and public/data/alkalinity_1deg.json, built by
   code/build_alkalinity_data.py from GLODAP (loaded separately: the globe works without it). There are no libraries: for every pixel of the globe we work out
   which latitude and longitude it shows, look that spot up in the data grid, and color it.

   The first part of this file is plain maths that needs no web page, so it can be tested
   (code/test_globe.py does). The second part, start(), connects it to the page; the tests
   run that too, in a pretend page (code/globe_harness.js).
*/

var OceanGlobe = (function () {
  "use strict";

  var DEG = Math.PI / 180;
  var NLON = 360, NLAT = 180;          // one-degree grid: 360 columns, 180 rows, row 0 is the south
  var DATA_URL = "/data/surface_1deg.json";
  var ALK_URL = "/data/alkalinity_1deg.json";
  // Marked grids (Ω and alkalinity) use negative numbers for ocean cells with no value, and why:
  var FRESH = -1;                      // too fresh for the model (salinity below SAL_MIN): no Ω
  var NO_ALK = -2;                     // GLODAP has no alkalinity here

  // ---------- colors ----------
  // Temperature: ColorBrewer "RdYlBu", reversed, so cold is blue and warm is red.
  // Salinity: viridis, so fresh is dark purple and salty is yellow.
  // (ColorBrewer: Brewer, Harrower and Penn State. Viridis: van der Walt and Smith.)
  // Values outside min..max get the end color. The descriptions are the text version of
  // the picture; code/test_globe.py checks what they say against the data.
  var LAYERS = {
    temperature: {
      label: "Sea surface temperature", unit: "°C", digits: 1,
      min: -2, max: 30, minLabel: "≤ −2", maxLabel: "30", ticks: [10, 20],
      stops: ["#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8", "#ffffbf",
              "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"],
      description: "Warm water (red) lies near the equator and cold water (blue) near the poles, " +
                   "down to about −2 °C. The warmest open water, about 29 °C, is in the western " +
                   "Pacific, near the Philippines and Indonesia."
    },
    salinity: {
      label: "Sea surface salinity", unit: "PSU", digits: 2,
      min: 31, max: 38, minLabel: "≤ 31", maxLabel: "≥ 38", ticks: [33, 35],
      stops: ["#440154", "#482878", "#3e4a89", "#31688e", "#26828e",
              "#1f9e89", "#35b779", "#6dcd59", "#b4de2c", "#fde725"],
      description: "The saltiest open water (yellow-green) is in the subtropics, and enclosed seas " +
                   "such as the Red Sea and the Mediterranean are saltier still, up to about 40. " +
                   "The freshest water (purple) is near large rivers and in the Arctic and the Baltic Sea."
    },
    // Total alkalinity (GLODAP): ColorBrewer "YlGnBu", light yellow for low to dark blue for high.
    // The scale covers almost all open ocean; river-fed coasts go below it and get the end color.
    alkalinity: {
      label: "Surface total alkalinity", unit: "µmol/kg", digits: 0, marked: true,
      min: 2000, max: 2450, minLabel: "≤ 2000", maxLabel: "≥ 2450", ticks: [2100, 2200, 2300, 2400],
      stops: ["#ffffd9", "#edf8b1", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#253494", "#081d58"],
      description: "Alkalinity is seawater's capacity to neutralize acid: with more of it, the same CO₂ leaves more " +
                   "carbonate ions and a higher Ω. It follows salinity. It is highest (dark blue) in the salty " +
                   "subtropics and in the Mediterranean, up to about 2600 µmol/kg, and lowest (yellow) " +
                   "where rivers freshen the sea, down to about 1100 off the Lena River in the Siberian Arctic. " +
                   "Striped gray: no data, mainly Hudson Bay, the Gulf of Mexico, the Red Sea, parts of the " +
                   "Caribbean, the Beaufort Sea and the water around the North Pole, and the Black Sea, the Baltic " +
                   "and the Persian Gulf, which were hardly measured."
    },
    // Aragonite saturation: diverging around Ω = 1, red below (corrosive to shells), near white at 1,
    // blue above. The stops are 0.5 apart, so the third one (index 2) sits exactly at Ω = 1. The scale
    // is fixed, so a color means the same Ω at every CO2. Ω itself depends on CO2, so this layer has
    // no fixed description: describeOmega() writes one for the current CO2.
    omega: {
      label: "Aragonite saturation", unit: "", prefix: "Ω ", digits: 2, marked: true,
      min: 0, max: 4.5, minLabel: "0", maxLabel: "≥ 4.5", ticks: [1, 2, 3],
      stops: ["#b2182b", "#ef8a62", "#f7f7f7", "#d1e5f0", "#b2d4e8", "#92c5de", "#6aaad1", "#4393c3", "#2166ac", "#053061"],
      tooFresh: [140, 140, 140],         // too fresh for the model (salinity below SAL_MIN): no Ω
      description: ""
    }
  };
  var SAL_MIN = 20;                    // the calculator's lowest salinity; below it fixed alkalinity is far off
  var PLAIN_DESCRIPTION = "Ocean is blue and land is tan. Grid cells with no data also show as tan.";
  var LAND = [196, 191, 174];          // land, and ocean the data does not cover
  var NO_ALK_STRIPES = [[150, 150, 150], [105, 105, 105]];   // ocean with no alkalinity data: gray stripes
  var PLAIN_OCEAN = [44, 108, 160];    // the "plain" view

  var LUT_SIZE = 512;                  // colors are looked up in a table of this many steps

  function hexToRgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  // A smooth color table: LUT_SIZE colors blended between the stops, r, g, b, r, g, b, ...
  function buildLut(stops) {
    var rgb = stops.map(hexToRgb);
    var lut = new Uint8Array(LUT_SIZE * 3);
    for (var i = 0; i < LUT_SIZE; i++) {
      var p = (i / (LUT_SIZE - 1)) * (rgb.length - 1);
      var k = Math.min(Math.floor(p), rgb.length - 2);
      var f = p - k;
      for (var c = 0; c < 3; c++) {
        lut[i * 3 + c] = Math.round(rgb[k][c] + (rgb[k + 1][c] - rgb[k][c]) * f);
      }
    }
    return lut;
  }

  var lutCache = {};
  function lutFor(layerName) {
    if (!lutCache[layerName]) lutCache[layerName] = buildLut(LAYERS[layerName].stops);
    return lutCache[layerName];
  }

  // The color [r, g, b] a layer gives to a value.
  function colorAt(layerName, value) {
    var layer = LAYERS[layerName], lut = lutFor(layerName);
    var p = (value - layer.min) / (layer.max - layer.min);
    p = p < 0 ? 0 : (p > 1 ? 1 : p);
    var i = Math.round(p * (LUT_SIZE - 1)) * 3;
    return [lut[i], lut[i + 1], lut[i + 2]];
  }

  // ---------- geometry ----------
  function wrapLon(lon) {
    return ((lon + 180) % 360 + 360) % 360 - 180;
  }

  // Which latitude and longitude does a spot on the globe show? x and y give the spot on the
  // disc, in units of the globe's radius (x to the right, y up). lat0 and lon0 are the point
  // at the center of the view, in degrees. Returns null for a spot off the globe.
  function viewToLatLon(x, y, lat0, lon0) {
    var rho2 = x * x + y * y;
    if (rho2 > 1) return null;
    var z = Math.sqrt(1 - rho2);                       // how directly the spot faces us
    var p0 = lat0 * DEG, s0 = Math.sin(p0), c0 = Math.cos(p0);
    return {
      lat: Math.asin(z * s0 + y * c0) / DEG,
      lon: wrapLon(lon0 + Math.atan2(x, z * c0 - y * s0) / DEG)
    };
  }

  // The other way round: where on the disc is a latitude and longitude? z > 0 means it faces us.
  function latLonToView(lat, lon, lat0, lon0) {
    var p = lat * DEG, dl = (lon - lon0) * DEG, p0 = lat0 * DEG;
    return {
      x: Math.cos(p) * Math.sin(dl),
      y: Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(dl),
      z: Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(dl)
    };
  }

  // ---------- the data grid ----------
  // The grid cell holding a latitude and longitude. Cells are 1 degree: column k covers
  // longitudes k-180 to k-179, row k covers latitudes k-90 to k-89.
  function cellIndex(lat, lon) {
    var col = Math.floor(wrapLon(lon) + 180);
    var row = Math.floor(lat + 90);
    if (col > NLON - 1) col = NLON - 1;
    if (row < 0) row = 0; else if (row > NLAT - 1) row = NLAT - 1;
    return row * NLON + col;
  }

  // A smooth value at a latitude and longitude: a blend of the four nearest cell centers,
  // leaving out cells with no data (NaN). Gives NaN when less than half of the blend has
  // data, which is also what rounds off the blocky coastline. The picture and the readout
  // both use this, so the number you read always matches the color under the pointer.
  // With `marked` (the Ω and alkalinity grids), negative values mark ocean with no value: FRESH
  // (too fresh for the model) or NO_ALK (no alkalinity data). They are left out of the blend like
  // missing data, and the result is the mark itself when marked cells make up most of the blend.
  var blend = { sum: 0, weight: 0, fresh: 0, gap: 0 };
  function addCell(v, w, marked) {
    if (v !== v) return;
    if (marked && v < 0) { if (v === NO_ALK) blend.gap += w; else blend.fresh += w; return; }
    blend.sum += w * v; blend.weight += w;
  }
  function sampleSmooth(values, lat, lon, marked) {
    var gx = wrapLon(lon) + 179.5;                     // whole numbers are cell centers
    var gy = lat + 89.5;
    var x0 = Math.floor(gx), y0 = Math.floor(gy);
    var fx = gx - x0, fy = gy - y0;
    var xa = x0 < 0 ? NLON - 1 : x0;
    var xb = x0 + 1 >= NLON ? 0 : x0 + 1;
    var ya = y0 < 0 ? 0 : (y0 > NLAT - 1 ? NLAT - 1 : y0);
    var yb = y0 + 1 < 0 ? 0 : (y0 + 1 > NLAT - 1 ? NLAT - 1 : y0 + 1);
    blend.sum = 0; blend.weight = 0; blend.fresh = 0; blend.gap = 0;
    addCell(values[ya * NLON + xa], (1 - fx) * (1 - fy), marked);
    addCell(values[ya * NLON + xb], fx * (1 - fy), marked);
    addCell(values[yb * NLON + xa], (1 - fx) * fy, marked);
    addCell(values[yb * NLON + xb], fx * fy, marked);
    var weight = blend.weight, marks = blend.fresh + blend.gap;
    if (weight + marks < 0.5) return NaN;               // mostly land or no data
    if (marks > weight) return blend.fresh >= blend.gap ? FRESH : NO_ALK;
    return blend.sum / weight;
  }

  // ---------- drawing the globe ----------
  // Fill `out` (a Uint32Array of size * size pixels, each 0xAABBGGRR) with the globe as seen
  // from lat0, lon0, zoomed by `zoom`. `grid` holds the values to color (NaN means none).
  // `layerName` picks the color scale, or is null for the plain Earth, where `grid` just
  // marks the ocean.
  function renderGlobe(out, size, lat0, lon0, zoom, grid, layerName) {
    var half = size / 2, radius = half * 0.94 * zoom;
    var p0 = lat0 * DEG, s0 = Math.sin(p0), c0 = Math.cos(p0);
    var layer = layerName ? LAYERS[layerName] : null;
    var lut = layer ? lutFor(layerName) : null;
    var perStep = layer ? (LUT_SIZE - 1) / (layer.max - layer.min) : 0;
    var marked = !!(layer && layer.marked);
    var stripe = Math.max(2, Math.round(size / 100));  // width of the "no alkalinity data" stripes, in pixels
    var i = 0;
    for (var py = 0; py < size; py++) {
      var y = (half - (py + 0.5)) / radius;
      for (var px = 0; px < size; px++, i++) {
        var x = (px + 0.5 - half) / radius;
        var rho2 = x * x + y * y;
        if (rho2 >= 1) { out[i] = 0; continue; }       // off the globe: transparent
        var z = Math.sqrt(1 - rho2);
        var lat = Math.asin(z * s0 + y * c0) / DEG;
        var lon = lon0 + Math.atan2(x, z * c0 - y * s0) / DEG;
        var v = sampleSmooth(grid, lat, lon, marked);
        var r, g, b;
        if (v !== v) {
          r = LAND[0]; g = LAND[1]; b = LAND[2];
        } else if (v < 0 && marked) {                   // ocean with no value: say why by its look
          var mark = v === NO_ALK ? NO_ALK_STRIPES[Math.floor((px + py) / stripe) & 1] : layer.tooFresh;
          r = mark[0]; g = mark[1]; b = mark[2];
        } else if (layer) {
          var k = (v - layer.min) * perStep;
          k = k < 0 ? 0 : (k > LUT_SIZE - 1 ? LUT_SIZE - 1 : k);
          k = ((k + 0.5) | 0) * 3;
          r = lut[k]; g = lut[k + 1]; b = lut[k + 2];
        } else {
          r = PLAIN_OCEAN[0]; g = PLAIN_OCEAN[1]; b = PLAIN_OCEAN[2];
        }
        var shade = 0.75 + 0.25 * z;                   // a little darker at the edge, so it looks round
        out[i] = 0xFF000000 | ((b * shade) << 16) | ((g * shade) << 8) | (r * shade);
      }
    }
  }

  function formatLat(lat) {
    var r = Math.round(lat * 10) / 10;
    return Math.abs(r).toFixed(1) + "°" + (r >= 0 ? "N" : "S");
  }
  function formatLon(lon) {
    var r = Math.round(wrapLon(lon) * 10) / 10;
    return Math.abs(r).toFixed(1) + "°" + (r >= 0 ? "E" : "W");
  }
  // A value with its unit, "25.6 °C" (or "Ω 2.34"). A tiny negative number is shown as 0, not "-0.0".
  function formatValue(value, layer) {
    var text = value.toFixed(layer.digits);
    if (Number(text) === 0) text = (0).toFixed(layer.digits);
    return (layer.prefix || "") + text + (layer.unit ? " " + layer.unit : "");
  }

  // Ω for every cell at `co2` ppm: NaN where there is no data, FRESH where the water is too fresh
  // for the model (salinity below SAL_MIN). With an `alkalinity` grid (µmol/kg), each cell uses its
  // own alkalinity instead of the fixed 2300, and cells without one are NO_ALK. Also the share of
  // the ocean surface below Ω = 1, by area (a cell's area goes with the cosine of its latitude),
  // counting only cells with an Ω.
  function omegaGrid(co2, temperature, salinity, chem, alkalinity) {
    var grid = new Float32Array(temperature.length), area = 0, corrosive = 0;
    for (var n = 0; n < grid.length; n++) {
      var t = temperature[n], s = salinity[n];
      if (t !== t || s !== s) { grid[n] = NaN; continue; }
      if (s < SAL_MIN) { grid[n] = FRESH; continue; }
      var alk;
      if (alkalinity) {
        if (!(alkalinity[n] > 0)) { grid[n] = NO_ALK; continue; }
        alk = alkalinity[n] * 1e-6;
      }
      var omega = chem.carbonate(co2, t, s, alk).omega;
      grid[n] = omega;
      var w = Math.cos(((Math.floor(n / NLON)) - 89.5) * DEG);
      area += w;
      if (omega < 1) corrosive += w;
    }
    return { grid: grid, co2: co2, local: !!alkalinity, corrosiveShare: area > 0 ? corrosive / area : 0 };
  }

  // The words for the Ω layer at one CO2.
  function describeOmega(o) {
    var pct = o.corrosiveShare * 100;
    var share = pct === 0 ? "none" : pct < 0.1 ? "less than 0.1%" : (pct < 10 ? pct.toFixed(1) : Math.round(pct)) + "%";
    return "At " + Math.round(o.co2) + " ppm CO₂" + (o.local ? " with each spot's own alkalinity (GLODAP)" : "") + ", " + share +
           " of the ocean surface has Ω below 1 (red), where seawater dissolves aragonite shells. " +
           "Ω is lowest in cold polar water and highest in the warm tropics. " +
           "Near the poles the real Ω is likely higher than shown: the surface water there holds less CO₂ than the air would put in it. " +
           "Gray water is too fresh for this model (salinity below " + SAL_MIN + ")" +
           (o.local ? "." : "; below about 30 the real Ω is likely lower than shown.") +   // with local alkalinity, already shown
           (o.local ? " Striped gray: no alkalinity data, so no Ω." : "");
  }

  // Turn the alkalinity file's list into a grid: the value, NO_ALK for ocean (where `ocean` is 1)
  // that GLODAP leaves out, NaN elsewhere.
  function alkalinityGrid(list, ocean) {
    var a = new Float32Array(list.length);
    for (var n = 0; n < list.length; n++) a[n] = list[n] !== null ? list[n] : (ocean[n] === 1 ? NO_ALK : NaN);
    return a;
  }

  // ---------- the page ----------
  function start() {
    var canvas = document.getElementById("globe");
    var statusEl = document.getElementById("globe-status");
    if (!canvas || !statusEl) return;
    statusEl.hidden = false;
    statusEl.textContent = "Loading ocean data…";

    var off = document.createElement("canvas");        // the globe is drawn here, then scaled up
    var ctx = canvas.getContext && canvas.getContext("2d");
    var offCtx = off.getContext && off.getContext("2d");
    if (!ctx || !offCtx) { statusEl.textContent = "Your browser can't draw the globe."; return; }

    var readoutEl = document.getElementById("globe-readout");
    var centerEl = document.getElementById("globe-center");
    var descriptionEl = document.getElementById("globe-description");
    var announceEl = document.getElementById("globe-announce");
    var pickEl = document.getElementById("globe-pick");
    var pickLink = document.getElementById("globe-pick-link");
    var pickEstimateEl = document.getElementById("globe-pick-estimate");
    var legendEl = document.getElementById("globe-legend");
    var legendTitle = document.getElementById("legend-title");
    var legendBar = document.getElementById("legend-bar");
    var legendTicks = document.getElementById("legend-ticks");
    var tooFreshEl = document.getElementById("legend-too-fresh");
    var noAlkEl = document.getElementById("legend-no-alk");
    var useAlkEl = document.getElementById("use-alk");    // the calculator's "Use local alkalinity" box
    var HINT = "Hover for a value. Click or tap a spot to use it in the calculator.";

    var HOME = { lat: 20, lon: -160, zoom: 1 };        // the Pacific, with Hawaii near the middle
    var state = { lat: HOME.lat, lon: HOME.lon, zoom: HOME.zoom, layer: "temperature" };
    var grids = null;                                  // filled in when the data arrives
    var reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    var image = null, pixels = null;
    var picked = null;           // the spot the calculator was last set from: { lat, lon, temperature, salinity, exact }
    var applying = false;        // true while we move the calculator's sliders ourselves
    var awaiting = false;        // true while we wait for the calculator's estimate for that spot
    var co2Year = null;          // the year picked on the CO2 graph, { year, ppm }, while the calculator uses it
    var resultText = "";         // the calculator's latest result for the picked spot
    var loadFailed = false;      // true if the ocean data could not be loaded
    var alkList = null;          // the alkalinity file's values, until the ocean data is here to make a grid
    var alkFailed = false;       // true if the alkalinity data could not be loaded

    function globeRadius(width) { return width / 2 * 0.94 * state.zoom; }

    function drawHalo(full) {
      if (state.zoom > 1.05) return;
      var c = full / 2, r = globeRadius(full);
      var g = ctx.createRadialGradient(c, c, r * 0.97, c, c, r * 1.07);
      g.addColorStop(0, "rgba(130, 185, 255, 0.5)");
      g.addColorStop(1, "rgba(130, 185, 255, 0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(c, c, r * 1.07, 0, 2 * Math.PI); ctx.fill();
    }

    // Faint lines every 30 degrees, drawn as crisp vectors on top of the pixels.
    function drawGraticule(full) {
      var c = full / 2, r = globeRadius(full);
      ctx.save();
      ctx.beginPath(); ctx.arc(c, c, r, 0, 2 * Math.PI); ctx.clip();
      ctx.lineWidth = Math.max(1, full / 520);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
      ctx.beginPath();
      function trace(points) {
        var pen = false;
        for (var n = 0; n < points.length; n++) {
          var q = latLonToView(points[n][0], points[n][1], state.lat, state.lon);
          if (q.z <= 0) { pen = false; continue; }
          var px = c + q.x * r, py = c - q.y * r;
          if (pen) ctx.lineTo(px, py); else ctx.moveTo(px, py);
          pen = true;
        }
      }
      var line, lat, lon;
      for (lon = -180; lon < 180; lon += 30) {
        line = []; for (lat = -90; lat <= 90; lat += 3) line.push([lat, lon]); trace(line);
      }
      for (lat = -60; lat <= 60; lat += 30) {
        line = []; for (lon = -180; lon <= 180; lon += 3) line.push([lat, lon]); trace(line);
      }
      ctx.stroke();
      ctx.restore();
      ctx.lineWidth = Math.max(1, full / 400);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
      ctx.beginPath(); ctx.arc(c, c, r, 0, 2 * Math.PI); ctx.stroke();   // smooths the rim
    }

    // A ring on the spot the calculator was set from, so you can see which spot it is. It is
    // drawn before the grid lines, so the rim stays the last thing drawn.
    function drawMarker(full) {
      if (!picked) return;
      var q = latLonToView(picked.lat, picked.lon, state.lat, state.lon);
      if (q.z <= 0.02) return;                         // round the back of the globe
      var c = full / 2, r = globeRadius(full);
      var x = c + q.x * r, y = c - q.y * r, size = Math.max(6, full / 60), line = Math.max(2, full / 260);
      ctx.save();
      ctx.lineWidth = line * 3; ctx.strokeStyle = "rgba(0, 0, 0, 0.65)";        // a dark outline, so the ring shows on any color
      ctx.beginPath(); ctx.arc(x, y, size, 0, 2 * Math.PI); ctx.stroke();
      ctx.lineWidth = line; ctx.strokeStyle = "#ffffff";
      ctx.beginPath(); ctx.arc(x, y, size, 0, 2 * Math.PI); ctx.stroke();
      ctx.restore();
    }

    // ---- words for a spot on the globe ----
    function whereText(lat, lon) { return formatLat(lat) + ", " + formatLon(lon); }
    // The value at a spot as text ("25.6 °C"), or null when this layer has nothing there.
    function valueAt(lat, lon) {
      if (state.layer === "plain") return sampleSmooth(grids.ocean, lat, lon) === 1 ? "ocean" : null;
      var layer = LAYERS[state.layer], v = sampleSmooth(gridFor(state.layer), lat, lon, layer.marked);
      if (v !== v) return null;
      if (v === FRESH) return "too fresh to estimate Ω";             // the blend leans on marked cells
      if (v === NO_ALK) return state.layer === "omega" ? "no alkalinity data, so no Ω" : "no alkalinity data";
      return formatValue(v, layer);
    }
    // Is the calculator's "Use local alkalinity" box ticked? Then the Ω layer uses GLODAP's values too, once loaded.
    function wantLocal() { return !!(useAlkEl && useAlkEl.checked); }
    function useLocal() { return wantLocal() && !!(grids && grids.alkalinity); }
    // The calculator's CO2 now (the Ω layer follows it), or 425 ppm when there is no calculator.
    function currentCo2() {
      var el = document.getElementById("co2"), v = el ? Number(el.value) : NaN;
      return v > 0 ? v : 425;
    }
    var omega = null;            // the Ω grid, worked out when the Ω layer is shown, again when CO2 changes
    function gridFor(name) {
      if (name !== "omega") return grids[name];
      var co2 = currentCo2(), local = useLocal();
      if (!omega || omega.co2 !== co2 || omega.local !== local) {
        omega = omegaGrid(co2, grids.temperature, grids.salinity, OceanChem, local ? grids.alkalinity : null);
      }
      return omega.grid;
    }
    function omegaNow() { gridFor("omega"); return omega; }

    function centerText() {
      var v = valueAt(state.lat, state.lon);
      return "Center of the view: " + whereText(state.lat, state.lon) + ", " + (v === null ? "land or no data" : v);
    }

    function draw(quality) {
      if (!grids) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var full = Math.max(200, Math.round(canvas.clientWidth * dpr));
      if (canvas.width !== full || canvas.height !== full) { canvas.width = full; canvas.height = full; }
      var size = Math.max(96, Math.round(full * quality));
      if (!pixels || off.width !== size) {              // (a new canvas starts at 300 x 150, so test for no pixels too)
        off.width = size; off.height = size;
        image = offCtx.createImageData(size, size);
        pixels = new Uint32Array(image.data.buffer);
      }
      var plain = state.layer === "plain";
      renderGlobe(pixels, size, state.lat, state.lon, state.zoom,
                  plain ? grids.ocean : gridFor(state.layer), plain ? null : state.layer);
      offCtx.putImageData(image, 0, 0);
      ctx.clearRect(0, 0, full, full);
      drawHalo(full);
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(off, 0, 0, full, full);
      drawMarker(full);
      drawGraticule(full);
      centerEl.textContent = centerText();
    }

    // Drawing is batched: ask for a redraw as often as you like, it happens once per frame.
    // While the globe is moving it is drawn at a lower resolution, then sharpened when it rests.
    var frame = 0, settle = 0, wantQuality = 1;
    function requestDraw(moving) {
      wantQuality = moving ? 0.5 : 1;
      if (!frame) {
        frame = requestAnimationFrame(function () { frame = 0; draw(wantQuality); });
      }
      clearTimeout(settle);
      if (moving) settle = setTimeout(function () { requestDraw(false); }, 160);
    }

    function turn(dLon, dLat) {
      state.lon = wrapLon(state.lon + dLon);
      state.lat = Math.max(-90, Math.min(90, state.lat + dLat));
    }
    function zoomBy(factor) {
      state.zoom = Math.max(1, Math.min(4, state.zoom * factor));
      requestDraw(true);
    }

    // For people using a screen reader: say where the view is and what is there, a moment
    // after they stop pressing buttons (never while someone is dragging).
    var announceTimer = 0;
    function announceSoon() {
      clearTimeout(announceTimer);
      announceTimer = setTimeout(function () {
        if (!grids) return;
        var layer = LAYERS[state.layer];
        announceEl.textContent = (layer ? layer.label : "Plain globe") + ". " + centerText() +
          (state.zoom > 1.05 ? ". Zoom " + state.zoom.toFixed(1) + " times." : ".");
      }, 400);
    }

    // ---- sending a spot to the calculator ----
    // Sets the calculator's temperature and salinity sliders to the data at a spot, then tells the
    // calculator by sending the same "input" event a drag would. The sliders are found by their ids
    // ("temp" and "sal") and their limits are read from the page, so they cannot drift apart.
    // Carbon dioxide is in the air, not the water, so it is left alone.
    function setSlider(id, value) {
      var el = document.getElementById(id);
      if (!el) return null;
      var low = Number(el.min), high = Number(el.max);
      var shown = Math.round(value * 10) / 10;                     // the sliders show one decimal
      var inRange = Math.max(low, Math.min(high, shown));
      applying = true;
      try {
        el.value = String(inRange);                                // the browser snaps this to the slider's step
        el.dispatchEvent(new Event("input", { bubbles: true }));
      } finally {
        applying = false;
      }
      return { value: Number(el.value), outOfRange: inRange !== shown, low: low, high: high };
    }

    function showPick(text, linked) {
      pickEl.textContent = text;
      resultText = "";
      showEstimate();
      pickLink.hidden = !linked;
    }

    // The line after the spot: the CO2 year (if one is picked on the graph), then the result.
    function showEstimate() {
      if (!awaiting || !picked) { pickEstimateEl.textContent = ""; return; }
      var year = !co2Year ? "" : co2Year.pathway
        ? "On pathway " + co2Year.pathway + ", atmospheric CO₂ in " + co2Year.year + " would be " + co2Year.ppm.toFixed(1) + " ppm."
        : "Atmospheric CO₂ in " + co2Year.year + " was " + co2Year.ppm.toFixed(1) + " ppm.";
      pickEstimateEl.textContent = [year, resultText].filter(Boolean).join(" ");
    }

    function sendToCalculator(lat, lon) {
      awaiting = false;
      if (!grids) {
        showPick(loadFailed ? "The ocean data couldn't be loaded, so the calculator was not changed. Reload the page to try again."
                            : "The ocean data hasn't loaded yet.", false);
        return;
      }
      var where = whereText(lat, lon);
      var t = sampleSmooth(grids.temperature, lat, lon), s = sampleSmooth(grids.salinity, lat, lon);
      if (t !== t || s !== s) {                        // the calculator needs both, so change neither
        showPick((t !== t && s !== s ? "Land or no data" : (t !== t ? "No temperature data" : "No salinity data")) +
                 " at " + where + ", so the calculator was not changed.", false);
        return;
      }
      var salSlider = document.getElementById("sal");
      if (!salSlider || !document.getElementById("temp")) { showPick("The calculator isn't on this page.", false); return; }
      var salLow = Number(salSlider.min), salHigh = Number(salSlider.max), sShown = Math.round(s * 10) / 10;
      if (sShown < salLow || sShown > salHigh) {      // brackish water: the model's equations don't hold, so leave it alone
        showPick("Salinity at " + where + " is " + formatValue(s, LAYERS.salinity) + ", outside this calculator's range (" +
                 salLow + " to " + salHigh + " PSU), so the calculator was not changed.", false);
        return;
      }
      var tempSet = setSlider("temp", t), salSet = setSlider("sal", s);
      var notes = [], alk = null, measured = false;
      if (wantLocal() && document.getElementById("alk")) {        // also set the alkalinity slider, from GLODAP
        var a = grids.alkalinity ? sampleSmooth(grids.alkalinity, lat, lon, true) : NaN;
        measured = a > 0;
        if (measured) {
          alk = setSlider("alk", a).value;
          notes.push("GLODAP alkalinity there is " + Math.round(alk) + " µmol/kg.");
        } else {
          alk = setSlider("alk", 2300).value;
          notes.push(alkFailed ? "The alkalinity data couldn't be loaded, so the calculator uses 2300 µmol/kg."
            : !grids.alkalinity ? "The alkalinity data is still loading, so for now the calculator uses 2300 µmol/kg."
            : "There is no alkalinity data for this spot (striped gray on the Alkalinity map), so the calculator uses 2300 µmol/kg.");
        }
      }
      if (tempSet.outOfRange) {                        // only a few cells, by less than half a degree
        notes.push("That temperature is just outside the calculator's range (" + tempSet.low + " to " + tempSet.high +
                   " °C), so it uses " + tempSet.value.toFixed(1) + " °C.");
      }
      if (salSet.value < 30 && !measured) {                         // with measured alkalinity this warning is moot
        notes.push("Below 30 PSU the real alkalinity is probably lower than the model's 2300 µmol/kg, " +
                   "so treat the pH and Ω as a what-if: the real Ω is likely lower.");
      }
      if (Math.abs(lat) >= 60) {
        notes.push("Polar surface water usually holds less CO₂ than the air would put in it, which makes the real Ω higher than the model's.");
      }
      picked = { lat: lat, lon: lon, temperature: tempSet.value, salinity: salSet.value, alkalinity: alk };
      awaiting = true;                                 // follow the calculator's estimates while it matches this spot
      showPick("At " + where + ", average annual temperature is " + formatValue(t, { digits: 1, unit: "°C" }) +
               " and salinity is " + salSet.value.toFixed(1) + " PSU." + (notes.length ? " " + notes.join(" ") : ""), true);
      requestDraw(false);                              // to put the ring on the globe
    }

    // The calculator reports each estimate (also after CO₂ moves). While it still matches the spot,
    // show it under the globe. This text is not a live region: the calculator already reads it out.
    window.addEventListener("estimate", function (e) {
      var d = e.detail;
      if (!awaiting || !picked || !d) return;
      if (d.error) { resultText = "The calculator couldn't get an estimate; click the spot again to retry."; showEstimate(); return; }
      if (typeof d.pH !== "number") return;
      if (Math.abs(d.temp - picked.temperature) > 0.05 || Math.abs(d.sal - picked.salinity) > 0.05) return;   // not for this spot
      if (picked.alkalinity !== null && !(Math.abs(d.alk - picked.alkalinity) <= 0.5)) return;          // nor this one
      var co2El = document.getElementById("co2");
      if (co2El && Math.round(d.co2) !== Number(co2El.value)) return;   // a late answer for an older CO2
      resultText = "Result: pH " + d.pH.toFixed(3) + ", Ω " + d.omega.toFixed(2) + ".";
      showEstimate();
    });

    // The CO2 graph says when a year is picked ({ year, ppm }) or no longer used (null). The CO2
    // changed, so the old result is out of date until the calculator's next estimate.
    window.addEventListener("co2year", function (e) {
      var d = e.detail;
      co2Year = d && typeof d.year === "number" && typeof d.ppm === "number"
        ? { year: d.year, ppm: d.ppm, pathway: typeof d.pathway === "string" ? d.pathway : null } : null;
      resultText = "";
      showEstimate();
    });

    // If someone moves the temperature or salinity slider themselves, the calculator no longer
    // matches that spot, so take the ring and the message away.
    ["temp", "sal", "alk"].forEach(function (id) {
      var slider = document.getElementById(id);
      if (!slider) return;
      slider.addEventListener("input", function () {
        if (applying || !picked) return;
        picked = null; awaiting = false;
        showPick("", false);
        requestDraw(false);
      });
    });

    // ---- layers and the legend ----
    function applyLayer() {
      var layer = LAYERS[state.layer];
      canvas.setAttribute("aria-label", "Globe colored by " + (layer ? layer.label.toLowerCase() : "nothing: plain Earth"));
      var isOmega = state.layer === "omega";
      var description = !layer ? PLAIN_DESCRIPTION : isOmega ? (grids ? describeOmega(omegaNow()) : "Loading…") : layer.description;
      if (isOmega && grids && wantLocal() && !grids.alkalinity) {
        description += alkFailed ? " The alkalinity data couldn't be loaded, so this uses the fixed 2300 µmol/kg."
                                 : " The alkalinity data is still loading, so for now this uses the fixed 2300 µmol/kg.";
      }
      descriptionEl.textContent = description;
      legendEl.hidden = !layer;
      if (tooFreshEl) tooFreshEl.hidden = !isOmega;
      if (noAlkEl) noAlkEl.hidden = !(state.layer === "alkalinity" || (isOmega && useLocal()));
      if (!layer) return;
      legendTitle.textContent = isOmega
        ? "Aragonite saturation Ω at " + Math.round(currentCo2()) + " ppm CO₂" + (useLocal() ? ", GLODAP alkalinity" : "")
        : layer.label + " (" + layer.unit + ")";
      legendBar.style.background = "linear-gradient(to right, " + layer.stops.join(", ") + ")";
      legendTicks.textContent = "";
      function label(text, fraction, cls) {
        var span = document.createElement("span");
        span.textContent = text;
        if (cls) span.className = cls; else span.style.left = (fraction * 100) + "%";
        legendTicks.appendChild(span);
      }
      label(layer.minLabel, 0, "min");
      layer.ticks.forEach(function (t) { label(String(t), (t - layer.min) / (layer.max - layer.min)); });
      label(layer.maxLabel, 1, "max");
    }

    // ---- reading a value under the pointer ----
    function latLonAt(e) {
      var rect = canvas.getBoundingClientRect();
      var half = rect.width / 2, radius = globeRadius(rect.width);
      return viewToLatLon((e.clientX - rect.left - half) / radius, (half - (e.clientY - rect.top)) / radius,
                          state.lat, state.lon);
    }
    function showReadout(e) {
      if (!grids) return;
      var p = latLonAt(e);
      if (!p) { readoutEl.textContent = HINT; return; }
      var v = valueAt(p.lat, p.lon);
      var text = v === null ? "Land or no data" : v;
      readoutEl.textContent = text.charAt(0).toUpperCase() + text.slice(1) + " at " + whereText(p.lat, p.lon);
    }

    // ---- dragging: turns the globe roughly in step with your finger (exactly so only near
    // the middle of the equator; near the poles it lags, because the lines of longitude crowd together) ----
    var drag = null, glide = 0;
    function stopGlide() { cancelAnimationFrame(glide); glide = 0; }

    canvas.addEventListener("pointerdown", function (e) {
      if (drag) return;                                // a second finger or button is ignored
      if (e.pointerType === "mouse" && (e.button !== 0 || e.ctrlKey)) return;   // only the plain left button drags
      stopGlide();
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, t: e.timeStamp, vLon: 0, vLat: 0, moved: false };
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* not fatal */ }
      canvas.classList.add("dragging");
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!drag || e.pointerId !== drag.id) {
        if (!drag && e.pointerType === "mouse") showReadout(e);
        return;
      }
      if (e.pointerType === "mouse" && e.buttons === 0) { endDrag(e); return; }   // the button was let go elsewhere
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 4) return;   // a tiny wobble is a tap, not a drag
      drag.moved = true;
      var perPixel = 1 / DEG / globeRadius(canvas.clientWidth);
      var dLon = -dx * perPixel, dLat = dy * perPixel;
      var dt = Math.max(1, e.timeStamp - drag.t);
      drag.vLon = 0.8 * drag.vLon + 0.2 * (dLon / dt);     // degrees per millisecond, smoothed
      drag.vLat = 0.8 * drag.vLat + 0.2 * (dLat / dt);
      drag.x = e.clientX; drag.y = e.clientY; drag.t = e.timeStamp;
      turn(dLon, dLat);
      requestDraw(true);
    });
    function endDrag(e, cancelled) {
      if (!drag || e.pointerId !== drag.id) return;
      var finished = drag; drag = null;
      canvas.classList.remove("dragging");
      if (!finished.moved) {                               // a click or tap: read the value there and send it to the calculator
        if (cancelled) return;                             // the touch was taken over (by scrolling, say): not a tap
        showReadout(e);
        var spot = grids && latLonAt(e);
        if (spot) sendToCalculator(spot.lat, spot.lon);
        return;
      }
      var speed = Math.hypot(finished.vLon, finished.vLat);
      if (reduceMotion || speed < 0.02 || e.timeStamp - finished.t > 80) { requestDraw(false); return; }
      var vLon = finished.vLon, vLat = finished.vLat, last = performance.now();
      (function coast(now) {
        var dt = Math.max(0, Math.min(50, now - last)); last = now;
        turn(vLon * dt, vLat * dt);
        var decay = Math.pow(0.94, dt / 16);
        vLon *= decay; vLat *= decay;
        if (Math.hypot(vLon, vLat) < 0.005) { glide = 0; requestDraw(false); return; }
        requestDraw(true);
        glide = requestAnimationFrame(coast);
      })(last);
    }
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", function (e) { endDrag(e, true); });
    canvas.addEventListener("pointerleave", function (e) {
      if (!drag && e.pointerType === "mouse") readoutEl.textContent = HINT;
    });

    // ctrl + scroll (also how a laptop trackpad pinch arrives) zooms; plain scrolling still scrolls the page.
    // One wheel notch is one zoom step, whatever unit the browser reports in.
    canvas.addEventListener("wheel", function (e) {
      if (!e.ctrlKey) return;
      e.preventDefault();
      var delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;   // lines to pixels
      zoomBy(Math.pow(1.25, -Math.max(-100, Math.min(100, delta)) / 100));
    }, { passive: false });

    // ---- buttons: everything the mouse can do, without dragging ----
    function press(id, action) {
      document.getElementById(id).addEventListener("click", function () {
        stopGlide(); action(); requestDraw(true); announceSoon();
      });
    }
    press("globe-west", function () { turn(-10, 0); });
    press("globe-east", function () { turn(10, 0); });
    press("globe-north", function () { turn(0, 10); });
    press("globe-south", function () { turn(0, -10); });
    press("globe-zoom-in", function () { zoomBy(1.25); });
    press("globe-zoom-out", function () { zoomBy(0.8); });
    press("globe-reset", function () { state.lat = HOME.lat; state.lon = HOME.lon; state.zoom = HOME.zoom; });
    // The same thing as clicking, for people who cannot click on the globe: use the spot in the middle of the view.
    document.getElementById("globe-use-center").addEventListener("click", function () {
      sendToCalculator(state.lat, state.lon);
    });

    var alkRadio = null;
    Array.prototype.forEach.call(document.querySelectorAll('input[name="layer"]'), function (radio) {
      if (radio.value === "omega" && typeof OceanChem === "undefined") { radio.disabled = true; return; }   // chem.js did not load
      if (radio.value === "alkalinity") {                     // off until its data arrives
        radio.disabled = true; alkRadio = radio;
        if (radio.checked) {                                  // (a browser may bring back a choice from before a reload)
          radio.checked = false;
          var first = document.getElementById("layer-temperature");
          if (first) first.checked = true;
        }
      }
      radio.addEventListener("change", function () {
        if (!radio.checked) return;
        state.layer = radio.value; applyLayer(); readoutEl.textContent = HINT;
        requestDraw(false); announceSoon();
      });
      if (radio.checked) state.layer = radio.value;
    });

    // The Ω layer follows the calculator's CO2 (moved by hand, or by picking a year on the CO2 graph).
    var co2El = document.getElementById("co2");
    if (co2El) co2El.addEventListener("input", function () {
      if (state.layer !== "omega" || !grids) return;
      applyLayer(); requestDraw(false);
    });

    // Ticking or clearing "Use local alkalinity": the Ω layer switches, and a picked spot is sent again,
    // so the calculator gets (or drops) that spot's alkalinity.
    if (useAlkEl) useAlkEl.addEventListener("change", function () {
      if (picked && grids) sendToCalculator(picked.lat, picked.lon);
      if (state.layer === "omega" && grids) { applyLayer(); requestDraw(false); }
    });

    // The alkalinity grid is made once both files are here (it needs to know which cells are ocean).
    function alkalinityReady() {
      if (!grids || !alkList) return;
      grids.alkalinity = alkalinityGrid(alkList, grids.ocean);
      alkList = null;
      if (alkRadio) alkRadio.disabled = false;
      if (picked && wantLocal()) sendToCalculator(picked.lat, picked.lon);   // it was given 2300 while the data loaded
      if (state.layer === "omega") { applyLayer(); requestDraw(false); }
    }

    if (window.ResizeObserver) new ResizeObserver(function () { requestDraw(false); }).observe(canvas);
    else window.addEventListener("resize", function () { requestDraw(false); });

    applyLayer();
    readoutEl.textContent = HINT;

    fetch(DATA_URL)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        if (!(data.scale > 0) || !data.temperature_c || !data.salinity_psu ||
            data.temperature_c.length !== NLON * NLAT || data.salinity_psu.length !== NLON * NLAT) {
          throw new Error("unexpected data");
        }
        function toGrid(list) {
          var a = new Float32Array(list.length);
          for (var n = 0; n < list.length; n++) a[n] = list[n] === null ? NaN : list[n] * data.scale;
          return a;
        }
        var temperature = toGrid(data.temperature_c), salinity = toGrid(data.salinity_psu);
        var ocean = new Float32Array(temperature.length);   // 1 where either layer has data, else NaN
        for (var n = 0; n < ocean.length; n++) {
          ocean[n] = (temperature[n] === temperature[n] || salinity[n] === salinity[n]) ? 1 : NaN;
        }
        grids = { temperature: temperature, salinity: salinity, ocean: ocean };
        alkalinityReady();
        statusEl.textContent = "";
        statusEl.hidden = true;
        if (state.layer === "omega") applyLayer();     // its description needs the data
        requestDraw(false);
      })
      .catch(function () {
        loadFailed = true;
        statusEl.hidden = false;
        statusEl.textContent = "Couldn't load the ocean data. Reload the page to try again.";
      });

    fetch(ALK_URL)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        var list = data && data.alkalinity_umol_kg;
        if (!list || list.length !== NLON * NLAT) throw new Error("unexpected data");
        alkList = list;
        alkalinityReady();
      })
      .catch(function () {
        alkFailed = true;                    // the Alkalinity button stays off; the Ω layer keeps the fixed 2300
        if (picked && wantLocal()) sendToCalculator(picked.lat, picked.lon);   // "still loading" becomes "couldn't be loaded"
        if (state.layer === "omega" && grids) applyLayer();
      });
  }

  // The page loads this script with `defer`, so the page is ready; in a test there is no page.
  if (typeof document !== "undefined") {
    try {
      start();
    } catch (err) {
      var failed = document.getElementById("globe-status");
      if (failed) { failed.hidden = false; failed.textContent = "The globe could not start. Reload the page to try again."; }
    }
  }

  return {
    LAYERS: LAYERS, LAND: LAND, PLAIN_OCEAN: PLAIN_OCEAN, NLON: NLON, NLAT: NLAT,
    wrapLon: wrapLon, viewToLatLon: viewToLatLon, latLonToView: latLonToView,
    cellIndex: cellIndex, sampleSmooth: sampleSmooth, buildLut: buildLut, colorAt: colorAt,
    renderGlobe: renderGlobe, formatLat: formatLat, formatLon: formatLon, formatValue: formatValue,
    omegaGrid: omegaGrid, describeOmega: describeOmega, alkalinityGrid: alkalinityGrid, SAL_MIN: SAL_MIN,
    FRESH: FRESH, NO_ALK: NO_ALK, NO_ALK_STRIPES: NO_ALK_STRIPES
  };
})();
