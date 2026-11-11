// A pretend web page for public/globe.js, so the page code (dragging, buttons, layers, what happens
// when the data fails to load) can be tested without a browser. code/test_globe.py loads this file
// under jsc (built into macOS) or node and drives it. Nothing here is sent to the website.
//
//   var env = makeEnv({ globeJs: "<source of public/globe.js>", data: <the parsed json> }, options);
//
// options: fetch ("ok", "reject", "404", "badjson", "shape", "short", "manual"), reduceMotion, dpr,
//          canvasWidth (css pixels), noResizeObserver, noContext, captureThrows.
// Everything here is synchronous: time only moves when a test calls env.frame() or env.advance().
"use strict";

// A tiny promise that settles at once, so there is nothing to wait for.
function SyncPromise(executor) {
  var self = this;
  this.state = "pending"; this.value = undefined; this.waiters = [];
  function settle(state, value) {
    if (self.state !== "pending") return;
    if (state === "ok" && value && typeof value.then === "function") {
      value.then(function (v) { settle("ok", v); }, function (e) { settle("bad", e); });
      return;
    }
    self.state = state; self.value = value;
    self.waiters.splice(0).forEach(function (w) { w(); });
  }
  this.then = function (onOk, onBad) {
    return new SyncPromise(function (resolve, reject) {
      function go() {
        var handler = self.state === "ok" ? onOk : onBad;
        if (typeof handler !== "function") { (self.state === "ok" ? resolve : reject)(self.value); return; }
        try { resolve(handler(self.value)); } catch (e) { reject(e); }
      }
      if (self.state === "pending") self.waiters.push(go); else go();
    });
  };
  this["catch"] = function (onBad) { return this.then(undefined, onBad); };
  try { executor(function (v) { settle("ok", v); }, function (e) { settle("bad", e); }); } catch (e) { settle("bad", e); }
}
SyncPromise.resolve = function (v) { return new SyncPromise(function (resolve) { resolve(v); }); };
SyncPromise.reject = function (e) { return new SyncPromise(function (resolve, reject) { reject(e); }); };

