  var rdz_prevG = null;

  function rdz_crossed(t, g, prevG) {
    if (!state.playing || prevG === null || t == null) return false;
    var maxStep = 30 * (state.speed || 1);
    return prevG < t && g >= t && (g - prevG) < maxStep;
  }

  function rdz_scaleBar(kmPerPx) {
    var safeKmPerPx = Math.max(1e-9, kmPerPx);
    var target = 110 * safeKmPerPx;
    var p = Math.pow(10, Math.floor(Math.log10(target)));
    var r = target / p;
    var km = (r < 2 ? 1 : r < 5 ? 2 : 5) * p;
    var px = km / safeKmPerPx;
    var x = 14, y = Math.round(H - 16), rx = Math.round(x + px);
    var lbl = km < 1 ? Math.round(km * 1000) + " m" : km.toLocaleString("en-US") + " km";
    ctx.save();
    ctx.font = "400 11px IBM Plex Mono, monospace";
    var tw = ctx.measureText(lbl).width;
    ctx.fillStyle = "rgba(13, 18, 27, 0.72)";
    var bw = (rx - x) + tw + 20;
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(x - 6, y - 13, bw, 18, 3);
      ctx.fill();
    } else {
      ctx.fillRect(x - 6, y - 13, bw, 18);
    }
    ctx.strokeStyle = C.fg;
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(x, y - 4);
    ctx.lineTo(x, y);
    ctx.lineTo(rx, y);
    ctx.lineTo(rx, y - 4);
    ctx.stroke();
    ctx.globalAlpha = 1;
    text(lbl, rx + 8, y + 1, { size: 11, font: "IBM Plex Mono, monospace", weight: 400, color: C.fg });
    ctx.restore();
  }

  function rdz_wrapLines(str, maxW, font, maxLines) {
    if (!str) return [];
    ctx.font = font;
    var words = str.split(" "), lines = [], line = "";
    for (var wi = 0; wi < words.length; wi++) {
      var test = line ? line + " " + words[wi] : words[wi];
      if (ctx.measureText(test).width > maxW && line) {
        lines.push(line);
        line = words[wi];
      } else {
        line = test;
      }
    }
    if (line) lines.push(line);
    return lines.slice(0, maxLines);
  }

  function rdz_pillLabel(txt, x, y, color, align) {
    if (!isFinite(x) || !isFinite(y)) return;
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

  SCENES.rendezvous = function (g, dt) {
    var tr = T.rendezvous;
    var s = sampleTrack(tr.get, [["x", tr.x], ["z", tr.z]], g);
    var Ex = s.x * 1000, Ez = s.z * 1000;
    var range = Math.hypot(Ex, Ez);

    // Freeze unit vector u when range < 1 m or g >= tr.contact
    var s60 = sampleTrack(tr.get, [["x", tr.x], ["z", tr.z]], tr.contact - 60);
    var fDist = Math.hypot(s60.x, s60.z) * 1000;
    var safeFDist = fDist > 1e-6 ? fDist : 1;
    var uFzX = (s60.x * 1000) / safeFDist;
    var uFzZ = (s60.z * 1000) / safeFDist;
    var safeRange = range > 1e-6 ? range : 1;
    var ux = (range < 1 || g >= tr.contact) ? uFzX : Ex / safeRange;
    var uz = (range < 1 || g >= tr.contact) ? uFzZ : Ez / safeRange;

    // Eagle attitude: 0 = front (windows/radar) to Columbia, 90 = top hatch to Columbia
    var g0 = tr.lm_att.get[0], g1 = tr.lm_att.get[1];
    var attSpan = Math.max(1e-6, g1 - g0);
    var att_deg = g <= g0 ? 0 : g >= g1 ? 90 : (g - g0) / attSpan * 90;

    // Retract slide and wobble
    var wobble_deg = 0, slide_m = 0;
    if (g >= tr.retract && g < EV.docking.get) {
      var dtRet = g - tr.retract;
      var env = Math.max(0, 1 - dtRet / 12);
      if (!reduceMotion) wobble_deg = 9 * Math.sin(2 * Math.PI * dtRet / 3) * env;
      var retDur = EV.docking.get - tr.retract;
      slide_m = retDur > 0 ? 0.35 * Math.min(1, Math.max(0, dtRet / retDur)) : 0.35;
    } else if (g >= EV.docking.get) {
      slide_m = 0.35;
    }

    // Positions in world metres: drogue apex, body centres
    var apex_x = Ex - slide_m * ux;
    var apex_z = Ez - slide_m * uz;
    var dirColWorld = Math.atan2(-uz, -ux);
    var eagleWorldAngle = dirColWorld - (att_deg + wobble_deg) * Math.PI / 180;
    var eagleCenterX = apex_x + 1.85 * Math.sin(eagleWorldAngle);
    var eagleCenterZ = apex_z - 1.85 * Math.cos(eagleWorldAngle);
    var colCenterX = -5.5 * ux;
    var colCenterZ = -5.5 * uz;

    // Camera directly from g (snaps on seek): centre on midpoint of craft bodies
    var midX = (colCenterX + eagleCenterX) / 2;
    var midZ = (colCenterZ + eagleCenterZ) / 2;
    var spanM = Math.max(range * 2.4, 30);
    var avail = Math.max(120, Math.min(W, H) - 72);
    var scale = avail / spanM;
    var gs = Math.max(scale, 40 / 11);
    var cx = W / 2, cy = H / 2;
    function w2sX(x) { return cx + (x - midX) * scale; }
    function w2sY(z) { return cy - (z - midZ) * scale; }
    function w2sX_km(xKm) { return w2sX(xKm * 1000); }
    function w2sY_km(zKm) { return w2sY(zKm * 1000); }

    // 1. Stars & Moon
    drawStars();
    var moonTopY = w2sY(-111000);
    if (moonTopY < H) {
      var moonCx = w2sX(0), moonCy = w2sY(-1848400), moonR = 1737400 * scale;
      if (moonR <= 2600) {
        body(moonCx, moonCy, moonR, C.moon, "");
      } else {
        ctx.save();
        var rimGlow = ctx.createRadialGradient(moonCx, moonCy, moonR - 6, moonCx, moonCy, moonR + 28);
        rimGlow.addColorStop(0, "rgba(200, 210, 228, 0.22)");
        rimGlow.addColorStop(1, "rgba(185, 190, 205, 0)");
        ctx.fillStyle = rimGlow;
        ctx.beginPath();
        ctx.arc(moonCx, moonCy, moonR + 28, 0, Math.PI * 2);
        ctx.fill();

        var moonFill = ctx.createLinearGradient(0, Math.max(0, moonTopY), 0, H);
        moonFill.addColorStop(0, shade(C.moon, 0.56));
        moonFill.addColorStop(0.35, shade(C.moon, 0.44));
        moonFill.addColorStop(1, shade(C.moon, 0.30));
        ctx.beginPath();
        ctx.arc(moonCx, moonCy, moonR, 0, Math.PI * 2);
        ctx.fillStyle = moonFill;
        ctx.fill();
        ctx.strokeStyle = "rgba(220, 228, 242, 0.32)";
        ctx.lineWidth = 1.4;
        ctx.stroke();
        ctx.restore();
      }
      if (moonTopY < H - 22) {
        label("MOON", Math.max(80, Math.min(W - 80, moonCx)), Math.max(moonTopY + 18, H - 14), C.muted, "center");
      }
    } else {
      var mGrad = ctx.createLinearGradient(0, H - 24, 0, H);
      mGrad.addColorStop(0, "rgba(0,0,0,0)");
      mGrad.addColorStop(1, shade(C.moon, 0.25));
      ctx.fillStyle = mGrad;
      ctx.fillRect(0, H - 24, W, 24);
      text("MOON 111 KM BELOW", W - 14, H - 10, { size: 10, weight: 600, font: "Barlow Condensed, Arial Narrow, sans-serif", color: C.faint, align: "right" });
    }

    // 2. Relative trajectory: dashed full path + FX.trail comet tail
    polyline(tr.x, tr.z, w2sX_km, w2sY_km, 0, tr.x.length - 1, C.lm, 1, [4, 5], 0.28);
    var trailAlpha = 0.28 + 0.72 * Math.min(1, range / 1000); // fades in the close-up so it doesn't read as a tether
    FX.trail(tr.x, tr.z, w2sX_km, w2sY_km, 0, s.i, s.f, C.lm, {
      width: 2.3,
      tail: 64,
      alpha: trailAlpha,
      baseAlpha: 0.24 * trailAlpha
    });

    // 3. Burn dots, labels, and one-shot FX.ping / FX.flash triggers
    var maxStep = 30 * (state.speed || 1);
    if (rdz_prevG !== null && (g < rdz_prevG || (g - rdz_prevG) > maxStep)) {
      rdz_prevG = g;
    }
    var drawnLabels = [];
    var eagCenterSx = w2sX(eagleCenterX), eagCenterSy = w2sY(eagleCenterZ);
    var colOriginSx = w2sX(0), colOriginSy = w2sY(0);
    var colBodySx = w2sX(colCenterX), colBodySy = w2sY(colCenterZ);

    tr.burns.forEach(function (b) {
      if (rdz_crossed(b.get, g, rdz_prevG)) {
        var bposTrig = sampleTrack(tr.get, [["x", tr.x], ["z", tr.z]], b.get);
        var btx = w2sX(bposTrig.x * 1000), bty = w2sY(bposTrig.z * 1000);
        FX.ping(btx, bty, C.amber);
        FX.flash(C.amber, b.id === "braking" ? 0.08 : 0.12);
      }
      if (g < b.get) return;
      var bpos = sampleTrack(tr.get, [["x", tr.x], ["z", tr.z]], b.get);
      var bx = w2sX(bpos.x * 1000), by = w2sY(bpos.z * 1000);
      if (bx >= -20 && bx <= W + 20 && by >= -20 && by <= H + 20) {
        FX.glowDot(bx, by, 3.5, C.amber);
      }
      if (bx >= 0 && bx <= W && by >= 0 && by <= H) {
        var tooClose = false;
        for (var di = 0; di < drawnLabels.length; di++) {
          if (Math.hypot(bx - drawnLabels[di].x, by - drawnLabels[di].y) < 60) { tooClose = true; break; }
        }
        // Avoid colliding with craft bodies when zoomed in close
        if (Math.hypot(bx - eagCenterSx, by - eagCenterSy) < 28 || Math.hypot(bx - colBodySx, by - colBodySy) < 34) {
          tooClose = true;
        }
        if (!tooClose) {
          var blbl = b.id.toUpperCase() + (b.dv_ms != null ? " " + b.dv_ms.toFixed(1) + " m/s" : "");
          var isOnCraft = Math.hypot(bx - eagCenterSx, by - eagCenterSy) < 28;
          var lblDx = isOnCraft ? -18 : 8;
          var lblDy = isOnCraft ? -24 : -7;
          var lblAlign = isOnCraft ? "right" : "left";
          rdz_pillLabel(blbl, bx + lblDx, by + lblDy, C.amber, lblAlign);
          drawnLabels.push({ x: bx, y: by });
        }
      }
    });

    // Contact, Retract, and Docking one-shot triggers
    if (rdz_crossed(tr.contact, g, rdz_prevG)) {
      FX.ping(colOriginSx, colOriginSy, C.amber);
      FX.flash(C.amber, 0.11);
      FX.shake(1.8);
    }
    if (rdz_crossed(tr.retract, g, rdz_prevG)) {
      FX.ping(colOriginSx, colOriginSy, C.lm);
    }
    if (rdz_crossed(EV.docking.get, g, rdz_prevG)) {
      FX.ping(colOriginSx, colOriginSy, C.csm);
      FX.flash(C.csm, 0.14);
      FX.shake(2.6);
    }
    rdz_prevG = g;

    // 4. Soft spacecraft ambient glow halo (registers position for smoke test & adds cinematic depth)
    var colCanvasAngle = Math.atan2(-uz, ux);
    var eagSx = w2sX(apex_x), eagSy = w2sY(apex_z);

    if (typeof FX !== "undefined" && FX._mark) {
      FX._mark(colBodySx, colBodySy, C.csm);
      FX._mark(eagCenterSx, eagCenterSy, C.lm);
    }

    ctx.save();
    var cGlowR = Math.max(18, 6.2 * gs);
    var cHalo = ctx.createRadialGradient(colBodySx, colBodySy, 2, colBodySx, colBodySy, cGlowR);
    cHalo.addColorStop(0, C.csm);
    cHalo.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = cHalo;
    ctx.beginPath();
    ctx.arc(colBodySx, colBodySy, cGlowR, 0, Math.PI * 2);
    ctx.fill();

    var eGlowR = Math.max(16, 4.0 * gs);
    var eHalo = ctx.createRadialGradient(eagCenterSx, eagCenterSy, 2, eagCenterSx, eagCenterSy, eGlowR);
    eHalo.addColorStop(0, C.lm);
    eHalo.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalAlpha = 0.20;
    ctx.fillStyle = eHalo;
    ctx.beginPath();
    ctx.arc(eagCenterSx, eagCenterSy, eGlowR, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // 5. Active burn FX.exhaust on Eagle (for 40s after CSI, CDH, TPI, MCC 2, plus RCS braking)
    var eagleCanvasRot = -eagleWorldAngle;
    var nozSx = eagSx - 3.7 * gs * Math.sin(eagleCanvasRot);
    var nozSy = eagSy + 3.7 * gs * Math.cos(eagleCanvasRot);
    var nozOutAngle = eagleCanvasRot + Math.PI / 2;

    if (g < EV.docking.get) {
      for (var bi = 0; bi < tr.burns.length; bi++) {
        var bb = tr.burns[bi];
        if (bb.id !== "braking" && g >= bb.get && g < bb.get + 40) {
          var burnPwr = Math.max(0.35, 1 - (g - bb.get) / 45);
          var exScale = Math.min(1.6, Math.max(0.75, gs * 0.22));
          FX.exhaust(nozSx, nozSy, nozOutAngle, burnPwr, {
            nozzleAngle: true,
            color: C.amber,
            scale: exScale,
            offset: 0
          });
        }
      }
      // Intermittent amber RCS puff toward Columbia during braking
      if (g >= tr.brake && g < tr.brake_end && Math.floor(g / 25) % 3 !== 0) {
        var rcsBrkX = eagSx + 2.2 * gs * Math.cos(eagleCanvasRot) - 1.9 * gs * Math.sin(eagleCanvasRot);
        var rcsBrkY = eagSy + 2.2 * gs * Math.sin(eagleCanvasRot) + 1.9 * gs * Math.cos(eagleCanvasRot);
        var rcsScale = Math.min(0.85, Math.max(0.45, gs * 0.12));
        FX.exhaust(rcsBrkX, rcsBrkY, eagleCanvasRot, 0.55, {
          nozzleAngle: true,
          color: C.amber,
          scale: rcsScale,
          offset: 0,
          spread: 0.35
        });
      }
    }

    // 6. Columbia (CSM) — to-scale drawing
    ctx.save();
    ctx.translate(colOriginSx, colOriginSy);
    ctx.rotate(colCanvasAngle);
    ctx.scale(gs, gs);
    // Probe rod
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-0.8, 0);
    ctx.strokeStyle = C.fg; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // CM cone
    ctx.beginPath();
    ctx.moveTo(-0.8, -0.4); ctx.lineTo(-0.8, 0.4); ctx.lineTo(-4.0, 1.95); ctx.lineTo(-4.0, -1.95); ctx.closePath();
    ctx.fillStyle = shade(C.fg, 0.88); ctx.fill();
    ctx.strokeStyle = C.csm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // SM cylinder
    ctx.beginPath(); ctx.rect(-9.0, -1.95, 5.0, 3.9);
    ctx.fillStyle = shade(C.fg, 0.65); ctx.fill();
    ctx.strokeStyle = C.csm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // SM RCS quad blocks
    ctx.fillStyle = shade(C.fg, 0.5);
    ctx.fillRect(-5.0, 1.95, 0.4, 0.35);
    ctx.fillRect(-5.0, -2.3, 0.4, 0.35);
    // SPS engine bell
    ctx.beginPath();
    ctx.moveTo(-9.0, -0.5); ctx.lineTo(-9.0, 0.5); ctx.lineTo(-11.0, 1.0); ctx.lineTo(-11.0, -1.0); ctx.closePath();
    ctx.fillStyle = shade(C.fg, 0.4); ctx.fill();
    ctx.strokeStyle = C.csm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // Tiny white RCS puff at Columbia SM quad
    if (g < EV.docking.get && g >= tr.collins && g < tr.contact && Math.floor(g / 20) % 4 === 0) {
      ctx.beginPath();
      ctx.moveTo(-4.8, 2.3); ctx.lineTo(-4.6, 2.3 + 6 / gs); ctx.lineTo(-5.0, 2.3 + 6 / gs); ctx.closePath();
      ctx.fillStyle = C.fg; ctx.globalAlpha = 0.8; ctx.fill(); ctx.globalAlpha = 1;
    }
    ctx.restore();

    // 7. Eagle (LM ascent stage) — to-scale drawing
    ctx.save();
    ctx.translate(eagSx, eagSy);
    ctx.rotate(-eagleWorldAngle);
    ctx.scale(gs, -gs);
    // Docking tunnel
    ctx.beginPath(); ctx.rect(-0.5, -0.45, 1.0, 0.45);
    ctx.fillStyle = shade(C.lm, 0.9); ctx.fill();
    ctx.strokeStyle = C.lm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // Cabin
    ctx.beginPath();
    ctx.moveTo(-1.6, -0.45); ctx.lineTo(1.2, -0.45); ctx.lineTo(2.15, -1.4); ctx.lineTo(2.15, -2.6);
    ctx.lineTo(1.4, -3.3); ctx.lineTo(-1.9, -3.3); ctx.lineTo(-2.15, -2.4); ctx.lineTo(-2.15, -1.0); ctx.closePath();
    ctx.fillStyle = shade(C.lm, 0.75); ctx.fill();
    ctx.strokeStyle = C.lm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // Windows
    ctx.fillStyle = C.bg;
    ctx.beginPath(); ctx.moveTo(1.55, -1.25); ctx.lineTo(1.85, -1.35); ctx.lineTo(1.60, -1.45); ctx.closePath(); ctx.fill();
    ctx.beginPath(); ctx.moveTo(1.65, -1.55); ctx.lineTo(1.95, -1.65); ctx.lineTo(1.70, -1.75); ctx.closePath(); ctx.fill();
    // Radar dish
    ctx.beginPath(); ctx.moveTo(0.9, -0.45); ctx.lineTo(0.9, -0.1);
    ctx.strokeStyle = C.lm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    ctx.beginPath(); ctx.arc(0.9, -0.1, 0.35, 0, Math.PI * 2);
    ctx.strokeStyle = C.lm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // RCS quad crosses
    [-2.15, 2.15].forEach(function (qx) {
      ctx.beginPath(); ctx.moveTo(qx - 0.25, -1.9); ctx.lineTo(qx + 0.25, -1.9);
      ctx.moveTo(qx, -2.15); ctx.lineTo(qx, -1.65);
      ctx.strokeStyle = C.lm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    });
    // Ascent engine bell
    ctx.beginPath();
    ctx.moveTo(-0.35, -3.3); ctx.lineTo(0.35, -3.3); ctx.lineTo(0.6, -3.7); ctx.lineTo(-0.6, -3.7); ctx.closePath();
    ctx.fillStyle = shade(C.lm, 0.5); ctx.fill();
    ctx.strokeStyle = C.lm; ctx.lineWidth = 1.2 / gs; ctx.stroke();
    // Inner burn plume cone on Eagle's engine for 40s after CSI, CDH, TPI, MCC 2
    if (g < EV.docking.get) {
      for (var bi2 = 0; bi2 < tr.burns.length; bi2++) {
        var bb2 = tr.burns[bi2];
        if (bb2.id !== "braking" && g >= bb2.get && g < bb2.get + 40) {
          ctx.beginPath();
          ctx.moveTo(-0.4, -3.7);
          ctx.lineTo(0, -3.7 - (14 + (reduceMotion ? 3 : Math.random() * 6)) / gs);
          ctx.lineTo(0.4, -3.7);
          ctx.closePath();
          ctx.fillStyle = C.amber;
          ctx.globalAlpha = 0.85;
          ctx.fill();
          ctx.globalAlpha = 1;
        }
      }
    }
    // Intermittent amber RCS puff toward Columbia during braking
    if (g < EV.docking.get && g >= tr.brake && g < tr.brake_end && Math.floor(g / 25) % 3 !== 0) {
      ctx.beginPath();
      ctx.moveTo(2.2, -1.9); ctx.lineTo(2.2 + 8 / gs, -1.75); ctx.lineTo(2.2 + 8 / gs, -2.05); ctx.closePath();
      ctx.fillStyle = C.amber; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
    }
    ctx.restore();

    // 8. Probe/drogue contact glow & Docking interface flash ring for 20s
    if (g >= tr.contact && g < EV.docking.get) {
      FX.glowDot(w2sX(-0.2 * ux), w2sY(-0.2 * uz), 3.2, C.amber);
    }
    if (g >= EV.docking.get && g < EV.docking.get + 20) {
      var flashAlpha = reduceMotion ? 0.65 : (0.4 + 0.6 * Math.abs(Math.sin((g - EV.docking.get) * Math.PI * 2)));
      ctx.save();
      ctx.translate(w2sX(-0.55 * ux), w2sY(-0.55 * uz));
      ctx.rotate(colCanvasAngle);
      ctx.beginPath();
      ctx.ellipse(0, 0, 1.2 * gs, 2.0 * gs, 0, 0, Math.PI * 2);
      ctx.strokeStyle = C.amber;
      ctx.globalAlpha = flashAlpha;
      ctx.lineWidth = 1.8;
      ctx.stroke();
      ctx.restore();
    }

    // 9. Craft labels
    var perpX = Math.sin(colCanvasAngle), perpY = -Math.cos(colCanvasAngle);
    var colOff = 1.95 * gs + 14 + 34 * Math.abs(perpX) + 6 * Math.abs(perpY);
    var eagOff = 2.3 * gs + 14 + 20 * Math.abs(perpX) + 6 * Math.abs(perpY);
    rdz_pillLabel("COLUMBIA", colBodySx - colOff * perpX, colBodySy - colOff * perpY, C.csm, "center");
    rdz_pillLabel("EAGLE", eagCenterSx + eagOff * perpX, eagCenterSy + eagOff * perpY, C.lm, "center");

    // 10. Earthrise (Collins at 127:51:36: "I got the Earth coming up already.")
    if (g >= tr.brake_end) {
      var erF = Math.min(1, (g - tr.brake_end) / 150);
      var erR = Math.max(8, Math.min(W, H) * 0.022);
      var erX = W - 70;
      var erY = (H + erR + 10) - erF * (erR + 10 + 70);
      ctx.save();
      body(erX, erY, erR, C.earth, "");
      label("EARTHRISE", erX, erY - erR - 6, C.muted, "center");
      ctx.restore();
    }

    // 11. Stage text (top-left)
    var curStage = tr.stages[0];
    for (var si = 0; si < tr.stages.length; si++) {
      if (g >= tr.stages[si].get) curStage = tr.stages[si];
    }
    text(curStage.label.toUpperCase(), 14, 26, { font: "Barlow Condensed, Arial Narrow, sans-serif", size: 22, weight: 700, color: C.fg });

    var rightBoundary = (readoutLeftX > 0 && readoutLeftX <= W ? readoutLeftX : W - 170) - 18;
    var maxStageW = Math.max(140, Math.min(520, rightBoundary - 14));
    var stageLines = rdz_wrapLines(curStage.text, maxStageW, "500 12px IBM Plex Sans, Helvetica Neue, Arial, sans-serif", 3);
    stageLines.forEach(function (l, li) { text(l, 14, 44 + li * 15, { size: 11.5, color: C.muted }); });

    // 12. tr.note (bottom-left above scaleBar)
    var noteMaxW = Math.min(W - 28, 560);
    if (W >= 560) noteMaxW = Math.min(noteMaxW, Math.max(180, W - 210));
    var noteLines = rdz_wrapLines(tr.note, noteMaxW, "400 11px IBM Plex Sans, Helvetica Neue, Arial, sans-serif", 2);
    var noteBaseY = H - 32 - (noteLines.length - 1) * 14;
    if (noteLines.length) {
      ctx.save();
      ctx.font = "400 11px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
      var maxNoteLineW = 0;
      for (var nli = 0; nli < noteLines.length; nli++) {
        maxNoteLineW = Math.max(maxNoteLineW, ctx.measureText(noteLines[nli]).width);
      }
      ctx.fillStyle = "rgba(13, 18, 27, 0.68)";
      var nbH = noteLines.length * 14 + 6;
      if (ctx.roundRect) {
        ctx.beginPath();
        ctx.roundRect(8, noteBaseY - 11, maxNoteLineW + 12, nbH, 3);
        ctx.fill();
      } else {
        ctx.fillRect(8, noteBaseY - 11, maxNoteLineW + 12, nbH);
      }
      ctx.restore();
    }
    noteLines.forEach(function (l, li) {
      text(l, 14, noteBaseY + li * 14, { size: 11, weight: 400, color: C.muted });
    });

    // 13. Scale bar in metres / km that follows the zoom
    rdz_scaleBar(1 / (scale * 1000));

    // 14. Readout (range, range rate / closing from telemetry, flying, Eagle attitude)
    var rangeStr;
    if (g >= EV.docking.get) {
      rangeStr = "docked";
    } else if (g >= tr.contact) {
      rangeStr = "probe in drogue";
    } else if (range >= 1000) {
      rangeStr = (range / 1000).toFixed(1) + " km";
    } else if (range >= 100) {
      rangeStr = Math.round(range) + " m";
    } else {
      rangeStr = range.toFixed(1) + " m (" + Math.round(range * 3.28084) + " ft)";
    }

    var rrSeries = null;
    if (tr.telemetry) {
      for (var ti = 0; ti < tr.telemetry.length; ti++) {
        if (tr.telemetry[ti].key === "range_rate") { rrSeries = tr.telemetry[ti]; break; }
      }
    }
    var closingStr;
    if (g >= tr.contact) {
      closingStr = "0";
    } else {
      var rate = 0;
      if (rrSeries && rrSeries.get && rrSeries.v) {
        var rrVal = sampleTrack(rrSeries.get, [["v", rrSeries.v]], g).v;
        if (isFinite(rrVal)) rate = Math.max(0, -rrVal);
      } else {
        var sPrev = sampleTrack(tr.get, [["x", tr.x], ["z", tr.z]], g - 10);
        var rPrev = Math.hypot(sPrev.x, sPrev.z) * 1000;
        rate = Math.max(0, (rPrev - range) / 10);
      }
      if (rate >= 1) {
        closingStr = rate.toFixed(1) + " m/s";
      } else {
        closingStr = Math.round(rate * 100) + " cm/s";
      }
    }

    var facesStr = att_deg < 5 ? "front to Columbia" : att_deg < 85 ? "turning" : "hatch to Columbia";

    var rRows = [
      ["Range", rangeStr],
      ["Closing", closingStr],
      ["Flying", g < tr.collins ? "Eagle" : "Columbia", g < tr.collins ? C.lm : C.csm]
    ];
    if (H >= 350) {
      rRows.push(["Eagle faces", facesStr]);
    }
    readout(rRows);
  };
