  var s2_eoPrevG = null;

  function s2_eoSmooth01(t) {
    t = Math.max(0, Math.min(1, t));
    return t * t * (3 - 2 * t);
  }

  function s2_eoLerpAng(a0, a1, f) {
    var d = a1 - a0;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    return a0 + d * Math.max(0, Math.min(1, f));
  }

  function s2_eoTangent(xs, ys, X, Y, i, f) {
    var n = xs.length;
    if (n < 2) return 0;
    var i0 = Math.max(0, Math.min(n - 2, i | 0));
    var a0 = Math.atan2(Y(ys[i0 + 1]) - Y(ys[i0]), X(xs[i0 + 1]) - X(xs[i0]));
    if (i0 + 2 < n && f > 0) {
      var a1 = Math.atan2(Y(ys[i0 + 2]) - Y(ys[i0 + 1]), X(xs[i0 + 2]) - X(xs[i0 + 1]));
      return s2_eoLerpAng(a0, a1, f);
    }
    return a0;
  }

  function s2_eoMeta(tr) {
    if (tr._s2Meta) return tr._s2Meta;
    var tli0 = EV.tli ? EV.tli.get : 9856;
    var tli1 = (tr.burns && tr.burns[0]) ? tr.burns[0].get1 : 10203;
    var iStart = 0, iEnd = 0, iRev1 = 0;
    var g0 = tr.get[0];
    for (var i = 0; i < tr.get.length; i++) {
      if (tr.get[i] <= g0 + 5310) iRev1 = i;
      if (tr.get[i] <= tli0) iStart = i;
      if (tr.get[i] <= tli1) iEnd = i;
    }
    tr._s2Meta = { iStart: iStart, iEnd: iEnd, iRev1: Math.max(12, iRev1), tli0: tli0, tli1: tli1 };
    return tr._s2Meta;
  }

  function s2_eoSpeedKmS(tr, r, g, b) {
    var cisLeg0 = T.cislunar && T.cislunar.legs && T.cislunar.legs[0];
    var vCut = (cisLeg0 && cisLeg0.v && cisLeg0.v.length) ? cisLeg0.v[0] / 1000 : 10.84;
    var vPark = Math.sqrt(398600.4418 / Math.max(6378, r));
    var tli0 = (tr.burns && tr.burns[0]) ? tr.burns[0].get0 : EV.tli.get;
    var tli1 = (tr.burns && tr.burns[0]) ? tr.burns[0].get1 : 10203;
    if (g <= tli0) return vPark;
    if (g < tli1) {
      var u = (g - tli0) / Math.max(1, tli1 - tli0);
      return vPark + (vCut - vPark) * (0.35 * u + 0.65 * u * u);
    }
    if (cisLeg0 && cisLeg0.v && cisLeg0.v.length) {
      return sampleTrack(cisLeg0.get, [["v", cisLeg0.v]], g).v / 1000;
    }
    return Math.sqrt(Math.max(50, vCut * vCut - 2 * 398600.4418 * (1 / 6563.2 - 1 / Math.max(6563.2, r))));
  }

  function s2_eoCrossed(prevG, g, t) {
    var spd = (typeof state !== "undefined" && state.speed) ? state.speed : 1;
    return state.playing && prevG !== null && prevG < t && g >= t && (g - prevG) < 30 * spd;
  }

  SCENES["earth-orbit"] = function (g, dt) {
    var tr = T["earth-orbit"];
    var meta = s2_eoMeta(tr);
    var s = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], g);
    var r = Math.hypot(s.x, s.y);

    // Smooth camera pullback as spacecraft climbs away from parking orbit
    var departFrac = s2_eoSmooth01((r - 6600) / 9000);
    var v = smooth({
      cx: s.x * 0.14 * departFrac,
      cy: s.y * 0.14 * departFrac,
      span: Math.max(17000, r * 2.6)
    }, "earth-orbit", dt);
    var M = mapXf(v);

    drawStars();
    body(M.X(0), M.Y(0), 6378 * M.s, C.earth, "Earth");

    // Faint reference parking orbit circle
    polyline(tr.x, tr.y, M.X, M.Y, 0, meta.iRev1, C.csm, 1, [3, 5], 0.18);

    // Future translunar path drawn dashed ahead of the craft
    var showFuture = g >= meta.tli0 - 900;
    if (showFuture && s.i < tr.x.length - 1) {
      polyline(tr.x, tr.y, M.X, M.Y, s.i, tr.x.length - 1, C.csm, 1.3, [5, 6], g >= meta.tli0 ? 0.48 : 0.25);
      var iTip = tr.x.length - 1;
      var tipX = M.X(tr.x[iTip]), tipY = M.Y(tr.y[iTip]);
      if (tipX > 40 && tipX < W - 40 && tipY > 65 && tipY < H - 35) {
        label("TO MOON (TLI PATH)", tipX - 8, tipY - 8, C.csm, "right");
      }
    }

    // Comet trail for travelled trajectory (with faint full history baseline)
    FX.trail(tr.x, tr.y, M.X, M.Y, 0, s.i, s.f, C.csm, { width: 2.4, tail: 38, baseAlpha: 0.24 });

    // Highlight the TLI burn arc on the parking circle once TLI starts
    if (g >= meta.tli0 && meta.iEnd > meta.iStart) {
      var iBurnHead = Math.min(s.i, meta.iEnd);
      if (iBurnHead > meta.iStart) {
        polyline(tr.x, tr.y, M.X, M.Y, meta.iStart, iBurnHead, C.amber, 2.8, null, 0.72);
      }
      var tigX = M.X(tr.x[meta.iStart]), tigY = M.Y(tr.y[meta.iStart]);
      FX.glowDot(tigX, tigY, 2.8, C.amber);
      if (Math.hypot(M.X(s.x) - tigX, M.Y(s.y) - tigY) > 38) {
        label("TLI IGNITION", tigX + (tr.x[meta.iStart] >= 0 ? 8 : -8), tigY + 4, C.amber, tr.x[meta.iStart] >= 0 ? "left" : "right");
      }
    }

    var b = burnActive(tr.burns, g);
    var px = M.X(s.x), py = M.Y(s.y);
    var ang = s2_eoTangent(tr.x, tr.y, M.X, M.Y, s.i, s.f);

    // One-shot event triggers when playhead crosses key moments
    if (s2_eoCrossed(s2_eoPrevG, g, meta.tli0)) {
      FX.ping(px, py, C.amber);
      FX.flash(C.amber, 0.14);
      FX.shake(3.2);
    }
    if (s2_eoCrossed(s2_eoPrevG, g, meta.tli1)) {
      FX.ping(px, py, C.csm);
      FX.flash(C.csm, 0.08);
    }
    if (EV["docking-lm"] && s2_eoCrossed(s2_eoPrevG, g, EV["docking-lm"].get)) {
      FX.ping(px, py, C.lm);
    }
    s2_eoPrevG = g;

    // Brief illustrative transposition-and-docking beat near end of scene / docking-lm
    var tdStart = 11250;
    var inTdBeat = g >= tdStart && g < (EV["docking-lm"] ? EV["docking-lm"].get + 600 : 12600);
    var docked = g >= EV["docking-lm"].get;

    if (b) {
      var burnProg = Math.max(0.15, Math.min(1, (g - b.get0) / Math.max(1, b.get1 - b.get0)));
      var pwr = 1.05 + 0.35 * burnProg;
      FX.exhaust(px, py, ang, pwr, { color: C.amber, scale: 1.45, offset: 13 });
      FX.glowDot(px - Math.cos(ang) * 11, py - Math.sin(ang) * 11, 4.0, C.amber);
    }

    var craftTitle = g < EV["docking-lm"].get ? "Columbia + S-IVB" : "Columbia + Eagle";
    var rdx = s.x >= 0 ? 14 : -14;
    var rdy = s.y >= 0 ? -12 : 18;
    var rAlign = s.x >= 0 ? "left" : "right";
    marker(px, py, b ? C.amber : C.csm, craftTitle, { dx: rdx, dy: rdy, align: rAlign });

    if (inTdBeat && !docked) {
      // Small illustrative separation & turnaround beat before docking
      var uTd = s2_eoSmooth01((g - tdStart) / Math.max(1, EV["docking-lm"].get - tdStart));
      var sepPx = 11 + 8 * Math.sin(uTd * Math.PI * 0.85);
      var ux = Math.cos(ang), uy = Math.sin(ang);
      var s4x = px - ux * sepPx * 0.55, s4y = py - uy * sepPx * 0.55;
      var csmX = px + ux * sepPx * 0.55, csmY = py + uy * sepPx * 0.55;
      FX.craft("csm-sivb", s4x, s4y, ang, 0.82);
      FX.craft("csm", csmX, csmY, ang + Math.PI * s2_eoSmooth01(uTd * 1.15), 0.88);
      label("T&D TURNAROUND (ILLUSTRATIVE)", px + rdx, py + rdy + (rdy < 0 ? -14 : 14), C.lm, rAlign);
    } else {
      var kind = docked ? "csm-lm" : "csm-sivb";
      FX.craft(kind, px, py, ang, 1.08, { engine: !!b, throttle: b ? 1.2 : 0 });
      if (b) {
        label("S-IVB TLI BURN", px + rdx, py + rdy + (rdy < 0 ? -14 : 14), C.amber, rAlign);
      }
    }

    note(tr.note + " Craft attitude and separation are illustrative.");
    scaleBar(1 / M.s);

    var spdKmS = s2_eoSpeedKmS(tr, r, g, b);
    var rows = [
      ["Altitude", Math.round(r - 6378).toLocaleString("en-US") + " km"],
      ["Speed", spdKmS.toFixed(2) + " km/s", b ? C.amber : C.fg],
      ["Orbit", g < EV.tli.get ? "185 km parking orbit" : g < 10203 ? "TLI burn" : "Leaving Earth"],
      ["Docked", g >= EV["docking-lm"].get ? "Eagle extracted soon" : "No"]
    ];
    readout(rows);
  };
