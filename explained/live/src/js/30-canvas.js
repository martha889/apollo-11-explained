  // ---------- canvas ----------
  var canvas = $("scope"), ctx = canvas.getContext("2d");
  var W = 0, H = 0, DPR = 1, canvasResized = false;
  // The size change is applied inside the frame loop (applyResize), right before the redraw:
  // assigning canvas.width clears the bitmap, so doing it in the ResizeObserver callback
  // (after rAF, before paint) would paint one blank frame.
  var resizePending = true;
  function resize() { resizePending = true; state.dirty = true; }
  function applyResize() {
    if (!resizePending) return;
    resizePending = false;
    var r = $("canvas-wrap").getBoundingClientRect();
    DPR = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    W = Math.max(1, r.width); H = Math.max(1, r.height);
    var cw = Math.round(W * DPR), ch = Math.round(H * DPR);
    if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; canvasResized = true; }
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
  }
  if (window.ResizeObserver) new ResizeObserver(resize).observe($("canvas-wrap"));
  window.addEventListener("resize", resize);
  if (window.matchMedia) { var mq = window.matchMedia("screen and (min-resolution: 2dppx)"); if (mq.addEventListener) mq.addEventListener("change", resize); else if (mq.addListener) mq.addListener(resize); }
  applyResize();

  var view = null, viewScene = null, viewVel = {}, viewMoving = false;
  function smooth(target, scene, dt) {
    if (!view || viewScene !== scene || reduceMotion) {
      view = {}; viewVel = {};
      for (var k0 in target) { view[k0] = target[k0]; viewVel[k0] = 0; }
      viewScene = scene; viewMoving = false;
      return view;
    }
    var stepDt = dt > 0 ? Math.min(0.1, dt) : 0.016;
    var omega = 6.5;
    var e = Math.exp(-omega * stepDt);
    var moving = false;
    for (var k in target) {
      if (view[k] === undefined) { view[k] = target[k]; viewVel[k] = 0; continue; }
      var d0 = view[k] - target[k];
      var v0 = viewVel[k] || 0;
      var c1 = v0 + omega * d0;
      view[k] = target[k] + (d0 + c1 * stepDt) * e;
      viewVel[k] = (v0 - c1 * omega * stepDt) * e;
      var ref = Math.max(1, Math.abs(target[k]));
      if (Math.abs(view[k] - target[k]) > ref * 1e-4 || Math.abs(viewVel[k]) > ref * 1e-3) {
        moving = true;
      } else {
        view[k] = target[k]; viewVel[k] = 0;
      }
    }
    viewMoving = moving;
    return view;
  }

  // ---------- 3-layer starfield + Milky Way cache ----------
  var STARS = (function () {
    var s = [], seed = 7;
    function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    var tints = ["#dbe3ef", "#cfe2ff", "#fff4dc", "#b8d4ff", "#ffe8c2"];
    for (var i = 0; i < 320; i++) {
      var u = rnd(), v = rnd(), b = rnd(), layer = i < 170 ? 0 : i < 265 ? 1 : 2;
      var tint = tints[Math.floor(rnd() * tints.length)];
      var phase = rnd() * Math.PI * 2, speed = 1.4 + rnd() * 2.8;
      s.push([u, v, b, layer, tint, phase, speed]);
    }
    return s;
  })();

  var starCache = null;
  function buildStarCache(w, h, dpr) {
    var pad = 28, pw = Math.ceil(w + pad * 2), ph = Math.ceil(h + pad * 2);
    var layers = [0, 1, 2].map(function () {
      var c = document.createElement("canvas");
      c.width = Math.round(pw * dpr);
      c.height = Math.round(ph * dpr);
      return c;
    });
    // Layer 0: faint diagonal Milky Way band + deep field stars
    var g0 = layers[0].getContext("2d");
    g0.setTransform(dpr, 0, 0, dpr, 0, 0);
    g0.save();
    g0.translate(pw * 0.5, ph * 0.48);
    g0.rotate(-0.42);
    var bandH = Math.max(pw, ph) * 0.36, bandW = Math.max(pw, ph) * 1.45;
    var mg = g0.createLinearGradient(0, -bandH, 0, bandH);
    mg.addColorStop(0, "rgba(110, 145, 210, 0)");
    mg.addColorStop(0.28, "rgba(115, 150, 215, 0.026)");
    mg.addColorStop(0.46, "rgba(165, 190, 240, 0.058)");
    mg.addColorStop(0.54, "rgba(210, 195, 230, 0.048)");
    mg.addColorStop(0.72, "rgba(115, 150, 215, 0.024)");
    mg.addColorStop(1, "rgba(110, 145, 210, 0)");
    g0.fillStyle = mg;
    g0.fillRect(-bandW * 0.5, -bandH, bandW, bandH * 2);
    // Soft galactic core / dust patches along the band
    var mSeed = 43;
    function mrnd() { mSeed = (mSeed * 16807) % 2147483647; return mSeed / 2147483647; }
    for (var k = 0; k < 14; k++) {
      var cx = (mrnd() - 0.5) * bandW * 0.85, cy = (mrnd() - 0.5) * bandH * 0.65;
      var cr = 40 + mrnd() * 95;
      var cg = g0.createRadialGradient(cx, cy, 2, cx, cy, cr);
      cg.addColorStop(0, k % 3 === 0 ? "rgba(230, 205, 175, 0.032)" : "rgba(145, 180, 245, 0.035)");
      cg.addColorStop(1, "rgba(145, 180, 245, 0)");
      g0.fillStyle = cg;
      g0.beginPath(); g0.arc(cx, cy, cr, 0, Math.PI * 2); g0.fill();
    }
    // Fine galactic dust pinpoint stars concentrated along the band
    g0.fillStyle = "#dce8ff";
    for (var m = 0; m < 180; m++) {
      var bx = (mrnd() - 0.5) * bandW * 0.95;
      var by = (mrnd() + mrnd() - 1) * bandH * 0.55;
      g0.globalAlpha = 0.05 + mrnd() * 0.14;
      g0.fillRect(bx, by, 1, 1);
    }
    g0.restore();
    g0.globalAlpha = 1;

    var ctxs = [g0, layers[1].getContext("2d"), layers[2].getContext("2d")];
    ctxs[1].setTransform(dpr, 0, 0, dpr, 0, 0);
    ctxs[2].setTransform(dpr, 0, 0, dpr, 0, 0);

    var twinkle = [];
    for (var i = 0; i < STARS.length; i++) {
      var s = STARS[i], lay = s[3], sg = ctxs[lay];
      var sx = s[0] * pw, sy = s[1] * ph;
      var baseA = lay === 0 ? (0.14 + s[2] * 0.26) : lay === 1 ? (0.24 + s[2] * 0.38) : (0.42 + s[2] * 0.52);
      var sz = lay === 0 ? (0.65 + s[2] * 0.35) : lay === 1 ? (0.85 + s[2] * 0.45) : (1.1 + s[2] * 0.65);
      if (lay === 2 && s[2] > 0.6) {
        var hr = sz * 3.2;
        var hg = sg.createRadialGradient(sx, sy, 0, sx, sy, hr);
        hg.addColorStop(0, s[4]);
        hg.addColorStop(0.35, "rgba(210, 228, 255, 0.18)");
        hg.addColorStop(1, "rgba(210, 228, 255, 0)");
        sg.globalAlpha = baseA * 0.65;
        sg.fillStyle = hg;
        sg.beginPath(); sg.arc(sx, sy, hr, 0, Math.PI * 2); sg.fill();
      }
      sg.globalAlpha = baseA;
      sg.fillStyle = s[4];
      sg.beginPath(); sg.arc(sx, sy, sz * 0.5, 0, Math.PI * 2); sg.fill();
      if (i % 8 === 0) twinkle.push(s);
    }
    ctxs[0].globalAlpha = 1; ctxs[1].globalAlpha = 1; ctxs[2].globalAlpha = 1;
    return { w: w, h: h, dpr: dpr, pad: pad, pw: pw, ph: ph, layers: layers, twinkle: twinkle };
  }

  function drawStars() {
    var cw = Math.round(W), ch = Math.round(H);
    if (!starCache || starCache.w !== cw || starCache.h !== ch || starCache.dpr !== DPR) {
      starCache = buildStarCache(cw, ch, DPR);
    }
    var ox = 0, oy = 0;
    if (!reduceMotion && view) {
      if (view.cx !== undefined && view.span) {
        ox = -Math.atan2(view.cx, view.span) * 18;
        oy = Math.atan2(view.cy || 0, view.span) * 18;
      } else if (view.x0 !== undefined && view.x1 !== undefined) {
        var spx = Math.max(1, view.x1 - view.x0), spy = Math.max(1, (view.y1 || 1) - (view.y0 || 0));
        ox = -Math.atan2((view.x0 + view.x1) * 0.5, spx) * 12;
        oy = Math.atan2(((view.y0 || 0) + (view.y1 || 0)) * 0.5, spy) * 12;
      }
    }
    var pad = starCache.pad, pw = starCache.pw, ph = starCache.ph;
    var pFactors = [0.22, 0.55, 1.0];
    for (var l = 0; l < 3; l++) {
      var dx = -pad + ox * pFactors[l], dy = -pad + oy * pFactors[l];
      ctx.drawImage(starCache.layers[l], dx, dy, pw, ph);
    }
    if (!reduceMotion) {
      var t = performance.now() * 0.001;
      var tw = starCache.twinkle;
      for (var i = 0; i < tw.length; i++) {
        var s = tw[i], pf = pFactors[s[3]];
        var wave = Math.sin(t * s[6] + s[5]);
        if (wave <= 0.15) continue;
        var tx = s[0] * pw - pad + ox * pf, ty = s[1] * ph - pad + oy * pf;
        ctx.globalAlpha = (wave - 0.15) * 0.42;
        ctx.fillStyle = "#ffffff";
        var r = s[3] === 2 ? 1.8 : 1.2;
        ctx.fillRect(tx - r * 0.5, ty - r * 0.5, r, r);
      }
      ctx.globalAlpha = 1;
    }
  }

  function text(t, x, y, opt) {
    opt = opt || {};
    ctx.font = (opt.weight || 500) + " " + (opt.size || 12) + "px " + (opt.font || "IBM Plex Sans, Helvetica Neue, Arial, sans-serif");
    ctx.fillStyle = opt.color || C.muted;
    ctx.textAlign = opt.align || "left";
    ctx.textBaseline = opt.base || "alphabetic";
    ctx.fillText(t, x, y);
  }
  function label(t, x, y, color, align) {
    text(t, x, y, { size: 12, weight: 600, color: color, font: "Barlow Condensed, Arial Narrow, sans-serif", align: align || "left" });
  }
  function marker(x, y, color, name, opts) {
    opts = opts || {};
    if (typeof FX !== "undefined" && FX._mark) FX._mark(x, y, color);
    // Soft outer glow
    var g = ctx.createRadialGradient(x, y, 1, x, y, 15);
    g.addColorStop(0, color);
    g.addColorStop(0.45, color);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.save();
    ctx.globalAlpha = 0.24;
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x, y, 15, 0, Math.PI * 2); ctx.fill();
    // Pulsing halo ring
    if (reduceMotion) {
      ctx.globalAlpha = 0.42;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(x, y, 8.5, 0, Math.PI * 2); ctx.stroke();
    } else {
      var now = performance.now() * 0.001;
      var pulse = (now * 0.9) % 1;
      var pr = 5 + pulse * 12;
      ctx.globalAlpha = (1 - pulse) * 0.58;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4 - pulse * 0.6;
      ctx.beginPath(); ctx.arc(x, y, pr, 0, Math.PI * 2); ctx.stroke();
      // Steady inner tracking ring
      ctx.globalAlpha = 0.32 + 0.12 * Math.sin(now * 4.2);
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x, y, 7.2, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
    // Core marker dot
    ctx.beginPath(); ctx.arc(x, y, 4.2, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
    ctx.lineWidth = 1.5; ctx.strokeStyle = C.bg; ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, 1.5, 0, Math.PI * 2); ctx.fillStyle = "#ffffff"; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
    // Label with subtle dark backing pill
    if (name) {
      var up = name.toUpperCase();
      var lx = x + (opts.dx || 10), ly = y + (opts.dy || -10), al = opts.align || "left";
      ctx.save();
      ctx.font = "600 12px Barlow Condensed, Arial Narrow, sans-serif";
      var tw = ctx.measureText(up).width;
      var padX = 5, bh = 15, bw = tw + padX * 2;
      var bx = al === "right" ? lx - tw - padX : al === "center" ? lx - tw * 0.5 - padX : lx - padX;
      var by = ly - 11.5;
      ctx.fillStyle = "rgba(13, 18, 27, 0.78)";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 3);
      else ctx.rect(bx, by, bw, bh);
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.26;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();
      label(up, lx, ly, color, al);
    }
  }
  function plume(x, y, ang, color) { // short flame behind the craft, pointing opposite to the thrust
    if (typeof FX !== "undefined" && FX.exhaust) {
      FX.exhaust(x, y, ang, 0.9, { color: color || C.amber });
      return;
    }
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    ctx.beginPath(); ctx.moveTo(-6, -3.5); ctx.lineTo(-22 - (reduceMotion ? 2 : Math.random() * 6), 0); ctx.lineTo(-6, 3.5); ctx.closePath();
    ctx.fillStyle = color || C.amber; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1; ctx.restore();
  }
  function polyline(xs, ys, X, Y, i0, i1, color, width, dash, alpha) {
    if (i1 <= i0) return;
    ctx.beginPath();
    ctx.moveTo(X(xs[i0]), Y(ys[i0]));
    for (var i = i0 + 1; i <= i1; i++) ctx.lineTo(X(xs[i]), Y(ys[i]));
    var w = width || 2, a = alpha == null ? 1 : alpha;
    var isSolid = !dash || !dash.length;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.setLineDash(dash || []);
    if (isSolid) {
      ctx.lineWidth = w * 3.6;
      ctx.globalAlpha = a * 0.14;
      ctx.stroke();
      ctx.lineWidth = w * 1.9;
      ctx.globalAlpha = a * 0.28;
      ctx.stroke();
    }
    ctx.lineWidth = w;
    ctx.globalAlpha = a;
    ctx.stroke();
    ctx.restore();
  }
  function niceStep(range, n) {
    var raw = range / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / mag;
    return (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag;
  }
  function fmtNum(v, step) { if (Math.abs(v) < step * 1e-6) v = 0; var d = step < 1 ? Math.min(3, Math.ceil(-Math.log10(step))) : 0; return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }

  // Chart frame for profile scenes. Returns mapping functions.
  function chart(v, xl, yl) {
    var m = { l: 58, r: 18, t: 52, b: 44 };
    if (W < 520) { m.l = 48; m.r = 12; }
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var X = function (x) { return m.l + (x - v.x0) / (v.x1 - v.x0) * pw; };
    var Y = function (y) { return m.t + ph - (y - v.y0) / (v.y1 - v.y0) * ph; };
    // Subtle recessed scope backdrop inside plot area
    var bgGrad = ctx.createLinearGradient(0, m.t, 0, m.t + ph);
    bgGrad.addColorStop(0, "rgba(9, 13, 21, 0.52)");
    bgGrad.addColorStop(1, "rgba(13, 18, 27, 0.18)");
    ctx.fillStyle = bgGrad;
    ctx.fillRect(m.l, m.t, pw, ph);
    ctx.strokeStyle = C.line; ctx.lineWidth = 1;
    var sx = niceStep(v.x1 - v.x0, Math.max(3, Math.floor(pw / 110))), sy = niceStep(v.y1 - v.y0, Math.max(3, Math.floor(ph / 70)));
    ctx.beginPath();
    for (var x = Math.ceil(v.x0 / sx) * sx; x <= v.x1 + 1e-9; x += sx) { ctx.moveTo(Math.round(X(x)) + 0.5, m.t); ctx.lineTo(Math.round(X(x)) + 0.5, m.t + ph); }
    for (var y = Math.ceil(v.y0 / sy) * sy; y <= v.y1 + 1e-9; y += sy) { ctx.moveTo(m.l, Math.round(Y(y)) + 0.5); ctx.lineTo(m.l + pw, Math.round(Y(y)) + 0.5); }
    ctx.globalAlpha = 0.6; ctx.stroke(); ctx.globalAlpha = 1;
    for (x = Math.ceil(v.x0 / sx) * sx; x <= v.x1 + 1e-9; x += sx) text(fmtNum(x, sx), X(x), m.t + ph + 16, { size: 11, align: "center", font: "IBM Plex Mono, monospace", weight: 400 });
    for (y = Math.ceil(v.y0 / sy) * sy; y <= v.y1 + 1e-9; y += sy) text(fmtNum(y, sy), m.l - 6, Y(y) + 4, { size: 11, align: "right", font: "IBM Plex Mono, monospace", weight: 400 });
    text(xl, m.l + pw / 2, H - 10, { size: 12, align: "center" });
    ctx.save(); ctx.translate(14, m.t + ph / 2); ctx.rotate(-Math.PI / 2); text(yl, 0, 0, { size: 12, align: "center", base: "middle" }); ctx.restore();
    ctx.save(); ctx.beginPath(); ctx.rect(m.l, m.t, pw, ph); ctx.clip();
    return {
      X: X, Y: Y, m: m, pw: pw, ph: ph,
      done: function () {
        ctx.restore();
        ctx.save();
        ctx.strokeStyle = C.line;
        ctx.globalAlpha = 0.85;
        ctx.lineWidth = 1;
        ctx.strokeRect(m.l + 0.5, m.t + 0.5, pw - 1, ph - 1);
        ctx.restore();
      }
    };
  }
  var readoutLeftX = 0;
  function readout(rows) { // top-right block of key numbers
    var x = W - 14, y = 22;
    ctx.font = "500 13px IBM Plex Mono, monospace";
    var vw = 0, lw = 0;
    rows.forEach(function (r) { vw = Math.max(vw, ctx.measureText(r[1]).width); });
    ctx.font = "600 11px Barlow Condensed, Arial Narrow, sans-serif";
    rows.forEach(function (r) { lw = Math.max(lw, ctx.measureText(r[0].toUpperCase()).width); });
    var nextLeft = rows.length ? (x - vw - 12 - lw) : (W - 14);
    if (Math.abs(nextLeft - readoutLeftX) > 1) state.dirty = true;
    readoutLeftX = nextLeft;
    rows.forEach(function (r) {
      text(r[0].toUpperCase(), x - vw - 12, y, { size: 11, weight: 600, font: "Barlow Condensed, Arial Narrow, sans-serif", color: C.muted, align: "right" });
      text(r[1], x, y, { size: 13, weight: 500, font: "IBM Plex Mono, monospace", color: r[2] || C.fg, align: "right" });
      y += 18;
    });
  }
  function note(t) {
    if (!t) return;
    ctx.font = "400 11px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
    var rightEdge = (readoutLeftX > 0 && readoutLeftX <= W ? readoutLeftX : W - 200) - 16;
    var maxW = Math.max(150, Math.min(W - 28, 560, rightEdge - 14));
    var words = t.split(" "), line = "", lines = [];
    words.forEach(function (w) {
      var test = line ? line + " " + w : w;
      if (line && ctx.measureText(test).width > maxW) { lines.push(line); line = w; }
      else line = test;
    });
    if (line) lines.push(line);
    var shown = lines.slice(0, 3);
    if (lines.length > 3) {
      var last = shown[2].replace(/[.,;:\s]+$/, "");
      while (last.length > 0 && ctx.measureText(last + "…").width > maxW) {
        var sp = last.lastIndexOf(" ");
        last = sp > 0 ? last.slice(0, sp).replace(/[.,;:\s]+$/, "") : last.slice(0, -1);
      }
      shown[2] = last + "…";
    }
    shown.forEach(function (l, i) { text(l, 14, 20 + i * 14, { size: 11, weight: 400, color: C.faint }); });
  }
  function scaleBar(kmPerPx) {
    var target = 110 * kmPerPx, p = Math.pow(10, Math.floor(Math.log10(target))), r = target / p;
    var km = (r < 2 ? 1 : r < 5 ? 2 : 5) * p, px = km / kmPerPx;
    var x = 14, y = H - 16;
    ctx.strokeStyle = C.muted; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x, y - 4); ctx.lineTo(x, y); ctx.lineTo(x + px, y); ctx.lineTo(x + px, y - 4); ctx.stroke();
    text(km.toLocaleString("en-US") + " km", x + px + 8, y + 1, { size: 11, font: "IBM Plex Mono, monospace", weight: 400 });
  }

  // ---------- Procedural Earth & Moon offscreen cache ----------
  var bodyCache = {};
  var MOON_CRATERS = (function () {
    var list = [], s = 1337;
    function r() { s = (s * 16807) % 2147483647; return s / 2147483647; }
    // Deterministic craters in 3D unit-sphere coordinates (cx, cy, cz, rad, depth)
    var raw = [
      [-0.18, 0.48, 0.11, 0.95], [0.26, 0.14, 0.085, 0.75], [-0.38, -0.22, 0.095, 0.8],
      [0.08, -0.35, 0.075, 0.75], [-0.12, -0.52, 0.09, 0.85], [0.44, -0.28, 0.08, 0.8],
      [-0.52, 0.18, 0.085, 0.75], [0.15, 0.36, 0.07, 0.7]
    ];
    for (var i = 0; i < raw.length; i++) {
      var x0 = raw[i][0], y0 = raw[i][1], z0 = Math.sqrt(Math.max(0.05, 1 - x0 * x0 - y0 * y0));
      list.push([x0, y0, z0, raw[i][2], raw[i][3]]);
    }
    for (var j = 0; j < 38; j++) {
      var rx = (r() - 0.5) * 1.65, ry = (r() - 0.5) * 1.65;
      if (rx * rx + ry * ry > 0.88) continue;
      var rz = Math.sqrt(1 - rx * rx - ry * ry);
      list.push([rx, ry, rz, 0.028 + r() * 0.055, 0.45 + r() * 0.5]);
    }
    return list;
  })();

  function pHash(ix, iy) {
    var n = Math.sin(ix * 127.1 + iy * 311.7) * 43758.5453;
    return n - Math.floor(n);
  }
  function vNoise(x, y) {
    var ix = Math.floor(x), iy = Math.floor(y);
    var fx = x - ix, fy = y - iy;
    var ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
    var a = pHash(ix, iy), b = pHash(ix + 1, iy);
    var c = pHash(ix, iy + 1), d = pHash(ix + 1, iy + 1);
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
  }
  function fbm(x, y, oct) {
    var v = 0, amp = 0.5, freq = 1;
    for (var i = 0; i < oct; i++) {
      v += amp * vNoise(x * freq, y * freq);
      freq *= 2.03; amp *= 0.5;
    }
    return v;
  }
  function sstep(a, b, x) {
    var t = Math.max(0, Math.min(1, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  }

  function getBodyBucket(rpx) {
    if (rpx < 18) return 16;
    if (rpx < 38) return 32;
    if (rpx < 84) return 68;
    if (rpx < 165) return 136;
    return 240;
  }

  function renderBodySprite(kind, rb, dpr) {
    var padFactor = kind === "earth" ? 1.32 : 1.18;
    var R = Math.round(rb * dpr);
    var half = Math.ceil(R * padFactor);
    var size = half * 2;
    var c = document.createElement("canvas");
    c.width = size; c.height = size;
    var g = c.getContext("2d");

    // Outer atmosphere / horizon glow
    if (kind === "earth") {
      var ag = g.createRadialGradient(half - R * 0.08, half - R * 0.08, R * 0.86, half, half, R * 1.28);
      ag.addColorStop(0, "rgba(95, 185, 255, 0.42)");
      ag.addColorStop(0.45, "rgba(65, 145, 245, 0.22)");
      ag.addColorStop(0.75, "rgba(40, 105, 215, 0.06)");
      ag.addColorStop(1, "rgba(30, 85, 190, 0)");
      g.fillStyle = ag;
      g.beginPath(); g.arc(half, half, R * 1.28, 0, Math.PI * 2); g.fill();
    } else {
      var mg = g.createRadialGradient(half, half, R * 0.92, half, half, R * 1.14);
      mg.addColorStop(0, "rgba(195, 202, 218, 0.16)");
      mg.addColorStop(1, "rgba(185, 190, 205, 0)");
      g.fillStyle = mg;
      g.beginPath(); g.arc(half, half, R * 1.14, 0, Math.PI * 2); g.fill();
    }

    // Procedural spherical texture buffer
    var texN = Math.min(136, Math.max(36, Math.round(rb * 1.15)));
    var tc = document.createElement("canvas");
    tc.width = texN; tc.height = texN;
    var tg = tc.getContext("2d");
    var img = tg.createImageData(texN, texN);
    var data = img.data;
    var sunX = kind === "earth" ? -0.48 : -0.34;
    var sunY = kind === "earth" ? -0.36 : -0.28;
    var sunZ = Math.sqrt(1 - sunX * sunX - sunY * sunY);
    var rad = texN * 0.5 - 1;

    for (var py = 0; py < texN; py++) {
      var ny = (py + 0.5 - texN * 0.5) / rad;
      for (var px = 0; px < texN; px++) {
        var nx = (px + 0.5 - texN * 0.5) / rad;
        var r2 = nx * nx + ny * ny;
        if (r2 > 1.0) continue;
        var nz = Math.sqrt(Math.max(0, 1 - r2));
        var lon = Math.atan2(nx, nz);
        var lat = Math.asin(Math.max(-1, Math.min(1, ny)));
        var ndotl = nx * sunX + ny * sunY + nz * sunZ;
        var rr = 0, gg = 0, bb = 0;

        if (kind === "earth") {
          var nCont = fbm(lon * 1.95 + 2.3, lat * 2.05 + 1.1, 4);
          var nDet = fbm(lon * 5.2 + 7.1, lat * 5.2 - 3.4, 3);
          var landVal = nCont * 0.78 + nDet * 0.22 - 0.04 * Math.cos(lat * 2.5);
          var isLand = landVal > 0.505 && Math.abs(lat) < 1.32;
          if (isLand) {
            var elev = Math.min(1, (landVal - 0.505) / 0.28);
            var arid = sstep(0.15, 0.65, Math.abs(Math.sin(lat * 2.1 + nDet)));
            rr = 46 + elev * 58 + arid * 38;
            gg = 104 + elev * 18 - arid * 6;
            bb = 66 - elev * 12 + arid * 8;
          } else {
            var shelf = sstep(0.42, 0.505, landVal);
            rr = 18 + shelf * 26;
            gg = 68 + shelf * 64;
            bb = 142 + shelf * 48;
            // Solar ocean specular highlight
            var hx = sunX * 0.5, hy = sunY * 0.5, hz = (sunZ + 1) * 0.5;
            var hLen = Math.hypot(hx, hy, hz) || 1;
            var spec = Math.max(0, (nx * hx + ny * hy + nz * hz) / hLen);
            var glint = Math.pow(spec, 22) * 58 * (1 - shelf * 0.4);
            rr += glint * 0.85; gg += glint * 0.92; bb += glint;
          }
          // Polar ice caps
          var ice = sstep(1.08, 1.26, Math.abs(lat) + (nDet - 0.5) * 0.22);
          if (ice > 0) {
            rr += (228 - rr) * ice;
            gg += (238 - gg) * ice;
            bb += (248 - bb) * ice;
          }
          // Cloud wisps
          var warp = fbm(lon * 2.8 + 4.1, lat * 2.8 + 0.7, 3);
          var cVal = fbm(lon * 3.6 + warp * 1.3 + 9.2, lat * 4.4 - warp * 0.9, 4);
          var cloud = sstep(0.50, 0.72, cVal);
          if (cloud > 0) {
            var ca = cloud * 0.78;
            rr += (244 - rr) * ca;
            gg += (248 - gg) * ca;
            bb += (255 - bb) * ca;
          }
          // Day/night terminator + Fresnel rim
          var lit = sstep(-0.22, 0.28, ndotl);
          var diff = 0.12 + 0.88 * lit * (0.42 + 0.58 * Math.max(0, ndotl));
          rr = rr * diff + (1 - lit) * 6;
          gg = gg * diff + (1 - lit) * 14;
          bb = bb * diff + (1 - lit) * 32;
          var fres = Math.pow(1 - nz, 2.5) * (0.28 + 0.72 * lit);
          rr += (105 - rr) * fres * 0.65;
          gg += (192 - gg) * fres * 0.65;
          bb += (255 - bb) * fres * 0.65;
        } else {
          // Moon: maria basins + highland regolith + 3D normal-perturbed craters + limb darkening
          var mLow = fbm(nx * 2.4 + 1.4, ny * 2.4 + 2.2, 4);
          var mHigh = fbm(nx * 8.5 + 3.1, ny * 8.5 - 1.8, 3);
          // Smooth near-side maria basins (Imbrium, Serenitatis, Tranquillitatis, Crisium)
          var b1 = Math.exp(-((nx + 0.22) * (nx + 0.22) + (ny + 0.24) * (ny + 0.24)) * 6.5);
          var b2 = Math.exp(-((nx - 0.18) * (nx - 0.18) + (ny + 0.08) * (ny + 0.08)) * 7.5);
          var b3 = Math.exp(-((nx - 0.34) * (nx - 0.34) + (ny - 0.14) * (ny - 0.14)) * 8.0);
          var b4 = Math.exp(-((nx - 0.56) * (nx - 0.56) + (ny + 0.14) * (ny + 0.14)) * 18.0);
          var maria = sstep(0.28, 0.78, mLow * 0.52 + (b1 + b2 * 0.9 + b3 * 0.85 + b4 * 0.7) * 0.52);
          var base = 196 - maria * 56 + (mHigh - 0.5) * 24;

          // 3D spherical craters with smooth slope normal perturbation
          var pnx = nx, pny = ny, pnz = nz;
          for (var ci = 0; ci < MOON_CRATERS.length; ci++) {
            var cr = MOON_CRATERS[ci];
            var dx = nx - cr[0], dy = ny - cr[1], dz = nz - cr[2];
            var cd = Math.sqrt(dx * dx + dy * dy + dz * dz);
            var cRad = cr[3];
            if (cd < cRad * 1.3) {
              var u = cd / (cRad + 1e-5);
              var dep = cr[4];
              if (u < 0.88) {
                // Bowl interior: inward radial slope tilts normal toward crater center
                var bowlSlope = Math.sin((u / 0.88) * Math.PI) * 0.42 * dep;
                pnx -= (dx / (cd + 1e-5)) * bowlSlope;
                pny -= (dy / (cd + 1e-5)) * bowlSlope;
                base -= (1 - u * u) * 5 * dep;
              } else {
                // Raised outer rim slope + subtle ejecta brightening
                var rimPhase = (u - 0.88) / 0.42;
                var rimSlope = Math.sin(rimPhase * Math.PI) * 0.26 * dep;
                pnx += (dx / (cd + 1e-5)) * rimSlope;
                pny += (dy / (cd + 1e-5)) * rimSlope;
                base += (1 - rimPhase) * 9 * dep;
              }
            }
          }
          var nLen = Math.hypot(pnx, pny, pnz) || 1;
          var cLight = (pnx * sunX + pny * sunY + pnz * sunZ) / nLen;
          var mLit = sstep(-0.26, 0.24, ndotl);
          var limb = 0.52 + 0.48 * Math.pow(nz, 0.55);
          var mShade = (0.18 + 0.82 * mLit * (0.48 + 0.52 * Math.max(0, cLight))) * limb;
          rr = (base - 2) * mShade;
          gg = base * mShade;
          bb = (base + 5) * mShade;
        }

        var idx = (py * texN + px) * 4;
        data[idx] = Math.max(0, Math.min(255, Math.round(rr)));
        data[idx + 1] = Math.max(0, Math.min(255, Math.round(gg)));
        data[idx + 2] = Math.max(0, Math.min(255, Math.round(bb)));
        data[idx + 3] = 255;
      }
    }
    tg.putImageData(img, 0, 0);

    // Clip to crisp high-DPI circle and draw spherical texture
    g.save();
    g.beginPath();
    g.arc(half, half, R, 0, Math.PI * 2);
    g.clip();
    g.imageSmoothingEnabled = true;
    var bleed = Math.max(2, R * 0.03);
    g.drawImage(tc, half - R - bleed, half - R - bleed, (R + bleed) * 2, (R + bleed) * 2);
    g.restore();

    // Subtle sunlit rim arc
    g.save();
    g.beginPath();
    g.arc(half, half, R - 0.5, 0, Math.PI * 2);
    g.strokeStyle = kind === "earth" ? "rgba(135, 210, 255, 0.45)" : "rgba(220, 225, 238, 0.28)";
    g.lineWidth = Math.max(1, dpr * 1.1);
    g.stroke();
    g.restore();

    return { canvas: c, half: half, R: R, padFactor: padFactor };
  }

  function body(x, y, rpx, color, name) {
    rpx = Math.max(rpx, 2.5);
    var isEarth = (name && /earth/i.test(name)) || color === C.earth || color === "#3d7fd9";
    var isMoon = !isEarth && ((name && /moon/i.test(name)) || color === C.moon || color === "#b9bcc4");

    if (rpx < 6 || (!isEarth && !isMoon)) {
      // Small radii (<6px) stay simple glowing discs
      var halo = ctx.createRadialGradient(x, y, rpx * 0.2, x, y, rpx * 2.6);
      halo.addColorStop(0, color);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.save();
      ctx.globalAlpha = 0.28;
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(x, y, rpx * 2.6, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      var g = ctx.createRadialGradient(x - rpx * 0.35, y - rpx * 0.35, rpx * 0.1, x, y, rpx);
      g.addColorStop(0, color); g.addColorStop(1, shade(color, 0.45));
      ctx.beginPath(); ctx.arc(x, y, rpx, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
      if (name) label(name.toUpperCase(), x, y + rpx + 16, C.muted, "center");
      return;
    }

    var kind = isEarth ? "earth" : "moon";
    var rb = getBodyBucket(rpx);
    var key = kind + ":" + rb + ":" + DPR;
    var sp = bodyCache[key];
    if (!sp) {
      sp = renderBodySprite(kind, rb, DPR);
      bodyCache[key] = sp;
    }
    var drawHalf = rpx * sp.padFactor;
    ctx.drawImage(sp.canvas, x - drawHalf, y - drawHalf, drawHalf * 2, drawHalf * 2);
    if (name) label(name.toUpperCase(), x, y + rpx + 16, C.muted, "center");
  }

  function shade(hex, k) {
    var n = parseInt(hex.slice(1), 16);
    return "rgb(" + Math.round(((n >> 16) & 255) * k) + "," + Math.round(((n >> 8) & 255) * k) + "," + Math.round((n & 255) * k) + ")";
  }
  function burnActive(burns, g) { for (var i = 0; i < burns.length; i++) if (g >= burns[i].get0 && g <= burns[i].get1) return burns[i]; return null; }

  // --- map transform (centre + span in km) ---
  function mapXf(v) {
    var s = Math.min(W, H) / v.span;
    return { X: function (x) { return W / 2 + (x - v.cx) * s; }, Y: function (y) { return H / 2 - (y - v.cy) * s; }, s: s };
  }

  var SCENES = {};
  var T = D.tracks;
