(function () {
  "use strict";
  window.addEventListener("error", function (e) {
    document.documentElement.setAttribute("data-js-error", (e && e.message) || "error");
  });
  var D = JSON.parse(document.getElementById("mission-data").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var css = getComputedStyle(document.documentElement);
  var C = {};
  ["bg", "panel", "panel-2", "line", "fg", "muted", "faint", "amber", "alarm", "el", "csm", "lm", "earth", "moon", "p63", "p64", "p66"].forEach(function (k) {
    C[k] = css.getPropertyValue("--" + k).trim();
  });

  // ---------- time map ----------
  var TM = D.timemap;
  var TOTAL = TM[TM.length - 1][1];
  var GET_END = TM[TM.length - 1][0];
  function interp(arr, x, ix, iy) {
    if (x <= arr[0][ix]) return arr[0][iy];
    var lo = 0, hi = arr.length - 1;
    if (x >= arr[hi][ix]) return arr[hi][iy];
    while (hi - lo > 1) { var m = (lo + hi) >> 1; if (arr[m][ix] <= x) lo = m; else hi = m; }
    var a = arr[lo], b = arr[hi];
    return a[iy] + (b[iy] - a[iy]) * (x - a[ix]) / (b[ix] - a[ix]);
  }
  function playToGet(p) { return interp(TM, p, 1, 0); }
  function getToPlay(g) { return interp(TM, g, 0, 1); }

  // ---------- helpers ----------
  function pad(n, w) { n = String(n); while (n.length < w) n = "0" + n; return n; }
  function fmtGET(g) {
    g = Math.max(0, Math.floor(g));
    return pad(Math.floor(g / 3600), 3) + ":" + pad(Math.floor(g / 60) % 60, 2) + ":" + pad(g % 60, 2);
  }
  var LAUNCH_MS = Date.parse(D.meta.launch_utc);
  function fmtUTC(g) {
    var d = new Date(LAUNCH_MS + Math.floor(g) * 1000);
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  }
  function fmtPlay(p) { p = Math.max(0, Math.floor(p)); return Math.floor(p / 60) + ":" + pad(p % 60, 2); }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function bsearch(arr, x) { // last index with arr[i] <= x, or -1
    var lo = 0, hi = arr.length - 1, r = -1;
    while (lo <= hi) { var m = (lo + hi) >> 1; if (arr[m] <= x) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  }
  function sampleTrack(get, keys, g) { // linear interpolation of several arrays by GET
    var i = bsearch(get, g), out = {};
    if (i < 0) i = 0;
    var j = Math.min(i + 1, get.length - 1);
    var f = j === i ? 0 : Math.max(0, Math.min(1, (g - get[i]) / (get[j] - get[i])));
    keys.forEach(function (k) { out[k[0]] = k[1][i] + (k[1][j] - k[1][i]) * f; });
    out.i = i; out.f = f;
    return out;
  }
  function phaseAt(g) {
    var P = D.phases;
    for (var i = 0; i < P.length; i++) if (g < P[i].get_end) return i;
    return P.length - 1;
  }
  var EVENTS = D.events;
  var EV = {}; EVENTS.forEach(function (e) { EV[e.id] = e; });
  function lastEvent(g) { var r = null; for (var i = 0; i < EVENTS.length; i++) if (EVENTS[i].get <= g + 0.01) r = EVENTS[i]; return r; }

  // ---------- state ----------
  var state = { play: 0, playing: false, speed: 1, dirty: true, lastEvent: null };

