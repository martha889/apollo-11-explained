  var s1L_prevG = null;
  var s1L_teleCache = null;

  function s1L_getTele(tr, key) {
    if (!s1L_teleCache) {
      s1L_teleCache = {};
      if (tr.telemetry) {
        for (var i = 0; i < tr.telemetry.length; i++) {
          s1L_teleCache[tr.telemetry[i].key] = tr.telemetry[i];
        }
      }
    }
    return s1L_teleCache[key] || null;
  }

  function s1L_drawPadAndTower(c, g) {
    var px0 = c.X(0), py0 = c.Y(0);
    ctx.save();
    // Flame trench & concrete pad base
    ctx.fillStyle = "#3a4556";
    ctx.fillRect(px0 - 11, py0 - 2.5, 22, 3.5);
    ctx.fillStyle = "#1d2430";
    ctx.fillRect(px0 - 5, py0 - 1, 10, 2.5);

    // Launch Umbilical Tower (LUT) to the left of the rocket
    var tx = px0 - 9.5, tw = 4.2, th = 24;
    ctx.fillStyle = "#8c3b32";
    ctx.fillRect(tx - 1, py0 - 4, tw + 2, 2.5);
    ctx.strokeStyle = "#b85344";
    ctx.lineWidth = 1.1;
    ctx.strokeRect(tx, py0 - th, tw, th - 2);
    ctx.beginPath();
    for (var y = py0 - 5; y >= py0 - th + 2; y -= 4) {
      ctx.moveTo(tx, y);
      ctx.lineTo(tx + tw, y - 3);
      ctx.moveTo(tx + tw, y);
      ctx.lineTo(tx, y - 3);
    }
    var swing = Math.min(1, Math.max(0, (g - 0.5) / 4.0));
    var armLen = 5.5 * (1 - swing * 0.65);
    for (var ay = py0 - 8; ay >= py0 - th + 4; ay -= 5) {
      ctx.moveTo(tx + tw, ay);
      ctx.lineTo(tx + tw + armLen, ay - swing * 1.8);
    }
    ctx.stroke();

    // Lightning mast & red obstruction beacon
    ctx.strokeStyle = "#dce6f5";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(tx + tw * 0.5, py0 - th);
    ctx.lineTo(tx + tw * 0.5, py0 - th - 5);
    ctx.stroke();
    ctx.fillStyle = "#ff4d4d";
    ctx.beginPath();
    ctx.arc(tx + tw * 0.5, py0 - th - 5.5, 1.4, 0, Math.PI * 2);
    ctx.fill();

    // Liftoff deluge steam & ignition cloud around pad during first 24 s
    if (g >= 0 && g < 24) {
      var u = g / 24;
      var spread = 16 + u * 54;
      var alpha = (1 - u) * (1 - u) * 0.62;
      var sg = ctx.createRadialGradient(px0, py0 - 2, 2, px0, py0 - 3, spread);
      sg.addColorStop(0, "rgba(255, 238, 195, " + (alpha * 1.1) + ")");
      sg.addColorStop(0.45, "rgba(242, 185, 110, " + (alpha * 0.75) + ")");
      sg.addColorStop(1, "rgba(200, 215, 235, 0)");
      ctx.fillStyle = sg;
      ctx.beginPath();
      ctx.ellipse(px0, py0 - 2, spread, 6 + u * 10, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function s1L_drawSmokeTrail(tr, c, s, g) {
    if (s.i < 1 && s.f <= 0.01) return;
    ctx.save();
    var maxSmokeIdx = Math.min(s.i, tr.get.length - 1);
    for (var k = 0; k <= maxSmokeIdx; k += 2) {
      var tk = tr.get[k];
      if (tk > 240) break;
      var age = g - tk;
      if (age < 0 || age > 340) continue;
      var life = tk < 162 ? 320 : 190;
      if (age >= life) continue;
      var u = age / life;
      var altFactor = Math.max(0.15, 1 - tr.y[k] / 110);
      var sx = c.X(tr.x[k]), sy = c.Y(tr.y[k]);
      var driftX = Math.sin(k * 1.7 + age * 0.03) * (2.5 + u * 9);
      var driftY = Math.cos(k * 2.3 - age * 0.02) * (1.5 + u * 5) + u * 3.5;
      var rad = (3.2 + u * 15.5) * (0.55 + 0.45 * altFactor);
      var a = (1 - u) * (1 - u) * 0.22 * altFactor;
      ctx.fillStyle = age < 18 ? "#ffcf7c" : age < 55 ? "#e6dfcf" : "#b9cadf";
      ctx.globalAlpha = a;
      ctx.beginPath();
      ctx.arc(sx + driftX, sy + driftY, rad, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function s1L_drawSpentStage(kind, x, y, ang, alpha, dtSep) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(ang);
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));

    if (dtSep < 12) {
      var pa = (1 - dtSep / 12) * 0.65;
      ctx.fillStyle = C.amber;
      ctx.globalAlpha = alpha * pa;
      ctx.beginPath();
      ctx.arc(5, 0, 3 + dtSep * 0.9, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
    }

    if (kind === "s1c") {
      ctx.fillStyle = "#5b677a";
      ctx.fillRect(-7.5, -2.6, 2.0, 5.2);
      ctx.fillStyle = "#e6eef8";
      ctx.strokeStyle = C.bg;
      ctx.lineWidth = 1;
      ctx.fillRect(-5.8, -3.0, 11.6, 6.0);
      ctx.strokeRect(-5.8, -3.0, 11.6, 6.0);
      ctx.fillStyle = C.bg;
      ctx.fillRect(-4.8, -2.8, 3.0, 1.8);
      ctx.fillRect(-4.8, 1.0, 3.0, 1.8);
      ctx.fillRect(2.2, -2.8, 2.2, 5.6);
    } else if (kind === "s2") {
      ctx.fillStyle = "#5b677a";
      ctx.fillRect(-5.8, -2.0, 1.6, 4.0);
      ctx.fillStyle = "#e6eef8";
      ctx.strokeStyle = C.bg;
      ctx.lineWidth = 1;
      ctx.fillRect(-4.4, -2.6, 8.8, 5.2);
      ctx.strokeRect(-4.4, -2.6, 8.8, 5.2);
      ctx.fillStyle = C.bg;
      ctx.fillRect(-3.6, -2.4, 1.8, 4.8);
    } else if (kind === "let") {
      ctx.strokeStyle = "#f2b13c";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(-4.5, 0);
      ctx.lineTo(4.5, 0);
      ctx.stroke();
      ctx.fillStyle = "#e6eef8";
      ctx.fillRect(-3.5, -1.1, 4.2, 2.2);
    }
    ctx.restore();
  }

  function s1L_pinLabel(textStr, x, y, dx, dy, color, align) {
    var lx = x + dx, ly = y + dy;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.45;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(lx + (align === "right" ? 2 : -2), ly - 3.5);
    ctx.stroke();

    ctx.font = "600 10.5px Barlow Condensed, Arial Narrow, sans-serif";
    var up = textStr.toUpperCase();
    var tw = ctx.measureText(up).width;
    var padX = 4, bh = 13, bw = tw + padX * 2;
    var bx = align === "right" ? lx - tw - padX : align === "center" ? lx - tw * 0.5 - padX : lx - padX;
    var by = ly - 10;
    ctx.fillStyle = "rgba(10, 15, 24, 0.78)";
    ctx.globalAlpha = 0.88;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 2.5);
    else ctx.rect(bx, by, bw, bh);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.28;
    ctx.stroke();
    ctx.restore();

    text(up, lx, ly, {
      size: 10.5,
      weight: 600,
      color: color,
      font: "Barlow Condensed, Arial Narrow, sans-serif",
      align: align || "left"
    });
  }

  SCENES.launch = function (g, dt) {
    var tr = T.launch;
    var v = smooth({ x0: -40, x1: 2800, y0: -9, y1: 212 }, "launch", dt);
    var s = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y], ["v", tr.v]], g);

    // Real altitude-driven transition from morning sky to starry black space
    var altKm = Math.max(0, s.y);
    var spaceFrac = sstep(6, 92, altKm);
    var skyAlpha = 1 - spaceFrac * 0.92;

    ctx.save();
    ctx.globalAlpha = 0.16 + 0.84 * spaceFrac;
    drawStars();
    ctx.restore();

    if (skyAlpha > 0.02) {
      ctx.save();
      var fullSky = ctx.createLinearGradient(0, 0, 0, H);
      fullSky.addColorStop(0, "rgba(11, 26, 54, " + (skyAlpha * 0.78) + ")");
      fullSky.addColorStop(0.52, "rgba(24, 62, 118, " + (skyAlpha * 0.74) + ")");
      fullSky.addColorStop(0.84, "rgba(56, 110, 172, " + (skyAlpha * 0.68) + ")");
      fullSky.addColorStop(1, "rgba(162, 128, 96, " + (skyAlpha * 0.45) + ")");
      ctx.fillStyle = fullSky;
      ctx.fillRect(0, 0, W, H);
      ctx.restore();
    }

    var c = chart(v, tr.x_label, tr.y_label);

    var yTopAtm = c.Y(115), yGround = c.Y(0);
    if (skyAlpha > 0.03) {
      var chartSky = ctx.createLinearGradient(0, c.m.t, 0, yGround);
      chartSky.addColorStop(0, "rgba(14, 34, 70, " + (skyAlpha * 0.55) + ")");
      chartSky.addColorStop(0.55, "rgba(34, 82, 148, " + (skyAlpha * 0.52) + ")");
      chartSky.addColorStop(0.88, "rgba(74, 134, 196, " + (skyAlpha * 0.46) + ")");
      chartSky.addColorStop(1, "rgba(218, 162, 112, " + (skyAlpha * 0.36) + ")");
      ctx.fillStyle = chartSky;
      ctx.fillRect(c.m.l, c.m.t, c.pw, Math.max(0, yGround - c.m.t));
    }

    var atmGrad = ctx.createLinearGradient(0, yTopAtm, 0, yGround);
    atmGrad.addColorStop(0, "rgba(35, 85, 175, 0)");
    atmGrad.addColorStop(0.45, "rgba(42, 105, 205, 0.08)");
    atmGrad.addColorStop(0.78, "rgba(68, 148, 238, 0.20)");
    atmGrad.addColorStop(0.94, "rgba(115, 188, 255, 0.32)");
    atmGrad.addColorStop(1, "rgba(235, 188, 138, 0.38)");
    ctx.fillStyle = atmGrad;
    ctx.fillRect(c.m.l, yTopAtm, c.pw, Math.max(0, yGround - yTopAtm));

    var bandH = Math.max(8, c.m.t + c.ph - yGround + 4);
    var seaGrad = ctx.createLinearGradient(0, yGround, 0, yGround + bandH);
    seaGrad.addColorStop(0, "#15365e");
    seaGrad.addColorStop(0.35, "#0d2340");
    seaGrad.addColorStop(1, "#081528");
    ctx.fillStyle = seaGrad;
    ctx.fillRect(c.m.l, yGround, c.pw, bandH);

    var landX0 = c.X(-40), landX1 = c.X(28);
    ctx.fillStyle = "#1f332b";
    ctx.fillRect(landX0, yGround, Math.max(6, landX1 - landX0), bandH);

    ctx.save();
    ctx.strokeStyle = "#82c8ff";
    ctx.globalAlpha = 0.65;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(c.m.l, yGround + 0.5);
    ctx.lineTo(c.m.l + c.pw, yGround + 0.5);
    ctx.stroke();
    ctx.restore();

    s1L_drawPadAndTower(c, g);

    polyline(tr.x, tr.y, c.X, c.Y, 0, tr.x.length - 1, C.csm, 1, [4, 5], 0.35);

    s1L_drawSmokeTrail(tr, c, s, g);
    FX.trail(tr.x, tr.y, c.X, c.Y, 0, s.i, s.f, C.csm, { width: 2.5, tail: 72 });

    var maxJump = 30 * Math.max(0.25, state.speed || 1);
    var crossedAny = s1L_prevG !== null && state.playing && g > s1L_prevG && (g - s1L_prevG) <= maxJump;
    if (state.playing && g >= 0 && g < 10) {
      FX.shake(1.6 * (1 - g / 10));
    }

    var stages = tr.stages || [];
    var secoaGet = 548, secoGet = 700;
    for (var si = 0; si < stages.length; si++) {
      if (stages[si].id === "secoa") secoaGet = stages[si].get;
      if (stages[si].id === "seco") secoGet = stages[si].get;
    }

    for (var k = 0; k < stages.length; k++) {
      var st = stages[k];
      var q = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], st.get);
      var sx = c.X(q.x), sy = c.Y(q.y);

      if (crossedAny && s1L_prevG < st.get && g >= st.get) {
        FX.ping(sx, sy, st.approx ? C.csm : C.amber);
        if (st.id === "oeco" || st.id === "secoa" || st.id === "seco") {
          FX.shake(2.6);
          FX.flash(C.amber, 0.08);
        }
      }

      if (g >= st.get) {
        var pinCol = st.approx ? C.csm : C.amber;
        FX.glowDot(sx, sy, 2.8, pinCol);

        // Place early climb pins to the right of the trajectory so they never clip on the left chart edge
        var shortTag = st.id.toUpperCase();
        var dx = 12, dy = 4, al = "left";
        if (st.id === "ceco") {
          shortTag = "CECO"; dx = 12; dy = 6; al = "left";
        } else if (st.id === "oeco") {
          shortTag = "S-IC SEP"; dx = 12; dy = -5; al = "left";
        } else if (st.id === "s2-ign") {
          shortTag = "S-II IGN"; dx = 12; dy = 11; al = "left";
        } else if (st.id === "let") {
          shortTag = "LET JETT"; dx = 12; dy = -4; al = "left";
        } else if (st.id === "secoa") {
          shortTag = "S-II SEP"; dx = -10; dy = 16; al = "right";
        } else if (st.id === "s4-ign") {
          shortTag = "S-IVB IGN"; dx = 10; dy = 16; al = "left";
        } else if (st.id === "seco") {
          shortTag = "SECO"; dx = -10; dy = 18; al = "right";
        }
        if (st.approx) shortTag = "~" + shortTag;
        s1L_pinLabel(shortTag, sx, sy, dx, dy, pinCol, al);

        // Separated spent stage glyph tumbling away and fading (illustrative)
        var dtSep = g - st.get;
        if (st.id === "oeco" && dtSep > 0 && dtSep < 115) {
          var u1 = dtSep / 115;
          s1L_drawSpentStage("s1c", sx - 5 - u1 * 18, sy + 6 + u1 * u1 * 48, -0.95 + dtSep * 0.042, (1 - u1) * 0.9, dtSep);
        } else if (st.id === "let" && dtSep > 0 && dtSep < 75) {
          var uL = dtSep / 75;
          s1L_drawSpentStage("let", sx - 4 - uL * 16, sy - 6 - uL * 18 + uL * uL * 26, -0.7 - dtSep * 0.065, (1 - uL) * 0.85, dtSep);
        } else if (st.id === "secoa" && dtSep > 0 && dtSep < 120) {
          var u2 = dtSep / 120;
          s1L_drawSpentStage("s2", sx - 8 - u2 * 42, sy + 5 + u2 * u2 * 38, -0.15 + dtSep * 0.036, (1 - u2) * 0.9, dtSep);
        }
      }
    }
    s1L_prevG = g;

    var px = c.X(s.x), py = c.Y(s.y);
    var gMax = tr.get[tr.get.length - 1];
    var gAhead = Math.min(gMax, Math.max(12, g + 6));
    var gBehind = Math.max(0, Math.min(gMax - 12, g - 6));
    var sA = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], gAhead);
    var sB = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], gBehind);
    var dScreenX = c.X(sA.x) - c.X(sB.x);
    var dScreenY = c.Y(sA.y) - c.Y(sB.y);
    var tanAng = Math.atan2(dScreenY, dScreenX);
    var padBlend = sstep(0, 12, g);
    var ang = -Math.PI * 0.5 + (tanAng - (-Math.PI * 0.5)) * padBlend;

    if (g < secoGet) {
      var pwr = 0.75, exScale = 0.85;
      if (g < 162) {
        var uBoost = Math.max(0, Math.min(1, g / 162));
        pwr = (g < 135 ? (1.35 - 0.22 * uBoost) : 0.92);
        exScale = 1.42 - 0.32 * uBoost;
      } else if (g < secoaGet) {
        var uS2 = (g - 162) / Math.max(1, secoaGet - 162);
        pwr = 0.92 - 0.14 * uS2;
        exScale = 1.02 - 0.14 * uS2;
      } else {
        pwr = 0.72;
        exScale = 0.82;
      }
      FX.exhaust(px, py, ang, pwr, { color: C.amber, scale: exScale, offset: 12.5 });
    }

    var craftName = g < 709 ? "Saturn V" : "Columbia + S-IVB";
    var mOpts = s.x > 2100 ? { dx: -14, dy: -12, align: "right" } : (s.y > 185 ? { dx: 14, dy: 4, align: "left" } : { dx: 14, dy: -10, align: "left" });
    marker(px, py, C.csm, craftName, mOpts);
    FX.craft(g < secoaGet ? "saturn-v" : "csm-sivb", px, py, ang, 1.15, { engine: false });

    c.done();

    note(tr.note + " Vertical scale exaggerated about 14 times; separated stages illustrative.");

    var accTele = s1L_getTele(tr, "accel_g");
    var accG = 0;
    if (accTele && g <= secoGet) {
      accG = sampleTrack(accTele.get, [["a", accTele.v]], g).a;
    }
    readout([
      ["Altitude", s.y.toFixed(1) + " km"],
      ["Inertial speed", Math.round(s.v).toLocaleString("en-US") + " m/s"],
      ["Downrange", Math.round(s.x).toLocaleString("en-US") + " km"],
      ["Acceleration", accG.toFixed(2) + " g", accG > 3.5 ? C.amber : C.fg]
    ]);
  };