function makeEnv(sources, options) {
  options = options || {};
  var env = { errors: [], fetchUrls: [], drawImageCalls: [], announceWrites: 0, lastArcRadius: null, windowListeners: {}, arcs: 0 };
  var clock = 1000, frameQueue = [], frameId = 1, timers = [], timerId = 1, byId = {};

  function guard(label, fn) {
    try { return fn(); } catch (e) { env.errors.push(label + ": " + e); }
  }

  // ---- a 2D drawing context that only counts what it is asked to do
  function makeContext(owner) {
    var c = { counts: {} };
    function count(name) { c.counts[name] = (c.counts[name] || 0) + 1; }
    ["clearRect", "beginPath", "stroke", "fill", "clip", "save", "restore", "moveTo", "lineTo", "putImageData"]
      .forEach(function (name) { c[name] = function () { count(name); }; });
    c.arc = function (x, y, r) { count("arc"); if (owner === env.canvas) { env.lastArcRadius = r; env.arcs++; } };
    c.drawImage = function (source) {
      count("drawImage");
      if (owner === env.canvas) env.drawImageCalls.push({ frame: env.frames, sourceWidth: source.width, canvasWidth: owner.width, canvasHeight: owner.height });
    };
    c.createImageData = function (w, h) { count("createImageData"); return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }; };
    c.createRadialGradient = function () { count("createRadialGradient"); return { addColorStop: function () {} }; };
    return c;
  }

  // ---- a tiny page element
  function Element(tag, id) {
    var self = this;
    this.tagName = tag; this.id = id || "";
    this.listeners = {}; this.attrs = {}; this.children = []; this.style = {};
    this.hidden = false; this.className = ""; this._text = ""; this.clientWidth = 0;
    this.width = 300; this.height = 150;                       // what a new canvas starts as
    this.rect = { left: 0, top: 0, width: 0, height: 0 };
    this.classes = {};
    this.classList = {
      add: function (c) { self.classes[c] = true; },
      remove: function (c) { delete self.classes[c]; },
      contains: function (c) { return !!self.classes[c]; }
    };
  }
  Element.prototype.addEventListener = function (type, fn, opt) { (this.listeners[type] = this.listeners[type] || []).push({ fn: fn, opt: opt }); };
  Element.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
  Element.prototype.getAttribute = function (k) { return k in this.attrs ? this.attrs[k] : null; };
  Element.prototype.appendChild = function (c) { this.children.push(c); return c; };
  Object.defineProperty(Element.prototype, "textContent", {
    get: function () { return this.children.length ? this.children.map(function (c) { return c.textContent; }).join("") : this._text; },
    set: function (v) { this._text = String(v); this.children = []; if (this === env.announce) env.announceWrites++; }
  });
  Element.prototype.getBoundingClientRect = function () {
    var r = this.rect;
    return { left: r.left, top: r.top, width: r.width, height: r.height, right: r.left + r.width, bottom: r.top + r.height };
  };
  Element.prototype.setPointerCapture = function () { if (options.captureThrows) throw new Error("InvalidPointerId"); };
  // dispatchEvent is how the page sends a real event object (like new Event("input")) to an element
  Element.prototype.dispatchEvent = function (ev) {
    var el = this;
    ev.target = el;
    if (ev.type === "input") el.inputEvents = (el.inputEvents || 0) + 1;
    (el.listeners[ev.type] || []).slice().forEach(function (l) { guard(ev.type + " on #" + el.id, function () { l.fn.call(el, ev); }); });
    return true;
  };
  Element.prototype.dispatch = function (type, props) {
    var el = this;
    var ev = { type: type, target: el, defaultPrevented: false, timeStamp: clock,
               preventDefault: function () { this.defaultPrevented = true; }, stopPropagation: function () {} };
    for (var k in props) ev[k] = props[k];
    (el.listeners[type] || []).slice().forEach(function (l) { guard(type + " on #" + el.id, function () { l.fn.call(el, ev); }); });
    return ev;
  };

  function makeCanvas(e) {
    e.context = makeContext(e);
    e.getContext = function (kind) { return kind === "2d" && !options.noContext ? e.context : null; };
  }
  function add(tag, id) { var e = new Element(tag, id); byId[id] = e; return e; }

  var css = options.canvasWidth || 500;
  env.canvas = add("CANVAS", "globe"); makeCanvas(env.canvas);
  env.canvas.clientWidth = css; env.canvas.rect = { left: 100, top: 50, width: css, height: css };
  env.status = add("P", "globe-status"); env.status.hidden = true;
  env.readout = add("P", "globe-readout"); env.center = add("P", "globe-center");
  env.description = add("P", "globe-description"); env.announce = add("P", "globe-announce");
  env.legend = add("DIV", "globe-legend"); env.legendTitle = add("DIV", "legend-title");
  env.legendBar = add("DIV", "legend-bar"); env.legendTicks = add("DIV", "legend-ticks");
  env.buttons = {};
  ["west", "east", "north", "south", "zoom-in", "zoom-out", "reset"].forEach(function (name) {
    env.buttons[name] = add("BUTTON", "globe-" + name);
  });
  env.radios = ["temperature", "salinity", "plain"].map(function (v) {
    var r = new Element("INPUT", "layer-" + v); r.value = v; r.name = "layer"; r.checked = (v === "temperature"); return r;
  });
  env.useCenter = add("BUTTON", "globe-use-center");
  env.pickText = add("SPAN", "globe-pick"); env.pickEstimate = add("SPAN", "globe-pick-estimate"); env.pickLink = add("A", "globe-pick-link"); env.pickLink.hidden = true;

  // The calculator's three range sliders. Setting .value snaps it into range and onto the step, as a browser does.
  function makeSlider(id, min, max, step, value) {
    var e = add("INPUT", id), current = String(value);
    e.min = String(min); e.max = String(max); e.step = String(step); e.inputEvents = 0;
    Object.defineProperty(e, "value", {
      get: function () { return current; },
      set: function (v) {
        var n = Number(v);
        if (n !== n) n = min;
        n = Math.max(min, Math.min(max, n));
        n = min + Math.round((n - min) / step) * step;
        current = String(Math.round(n * 1000) / 1000);
      }
    });
    return e;
  }
  env.sliders = options.noCalculator ? {} : {
    co2: makeSlider("co2", 250, 1000, 1, 425),
    temp: makeSlider("temp", -2, 35, 0.1, 15),
    sal: makeSlider("sal", 20, 42, 0.1, 35)
  };

  var document = {
    getElementById: function (id) { return byId[id] || null; },
    createElement: function (tag) {
      var e = new Element(tag.toUpperCase(), "");
      if (tag === "canvas") makeCanvas(e);
      return e;
    },
    querySelectorAll: function (selector) { return selector === 'input[name="layer"]' ? env.radios : []; }
  };

  // ---- the window, timers and animation frames
  function FakeResizeObserver(callback) { this.callback = callback; env.resizeObserver = this; }
  FakeResizeObserver.prototype.observe = function () {};
  function FakeEvent(type, init) { this.type = type; this.bubbles = !!(init && init.bubbles); this.detail = init && init.detail; this.defaultPrevented = false; }
  function FakeCustomEvent(type, init) { FakeEvent.call(this, type, init); }
  var win = {
    devicePixelRatio: options.dpr || 1,
    matchMedia: function (query) { return { matches: !!options.reduceMotion && query.indexOf("prefers-reduced-motion") >= 0 }; },
    addEventListener: function (type, fn) { (env.windowListeners[type] = env.windowListeners[type] || []).push(fn); },
    dispatchEvent: function (ev) {
      (env.windowListeners[ev.type] || []).slice().forEach(function (fn) { guard("window " + ev.type, function () { fn(ev); }); });
      return true;
    }
  };
  if (!options.noResizeObserver) win.ResizeObserver = FakeResizeObserver;

  function fakeFrame(callback) { var id = frameId++; frameQueue.push({ id: id, callback: callback }); return id; }
  function fakeCancelFrame(id) { frameQueue = frameQueue.filter(function (f) { return f.id !== id; }); }
  function fakeSetTimeout(callback, ms) { var id = timerId++; timers.push({ id: id, due: clock + (ms || 0), callback: callback }); return id; }
  function fakeClearTimeout(id) { timers = timers.filter(function (t) { return t.id !== id; }); }

  env.frames = 0;
  env.now = function () { return clock; };
  env.pending = function () { return frameQueue.length + timers.length; };
  env.advance = function (ms) {                       // move the clock, running timers that come due
    var target = clock + ms;
    for (;;) {
      var due = timers.filter(function (t) { return t.due <= target; })
                      .sort(function (a, b) { return a.due - b.due || a.id - b.id; })[0];
      if (!due) break;
      timers = timers.filter(function (t) { return t !== due; });
      clock = Math.max(clock, due.due);
      guard("timer", due.callback);
    }
    clock = target;
  };
  env.frame = function (ms, stampOffset) {            // one animation frame
    env.advance(ms === undefined ? 16 : ms);
    var queue = frameQueue; frameQueue = [];
    var stamp = clock + (stampOffset || 0);
    queue.forEach(function (f) { guard("frame", function () { f.callback(stamp); }); });
    env.frames++;
  };
  env.run = function (maxFrames) {                    // frames until nothing is scheduled
    var n = 0, cap = maxFrames || 3000;
    while (env.pending() && n < cap) { env.frame(16); n++; }
    return { frames: n, stillPending: env.pending() };
  };

  // ---- fetch, in several flavors
  var release = null;
  function okResponse(data) { return { ok: true, status: 200, json: function () { return SyncPromise.resolve(data); } }; }
  function fakeFetch(url) {
    env.fetchUrls.push(url);
    var short = { scale: 0.01, temperature_c: [1, 2, 3], salinity_psu: [1, 2, 3] };
    switch (options.fetch || "ok") {
      case "ok": return SyncPromise.resolve(okResponse(sources.data));
      case "reject": return SyncPromise.reject(new TypeError("Failed to fetch"));
      case "404": return SyncPromise.resolve({ ok: false, status: 404, json: function () { return SyncPromise.reject(new SyntaxError("Unexpected token <")); } });
      case "badjson": return SyncPromise.resolve({ ok: true, status: 200, json: function () { return SyncPromise.reject(new SyntaxError("Unexpected end of JSON input")); } });
      case "shape": return SyncPromise.resolve(okResponse({ scale: 0.01 }));
      case "short": return SyncPromise.resolve(okResponse(short));
      case "manual": return new SyncPromise(function (resolve) { release = function () { resolve(okResponse(sources.data)); }; });
    }
  }
  env.releaseData = function () { release(); };

  // ---- run the page code
  var factory = new Function("document", "window", "fetch", "requestAnimationFrame", "cancelAnimationFrame",
                             "setTimeout", "clearTimeout", "performance", "ResizeObserver", "Event", "CustomEvent",
                             sources.globeJs + "\n;return OceanGlobe;");
  try {
    env.api = factory(document, win, fakeFetch, fakeFrame, fakeCancelFrame, fakeSetTimeout, fakeClearTimeout,
                      { now: function () { return clock; } }, win.ResizeObserver, FakeEvent, FakeCustomEvent);
  } catch (e) { env.loadError = String(e); }

  // ---- ways to poke the page
  env.start = function () { env.frame(0); return env; };              // let the first draw happen
  env.pointer = function (type, x, y, extra) {
    var ev = { pointerId: 1, pointerType: "mouse", clientX: x, clientY: y, button: 0, ctrlKey: false,
               buttons: (type === "pointerdown" || type === "pointermove") ? 1 : 0 };
    for (var k in extra) ev[k] = extra[k];
    return env.canvas.dispatch(type, ev);
  };
  env.wheel = function (deltaY, extra) {
    var ev = { deltaY: deltaY, deltaMode: 0, ctrlKey: false };
    for (var k in extra) ev[k] = extra[k];
    return env.canvas.dispatch("wheel", ev);
  };
  env.press = function (name) { return env.buttons[name].dispatch("click", {}); };
  env.pick = function (layer) {
    env.radios.forEach(function (r) { r.checked = (r.value === layer); });
    env.radios.filter(function (r) { return r.value === layer; })[0].dispatch("change", {});
  };
  // Where the page shows the center of the view, read back from the words on the page.
  env.view = function () {
    var m = /Center of the view: ([\d.]+)°([NS]), ([\d.]+)°([EW])/.exec(env.center.textContent);
    if (!m) return null;
    return { lat: (m[2] === "N" ? 1 : -1) * parseFloat(m[1]), lon: (m[4] === "E" ? 1 : -1) * parseFloat(m[3]) };
  };
  // How far in the view is zoomed, worked out from the circle the page last drew.
  env.zoom = function () { return env.lastArcRadius / (env.canvas.width / 2 * 0.94); };
  // Where on the screen a latitude and longitude is, in the current view (null: on the far side).
  env.spot = function (lat, lon) {
    var v = env.view(), q = env.api.latLonToView(lat, lon, v.lat, v.lon);
    if (q.z <= 0) return null;
    var half = env.canvas.rect.width / 2, r = half * 0.94 * env.zoom();
    return { x: env.canvas.rect.left + half + q.x * r, y: env.canvas.rect.top + half - q.y * r };
  };
  env.tap = function (lat, lon) {                                       // press and let go on the same spot: a click
    var p = env.spot(lat, lon);
    env.pointer("pointerdown", p.x, p.y); env.pointer("pointerup", p.x, p.y);
  };
  env.co2year = function (detail) { return win.dispatchEvent(new FakeCustomEvent("co2year", { detail: detail })); };
  env.estimate = function (detail) { return win.dispatchEvent(new FakeCustomEvent("estimate", { detail: detail })); };
  env.userMoves = function (name, value) {                              // someone drags a calculator slider
    var slider = env.sliders[name]; slider.value = value; slider.dispatchEvent(new FakeEvent("input", { bubbles: true }));
  };
  env.hover = function (lat, lon) {
    var p = env.spot(lat, lon);
    env.pointer("pointermove", p.x, p.y, { buttons: 0 });
    return env.readout.textContent;
  };
  return env;
}
