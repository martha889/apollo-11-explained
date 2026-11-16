  var s2_loPrevG = null;

  function s2_loSmooth01(t) {
    t = Math.max(0, Math.min(1, t));
    return t * t * (3 - 2 * t);
  }

  function s2_loEnsurePeriodicCache(seg, rMoon) {
    if (seg._s2Ready) return;
    var n = seg.x.length;
    seg._closedX = seg.x.concat([seg.x[0]]);
    seg._closedY = seg.y.concat([seg.y[0]]);
    seg._x2 = seg.x.concat(seg.x).concat([seg.x[0]]);
    seg._y2 = seg.y.concat(seg.y).concat([seg.y[0]]);
    var rMin = Infinity, rMax = -Infinity, kMin = 0, kMax = 0;
    for (var i = 0; i < n; i++) {
      var r = Math.hypot(seg.x[i], seg.y[i]);
      if (r < rMin) { rMin = r; kMin = i; }
      if (r > rMax) { rMax = r; kMax = i; }
    }
    seg._apsides = {
      kMin: kMin,
      kMax: kMax,
      hp: Math.round(rMin - rMoon),
      ha: Math.round(rMax - rMoon),
      pxMin: seg.x[kMin],
      pyMin: seg.y[kMin],
      pxMax: seg.x[kMax],
      pyMax: seg.y[kMax]
    };
    seg._s2Ready = true;
  }

  function segPos(seg, g) {
    if (seg.kind === "arc") {
      var s = sampleTrack(seg.get, [["x", seg.x], ["y", seg.y]], g);
      return [s.x, s.y, s.i, s.f];
    }
    if (seg.kind === "periodic") {
      var n = seg.x.length, k = ((g - seg.epoch) / seg.period) % 1;
      if (k < 0) k += 1;
      var fi = k * n, i = Math.floor(fi) % n, j = (i + 1) % n, f = fi - Math.floor(fi);
      return [seg.x[i] + (seg.x[j] - seg.x[i]) * f, seg.y[i] + (seg.y[j] - seg.y[i]) * f, i, f];
    }
    if (seg.kind === "surface") return [seg.x, seg.y, 0, 0];
    return null;
  }

  function findSeg(list, g) {
    for (var i = 0; i < list.length; i++) {
      var s = list[i], a = s.get ? s.get[0] : s.get_start, b = s.get ? s.get[s.get.length - 1] : s.get_end;
      if (g >= a && g < b) return s;
    }
    return null;
  }

  function s2_loSegTangent(seg, g, M) {
    if (!seg || seg.kind === "surface") return 0;
    var p0 = segPos(seg, g - 12);
    var p1 = segPos(seg, g + 12);
    if (!p0 || !p1) return 0;
    var dx = M.X(p1[0]) - M.X(p0[0]);
    var dy = M.Y(p1[1]) - M.Y(p0[1]);
    if (Math.hypot(dx, dy) < 1e-4) {
      var p2 = segPos(seg, g + 30);
      if (p2) {
        dx = M.X(p2[0]) - M.X(p0[0]);
        dy = M.Y(p2[1]) - M.Y(p0[1]);
      }
    }
    return Math.atan2(dy, dx);
  }

  function s2_loInLos(los, g) {
    if (!los) return false;
    for (var i = 0; i < los.length; i++) {
      if (g >= los[i].get0 && g <= los[i].get1) return true;
    }
    return false;
  }

  function s2_loCrossed(prevG, g, t) {
    var spd = (typeof state !== "undefined" && state.speed) ? state.speed : 1;
    return state.playing && prevG !== null && prevG < t && g >= t && (g - prevG) < 30 * spd;
  }

  function s2_loDrawApsis(M, mx, my, ax, ay, tag, color, avoidX, avoidY) {
    var sx = M.X(ax), sy = M.Y(ay);
    if (Math.hypot(sx - avoidX, sy - avoidY) < 42) return;
    var rx = sx - mx, ry = sy - my;
    var rl = Math.hypot(rx, ry) || 1;
    var ux = rx / rl, uy = ry / rl;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.68;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(sx - ux * 4, sy - uy * 4);
    ctx.lineTo(sx + ux * 6, sy + uy * 6);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(sx, sy, 2.2, 0, Math.PI * 2);
    ctx.fill();
    var lx = sx + ux * 11, ly = sy + uy * 11 + 4;
    var align = ux > 0.22 ? "left" : ux < -0.22 ? "right" : "center";
    if (lx > 18 && lx < W - 18 && ly > 48 && ly < H - 24) {
      label(tag, lx, ly, color, align);
    }
    ctx.restore();
  }

  SCENES["lunar-orbit"] = function (g, dt) {
    var tr = T["lunar-orbit"];
    var cs = findSeg(tr.csm, g) || tr.csm[tr.csm.length - 1];
    var cp = segPos(cs, g);
    var rr = Math.hypot(cp[0], cp[1]);
    var v = smooth({ cx: 0, cy: 0, span: Math.max(4700, rr * 2.5) }, "lunar-orbit", dt);
    var M = mapXf(v);

    drawStars();

    var mx = M.X(0), my = M.Y(0), rMoonPx = tr.r_moon * M.s;
    var ed = tr.earth_dir || [1, 0];
    var angEarth = Math.atan2(-ed[1], ed[0]);
    var angShadow = angEarth + Math.PI;
    var inLos = s2_loInLos(tr.los, g);

    // Far-side radio shadow wedge/cylinder behind the Moon
    ctx.save();
    ctx.translate(mx, my);
    ctx.rotate(angShadow);
    var shLen = Math.max(W, H) * 1.2;
    var shGrad = ctx.createLinearGradient(0, 0, shLen * 0.75, 0);
    shGrad.addColorStop(0, inLos ? "rgba(7, 10, 16, 0.56)" : "rgba(7, 10, 16, 0.38)");
    shGrad.addColorStop(0.55, inLos ? "rgba(18, 25, 38, 0.28)" : "rgba(18, 25, 38, 0.16)");
    shGrad.addColorStop(1, "rgba(18, 25, 38, 0)");
    ctx.fillStyle = shGrad;
    ctx.fillRect(0, -rMoonPx, shLen, rMoonPx * 2);

    ctx.strokeStyle = inLos ? C.amber : C.muted;
    ctx.globalAlpha = inLos ? 0.34 : 0.18;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(0, -rMoonPx);
    ctx.lineTo(shLen * 0.7, -rMoonPx);
    ctx.moveTo(0, rMoonPx);
    ctx.lineTo(shLen * 0.7, rMoonPx);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    var px = M.X(cp[0]), py = M.Y(cp[1]);

    // Label inside the radio shadow zone (offset below the horizontal axis to avoid perilune/craft labels)
    var shLblDist = rMoonPx + Math.min(76, Math.max(44, rMoonPx * 0.32));
    var shNormX = -Math.sin(angShadow), shNormY = Math.cos(angShadow);
    var shOff = (py > my) ? -34 : 34;
    var shLx = mx + Math.cos(angShadow) * shLblDist + shNormX * shOff;
    var shLy = my + Math.sin(angShadow) * shLblDist + shNormY * shOff;
    if (shLx > 60 && shLx < W - 60 && shLy > 55 && shLy < H - 30) {
      ctx.save();
      ctx.globalAlpha = inLos ? 0.85 : 0.45;
      label("RADIO SHADOW (LOS)", shLx, shLy, inLos ? C.amber : C.muted, "center");
      ctx.restore();
    }

    // Small "TO EARTH" arrow near the edge along earth_dir (placed clear of Moon limb and apolune label)
    var uxE = Math.cos(angEarth), uyE = Math.sin(angEarth);
    var nxE = -uyE, nyE = uxE;
    var eEdgeDist = Math.max(rMoonPx + 42, Math.min(W, H) * 0.44);
    var ex = Math.max(36, Math.min(W - 48, mx + uxE * eEdgeDist));
    var ey = Math.max(76, Math.min(H - 52, my + uyE * eEdgeDist - 68));
    ctx.save();
    ctx.strokeStyle = C.earth;
    ctx.fillStyle = C.earth;
    ctx.globalAlpha = 0.86;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(ex - uxE * 22, ey - uyE * 22);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(ex + uxE * 3, ey + uyE * 3);
    ctx.lineTo(ex - uxE * 6 - nxE * 4, ey - uyE * 6 - nyE * 4);
    ctx.lineTo(ex - uxE * 6 + nxE * 4, ey - uyE * 6 + nyE * 4);
    ctx.closePath();
    ctx.fill();
    label("TO EARTH", ex, ey - 10, C.earth, "left");
    ctx.restore();

    // Moon body
    body(mx, my, rMoonPx, C.moon, "");
    label("MOON", mx, my + 4, C.bg, "center");

    // CSM orbit traces + FX.trail comet tail + apsides
    if (cs.kind === "periodic") {
      s2_loEnsurePeriodicCache(cs, tr.r_moon);
      polyline(cs._closedX, cs._closedY, M.X, M.Y, 0, cs.x.length, C.csm, 1.1, [4, 5], 0.28);
      var nCsm = cs.x.length;
      var iHeadCsm = cp[2] + nCsm;
      FX.trail(cs._x2, cs._y2, M.X, M.Y, iHeadCsm - 48, iHeadCsm, cp[3], C.csm, { width: 2.3, tail: 46, baseAlpha: 0 });
      var ap = cs._apsides;
      s2_loDrawApsis(M, mx, my, ap.pxMin, ap.pyMin, "PERILUNE " + ap.hp + " KM", C.csm, px, py);
      s2_loDrawApsis(M, mx, my, ap.pxMax, ap.pyMax, "APOLUNE " + ap.ha + " KM", C.csm, px, py);
    }
    if (cs.kind === "arc") {
      tr.csm.forEach(function (s2) {
        if (s2.kind === "arc" && s2 !== cs && s2.get[0] <= cs.get[0] && (cs.get[0] - s2.get[s2.get.length - 1]) < 1200) {
          polyline(s2.x, s2.y, M.X, M.Y, 0, s2.x.length - 1, C.csm, 1.4, null, 0.32);
        }
      });
      if (cs.burn === "tei" || cs.burn === "loi-1") {
        polyline(cs.x, cs.y, M.X, M.Y, cp[2], cs.x.length - 1, C.csm, 1.15, [4, 6], 0.36);
      }
      FX.trail(cs.x, cs.y, M.X, M.Y, 0, cp[2], cp[3], C.csm, { width: 2.4, tail: 36, baseAlpha: 0.30 });
    }

    // LM orbit traces + comet trail + apsis
    var ls = findSeg(tr.lm, g), lp = null;
    if (ls) {
      if (ls.kind === "follow") lp = cp.slice();
      else lp = segPos(ls, g);
      if (ls.kind === "periodic") {
        s2_loEnsurePeriodicCache(ls, tr.r_moon);
        polyline(ls._closedX, ls._closedY, M.X, M.Y, 0, ls.x.length, C.lm, 1.1, [4, 5], 0.32);
        var nLm = ls.x.length;
        var iHeadLm = lp[2] + nLm;
        FX.trail(ls._x2, ls._y2, M.X, M.Y, iHeadLm - 46, iHeadLm, lp[3], C.lm, { width: 2.2, tail: 44, baseAlpha: 0 });
        var lap = ls._apsides;
        s2_loDrawApsis(M, mx, my, lap.pxMin, lap.pyMin, "LM PERILUNE " + lap.hp + " KM", C.lm, M.X(lp[0]), M.Y(lp[1]));
      }
    }

    var docked = (g < EV.undocking.get) || (g >= EV.docking.get && g < EV["lm-jettison"].get);

    // Tranquility Base landing site with FX.glowDot & surface pulse
    var site = tr.site;
    var sx = M.X(site.x), sy = M.Y(site.y);
    var onSurface = ls && ls.kind === "surface";
    if (onSurface) {
      var pulseK = (performance.now() * 0.0012) % 1;
      var pulseR = reduceMotion ? 11 : (7 + pulseK * 14);
      var pulseA = reduceMotion ? 0.45 : (1 - pulseK) * 0.65;
      ctx.save();
      ctx.strokeStyle = C.amber;
      ctx.globalAlpha = pulseA;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(sx, sy, pulseR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      FX.glowDot(sx, sy, 4.5, C.amber);
      var surfAng = Math.atan2(sy - my, sx - mx);
      var lmSurfKind = (EV.liftoff && g >= EV.liftoff.get) ? "lm-ascent" : "lm";
      FX.craft(lmSurfKind, sx + Math.cos(surfAng) * 7, sy + Math.sin(surfAng) * 7, surfAng, 0.78);
    } else {
      FX.glowDot(sx, sy, 3.4, C.amber);
    }
    label("TRANQUILITY BASE", sx + (site.x < 0 ? -10 : 10), sy + (site.y < 0 ? 15 : -9), C.amber, site.x < 0 ? "right" : "left");

    // Active burn & one-shot ignition/cutoff/event triggers
    var b = burnActive(tr.burns, g);
    if (tr.burns) {
      for (var bi = 0; bi < tr.burns.length; bi++) {
        var bn = tr.burns[bi];
        if (s2_loCrossed(s2_loPrevG, g, bn.get0)) {
          FX.ping(px, py, C.amber);
          FX.flash(C.amber, 0.13);
          FX.shake(2.6);
        }
        if (s2_loCrossed(s2_loPrevG, g, bn.get1)) {
          FX.ping(px, py, C.csm);
        }
      }
    }
    if (EV.undocking && s2_loCrossed(s2_loPrevG, g, EV.undocking.get)) {
      FX.ping(px, py, C.lm);
    }
    if (EV["lm-jettison"] && s2_loCrossed(s2_loPrevG, g, EV["lm-jettison"].get)) {
      FX.ping(px, py, C.lm);
    }
    s2_loPrevG = g;

    var angCsm = s2_loSegTangent(cs, g, M);
    var csmBurning = b && b.id !== "doi";
    // Retrograde burns (LOI-1, LOI-2): engine nozzle points forward along travel -> nose points angCsm + Math.PI, flame shoots ahead along angCsm.
    // Prograde burn (TEI): nose points along travel -> flame shoots behind along angCsm + Math.PI.
    var csmCraftAng = (csmBurning && b.id !== "tei") ? (angCsm + Math.PI) : angCsm;

    if (csmBurning) {
      FX.exhaust(px, py, csmCraftAng, 1.25, { color: C.amber, scale: 1.38, offset: 12 });
      FX.glowDot(px + Math.cos(csmCraftAng + Math.PI) * 10, py + Math.sin(csmCraftAng + Math.PI) * 10, 3.8, C.amber);
    }

    var isLmAscent = EV.liftoff && g >= EV.liftoff.get;
    var lmGlyphKind = isLmAscent ? "lm-ascent" : "lm";

    if (lp && !docked) {
      var lx = M.X(lp[0]), ly = M.Y(lp[1]);
      var angLm = ls.kind === "follow" ? angCsm : s2_loSegTangent(ls, g, M);

      if (ls.kind === "follow") {
        var dtUndock = Math.max(0, g - EV.undocking.get);
        var sepDist = 24 * s2_loSmooth01(dtUndock / 900);
        var radAng = Math.atan2(py - my, px - mx);
        lx = px - Math.cos(angCsm) * (sepDist * 0.75) + Math.cos(radAng) * (sepDist * 0.55);
        ly = py - Math.sin(angCsm) * (sepDist * 0.75) + Math.sin(radAng) * (sepDist * 0.55);
      }

      var doiBurning = b && b.id === "doi";
      var lmCraftAng = doiBurning ? (angLm + Math.PI) : angLm;
      if (doiBurning) {
        FX.exhaust(lx, ly, lmCraftAng, 1.2, { color: C.amber, scale: 1.28, offset: 10 });
        FX.glowDot(lx + Math.cos(lmCraftAng + Math.PI) * 9, ly + Math.sin(lmCraftAng + Math.PI) * 9, 3.6, C.amber);
      }

      if (ls.kind !== "surface") {
        marker(lx, ly, doiBurning ? C.amber : C.lm, "Eagle", { dy: 20, dx: lx < px ? -12 : 12, align: lx < px ? "right" : "left" });
        FX.craft(lmGlyphKind, lx, ly, lmCraftAng, 1.0, { engine: false });
        if (doiBurning) {
          label("DOI RETROGRADE BURN", lx + (lx < px ? -12 : 12), ly + 34, C.amber, lx < px ? "right" : "left");
        } else if (Math.abs(g - EV.undocking.get) < 300) {
          label("\"THE EAGLE HAS WINGS\"", lx + (lx < px ? -12 : 12), ly + 34, C.lm, lx < px ? "right" : "left");
        }
      }

      ctx.save();
      if (inLos) ctx.globalAlpha = 0.52;
      marker(px, py, csmBurning ? C.amber : C.csm, "Columbia", { dy: -12, dx: 12 });
      ctx.restore();
      FX.craft("csm", px, py, csmCraftAng, 1.04, { engine: false });
    } else {
      var csmName = docked && lmLabelOK(g) ? "Columbia + Eagle" : "Columbia";
      ctx.save();
      if (inLos) ctx.globalAlpha = 0.52;
      marker(px, py, csmBurning ? C.amber : C.csm, csmName, { dy: -12, dx: 14 });
      ctx.restore();
      var mainKind = (docked && lmLabelOK(g)) ? "csm-lm" : "csm";
      FX.craft(mainKind, px, py, csmCraftAng, 1.08, { engine: false });
    }

    if (csmBurning) {
      var bTag = b.id === "tei" ? "TEI PROGRADE BURN" : (b.id.toUpperCase() + " RETROGRADE BURN");
      label(bTag, px + 14, py - 26, C.amber, "left");
    }

    // LM Jettison: ascent stage drifts outward/behind in dark space and fades after EV["lm-jettison"].get
    if (EV["lm-jettison"] && g >= EV["lm-jettison"].get && g < EV["lm-jettison"].get + 3600) {
      var dtJett = g - EV["lm-jettison"].get;
      var jettAlpha = Math.max(0.14, 1 - dtJett / 3600);
      var jettSep = (20 + Math.min(54, dtJett * 0.032)) * s2_loSmooth01(dtJett / 60);
      var rAngJ = Math.atan2(py - my, px - mx);
      var jx = px - Math.cos(angCsm) * (jettSep * 0.85) + Math.cos(rAngJ) * (jettSep * 0.55);
      var jy = py - Math.sin(angCsm) * (jettSep * 0.85) + Math.sin(rAngJ) * (jettSep * 0.55);
      ctx.save();
      ctx.globalAlpha = jettAlpha * 0.55;
      ctx.strokeStyle = C.lm;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(px, py);
      ctx.lineTo(jx, jy);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = jettAlpha;
      FX.craft("lm-ascent", jx, jy, angCsm - 0.35 - dtJett * 0.001, 0.92);
      label("EAGLE ASCENT STAGE (JETTISONED)", jx - 10, jy - 10, C.lm, "right");
      ctx.restore();
    }

    note(tr.note);
    scaleBar(1 / M.s);

    var alt = rr - tr.r_moon;
    var rows = [["Columbia alt.", Math.round(alt).toLocaleString("en-US") + " km"]];
    if (lp && !docked && ls.kind !== "follow") {
      rows.push(["Eagle alt.", ls.kind === "surface" ? "on the surface" : Math.round(Math.hypot(lp[0], lp[1]) - tr.r_moon) + " km", C.lm]);
    }
    if (b) {
      rows.push(["Burn", b.id.toUpperCase(), C.amber]);
      if (b.id === "loi-1" && tr.telemetry && tr.telemetry.length > 1) {
        var dvSer = tr.telemetry[1];
        if (dvSer && dvSer.get && dvSer.v) {
          var dvNow = sampleTrack(dvSer.get, [["v", dvSer.v]], g).v;
          rows.push(["LOI-1 ΔV", Math.round(dvNow) + " m/s", C.amber]);
        }
      }
    }
    readout(rows);

    // Show 'LOSS OF SIGNAL (approx.)' tag in the readout area below the compact numeric rows
    if (inLos) {
      var losY = 22 + rows.length * 18;
      text("SIGNAL", W - 196, losY, { size: 11, weight: 600, font: "Barlow Condensed, Arial Narrow, sans-serif", color: C.muted, align: "right" });
      text("LOSS OF SIGNAL (approx.)", W - 14, losY, { size: 12, weight: 500, font: "IBM Plex Mono, monospace", color: C.amber, align: "right" });
    }
  };

  function lmLabelOK(g) { return g < EV["lm-jettison"].get; }
