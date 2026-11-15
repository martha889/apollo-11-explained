  var s2_cisPrevG = null;

  function s2_cisSmooth01(t) {
    t = Math.max(0, Math.min(1, t));
    return t * t * (3 - 2 * t);
  }

  function s2_cisLerpAng(a0, a1, f) {
    var d = a1 - a0;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    return a0 + d * Math.max(0, Math.min(1, f));
  }

  function s2_cisTangent(xs, ys, X, Y, i, f) {
    var n = xs.length;
    if (n < 2) return 0;
    var i0 = Math.max(0, Math.min(n - 2, i | 0));
    var a0 = Math.atan2(Y(ys[i0 + 1]) - Y(ys[i0]), X(xs[i0 + 1]) - X(xs[i0]));
    if (i0 + 2 < n && f > 0) {
      var a1 = Math.atan2(Y(ys[i0 + 2]) - Y(ys[i0 + 1]), X(xs[i0 + 2]) - X(xs[i0 + 1]));
      return s2_cisLerpAng(a0, a1, f);
    }
    return a0;
  }

  function s2_cisBuildTicks(leg) {
    var ticks = [];
    for (var dTarget = 50000; dTarget <= 350000; dTarget += 50000) {
      for (var i = 0; i < leg.x.length - 1; i++) {
        var d0 = Math.hypot(leg.x[i], leg.y[i]);
        var d1 = Math.hypot(leg.x[i + 1], leg.y[i + 1]);
        if ((d0 <= dTarget && d1 >= dTarget) || (d0 >= dTarget && d1 <= dTarget)) {
          var f = Math.abs(d1 - d0) < 1e-6 ? 0 : (dTarget - d0) / (d1 - d0);
          var tx = leg.x[i] + (leg.x[i + 1] - leg.x[i]) * f;
          var ty = leg.y[i] + (leg.y[i + 1] - leg.y[i]) * f;
          var dx = leg.x[i + 1] - leg.x[i];
          var dy = leg.y[i + 1] - leg.y[i];
          var dl = Math.hypot(dx, dy) || 1;
          ticks.push({ km: dTarget, x: tx, y: ty, tx: dx / dl, ty: dy / dl });
          break;
        }
      }
    }
    return ticks;
  }

  function s2_cisMeta(tr) {
    if (tr._s2Meta) return tr._s2Meta;
    var out = tr.legs[0], ret = tr.legs[1];
    var soiPt = sampleTrack(out.get, [["x", out.x], ["y", out.y]], tr.soi_get);
    var mcc2Pt = EV["mcc-2"] ? sampleTrack(out.get, [["x", out.x], ["y", out.y]], EV["mcc-2"].get) : null;
    var mcc5Pt = EV["mcc-5"] ? sampleTrack(ret.get, [["x", ret.x], ["y", ret.y]], EV["mcc-5"].get) : null;
    tr._s2Meta = {
      outTicks: s2_cisBuildTicks(out),
      retTicks: s2_cisBuildTicks(ret),
      soiPt: soiPt,
      mcc2Pt: mcc2Pt,
      mcc5Pt: mcc5Pt
    };
    return tr._s2Meta;
  }

  function s2_cisCrossed(prevG, g, t) {
    var spd = (typeof state !== "undefined" && state.speed) ? state.speed : 1;
    return state.playing && prevG !== null && prevG < t && g >= t && (g - prevG) < 3600 * spd;
  }

  SCENES.cislunar = function (g, dt) {
    var tr = T.cislunar;
    var meta = s2_cisMeta(tr);
    var out = tr.legs[0], ret = tr.legs[1];
    var leg = g < ret.get[0] ? out : ret;
    var s = sampleTrack(leg.get, [["x", leg.x], ["y", leg.y], ["v", leg.v]], g);
    var dm = Math.hypot(s.x - tr.moon[0], s.y), de = Math.hypot(s.x, s.y);

    // Smoothly blended camera target across wide, near-Earth, and near-Moon modes
    var wideSpan = W < H ? 430000 : 470000 * Math.max(1, (H / W) * 0.95);
    var wEarth = 1 - s2_cisSmooth01((de - 45000) / 38000);
    var wMoon = (1 - wEarth) * (1 - s2_cisSmooth01((dm - 52000) / 42000));
    var wWide = Math.max(0, 1 - wEarth - wMoon);
    var tgt = {
      cx: wWide * 192000 + wEarth * 0 + wMoon * (tr.moon[0] - 8000),
      cy: 0,
      span: wWide * wideSpan + wEarth * 140000 + wMoon * 150000
    };
    var v = smooth(tgt, "cislunar", dt);
    var M = mapXf(v);

    drawStars();

    // Moon's sphere of influence (faint dashed circle + subtle grav well tint)
    var mx = M.X(tr.moon[0]), my = M.Y(0);
    var soiR = tr.soi_radius_km * M.s;
    if (soiR > 8) {
      ctx.save();
      var sg = ctx.createRadialGradient(mx, my, Math.max(2, tr.r_moon * M.s), mx, my, soiR);
      sg.addColorStop(0, "rgba(108, 195, 255, 0.05)");
      sg.addColorStop(0.75, "rgba(108, 195, 255, 0.02)");
      sg.addColorStop(1, "rgba(108, 195, 255, 0)");
      ctx.fillStyle = sg;
      ctx.beginPath();
      ctx.arc(mx, my, soiR, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = dm <= tr.soi_radius_km ? C.amber : C.csm;
      ctx.globalAlpha = dm <= tr.soi_radius_km ? 0.42 : 0.26;
      ctx.lineWidth = 1.2;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.arc(mx, my, soiR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();

      if (soiR > 26 && mx - soiR > 16 && my - soiR > 36) {
        label("LUNAR SOI (64,374 KM)", mx, my - soiR - 6, C.muted, "center");
      }
    }

    // Draw Earth & Moon with body()
    body(M.X(0), M.Y(0), tr.r_earth * M.s, C.earth, "Earth");
    body(mx, my, tr.r_moon * M.s, C.moon, "Moon");

    // Trajectory figure-8 + FX.trail comet tail
    if (leg === out) {
      polyline(ret.x, ret.y, M.X, M.Y, 0, ret.x.length - 1, C.csm, 1, [3, 7], 0.16);
      polyline(out.x, out.y, M.X, M.Y, s.i, out.x.length - 1, C.csm, 1.15, [4, 6], 0.38);
      FX.trail(out.x, out.y, M.X, M.Y, 0, s.i, s.f, C.csm, { width: 2.4, tail: 46, baseAlpha: 0.28 });
    } else {
      polyline(out.x, out.y, M.X, M.Y, 0, out.x.length - 1, C.csm, 1.1, null, 0.22);
      polyline(ret.x, ret.y, M.X, M.Y, s.i, ret.x.length - 1, C.csm, 1.15, [4, 6], 0.38);
      FX.trail(ret.x, ret.y, M.X, M.Y, 0, s.i, s.f, C.csm, { width: 2.4, tail: 46, baseAlpha: 0.28 });
    }

    var px = M.X(s.x), py = M.Y(s.y);
    var ang = s2_cisTangent(leg.x, leg.y, M.X, M.Y, s.i, s.f);
    var soiX = M.X(meta.soiPt.x), soiY = M.Y(meta.soiPt.y);

    // Distance tick marks every 50,000 km along the active path
    var ticks = leg === out ? meta.outTicks : meta.retTicks;
    var stepPx50k = 50000 * M.s;
    if (stepPx50k > 22) {
      ctx.save();
      for (var ti = 0; ti < ticks.length; ti++) {
        var tk = ticks[ti];
        if (!(stepPx50k > 44 || (tk.km % 100000 === 0))) continue;
        var kx = M.X(tk.x), ky = M.Y(tk.y);
        if (kx < 24 || kx > W - 24 || ky < 44 || ky > H - 28) continue;
        var nx = tk.ty, ny = tk.tx;
        var distCraft = Math.hypot(kx - px, ky - py);
        var distSoi = leg === out ? Math.hypot(kx - soiX, ky - soiY) : 999;
        if (distCraft < 36) continue;
        ctx.strokeStyle = C.muted;
        ctx.globalAlpha = 0.55;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(kx - nx * 4.5, ky - ny * 4.5);
        ctx.lineTo(kx + nx * 4.5, ky + ny * 4.5);
        ctx.stroke();
        // Avoid colliding tick text with spacecraft label or SOI crossing dot
        if (distCraft > 82 && distSoi > 28) {
          var sign = leg === out ? -1 : 1;
          ctx.globalAlpha = 0.72;
          text((tk.km / 1000) + "k km", kx + nx * 12 * sign, ky + ny * 12 * sign + 3, {
            size: 10,
            font: "IBM Plex Mono, monospace",
            color: C.muted,
            align: "center"
          });
        }
      }
      ctx.restore();
    }

    // SOI crossing marker & "Moon's gravity takes over" callout
    if (leg === out && soiX > 20 && soiX < W - 20 && soiY > 30 && soiY < H - 20) {
      var passedSoi = g >= tr.soi_get;
      var nearSoi = Math.abs(g - tr.soi_get) < 14000;
      FX.glowDot(soiX, soiY, nearSoi ? 3.8 : 2.6, passedSoi ? C.amber : C.csm);
      if (passedSoi || nearSoi) {
        var sdy = soiY < H * 0.5 ? -10 : 16;
        label("Moon's gravity takes over", soiX - 8, soiY + sdy, passedSoi ? C.amber : C.csm, "right");
      }
    }

    // Midcourse correction burns & Transposition/Docking beat
    var isMcc2 = EV["mcc-2"] && Math.abs(g - EV["mcc-2"].get) < 180;
    var isMcc5 = EV["mcc-5"] && Math.abs(g - EV["mcc-5"].get) < 180;
    var isTd = EV["docking-lm"] && Math.abs(g - EV["docking-lm"].get) < 420;
    var burning = isMcc2 || isMcc5;

    // One-shot pings when crossing cislunar events during playback
    if (s2_cisCrossed(s2_cisPrevG, g, tr.soi_get)) {
      FX.ping(soiX, soiY, C.amber);
      FX.flash(C.amber, 0.10);
    }
    if (EV["mcc-2"] && s2_cisCrossed(s2_cisPrevG, g, EV["mcc-2"].get)) {
      FX.ping(px, py, C.amber);
      FX.flash(C.amber, 0.12);
    }
    if (EV["mcc-5"] && s2_cisCrossed(s2_cisPrevG, g, EV["mcc-5"].get)) {
      FX.ping(px, py, C.amber);
      FX.flash(C.amber, 0.12);
    }
    if (EV["docking-lm"] && s2_cisCrossed(s2_cisPrevG, g, EV["docking-lm"].get)) {
      FX.ping(px, py, C.lm);
      FX.flash(C.csm, 0.10);
    }
    s2_cisPrevG = g;

    // Static reference markers for MCC-2 / MCC-5 along the active leg
    if (leg === out && meta.mcc2Pt && !isMcc2) {
      var m2x = M.X(meta.mcc2Pt.x), m2y = M.Y(meta.mcc2Pt.y);
      if (Math.hypot(m2x - px, m2y - py) > 42 && m2x > 20 && m2x < W - 20) {
        FX.glowDot(m2x, m2y, 2.2, C.amber);
        label("MCC-2", m2x, m2y - 7, C.muted, "center");
      }
    }
    if (leg === ret && meta.mcc5Pt && !isMcc5) {
      var m5x = M.X(meta.mcc5Pt.x), m5y = M.Y(meta.mcc5Pt.y);
      if (Math.hypot(m5x - px, m5y - py) > 42 && m5x > 20 && m5x < W - 20) {
        FX.glowDot(m5x, m5y, 2.2, C.amber);
        label("MCC-5", m5x, m5y + 15, C.muted, "center");
      }
    }

    if (burning) {
      FX.exhaust(px, py, ang, 1.15, { color: C.amber, scale: 1.25, offset: 10 });
      FX.glowDot(px, py, 4.2, C.amber);
    }

    var craftName = leg === out ? "Columbia + Eagle" : "Columbia";
    var ldx = px > W * 0.72 ? -16 : 16;
    var ldy = (leg === ret || py < 90) ? 22 : -14;
    var lAlign = px > W * 0.72 ? "right" : "left";
    marker(px, py, burning ? C.amber : C.csm, craftName, { dx: ldx, dy: ldy, align: lAlign });

    // Spacecraft glyph (minimum pixel size 25 px so always crisp even in wide cislunar view)
    var craftKind = leg === out ? (g < EV["docking-lm"].get ? "csm-sivb" : "csm-lm") : "csm";
    if (isTd && leg === out) {
      var ux = Math.cos(ang), uy = Math.sin(ang);
      FX.craft("csm-sivb", px - ux * 18, py - uy * 18, ang, 20);
      FX.craft("csm-lm", px + ux * 10, py + uy * 10, ang, 24);
      label("TRANSPOSITION & DOCKING (ILLUSTRATIVE)", px + ldx, py + ldy + (ldy < 0 ? -16 : 16), C.lm, lAlign);
    } else {
      FX.craft(craftKind, px, py, ang, 26, { engine: burning, throttle: burning ? 1.15 : 0 });
      if (isMcc2) label("MCC-2 SPS BURN (3 s · 6.4 m/s)", px + ldx, py + ldy + (ldy < 0 ? -16 : 16), C.amber, lAlign);
      else if (isMcc5) label("MCC-5 SPS BURN (10 s)", px + ldx, py + ldy + (ldy < 0 ? -16 : 16), C.amber, lAlign);
    }

    note(tr.note + (isTd ? " T&D separation is illustrative." : ""));
    scaleBar(1 / M.s);

    var spdKmS = (s.v || 0) / 1000;
    var rows = [
      ["From Earth", Math.round(de).toLocaleString("en-US") + " km"],
      ["From Moon", Math.round(dm).toLocaleString("en-US") + " km"],
      ["Speed", spdKmS.toFixed(2) + " km/s", burning ? C.amber : C.fg]
    ];
    if (leg === out && g >= tr.soi_get) {
      rows.push(["Gravity", "Lunar SOI", C.amber]);
    }
    readout(rows);
  };
