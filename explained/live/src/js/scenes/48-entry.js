  var s1E_prevG = null;
  var s1E_skipInfo = null;

  function s1E_getSkipInfo(tr) {
    if (s1E_skipInfo) return s1E_skipInfo;
    var iMin = 0, yMin = 999, iMax = 0, yMax = -999;
    for (var i = 0; i < tr.x.length; i++) {
      var x = tr.x[i], y = tr.y[i];
      if (x >= 450 && x <= 1150 && y < yMin) {
        yMin = y; iMin = i;
      }
    }
    for (var j = iMin; j < tr.x.length; j++) {
      var x2 = tr.x[j], y2 = tr.y[j];
      if (x2 >= 1000 && x2 <= 1850 && y2 > yMax) {
        yMax = y2; iMax = j;
      }
    }
    s1E_skipInfo = { iMin: iMin, iMax: iMax, xMin: tr.x[iMin], yMin: yMin, xMax: tr.x[iMax], yMax: yMax };
    return s1E_skipInfo;
  }

  function s1E_drawPlasmaWakeAndSheath(tr, c, s, px, py, velAng, g) {
    if (g >= tr.sim_end) return;
    // 1. Historical g-load heat ribbon along travelled trajectory (highlights the two g peaks)
    if (s.i > 1) {
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (var k = 1; k <= s.i; k++) {
        var gk = tr.g[k];
        if (gk < 0.22) continue;
        var heatK = Math.min(1, (gk - 0.22) / 5.8);
        var recency = Math.max(0.32, 1 - (s.i - k) / 95);
        ctx.beginPath();
        ctx.moveTo(c.X(tr.x[k - 1]), c.Y(tr.y[k - 1]));
        ctx.lineTo(c.X(tr.x[k]), c.Y(tr.y[k]));
        ctx.strokeStyle = gk > 4.5 ? "#ff4d6d" : gk > 2.2 ? "#ff9233" : C.amber;
        ctx.lineWidth = 2.8 + heatK * 9.0;
        ctx.globalAlpha = (0.10 + heatK * 0.30) * recency;
        ctx.stroke();
      }
      ctx.restore();
    }

    // 2. Live ionised wake & bow-shock plasma sheath scaled by current g load (s.g)
    var gLoad = Math.max(0, s.g || 0);
    var altFade = s.y > 112 ? Math.max(0.22, (124 - s.y) / 12) : 1;
    var heat = Math.min(1, Math.max(0, (gLoad - 0.05) / 5.8)) * altFade;
    if (heat <= 0.08 && g >= EV["entry-interface"].get) {
      heat = Math.max(heat, Math.max(0.14, (123 - s.y) / 70) * 0.26);
    }
    if (heat <= 0.01) return;

    var hp = Math.pow(heat, 0.72);
    var wakeAng = velAng + Math.PI;

    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    // Trailing ionised wake cone behind the CM
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(wakeAng);

    var wakeLen = 22 + 78 * hp;
    var wakeWid = 5.5 + 14 * hp;
    var wg = ctx.createLinearGradient(0, 0, wakeLen, 0);
    if (gLoad > 4.5) {
      wg.addColorStop(0, "rgba(255, 250, 230, " + (0.88 * hp) + ")");
      wg.addColorStop(0.22, "rgba(255, 140, 50, " + (0.74 * hp) + ")");
      wg.addColorStop(0.58, "rgba(255, 55, 110, " + (0.48 * hp) + ")");
      wg.addColorStop(1, "rgba(150, 40, 210, 0)");
    } else {
      wg.addColorStop(0, "rgba(255, 240, 200, " + (0.78 * hp) + ")");
      wg.addColorStop(0.35, "rgba(255, 145, 45, " + (0.58 * hp) + ")");
      wg.addColorStop(0.75, "rgba(220, 70, 35, " + (0.28 * hp) + ")");
      wg.addColorStop(1, "rgba(180, 40, 20, 0)");
    }

    ctx.fillStyle = wg;
    ctx.beginPath();
    ctx.moveTo(-2, -wakeWid * 0.48);
    ctx.quadraticCurveTo(wakeLen * 0.45, -wakeWid, wakeLen, 0);
    ctx.quadraticCurveTo(wakeLen * 0.45, wakeWid, -2, wakeWid * 0.48);
    ctx.closePath();
    ctx.fill();

    var phase = g * 9.5;
    for (var p = 0; p < 6; p++) {
      var u = ((p / 6) + (phase * 0.05) % (1 / 6));
      var wx = 6 + u * wakeLen * 0.92;
      var wy = Math.sin(p * 2.4 + phase) * wakeWid * (0.25 + u * 0.55);
      var wr = (2.2 + u * 5.5) * (0.5 + 0.6 * hp);
      ctx.fillStyle = u < 0.3 ? "#fff7df" : (gLoad > 4.5 && u > 0.55) ? "#ff477e" : "#ff9436";
      ctx.globalAlpha = (1 - u) * (1 - u) * 0.55 * hp;
      ctx.beginPath();
      ctx.arc(wx, wy, wr, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    // Forward bow-shock plasma sheath around blunt heat shield
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(velAng);

    var haloR = 11 + 24 * hp;
    var hg = ctx.createRadialGradient(4, 0, 1, 2, 0, haloR);
    hg.addColorStop(0, "rgba(255, 252, 235, " + (0.92 * hp) + ")");
    hg.addColorStop(0.38, gLoad > 4.8 ? "rgba(255, 95, 65, " + (0.70 * hp) + ")" : "rgba(255, 165, 55, " + (0.64 * hp) + ")");
    hg.addColorStop(0.72, "rgba(255, 50, 105, " + (0.30 * hp) + ")");
    hg.addColorStop(1, "rgba(255, 50, 105, 0)");
    ctx.fillStyle = hg;
    ctx.beginPath();
    ctx.arc(2, 0, haloR, 0, Math.PI * 2);
    ctx.fill();

    var shockW = 8.5 + 5.5 * hp;
    ctx.strokeStyle = "#fff9e6";
    ctx.lineWidth = 1.8 + 2.2 * hp;
    ctx.globalAlpha = Math.min(1, 0.48 + 0.52 * hp);
    ctx.beginPath();
    ctx.moveTo(1.5, -shockW);
    ctx.quadraticCurveTo(9.5 + 3.5 * hp, 0, 1.5, shockW);
    ctx.stroke();

    ctx.strokeStyle = gLoad > 4.8 ? "#ff4268" : "#ff9b30";
    ctx.lineWidth = 3.5 + 4.0 * hp;
    ctx.globalAlpha = 0.45 * hp;
    ctx.beginPath();
    ctx.moveTo(-2.5, -shockW * 1.18);
    ctx.quadraticCurveTo(11.0 + 4.5 * hp, 0, -2.5, shockW * 1.18);
    ctx.stroke();

    ctx.restore();
    ctx.restore();
  }

  function s1E_drawParachutes(px, py, s, g) {
    var isDrogue = s.y > 4.2;
    var sway = Math.sin(g * 1.8) * 0.06;
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(sway);

    if (isDrogue) {
      var canopies = [[-10, -28, 7.5], [10, -29, 7.5]];
      ctx.strokeStyle = "rgba(220, 232, 248, 0.65)";
      ctx.lineWidth = 0.9;
      for (var d = 0; d < canopies.length; d++) {
        var cx = canopies[d][0], cy = canopies[d][1], cr = canopies[d][2];
        ctx.beginPath();
        ctx.moveTo(0, -6); ctx.lineTo(cx - cr * 0.7, cy + 2);
        ctx.moveTo(0, -6); ctx.lineTo(cx + cr * 0.7, cy + 2);
        ctx.stroke();

        ctx.fillStyle = "#e6eef8";
        ctx.beginPath();
        ctx.arc(cx, cy, cr, Math.PI, 0);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = C.amber;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
      label("DROGUE CHUTES · NOT SIMULATED", 16, -22, C.amber, "left");
    } else {
      var mains = [[-18, -38, 11.5], [0, -43, 12.2], [18, -38, 11.5]];
      for (var m = 0; m < mains.length; m++) {
        var mx = mains[m][0], my = mains[m][1], mr = mains[m][2];
        ctx.strokeStyle = "rgba(215, 228, 245, 0.62)";
        ctx.lineWidth = 0.9;
        ctx.beginPath();
        ctx.moveTo(0, -6); ctx.lineTo(mx - mr * 0.78, my + 2);
        ctx.moveTo(0, -6); ctx.lineTo(mx, my + 1);
        ctx.moveTo(0, -6); ctx.lineTo(mx + mr * 0.78, my + 2);
        ctx.stroke();

        ctx.fillStyle = "#e85d2a";
        ctx.beginPath();
        ctx.arc(mx, my, mr, Math.PI, 0);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = "#f4f7fc";
        ctx.beginPath();
        ctx.arc(mx, my, mr, Math.PI * 1.32, Math.PI * 1.68);
        ctx.lineTo(mx, my);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = C.bg;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(mx, my, mr, Math.PI, 0);
        ctx.stroke();
      }
      label("MAIN CHUTES · NOT SIMULATED", 22, -28, C.amber, "left");
    }
    ctx.restore();
  }

  function s1E_drawSplashdown(px, yWater, g) {
    var dtSplash = Math.max(0, g - EV.splashdown.get);
    ctx.save();

    for (var r = 0; r < 4; r++) {
      var phase = (r * 0.25 + (dtSplash * 0.18) % 0.25);
      var rx = 14 + phase * 62;
      var ry = 3.2 + phase * 10.5;
      var alpha = (1 - phase) * 0.68;
      ctx.strokeStyle = r % 2 === 0 ? "#9ad4ff" : "#ffffff";
      ctx.lineWidth = 1.6 - phase * 0.9;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.ellipse(px, yWater + 2, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
    }

    var plumeFactor = Math.max(0.28, 1 - dtSplash / 25);
    ctx.fillStyle = "#eaf6ff";
    ctx.globalAlpha = 0.75 * plumeFactor;
    ctx.beginPath();
    ctx.ellipse(px, yWater + 1, 16 * plumeFactor + 6, 3.5, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#e85d2a";
    ctx.globalAlpha = 0.72;
    ctx.beginPath();
    ctx.ellipse(px + 26, yWater + 3, 11, 2.6, 0.08, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#f4f7fc";
    ctx.globalAlpha = 0.72;
    ctx.beginPath();
    ctx.ellipse(px + 26, yWater + 3, 5, 1.8, 0.08, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }

  function s1E_drawGMeter(rows, curG, maxG) {
    ctx.save();
    ctx.font = "500 13px IBM Plex Mono, monospace";
    var vw = 0;
    for (var i = 0; i < rows.length; i++) {
      vw = Math.max(vw, ctx.measureText(rows[i][1]).width);
    }
    ctx.font = "600 11px Barlow Condensed, Arial Narrow, sans-serif";
    var lw = 0;
    for (var j = 0; j < rows.length; j++) {
      lw = Math.max(lw, ctx.measureText(rows[j][0].toUpperCase()).width);
    }
    var readoutLeft = W - 14 - vw - 12 - lw;
    var barW = 7, barH = 62;
    var barX = readoutLeft - 18;
    var barY = 12;

    if (W < 480) {
      barX = W - 22;
      barY = 86;
      barH = 48;
    }

    var maxScale = 8.0;
    var clampedG = Math.max(0, Math.min(maxScale, curG));
    var fillH = (clampedG / maxScale) * barH;
    var isAlarm = curG > 5.0;
    var barCol = isAlarm ? C.alarm : curG > 3.2 ? C.amber : C.csm;

    ctx.fillStyle = "rgba(9, 13, 21, 0.85)";
    ctx.strokeStyle = isAlarm ? C.alarm : C.line;
    ctx.lineWidth = 1;
    ctx.fillRect(barX, barY, barW, barH);
    ctx.strokeRect(barX + 0.5, barY + 0.5, barW - 1, barH - 1);

    var y5g = barY + barH - (5.0 / maxScale) * barH;
    ctx.fillStyle = "rgba(255, 85, 85, 0.18)";
    ctx.fillRect(barX + 1, barY + 1, barW - 2, y5g - barY - 1);

    if (fillH > 0.5) {
      ctx.fillStyle = barCol;
      ctx.fillRect(barX + 1, barY + barH - fillH, barW - 2, fillH);
    }

    ctx.strokeStyle = C.alarm;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(barX - 3, y5g);
    ctx.lineTo(barX + barW + 2, y5g);
    ctx.stroke();

    if (maxG > 0.2) {
      var yPeak = barY + barH - (Math.min(maxScale, maxG) / maxScale) * barH;
      ctx.strokeStyle = maxG > 5.0 ? C.alarm : C.amber;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(barX, yPeak);
      ctx.lineTo(barX + barW, yPeak);
      ctx.stroke();
    }

    text("5g", barX - 4, y5g + 3, { size: 9, align: "right", color: isAlarm ? C.alarm : C.muted, font: "IBM Plex Mono, monospace" });
    text("G-LOAD", barX + barW * 0.5, barY + barH + 10, { size: 9, weight: 600, align: "center", color: isAlarm ? C.alarm : C.muted, font: "Barlow Condensed, Arial Narrow, sans-serif" });
    ctx.restore();
  }

  SCENES.entry = function (g, dt) {
    var tr = T.entry;
    var pre = g < EV["entry-interface"].get;
    var s = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y], ["g", tr.g]], g);
    var tgt = g < tr.sim_end ? { x0: -40, x1: 2400, y0: -7, y1: 130 } : { x0: 2225, x1: 2385, y0: -0.85, y1: 12 };
    if (pre) tgt = { x0: -420, x1: 2400, y0: -7, y1: 145 };
    var v = smooth(tgt, "entry", dt);

    drawStars();

    var c = chart(v, tr.x_label, tr.y_label);
    var y0 = c.Y(0);

    // 1. Horizontal atmosphere gradient layers (denser lower: Thermosphere -> Mesosphere -> Stratosphere -> Troposphere)
    var y122 = c.Y(121.92), y90 = c.Y(90), y50 = c.Y(50), y15 = c.Y(15);
    var atmTop = Math.max(c.m.t, y122);
    var atmGrad = ctx.createLinearGradient(0, atmTop, 0, y0);
    atmGrad.addColorStop(0, "rgba(42, 72, 148, 0.03)");
    atmGrad.addColorStop(0.26, "rgba(46, 98, 192, 0.11)");
    atmGrad.addColorStop(0.58, "rgba(58, 136, 228, 0.22)");
    atmGrad.addColorStop(0.86, "rgba(88, 172, 248, 0.34)");
    atmGrad.addColorStop(1, "rgba(155, 214, 255, 0.46)");
    ctx.fillStyle = atmGrad;
    ctx.fillRect(c.m.l, atmTop, c.pw, Math.max(0, y0 - atmTop));

    if (v.y1 > 40) {
      ctx.save();
      ctx.setLineDash([3, 5]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(108, 195, 255, 0.32)";
      ctx.beginPath();
      ctx.moveTo(c.m.l, y122);
      ctx.lineTo(c.m.l + c.pw, y122);
      ctx.stroke();

      ctx.strokeStyle = "rgba(108, 195, 255, 0.14)";
      ctx.beginPath();
      ctx.moveTo(c.m.l, y90); ctx.lineTo(c.m.l + c.pw, y90);
      ctx.moveTo(c.m.l, y50); ctx.lineTo(c.m.l + c.pw, y50);
      ctx.moveTo(c.m.l, y15); ctx.lineTo(c.m.l + c.pw, y15);
      ctx.stroke();
      ctx.restore();

      if (W >= 520) {
        text("400,000 FT · ENTRY INTERFACE (122 KM)", c.X(900), y122 - 4, { size: 9.5, align: "center", color: "rgba(145, 205, 255, 0.52)", font: "Barlow Condensed, Arial Narrow, sans-serif", weight: 600 });
        text("MESOSPHERE", c.m.l + c.pw - 8, (y90 + y50) * 0.5 + 3, { size: 9.5, align: "right", color: "rgba(135, 190, 245, 0.35)", font: "Barlow Condensed, Arial Narrow, sans-serif", weight: 600 });
        text("STRATOSPHERE", c.m.l + c.pw - 8, (y50 + y15) * 0.5 + 3, { size: 9.5, align: "right", color: "rgba(155, 208, 255, 0.42)", font: "Barlow Condensed, Arial Narrow, sans-serif", weight: 600 });
      }
    }

    // 2. Pacific Ocean band & glowing Earth limb along the bottom (y <= 0)
    var seaH = Math.max(10, c.m.t + c.ph - y0 + 4);
    var seaGrad = ctx.createLinearGradient(0, y0, 0, y0 + seaH);
    seaGrad.addColorStop(0, "#16487d");
    seaGrad.addColorStop(0.35, "#0d2d52");
    seaGrad.addColorStop(1, "#07182e");
    ctx.fillStyle = seaGrad;
    ctx.fillRect(c.m.l, y0, c.pw, seaH);

    ctx.save();
    var limbGlow = ctx.createLinearGradient(0, y0 - 12, 0, y0 + 4);
    limbGlow.addColorStop(0, "rgba(110, 195, 255, 0)");
    limbGlow.addColorStop(0.75, "rgba(130, 210, 255, 0.44)");
    limbGlow.addColorStop(1, "rgba(80, 165, 240, 0)");
    ctx.fillStyle = limbGlow;
    ctx.fillRect(c.m.l, y0 - 12, c.pw, 16);

    ctx.strokeStyle = "#8fd4ff";
    ctx.globalAlpha = 0.78;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(c.m.l, y0 + 0.5);
    ctx.lineTo(c.m.l + c.pw, y0 + 0.5);
    ctx.stroke();

    ctx.strokeStyle = "rgba(175, 225, 255, 0.28)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (var wx = c.m.l + 18; wx < c.m.l + c.pw - 18; wx += 42) {
      var wy = y0 + 4 + (wx % 3) * 2.2;
      ctx.moveTo(wx, wy);
      ctx.lineTo(wx + 14, wy);
    }
    ctx.stroke();
    ctx.restore();

    // 3. Planned dashed entry path + Skip (Upcontrol) annotation
    polyline(tr.x, tr.y, c.X, c.Y, 0, tr.x.length - 1, C.csm, 1, [4, 5], 0.32);

    if (v.x1 - v.x0 > 1000) {
      var sk = s1E_getSkipInfo(tr);
      var sxMin = c.X(sk.xMin), syMin = c.Y(sk.yMin);
      var sxMax = c.X(sk.xMax), syMax = c.Y(sk.yMax);
      var midX = (sxMin + sxMax) * 0.5;
      var midY = Math.max(syMin, syMax) + 18;
      ctx.save();
      ctx.strokeStyle = "rgba(108, 195, 255, 0.36)";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(sxMin, syMin + 4);
      ctx.quadraticCurveTo(midX, syMin + 14, sxMax, syMax + 4);
      ctx.stroke();
      ctx.restore();
      text("SKIP / UPCONTROL LIFT", midX, midY + 4, {
        size: 10,
        weight: 600,
        align: "center",
        color: "rgba(145, 208, 255, 0.72)",
        font: "Barlow Condensed, Arial Narrow, sans-serif"
      });
    }

    var maxJump = 30 * Math.max(0.25, state.speed || 1);
    var crossed = s1E_prevG !== null && state.playing && g > s1E_prevG && (g - s1E_prevG) <= maxJump;

    if (crossed && s1E_prevG < EV["entry-interface"].get && g >= EV["entry-interface"].get) {
      FX.ping(c.X(tr.x[0]), c.Y(tr.y[0]), C.amber);
      FX.flash(C.amber, 0.10);
    }

    // 4. Program transition pins & labels
    tr.transitions.forEach(function (t) {
      var q = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], t.get);
      var tx = c.X(q.x), ty = c.Y(q.y);
      if (crossed && s1E_prevG < t.get && g >= t.get) {
        FX.ping(tx, ty, C.amber);
      }
      if (g < t.get) return;
      FX.glowDot(tx, ty, 3, C.amber);
      label(t.program, tx + 6, ty - 7, C.amber);
    });

    var targetX = c.X(tr.target_km);
    ctx.fillStyle = C.amber;
    ctx.fillRect(targetX - 1, y0 - 14, 2, 14);
    label("TARGET", targetX, y0 - 18, C.amber, "center");

    // 5. Pre-Entry Interface vs Active Entry vs Parachute/Splashdown
    if (pre) {
      var eiX = c.X(tr.x[0]), eiY = c.Y(tr.y[0]);
      var uPre = Math.max(0, Math.min(1, (g - EV["cm-sm-sep"].get) / Math.max(1, EV["entry-interface"].get - EV["cm-sm-sep"].get)));

      FX.glowDot(eiX, eiY, 3.2, C.amber);
      label("EI GATE", eiX + 8, eiY - 6, C.amber, "left");

      var sEI0 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], EV["entry-interface"].get);
      var sEI1 = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], EV["entry-interface"].get + 6);
      var toEiAng = Math.atan2(c.Y(sEI1.y) - c.Y(sEI0.y), c.X(sEI1.x) - c.X(sEI0.x));
      var eiSlope = (sEI1.y - sEI0.y) / (sEI1.x - sEI0.x);

      var cmWorldX = -240 * (1 - uPre);
      var cmWorldY = tr.y[0] + cmWorldX * eiSlope;
      var cmX = c.X(cmWorldX), cmY = c.Y(cmWorldY);

      ctx.save();
      ctx.strokeStyle = C.csm;
      ctx.globalAlpha = 0.45;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(c.X(-280), c.Y(tr.y[0] - 280 * eiSlope));
      ctx.lineTo(eiX, eiY);
      ctx.stroke();
      ctx.restore();

      // Separated Service Module drifting below-left behind the CM (illustrative)
      var smX = cmX - 18 - uPre * 32;
      var smY = cmY + 18 + uPre * 22;
      ctx.save();
      ctx.translate(smX, smY);
      ctx.rotate(-0.45 - uPre * 2.4);
      ctx.globalAlpha = 0.82;
      ctx.fillStyle = "#5b677a";
      ctx.fillRect(-7, -1.6, 2.5, 3.2);
      ctx.fillStyle = "#9fb0c7";
      ctx.strokeStyle = C.bg;
      ctx.lineWidth = 1;
      ctx.fillRect(-4.5, -3.4, 8.5, 6.8);
      ctx.strokeRect(-4.5, -3.4, 8.5, 6.8);
      ctx.restore();
      text("SM JETTISONED (ILLUSTRATIVE)", smX + 10, smY + 4, { size: 9.5, weight: 600, color: C.muted, font: "Barlow Condensed, Arial Narrow, sans-serif" });

      marker(cmX, cmY, C.csm, "Columbia (CM)", { dx: 14, dy: 4, align: "left" });
      FX.craft("cm", cmX, cmY, toEiAng + Math.PI, 1.18);
    } else {
      var px = c.X(s.x), py = c.Y(s.y);
      var gAhead = Math.min(tr.get[tr.get.length - 1], g + 6);
      var gBehind = Math.max(EV["entry-interface"].get, g - 6);
      var sA = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], gAhead);
      var sB = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], gBehind);
      var velAng = Math.atan2(c.Y(sA.y) - c.Y(sB.y), c.X(sA.x) - c.X(sB.x));

      s1E_drawPlasmaWakeAndSheath(tr, c, s, px, py, velAng, g);
      FX.trail(tr.x, tr.y, c.X, c.Y, 0, s.i, s.f, s.g > 3.5 ? C.amber : C.csm, { width: 2.4, tail: 55 });

      if (crossed && s1E_prevG < EV.splashdown.get && g >= EV.splashdown.get) {
        FX.ping(px, y0, C.csm);
        FX.shake(2.5);
        FX.flash(C.csm, 0.09);
      }

      var splashed = g >= EV.splashdown.get;
      var inChutes = g >= tr.sim_end && !splashed;

      if (inChutes) {
        s1E_drawParachutes(px, py, s, g);
      } else if (splashed) {
        s1E_drawSplashdown(px, y0, g);
      }

      var mOpts = splashed ? { dx: 14, dy: -12, align: "left" } : ((inChutes || s.x > 2050) ? { dx: -12, dy: -10, align: "right" } : { dx: 12, dy: -10, align: "left" });
      marker(px, py, C.csm, splashed ? "Splashdown" : "Columbia", mOpts);

      var cmAng = (g >= tr.sim_end) ? (-Math.PI * 0.5 + Math.sin(g * 2.1) * 0.06) : (velAng + Math.PI);
      FX.craft("cm", px, splashed ? y0 - 1 : py, cmAng, 1.18);
    }

    s1E_prevG = g;
    c.done();

    note(tr.note + " Parachute canopies and separated SM are illustrative.");

    var prog = "P63";
    tr.transitions.forEach(function (t) { if (g >= t.get) prog = t.program; });

    if (pre) {
      var cdText = "CM/SM separated. Entry interface (400,000 ft) in " + Math.max(0, Math.round(EV["entry-interface"].get - g)) + " s";
      ctx.save();
      ctx.font = "500 13px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
      var tw = ctx.measureText(cdText).width + 24;
      ctx.fillStyle = "rgba(9, 13, 21, 0.78)";
      ctx.strokeStyle = "rgba(108, 195, 255, 0.28)";
      ctx.lineWidth = 1;
      if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(W * 0.5 - tw * 0.5, H * 0.5 - 16, tw, 26, 4); ctx.fill(); ctx.stroke(); }
      else { ctx.fillRect(W * 0.5 - tw * 0.5, H * 0.5 - 16, tw, 26); }
      ctx.restore();
      text(cdText, W / 2, H / 2, { align: "center", size: 13, color: C.fg });
      readout([["Speed", "11.0 km/s"]]);
    } else {
      var rRows = [
        ["Program", g >= tr.steeroff.get ? "steering off" : prog, C.amber],
        ["Altitude", s.y.toFixed(1) + " km"],
        ["Load", s.g.toFixed(2) + " g", s.g > 5 ? C.alarm : C.fg],
        ["Range flown", Math.round(s.x).toLocaleString("en-US") + " km"]
      ];
      readout(rRows);
      var maxG = s.g;
      for (var gi = 0; gi <= s.i; gi++) {
        if (tr.g[gi] > maxG) maxG = tr.g[gi];
      }
      s1E_drawGMeter(rRows, s.g, maxG);
    }
  };
