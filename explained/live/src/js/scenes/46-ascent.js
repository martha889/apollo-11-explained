  var s4_asc_prevG = null;
  var s4_asc_terrainCache = null;

  function s4_asc_crossed(t, g, prevG) {
    if (!state.playing || prevG === null) return false;
    var maxStep = 30 * (state.speed || 1);
    return prevG < t && g >= t && (g - prevG) < maxStep;
  }

  function s4_asc_getTerrain(pw, ph, dpr) {
    var cw = Math.max(1, Math.round(pw)), ch = Math.max(1, Math.round(ph));
    if (s4_asc_terrainCache && s4_asc_terrainCache.w === cw && s4_asc_terrainCache.h === ch && s4_asc_terrainCache.dpr === dpr) {
      return s4_asc_terrainCache;
    }
    var pts = [];
    var n = Math.max(60, Math.round(cw / 6));
    for (var i = 0; i <= n; i++) {
      var u = i / n;
      // Flat near Tranquility Base (u ~ 0.025), gentle craters and mare ridges downrange
      var dist0 = Math.abs(u - 0.025);
      var flatMask = Math.min(1, Math.max(0, (dist0 - 0.018) / 0.045));
      var r1 = Math.sin(u * 19.3 + 0.4) * 0.45 + Math.sin(u * 47.7 + 1.9) * 0.30 + Math.cos(u * 91.1 - 0.7) * 0.25;
      var crater = Math.exp(-Math.pow((u - 0.28) / 0.032, 2)) * -3.2 +
                   Math.exp(-Math.pow((u - 0.25) / 0.012, 2)) * 2.4 +
                   Math.exp(-Math.pow((u - 0.31) / 0.012, 2)) * 2.4 +
                   Math.exp(-Math.pow((u - 0.64) / 0.042, 2)) * -3.8 +
                   Math.exp(-Math.pow((u - 0.60) / 0.015, 2)) * 2.8 +
                   Math.exp(-Math.pow((u - 0.68) / 0.015, 2)) * 2.8;
      var h = (2.8 + r1 * 3.6 + crater) * flatMask;
      pts.push([u * cw, Math.max(-2.5, h)]);
    }
    s4_asc_terrainCache = { w: cw, h: ch, dpr: dpr, pts: pts };
    return s4_asc_terrainCache;
  }

  function s4_asc_pillLabel(txt, x, y, color, align) {
    var up = txt.toUpperCase();
    var al = align || "left";
    ctx.save();
    ctx.font = "600 12px Barlow Condensed, Arial Narrow, sans-serif";
    var tw = ctx.measureText(up).width;
    var padX = 5, bh = 15, bw = tw + padX * 2;
    var bx = al === "right" ? x - tw - padX : al === "center" ? x - tw * 0.5 - padX : x - padX;
    var by = y - 11.5;
    ctx.fillStyle = "rgba(13, 18, 27, 0.80)";
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 3);
    else ctx.rect(bx, by, bw, bh);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.28;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
    label(up, x, y, color, al);
  }

  function s4_asc_drawDescentStage(x, y, blast01) {
    ctx.save();
    ctx.translate(x, y);
    // Subtle lunar shadow beneath descent stage
    ctx.fillStyle = "rgba(5, 8, 13, 0.65)";
    ctx.beginPath();
    ctx.ellipse(0, 1.5, 14, 2.5, 0, 0, Math.PI * 2);
    ctx.fill();

    // Splayed landing legs & footpads resting on y = 0
    ctx.strokeStyle = "#d99b26";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(-6, -5); ctx.lineTo(-11.5, 0.5);
    ctx.moveTo(6, -5); ctx.lineTo(11.5, 0.5);
    ctx.moveTo(-4.5, -1.5); ctx.lineTo(-11.5, 0.5);
    ctx.moveTo(4.5, -1.5); ctx.lineTo(11.5, 0.5);
    // Footpads
    ctx.moveTo(-13.5, 0.5); ctx.lineTo(-9.5, 0.5);
    ctx.moveTo(9.5, 0.5); ctx.lineTo(13.5, 0.5);
    ctx.stroke();

    // Descent engine skirt
    ctx.fillStyle = "#4d5868";
    ctx.beginPath();
    ctx.moveTo(-2.5, -1.5); ctx.lineTo(-4.0, 0.5); ctx.lineTo(4.0, 0.5); ctx.lineTo(2.5, -1.5);
    ctx.closePath();
    ctx.fill();

    // Gold Kapton octagonal descent stage body
    ctx.fillStyle = C.lm || "#f2b13c";
    ctx.strokeStyle = C.bg || "#0d121b";
    ctx.lineWidth = 1;
    ctx.fillRect(-6.5, -6.5, 13, 5.2);
    ctx.strokeRect(-6.5, -6.5, 13, 5.2);
    // Dark thermal panels
    ctx.fillStyle = "#252d3a";
    ctx.fillRect(-2.2, -6.0, 4.4, 4.2);

    // Small illustrative U.S. flag planted at Tranquility Base
    ctx.strokeStyle = "#cfd8e6";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(-18, 0.5); ctx.lineTo(-18, -8.5);
    ctx.stroke();
    ctx.fillStyle = "#d9534f";
    ctx.fillRect(-18, -8.5, 5.5, 3.4);
    ctx.fillStyle = "#4a90e2";
    ctx.fillRect(-18, -8.5, 2.4, 1.8);

    // Liftoff blast / staging fire-in-the-hole glow during first seconds
    if (blast01 > 0.01) {
      ctx.globalCompositeOperation = "lighter";
      var r = (14 + 22 * blast01);
      var bg = ctx.createRadialGradient(0, -6, 1, 0, -4, r);
      bg.addColorStop(0, "rgba(255, 250, 230, " + (0.85 * blast01).toFixed(3) + ")");
      bg.addColorStop(0.35, "rgba(242, 177, 60, " + (0.55 * blast01).toFixed(3) + ")");
      bg.addColorStop(1, "rgba(224, 82, 25, 0)");
      ctx.fillStyle = bg;
      ctx.beginPath();
      ctx.ellipse(0, -4, r * 1.35, r * 0.65, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  SCENES.ascent = function (g, dt) {
    var tr = T.ascent;
    var s = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y], ["p", tr.pitch_deg], ["fpa", tr.fpa_deg]], g);
    var spdSeries = null;
    if (tr.telemetry) {
      for (var ti = 0; ti < tr.telemetry.length; ti++) {
        if (tr.telemetry[ti].key === "speed") { spdSeries = tr.telemetry[ti]; break; }
      }
    }
    var spdVal = spdSeries ? sampleTrack(spdSeries.get, [["v", spdSeries.v]], g).v : 0;

    // Slight negative y0 (-1.3 km) keeps axis ticks starting at 0 while giving lunar terrain & descent stage room below y=0
    var v = smooth({ x0: -8, x1: 310, y0: -1.3, y1: 22 }, "ascent", dt);

    // Stars fade in with altitude above the lunar surface
    var starAlpha = 0.34 + 0.62 * Math.min(1, Math.max(0, s.y / 10));
    ctx.save();
    ctx.globalAlpha = starAlpha * 0.65;
    drawStars();
    ctx.restore();

    var c = chart(v, tr.x_label, tr.y_label);
    var yZero = c.Y(0);

    // Stars inside the plot area above the lunar horizon, fading gently near the horizon
    ctx.save();
    ctx.beginPath();
    ctx.rect(c.m.l, c.m.t, c.pw, Math.max(0, yZero - c.m.t));
    ctx.clip();
    ctx.globalAlpha = starAlpha * 0.78;
    drawStars();
    var hFade = ctx.createLinearGradient(0, Math.max(c.m.t, yZero - 48), 0, yZero);
    hFade.addColorStop(0, "rgba(13, 18, 27, 0)");
    hFade.addColorStop(1, "rgba(18, 24, 36, 0.55)");
    ctx.fillStyle = hFade;
    ctx.fillRect(c.m.l, Math.max(c.m.t, yZero - 48), c.pw, 48);
    ctx.restore();

    // Faint target insertion orbit line & band at the top (perilune x apolune)
    var yIns = tr.y[tr.y.length - 1];
    var yPeri = tr.perilune_km || yIns;
    var pyIns = c.Y(yIns), pyPeri = c.Y(yPeri);
    ctx.save();
    ctx.fillStyle = C.lm;
    ctx.globalAlpha = 0.06;
    ctx.fillRect(c.m.l, Math.min(pyIns, pyPeri) - 2, c.pw, Math.abs(pyPeri - pyIns) + 4);
    ctx.strokeStyle = C.lm;
    ctx.globalAlpha = 0.36;
    ctx.lineWidth = 1.2;
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(c.m.l, pyIns);
    ctx.lineTo(c.m.l + c.pw, pyIns);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 0.78;
    label("TARGET INSERTION ORBIT  " + tr.perilune_km.toFixed(1) + " × " + tr.apolune_km.toFixed(1) + " KM", c.m.l + 10, pyIns - 6, C.lm, "left");
    ctx.restore();

    // Cached lunar terrain silhouette along y = 0
    var terr = s4_asc_getTerrain(c.pw, c.ph, DPR);
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(c.m.l, c.m.t + c.ph + 4);
    for (var ri = 0; ri < terr.pts.length; ri++) {
      ctx.lineTo(c.m.l + terr.pts[ri][0], yZero - terr.pts[ri][1]);
    }
    ctx.lineTo(c.m.l + c.pw, c.m.t + c.ph + 4);
    ctx.closePath();
    var tGrad = ctx.createLinearGradient(0, yZero - 10, 0, c.m.t + c.ph);
    tGrad.addColorStop(0, "#2b3342");
    tGrad.addColorStop(0.35, C["panel-2"]);
    tGrad.addColorStop(1, "#121722");
    ctx.fillStyle = tGrad;
    ctx.fill();
    ctx.strokeStyle = "rgba(185, 192, 206, 0.38)";
    ctx.lineWidth = 1.2;
    ctx.stroke();
    ctx.restore();

    // Vertical rise & pitch-over guide on the initial climb
    var x0px = c.X(0);
    var qPoRef = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], tr.get[48]); // ~2.8 km alt knee where pitch-over curve bends downrange
    var pox = c.X(qPoRef.x), poy = c.Y(qPoRef.y);
    ctx.save();
    ctx.strokeStyle = C.muted;
    ctx.globalAlpha = 0.30;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.moveTo(x0px, yZero - 6);
    ctx.lineTo(x0px, c.Y(4.2));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = g >= tr.get[4] ? 0.84 : 0.58;
    ctx.fillStyle = C.amber;
    ctx.beginPath();
    ctx.arc(pox, poy, 2.5, 0, Math.PI * 2);
    ctx.fill();
    label("VERTICAL RISE → PITCHOVER", pox + 10, poy + 12, g >= tr.get[4] ? C.amber : C.muted, "left");
    ctx.restore();

    // Planned full ascent trajectory (dashed) + active comet trail
    polyline(tr.x, tr.y, c.X, c.Y, 0, tr.x.length - 1, C.lm, 1, [4, 5], 0.32);
    FX.trail(tr.x, tr.y, c.X, c.Y, 0, s.i, s.f, C.lm, { width: 2.5, tail: 56 });

    // Liftoff blast & regolith dust in the first seconds
    var t0 = tr.get[0], tCut = tr.get[tr.get.length - 1];
    var burning = g >= t0 && g < tCut;
    var elapsed = Math.max(0, g - t0);
    var blast01 = burning && elapsed < 14 ? Math.max(0, 1 - elapsed / 14) : 0;

    // Leave descent stage at x = 0 on the lunar surface
    s4_asc_drawDescentStage(x0px, yZero, blast01);
    if (elapsed > 6) {
      label("DESCENT STAGE", x0px + 16, yZero - 2, C.muted, "left");
    }
    if (blast01 > 0.02) {
      FX.dust(x0px, yZero + 1, blast01 * 1.45);
    }

    // One-shot triggers (only when crossing event times during playback)
    if (s4_asc_crossed(t0 + 0.4, g, s4_asc_prevG)) {
      FX.ping(x0px, yZero, C.amber);
      FX.flash(C.amber, 0.16);
      FX.shake(5.0);
      FX.dust(x0px, yZero + 1, 1.7, true);
    }
    // Pitch-over one-shot ping around t0 + 8s (when pitch steps to ~50 deg)
    if (s4_asc_crossed(tr.get[4], g, s4_asc_prevG)) {
      var qPo = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], tr.get[4]);
      FX.ping(c.X(qPo.x), c.Y(qPo.y), C.lm);
    }
    // Engine cutoff / orbit insertion one-shot ping
    var cutX = c.X(tr.x[tr.x.length - 1]), cutY = c.Y(tr.y[tr.y.length - 1]);
    if (s4_asc_crossed(tCut, g, s4_asc_prevG)) {
      FX.ping(cutX, cutY, C.lm);
      FX.flash(C.lm, 0.10);
    }
    s4_asc_prevG = g;

    // Eagle position & attitude (pitch_deg measured clockwise from vertical +y/up toward downrange +x)
    var px = c.X(s.x);
    var liftOffset = Math.max(0, 1 - s.y / 0.45) * 7;
    var py = c.Y(s.y) - liftOffset;
    var pitchRad = (s.p || 0) * Math.PI / 180;

    // Subtle pitch-angle telemetry arc at Eagle showing vertical vs current pitch attitude
    if (burning && s.p > 2) {
      ctx.save();
      ctx.strokeStyle = C.amber;
      ctx.globalAlpha = 0.38;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(px, py - 20);
      ctx.lineTo(px, py - 12);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(px, py, 16, -Math.PI * 0.5, -Math.PI * 0.5 + pitchRad, false);
      ctx.stroke();
      ctx.restore();
    }

    FX.craft("lm-ascent", px, py, pitchRad, 1.12, {
      upright: true,
      engine: burning,
      throttle: burning ? 1.0 : 0
    });

    // Cutoff glow + ORBIT INSERTION label at end of burn
    if (g >= tCut) {
      FX.glowDot(cutX, cutY, 3.8, C.lm);
      s4_asc_pillLabel("ORBIT INSERTION", cutX - 10, cutY + 22, C.lm, "right");
      s4_asc_pillLabel("EAGLE", px - 12, py - 12, C.lm, "right");
    } else {
      var eagleAlign = px > c.m.l + c.pw - 95 ? "right" : "left";
      var eagleDx = eagleAlign === "right" ? -14 : 14;
      s4_asc_pillLabel("EAGLE", px + eagleDx, py - 12, C.lm, eagleAlign);
    }

    c.done();
    note(tr.note + " Insertion orbit about " + Math.round(tr.perilune_km) + " x " + Math.round(tr.apolune_km) + " km. Vertical scale exaggerated; terrain and descent stage illustrative.");
    readout([
      ["Altitude", s.y.toFixed(2) + " km"],
      ["Speed", Math.round(spdVal) + " m/s"],
      ["Pitch", Math.round(s.p) + "°"],
      ["Engine", burning ? "ascent engine on" : "cut off", burning ? C.amber : C.lm]
    ]);
  };
