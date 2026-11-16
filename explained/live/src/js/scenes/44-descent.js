  var PHC = { 63: "p63", 64: "p64", 66: "p66" };
  var s3_descPrevG = null;
  var s3_descTerrainCache = {};

  function s3_descCrossed(t, g, prevG) {
    if (!state.playing || prevG === null || t == null) return false;
    var dp = getToPlay(g) - getToPlay(prevG);
    return prevG < t && g >= t && ((g - prevG) < 30 * (state.speed || 1) || (dp > 0 && dp < 0.65 * (state.speed || 1)));
  }

  function s3_descTele(tr, key, g) {
    if (!tr.telemetry) return null;
    if (!tr._s3map) {
      tr._s3map = {};
      for (var i = 0; i < tr.telemetry.length; i++) {
        tr._s3map[tr.telemetry[i].key] = tr.telemetry[i];
      }
    }
    var sr = tr._s3map[key];
    if (!sr || !sr.get || !sr.get.length) return null;
    if (g < sr.get[0] || g > sr.get[sr.get.length - 1]) return null;
    return sampleTrack(sr.get, [["v", sr.v]], g).v;
  }

  function s3_buildDescentTerrain(stage, pw, dpr) {
    var sh = 36;
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(pw * dpr));
    c.height = Math.round(sh * dpr);
    var g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);

    var seed = 401 + stage * 197;
    function rnd() {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    }

    // Pad zone around landing site (x = 0 is near right side of chart in all 3 stages:
    // stage 0: 460/472 = 0.975; stage 1: 9/9.6 = 0.938; stage 2: 1.6/1.75 = 0.914)
    var padU = stage === 0 ? 0.975 : stage === 1 ? 0.938 : 0.914;

    // Distant highland ridge silhouette
    g.beginPath();
    g.moveTo(0, sh);
    var steps = Math.max(48, Math.round(pw / 6));
    for (var i = 0; i <= steps; i++) {
      var u = i / steps;
      var padFlatten = 1 - 0.72 * Math.exp(-Math.pow((u - padU) / 0.065, 2));
      var w1 = Math.sin(u * (stage === 0 ? 9.5 : stage === 1 ? 13.0 : 17.5) + stage * 1.7) * 0.5 + 0.5;
      var w2 = Math.sin(u * (stage === 0 ? 23.0 : stage === 1 ? 31.0 : 43.0) + 0.8) * 0.5 + 0.5;
      var w3 = Math.cos(u * (stage === 0 ? 41.0 : 59.0) - 1.2) * 0.5 + 0.5;
      var ridgeH = (8 + (stage === 0 ? 13 : stage === 1 ? 10 : 7) * (w1 * 0.55 + w2 * 0.3 + w3 * 0.15)) * padFlatten;
      g.lineTo(u * pw, sh - ridgeH);
    }
    g.lineTo(pw, sh);
    g.closePath();
    var rg = g.createLinearGradient(0, sh - 24, 0, sh);
    rg.addColorStop(0, "rgba(74, 82, 98, 0.52)");
    rg.addColorStop(1, "rgba(22, 27, 37, 0.85)");
    g.fillStyle = rg;
    g.fill();
    g.strokeStyle = "rgba(155, 168, 192, 0.26)";
    g.lineWidth = 1;
    g.stroke();

    // Foreground regolith contour
    g.beginPath();
    g.moveTo(0, sh);
    for (var j = 0; j <= steps; j++) {
      var u2 = j / steps;
      var padFlat2 = 1 - 0.86 * Math.exp(-Math.pow((u2 - padU) / 0.045, 2));
      var f1 = Math.sin(u2 * (stage === 0 ? 15.0 : stage === 1 ? 24.0 : 34.0) + 2.1) * 0.5 + 0.5;
      var f2 = Math.cos(u2 * (stage === 0 ? 37.0 : stage === 1 ? 53.0 : 78.0) - 0.6) * 0.5 + 0.5;
      var fgH = (2.5 + (stage === 0 ? 5.5 : stage === 1 ? 6.5 : 7.5) * (f1 * 0.6 + f2 * 0.4)) * padFlat2;
      g.lineTo(u2 * pw, sh - fgH);
    }
    g.lineTo(pw, sh);
    g.closePath();
    var fg = g.createLinearGradient(0, sh - 12, 0, sh);
    fg.addColorStop(0, "rgba(110, 118, 134, 0.72)");
    fg.addColorStop(1, "rgba(42, 47, 58, 0.95)");
    g.fillStyle = fg;
    g.fill();
    g.strokeStyle = "rgba(195, 204, 222, 0.38)";
    g.lineWidth = 1;
    g.stroke();

    // Procedural craters & boulders (denser as zoom increases)
    var nCraters = stage === 0 ? 9 : stage === 1 ? 18 : 30;
    for (var k = 0; k < nCraters; k++) {
      var cu = (k + 0.18 + 0.64 * rnd()) / nCraters;
      if (Math.abs(cu - padU) < 0.028) continue;
      var cx = cu * pw;
      var crw = (stage === 0 ? (6 + rnd() * 14) : stage === 1 ? (5 + rnd() * 12) : (3.5 + rnd() * 10));
      // West Crater / boulder field emphasis just short of landing pad in stage 2
      if (stage === 2 && cu > 0.72 && cu < 0.87 && k % 3 === 0) crw *= 1.35;
      var cry = Math.max(1.4, crw * 0.24);
      var cy = sh - 2.2 - rnd() * 4.5;

      // Shadowed bowl
      g.fillStyle = "rgba(14, 18, 26, 0.68)";
      g.beginPath();
      g.ellipse(cx, cy, crw, cry, 0, 0, Math.PI * 2);
      g.fill();

      // Sunlit western/left inner rim arc (low eastern sun from right)
      g.strokeStyle = "rgba(210, 218, 234, 0.46)";
      g.lineWidth = 1;
      g.beginPath();
      g.ellipse(cx - crw * 0.08, cy, crw * 0.95, cry * 0.92, 0, Math.PI * 0.65, Math.PI * 1.45);
      g.stroke();

      // Stage 2 boulder field ejecta blocks
      if (stage === 2 && cu > 0.64 && cu < 0.88) {
        var bx = cx + (rnd() - 0.5) * crw * 1.6;
        var by = sh - 1.5 - rnd() * 3.5;
        var br = 1.1 + rnd() * 1.6;
        g.fillStyle = "rgba(12, 15, 22, 0.75)";
        g.fillRect(bx - br * 2.2, by - br * 0.4, br * 2.2, br * 0.9);
        g.fillStyle = "rgba(205, 212, 226, 0.65)";
        g.beginPath();
        g.arc(bx, by, br, 0, Math.PI * 2);
        g.fill();
      }
    }

    return { canvas: c, sh: sh };
  }

  function s3_drawDescentTerrain(c, v) {
    var stage = v.y1 > 6 ? 0 : v.y1 > 0.8 ? 1 : 2;
    var pw = Math.max(1, Math.round(c.pw));
    var key = stage + ":" + pw + ":" + DPR;
    var item = s3_descTerrainCache[key];
    if (!item) {
      item = s3_buildDescentTerrain(stage, pw, DPR);
      s3_descTerrainCache[key] = item;
    }
    var gy = c.Y(0);
    ctx.fillStyle = C["panel-2"];
    ctx.fillRect(c.m.l, gy, c.pw, 4000);
    ctx.drawImage(item.canvas, c.m.l, gy - item.sh, pw, item.sh);
  }

  function s3_drawPillTag(txt, x, y, col, align, bgAlpha) {
    ctx.save();
    ctx.font = "600 11px Barlow Condensed, Arial Narrow, sans-serif";
    var up = txt.toUpperCase();
    var tw = ctx.measureText(up).width;
    var padX = 5, bh = 15, bw = tw + padX * 2;
    var bx = align === "right" ? x - tw - padX : align === "center" ? x - tw * 0.5 - padX : x - padX;
    var by = y - 11;
    ctx.fillStyle = "rgba(11, 16, 24, " + (bgAlpha == null ? 0.82 : bgAlpha) + ")";
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 3);
    else ctx.rect(bx, by, bw, bh);
    ctx.fill();
    ctx.strokeStyle = col;
    ctx.globalAlpha = 0.38;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
    text(up, x, y, { size: 11, weight: 600, color: col, font: "Barlow Condensed, Arial Narrow, sans-serif", align: align || "left" });
  }

  SCENES.descent = function (g, dt) {
    var tr = T.descent;
    var s = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y], ["p", tr.pitch_deg], ["th", tr.throttle], ["vv", tr.v_vert]], g);
    s.th /= 100; // throttle is stored in percent
    var tgt = s.y > 2.6 ? { x0: -460, x1: 12, y0: 0, y1: 16 } : s.y > 0.25 ? { x0: -9, x1: 0.6, y0: 0, y1: 2.4 } : { x0: -1.6, x1: 0.15, y0: 0, y1: 0.26 };
    var v = smooth(tgt, "descent", dt);
    var c = chart(v, tr.x_label, tr.y_label);

    var landed = g >= EV.touchdown.get || s.y <= 0;
    var ph = tr.phase[Math.min(s.i + (s.f > 0.5 ? 1 : 0), tr.phase.length - 1)];
    var marks = tr.marks || {};
    var lrGet = marks.radar_lock_get;
    var tdGet = marks.throttle_down_get;

    // Ground & cached procedural lunar terrain silhouette strip
    s3_drawDescentTerrain(c, v);

    // Full trajectory dashed preview
    polyline(tr.x, tr.y, c.X, c.Y, 0, tr.x.length - 1, C.lm, 1, [4, 5], 0.28);

    // Phase-coloured travelled path + glowing comet trail on current phase head
    var start = 0;
    for (var i = 1; i <= s.i; i++) {
      if (tr.phase[i] !== tr.phase[start]) {
        polyline(tr.x, tr.y, c.X, c.Y, start, i, C[PHC[tr.phase[start]]], 2.4);
        start = i;
      }
    }
    if (s.i > start) {
      polyline(tr.x, tr.y, c.X, c.Y, start, s.i, C[PHC[tr.phase[start]]], 2.2);
    }
    FX.trail(tr.x, tr.y, c.X, c.Y, start, s.i, s.f, C[PHC[tr.phase[start]]], { width: 2.5, tail: 42, baseAlpha: 0.35 });

    var px = c.X(s.x), py = c.Y(s.y);
    var lmScale = v.y1 > 8 ? 0.96 : v.y1 > 1 ? 1.22 : 1.48;
    var gy = c.Y(0);
    var eagleY = Math.min(py, gy - 9.2 * lmScale);

    // One-shot FX triggers when crossing events/marks during playback
    if (s3_descCrossed(EV.pdi.get, g, s3_descPrevG)) {
      FX.ping(px, eagleY, C.amber);
      FX.flash(C.amber, 0.12);
      FX.shake(2.5);
    }
    if (lrGet && s3_descCrossed(lrGet, g, s3_descPrevG)) {
      var qlr0 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], lrGet);
      FX.ping(c.X(qlr0.x), c.Y(qlr0.y), C.el || C.csm);
    }
    if (tdGet && s3_descCrossed(tdGet, g, s3_descPrevG)) {
      var qtd0 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], tdGet);
      FX.ping(c.X(qtd0.x), c.Y(qtd0.y), C.amber);
    }
    if (s3_descCrossed(EV["alarm-1202"].get, g, s3_descPrevG)) {
      var qa1 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], EV["alarm-1202"].get);
      FX.ping(c.X(qa1.x), c.Y(qa1.y), C.alarm);
      FX.flash(C.alarm, 0.22);
      FX.shake(5.0);
    }
    if (s3_descCrossed(EV.p64.get, g, s3_descPrevG)) {
      var qp64 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], EV.p64.get);
      FX.ping(c.X(qp64.x), c.Y(qp64.y), C.p64);
    }
    if (s3_descCrossed(EV["alarm-1201"].get, g, s3_descPrevG)) {
      var qa2 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], EV["alarm-1201"].get);
      FX.ping(c.X(qa2.x), c.Y(qa2.y), C.alarm);
      FX.flash(C.alarm, 0.22);
      FX.shake(5.0);
    }
    if (s3_descCrossed(EV.p66.get, g, s3_descPrevG)) {
      var qp66 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], EV.p66.get);
      FX.ping(c.X(qp66.x), c.Y(qp66.y), C.p66);
    }
    if (s3_descCrossed(EV.touchdown.get, g, s3_descPrevG)) {
      FX.ping(px, gy - 4, C.amber);
      FX.dust(px, gy, 1.85, true);
      FX.shake(5.2);
      FX.flash(C.amber, 0.16);
    }
    s3_descPrevG = g;

    // Landing radar beam cone from Eagle to lunar surface once radar locks
    if (lrGet && g >= lrGet && !landed && gy - eagleY > 8) {
      var lrCol = C.el || C.csm;
      var beamH = gy - eagleY;
      var coneSpread = Math.min(44, Math.max(12, beamH * 0.16));
      var beamCenterX = px + Math.min(28, Math.max(-18, (s.p / 90) * beamH * 0.18));
      ctx.save();
      var bg = ctx.createLinearGradient(px, eagleY + 6, beamCenterX, gy);
      bg.addColorStop(0, "rgba(82, 224, 164, 0.22)");
      bg.addColorStop(0.7, "rgba(82, 224, 164, 0.09)");
      bg.addColorStop(1, "rgba(82, 224, 164, 0.02)");
      ctx.fillStyle = bg;
      ctx.beginPath();
      ctx.moveTo(px, eagleY + 5);
      ctx.lineTo(beamCenterX - coneSpread, gy);
      ctx.lineTo(beamCenterX + coneSpread, gy);
      ctx.closePath();
      ctx.fill();

      // Pulsing radar wavefront arcs down the cone
      var rPhase = reduceMotion ? 0.35 : ((state.playing ? performance.now() * 0.0018 : g * 0.6) % 1);
      ctx.strokeStyle = lrCol;
      ctx.lineWidth = 1.1;
      for (var rw = 0; rw < 3; rw++) {
        var ru = (rw / 3 + rPhase / 3) % 1;
        if (ru < 0.12) continue;
        var ry = eagleY + 6 + ru * (beamH - 6);
        var rx = px + (beamCenterX - px) * ru;
        var rhw = coneSpread * ru * 0.92;
        ctx.globalAlpha = (1 - ru) * 0.38;
        ctx.beginPath();
        ctx.moveTo(rx - rhw, ry - 2);
        ctx.quadraticCurveTo(rx, ry + 3.5, rx + rhw, ry - 2);
        ctx.stroke();
      }
      ctx.restore();

      // Keep a compact LR LOCK tag near the beam when zoomed past Stage 0
      if (v.x0 > -50 && beamH > 46) {
        s3_drawPillTag("LR LOCK", px - coneSpread * 0.55 - 6, eagleY + Math.min(54, beamH * 0.45), lrCol, "right", 0.75);
      }
    }

    // P64 pitch-over: dashed LPD line-of-sight from Eagle to landing site
    var siteX = c.X(0), siteY = gy;
    if (ph === 64 && !landed) {
      ctx.save();
      ctx.strokeStyle = C.p64;
      ctx.lineWidth = 1.4;
      ctx.setLineDash([6, 5]);
      ctx.globalAlpha = 0.72;
      ctx.beginPath();
      ctx.moveTo(px, eagleY);
      ctx.lineTo(siteX, siteY);
      ctx.stroke();
      ctx.setLineDash([]);
      // Sightline reticle on landing site
      ctx.globalAlpha = 0.65;
      ctx.beginPath();
      ctx.arc(siteX, siteY, 9, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      var midX = px + (siteX - px) * 0.48;
      var midY = eagleY + (siteY - eagleY) * 0.48;
      s3_drawPillTag("LPD LINE OF SIGHT", midX + 8, midY - 6, C.p64, "left", 0.8);
    }

    // Marks on the trajectory: radar lock & throttle-down
    if (lrGet && g >= lrGet) {
      var qlr = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], lrGet);
      var lrx = c.X(qlr.x), lry = c.Y(qlr.y);
      if (lrx >= c.m.l - 10 && lrx <= c.m.l + c.pw + 10) {
        FX.glowDot(lrx, lry, 3.2, C.el || C.csm);
        s3_drawPillTag("LR LOCK", lrx - 8, lry - 7, C.el || C.csm, "right");
      }
    }
    if (tdGet && g >= tdGet) {
      var qtd = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], tdGet);
      var tdx = c.X(qtd.x), tdy = c.Y(qtd.y);
      if (tdx >= c.m.l - 10 && tdx <= c.m.l + c.pw + 10) {
        FX.glowDot(tdx, tdy, 3.4, C.amber);
        s3_drawPillTag("THROTTLE DOWN", tdx - 8, tdy + 15, C.amber, "right");
      }
    }

    // Events on the path (1202, P64, 1201, P66)
    var nowPlay = getToPlay(g);
    [["alarm-1202", "1202", C.alarm], ["p64", "P64 PITCH-OVER", C.p64], ["alarm-1201", "1201", C.alarm], ["p66", "P66", C.p66]].forEach(function (e) {
      var eg = EV[e[0]].get;
      if (g < eg) return;
      var q = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], eg);
      var ex = c.X(q.x), ey = c.Y(q.y);
      var isAlarm = e[0] === "alarm-1202" || e[0] === "alarm-1201";
      FX.glowDot(ex, ey, isAlarm ? 4.2 : 3.5, e[2]);
      if (isAlarm) {
        // Deterministic expanding red ring on path during alarm window so scrubbing/screenshots show it
        var dpEv = nowPlay - getToPlay(eg);
        if (dpEv >= 0 && dpEv <= 4.2) {
          var ringU = Math.min(1, dpEv / 1.8);
          var ringR = 8 + ringU * 22;
          ctx.save();
          ctx.strokeStyle = C.alarm;
          ctx.lineWidth = 2.0;
          ctx.globalAlpha = (1 - ringU * 0.65) * 0.85;
          ctx.beginPath();
          ctx.arc(ex, ey, ringR, 0, Math.PI * 2);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(ex, ey, ringR * 0.58, 0, Math.PI * 2);
          ctx.globalAlpha = 0.55;
          ctx.stroke();
          ctx.restore();
        }
      }
      var lblDx = (e[0] === "p66" && Math.abs(g - eg) < 12) ? -18 : -8;
      var lblDy = (e[0] === "p66" && Math.abs(g - eg) < 12) ? 6 : 15;
      label(e[1], ex + lblDx, ey + lblDy, e[2], "right");
    });

    // Landing site marker & flag
    FX.glowDot(siteX, siteY, 3.0, C.amber);
    ctx.beginPath();
    ctx.moveTo(siteX, siteY);
    ctx.lineTo(siteX, siteY - 19);
    ctx.strokeStyle = C.amber;
    ctx.lineWidth = 1.6;
    ctx.stroke();
    ctx.fillStyle = C.amber;
    ctx.fillRect(siteX, siteY - 19, 10, 6.5);

    // Low-altitude engine plume ground glow, contact shadow & regolith dust (< ~30 m)
    if (!landed && g >= EV.pdi.get && s.y < 0.065) {
      var low01 = Math.max(0, Math.min(1, 1 - s.y / 0.065));
      var glowR = (18 + 38 * low01) * Math.max(0.4, s.th);
      var gg = ctx.createRadialGradient(px, gy, 1, px, gy, glowR);
      gg.addColorStop(0, "rgba(255, 200, 95, " + (0.45 * low01).toFixed(3) + ")");
      gg.addColorStop(0.5, "rgba(242, 177, 60, " + (0.20 * low01).toFixed(3) + ")");
      gg.addColorStop(1, "rgba(242, 177, 60, 0)");
      ctx.save();
      ctx.fillStyle = gg;
      ctx.beginPath();
      ctx.ellipse(px, gy, glowR * 1.35, Math.max(4, glowR * 0.25), 0, 0, Math.PI * 2);
      ctx.fill();
      // Subtle dark spacecraft shadow under footpads right before contact
      if (s.y < 0.025) {
        ctx.fillStyle = "rgba(5, 8, 14, " + ((1 - s.y / 0.025) * 0.55).toFixed(3) + ")";
        ctx.beginPath();
        ctx.ellipse(px, gy, 11 * lmScale, 2.5 * lmScale, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }
    if (!landed && s.y < 0.032 && g >= EV.pdi.get) {
      var dustStr = (1 - s.y / 0.032) * 1.45 * Math.max(0.35, s.th);
      FX.dust(px, gy, dustStr);
      // Deterministic sideways dust wisps so paused/scrubbed low-altitude frames show blowing regolith
      ctx.save();
      ctx.fillStyle = C.moon;
      var wispSpan = (18 + 46 * (1 - s.y / 0.032)) * lmScale;
      ctx.globalAlpha = 0.24 * Math.min(1, dustStr);
      ctx.beginPath();
      ctx.ellipse(px - wispSpan * 0.45, gy - 2, wispSpan * 0.42, 3.2, -0.06, 0, Math.PI * 2);
      ctx.ellipse(px + wispSpan * 0.45, gy - 2, wispSpan * 0.42, 3.2, 0.06, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    } else if (landed && g - EV.touchdown.get < 14) {
      // Settling dust cloud right after touchdown
      var settle01 = Math.max(0, 1 - (g - EV.touchdown.get) / 14);
      FX.dust(px, gy, settle01 * 0.65);
    }

    // Eagle spacecraft glyph rotated by real pitch & scaled with zoom stage, with throttle-scaled exhaust
    var pitchRad = -(landed ? 0 : s.p) * Math.PI / 180;
    var thrActive = (!landed && g >= EV.pdi.get) ? s.th : 0;
    FX.craft("lm", px, eagleY, pitchRad, lmScale, { upright: true, engine: thrActive > 0, throttle: thrActive });

    var nearRight = px + 46 > c.m.l + c.pw;
    var eagleLblX = landed ? (px + 10.5 * lmScale) : (nearRight ? px - 13 * lmScale : px + 13 * lmScale);
    var eagleLblY = landed ? (eagleY - 4 * lmScale) : Math.min(gy - 14, eagleY - 8 * lmScale);
    var eagleAlign = (!landed && nearRight) ? "right" : "left";
    label("EAGLE", eagleLblX, eagleLblY, C.lm, eagleAlign);
    if (ph === 66 && !landed) {
      s3_drawPillTag("MANUAL", eagleLblX, eagleLblY + 15, C.p66, eagleAlign);
    }

    // Program Alarm 1202 / 1201 Banner (holds ~3 s of playback then fades, derived from g)
    var alarms = [
      { id: "alarm-1202", code: "ALARM 1202", sub: "EXECUTIVE OVERFLOW · NO CORE SETS (BAILOUT)" },
      { id: "alarm-1201", code: "ALARM 1201", sub: "EXECUTIVE OVERFLOW · NO VAC AREAS (RESTART)" }
    ];
    for (var ai = 0; ai < alarms.length; ai++) {
      var al = alarms[ai];
      var ag = EV[al.id].get;
      var dpAl = nowPlay - getToPlay(ag);
      if (dpAl >= 0 && dpAl <= 4.2) {
        var alAlpha = dpAl <= 3.0 ? 1 : Math.max(0, 1 - (dpAl - 3.0) / 1.2);
        var bcx = c.m.l + c.pw * 0.45;
        var bcy = c.m.t + 26;
        var bw = Math.min(c.pw - 24, 304), bh = 38;
        ctx.save();
        ctx.globalAlpha = alAlpha;
        ctx.fillStyle = "rgba(28, 10, 14, 0.90)";
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(bcx - bw * 0.5, bcy - bh * 0.5, bw, bh, 5);
        else ctx.rect(bcx - bw * 0.5, bcy - bh * 0.5, bw, bh);
        ctx.fill();
        ctx.strokeStyle = C.alarm;
        ctx.lineWidth = 1.6;
        ctx.stroke();

        // Flashing/glowing warning dot
        ctx.fillStyle = C.alarm;
        ctx.beginPath();
        ctx.arc(bcx - bw * 0.5 + 16, bcy - 4, 4.5, 0, Math.PI * 2);
        ctx.fill();

        text(al.code, bcx - bw * 0.5 + 28, bcy - 1, { size: 14, weight: 700, color: C.alarm, font: "Barlow Condensed, Arial Narrow, sans-serif" });
        text("PROG · V05N09", bcx + bw * 0.5 - 12, bcy - 1, { size: 11, weight: 600, color: C.amber, font: "IBM Plex Mono, monospace", align: "right" });
        text(al.sub, bcx - bw * 0.5 + 28, bcy + 13, { size: 10, weight: 500, color: C.fg, font: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" });
        ctx.restore();
      }
    }

    // Calm "TRANQUILITY BASE" title fade-in after touchdown
    if (landed) {
      var tdElapsed = Math.max(0, g - EV.touchdown.get);
      var tbAlpha = state.playing ? Math.min(1, 0.38 + tdElapsed / 6.0) : 1;
      var tcx = c.m.l + c.pw * 0.44;
      var tcy = c.m.t + 40;
      ctx.save();
      ctx.globalAlpha = tbAlpha;
      var tbw = Math.min(c.pw - 24, 290), tbh = 48;
      ctx.fillStyle = "rgba(11, 16, 25, 0.84)";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(tcx - tbw * 0.5, tcy - 22, tbw, tbh, 5);
      else ctx.rect(tcx - tbw * 0.5, tcy - 22, tbw, tbh);
      ctx.fill();
      ctx.strokeStyle = C.amber;
      ctx.globalAlpha = tbAlpha * 0.55;
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.globalAlpha = tbAlpha;
      text("TRANQUILITY BASE", tcx, tcy, { size: 20, weight: 700, color: C.fg, font: "Barlow Condensed, Arial Narrow, sans-serif", align: "center" });
      text("THE EAGLE HAS LANDED · ENGINE OFF", tcx, tcy + 17, { size: 11, weight: 600, color: C.amber, font: "Barlow Condensed, Arial Narrow, sans-serif", align: "center" });
      ctx.restore();
    }

    // Real telemetry mini-HUD in the open lower-left quadrant of the chart
    var vhVal = s3_descTele(tr, "vh", g);
    var dhVal = (lrGet && g >= lrGet) ? s3_descTele(tr, "delta_h", g) : null;
    if (c.pw > 280 && c.ph > 190) {
      var hx = c.m.l + 12, hy = gy - 84;
      var ttg = Math.max(0, Math.round(EV.touchdown.get - g));
      var ttgStr = landed ? "00:00" : pad(Math.floor(ttg / 60), 2) + ":" + pad(ttg % 60, 2);
      ctx.save();
      ctx.fillStyle = "rgba(10, 15, 23, 0.74)";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(hx, hy, 152, dhVal !== null ? 58 : 44, 4);
      else ctx.rect(hx, hy, 152, dhVal !== null ? 58 : 44);
      ctx.fill();
      ctx.strokeStyle = C.line;
      ctx.lineWidth = 1;
      ctx.stroke();
      var hudRows = [
        ["HORIZ SPD", (landed ? 0 : (vhVal != null ? vhVal : 0)).toFixed(1) + " m/s", C.fg],
        ["PITCH", (landed ? 0 : s.p).toFixed(1) + "°", C.fg],
        ["T-TOUCHDOWN", landed ? "LANDED" : ttgStr, landed ? C.amber : C.muted]
      ];
      if (dhVal !== null && !landed) {
        hudRows.push(["RADAR ΔH", (dhVal >= 0 ? "+" : "") + dhVal.toFixed(1) + " m", C.el || C.csm]);
      }
      for (var hr = 0; hr < hudRows.length; hr++) {
        var ry2 = hy + 13 + hr * 13;
        text(hudRows[hr][0], hx + 7, ry2, { size: 10, weight: 600, color: C.muted, font: "Barlow Condensed, Arial Narrow, sans-serif" });
        text(hudRows[hr][1], hx + 145, ry2, { size: 11, weight: 500, color: hudRows[hr][2], font: "IBM Plex Mono, monospace", align: "right" });
      }
      ctx.restore();
    }

    // Air-to-ground callouts subtitle near bottom of chart (~4 s of playback each, alpha from g)
    if (D.callouts && D.callouts.length) {
      var activeCo = null, activeDp = 999;
      for (var ci = 0; ci < D.callouts.length; ci++) {
        var co = D.callouts[ci];
        if (co.get < EV.pdi.get - 5 || co.get > EV.touchdown.get + 30) continue;
        var dpCo = nowPlay - getToPlay(co.get);
        if (dpCo >= 0 && dpCo <= 4.2) {
          activeCo = co;
          activeDp = dpCo;
        }
      }
      if (activeCo) {
        var coAlpha = activeDp <= 3.2 ? 1 : Math.max(0, 1 - (activeDp - 3.2) / 1.0);
        var spk = activeCo.speaker.toUpperCase() + ": ";
        var quote = "\u201c" + activeCo.text + "\u201d";
        var approxTag = activeCo.approx ? " (time approx.)" : "";
        ctx.save();
        ctx.font = "500 12px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
        var wQuote = ctx.measureText(quote).width;
        ctx.font = "700 12px Barlow Condensed, Arial Narrow, sans-serif";
        var wSpk = ctx.measureText(spk).width;
        ctx.font = "400 10px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
        var wApp = approxTag ? ctx.measureText(approxTag).width : 0;
        var totalW = Math.min(c.pw - 20, wSpk + wQuote + wApp + 22);
        var scx = c.m.l + c.pw * 0.5;
        var scy = gy - 16;

        ctx.globalAlpha = coAlpha;
        ctx.fillStyle = "rgba(9, 13, 21, 0.88)";
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(scx - totalW * 0.5, scy - 14, totalW, 22, 4);
        else ctx.rect(scx - totalW * 0.5, scy - 14, totalW, 22);
        ctx.fill();
        ctx.strokeStyle = C.amber;
        ctx.globalAlpha = coAlpha * 0.42;
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.globalAlpha = coAlpha;
        var tx0 = scx - (wSpk + wQuote + wApp) * 0.5;
        text(spk, tx0, scy + 1, { size: 12, weight: 700, color: C.amber, font: "Barlow Condensed, Arial Narrow, sans-serif" });
        text(quote, tx0 + wSpk, scy + 1, { size: 12, weight: 500, color: C.fg, font: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" });
        if (approxTag) {
          text(approxTag, tx0 + wSpk + wQuote, scy + 1, { size: 10, weight: 400, color: C.muted, font: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" });
        }
        ctx.restore();
      }
    }

    c.done();
    note(tr.note + " The view zooms in as Eagle gets lower; terrain profile is illustrative.");
    readout([
      ["Program", landed ? "P68" : "P" + ph, C[PHC[ph]]],
      ["Altitude", s.y >= 1 ? s.y.toFixed(2) + " km" : Math.round(s.y * 1000) + " m"],
      ["Sink rate", (landed ? 0 : -s.vv).toFixed(1) + " m/s"],
      ["Throttle", landed ? "off" : Math.round(s.th * 100) + " %"],
      ["To site", Math.abs(s.x) >= 1 ? Math.abs(s.x).toFixed(1) + " km" : Math.round(Math.abs(s.x) * 1000) + " m"]
    ]);
  };
