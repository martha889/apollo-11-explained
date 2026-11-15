  // ---------- FX: particles, trails, spacecraft glyphs, overlays ----------
  var FX = (function () {
    var MAX_P = 600;
    var pActive = new Uint8Array(MAX_P);
    var pKind = new Uint8Array(MAX_P); // 0 = exhaust, 1 = dust
    var px = new Float32Array(MAX_P);
    var py = new Float32Array(MAX_P);
    var vx = new Float32Array(MAX_P);
    var vy = new Float32Array(MAX_P);
    var pAge = new Float32Array(MAX_P);
    var pLife = new Float32Array(MAX_P);
    var pR0 = new Float32Array(MAX_P);
    var pR1 = new Float32Array(MAX_P);
    var pCursor = 0, activeCount = 0;
    var frameId = 1, exhaustDrawnFrame = 0, dustDrawnFrame = 0;

    // Pings (expanding event rings)
    var MAX_PINGS = 16;
    var pings = [];
    for (var pi = 0; pi < MAX_PINGS; pi++) {
      pings.push({ active: false, x: 0, y: 0, age: 0, life: 0.9, color: "#f2b13c" });
    }
    var activePings = 0;

    // Full-canvas flash & decaying camera shake
    var flashAlpha = 0, flashColor = "#f2b13c";
    var shakeAmp = 0, shakeClock = 0;
    var lastMarkX = 0, lastMarkY = 0, lastMarkValid = false;

    // Deterministic fast PRNG for particle variation
    var fxSeed = 918273;
    function frnd() {
      fxSeed = (fxSeed * 1664525 + 1013904223) >>> 0;
      return fxSeed / 4294967296;
    }

    function spawnParticle(kind, x, y, svx, svy, life, r0, r1) {
      if (reduceMotion) return;
      var idx = pCursor;
      pCursor = (pCursor + 1) % MAX_P;
      if (!pActive[idx]) activeCount++;
      pActive[idx] = 1;
      pKind[idx] = kind;
      px[idx] = x;
      py[idx] = y;
      vx[idx] = svx;
      vy[idx] = svy;
      pAge[idx] = 0;
      pLife[idx] = life;
      pR0[idx] = r0;
      pR1[idx] = r1;
    }

    function reset() {
      for (var i = 0; i < MAX_P; i++) pActive[i] = 0;
      activeCount = 0;
      for (var j = 0; j < MAX_PINGS; j++) pings[j].active = false;
      activePings = 0;
      flashAlpha = 0;
      shakeAmp = 0;
      api.shakeX = 0;
      api.shakeY = 0;
      if (!state.playing) {
        view = null;
        viewMoving = false;
      }
    }

    function tick(dt, playing) {
      frameId++;
      if (reduceMotion) {
        if (activeCount > 0 || activePings > 0 || flashAlpha > 0 || shakeAmp > 0) reset();
        return false;
      }
      var step = dt > 0 ? Math.min(0.1, dt) : 0;
      if (step <= 0) return isActive();

      // Advance particles
      if (activeCount > 0) {
        var alive = 0;
        for (var i = 0; i < MAX_P; i++) {
          if (!pActive[i]) continue;
          var age = pAge[i] + step;
          if (age >= pLife[i]) {
            pActive[i] = 0;
            continue;
          }
          pAge[i] = age;
          px[i] += vx[i] * step;
          py[i] += vy[i] * step;
          if (pKind[i] === 1) {
            // Dust settles slightly downward with drag
            vy[i] += 18 * step;
            vx[i] *= (1 - 1.8 * step);
          } else {
            // Exhaust slows slightly
            vx[i] *= (1 - 1.2 * step);
            vy[i] *= (1 - 1.2 * step);
          }
          alive++;
        }
        activeCount = alive;
      }

      // Advance pings
      if (activePings > 0) {
        var pAlive = 0;
        for (var j = 0; j < MAX_PINGS; j++) {
          var pg = pings[j];
          if (!pg.active) continue;
          pg.age += step;
          if (pg.age >= pg.life) {
            pg.active = false;
            continue;
          }
          pAlive++;
        }
        activePings = pAlive;
      }

      // Advance flash
      if (flashAlpha > 0) {
        flashAlpha -= step * 0.85;
        if (flashAlpha < 0.004) flashAlpha = 0;
      }

      // Advance camera shake
      if (shakeAmp > 0.05) {
        shakeClock += step * 52;
        shakeAmp *= Math.exp(-step * 7.2);
        if (shakeAmp < 0.05) {
          shakeAmp = 0;
          api.shakeX = 0;
          api.shakeY = 0;
        } else {
          api.shakeX = Math.sin(shakeClock * 1.7) * Math.cos(shakeClock * 0.9) * shakeAmp;
          api.shakeY = Math.cos(shakeClock * 2.1) * Math.sin(shakeClock * 1.3) * shakeAmp;
        }
      } else {
        shakeAmp = 0;
        api.shakeX = 0;
        api.shakeY = 0;
      }
      return isActive();
    }

    function isActive() {
      if (reduceMotion) return false;
      return activeCount > 0 || activePings > 0 || flashAlpha > 0.004 || shakeAmp > 0.05;
    }

    function drawExhaustParticles() {
      if (exhaustDrawnFrame === frameId || activeCount === 0 || reduceMotion) return;
      exhaustDrawnFrame = frameId;
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      for (var i = 0; i < MAX_P; i++) {
        if (!pActive[i] || pKind[i] !== 0) continue;
        var u = pAge[i] / pLife[i];
        var r = pR0[i] + (pR1[i] - pR0[i]) * u;
        var alpha = (1 - u) * (1 - u) * 0.72;
        if (u < 0.24) ctx.fillStyle = "#fff9e6";
        else if (u < 0.62) ctx.fillStyle = "#ffb840";
        else ctx.fillStyle = "#e05219";
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.arc(px[i], py[i], r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    function drawDustParticles() {
      if (dustDrawnFrame === frameId || activeCount === 0 || reduceMotion) return;
      dustDrawnFrame = frameId;
      ctx.save();
      ctx.fillStyle = C.moon || "#b9bcc4";
      for (var i = 0; i < MAX_P; i++) {
        if (!pActive[i] || pKind[i] !== 1) continue;
        var u = pAge[i] / pLife[i];
        var r = pR0[i] + (pR1[i] - pR0[i]) * u;
        ctx.globalAlpha = (1 - u) * 0.42;
        ctx.beginPath();
        ctx.arc(px[i], py[i], r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    // Comet trail ending at exact interpolated head position
    function trail(xs, ys, X, Y, i0, iHead, fHead, color, opts) {
      if (!xs || !ys || !xs.length) return;
      opts = opts || {};
      i0 = Math.max(0, i0 | 0);
      iHead = Math.max(i0, Math.min(xs.length - 1, iHead | 0));
      var f = fHead == null ? 0 : Math.max(0, Math.min(1, fHead));
      if (iHead <= i0 && f <= 1e-5) return;

      var iNext = Math.min(xs.length - 1, iHead + 1);
      var hx = X(xs[iHead] + (xs[iNext] - xs[iHead]) * f);
      var hy = Y(ys[iHead] + (ys[iNext] - ys[iHead]) * f);
      var w = opts.width || 2.4;
      var col = color || C.csm;
      var baseA = opts.baseAlpha == null ? 0.25 : opts.baseAlpha;

      ctx.save();
      ctx.strokeStyle = col;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.setLineDash([]);

      // Faint baseline over full travelled history
      if (baseA > 0 && iHead > i0) {
        ctx.beginPath();
        ctx.moveTo(X(xs[i0]), Y(ys[i0]));
        for (var i = i0 + 1; i <= iHead; i++) ctx.lineTo(X(xs[i]), Y(ys[i]));
        ctx.lineTo(hx, hy);
        ctx.lineWidth = Math.max(1, w * 0.55);
        ctx.globalAlpha = baseA;
        ctx.stroke();
      }

      // Graduated comet tail segments up to exact interpolated head
      var span = Math.max(1, iHead - i0);
      var tailCount = opts.tail || Math.min(84, Math.max(16, Math.round(span * 0.42)));
      var tStart = Math.max(i0, iHead - tailCount);
      var totalPts = iHead - tStart;
      var bands = Math.min(8, Math.max(1, totalPts + (f > 0 ? 1 : 0)));

      for (var b = 0; b < bands; b++) {
        var b0 = Math.floor(tStart + (totalPts * b) / bands);
        var b1 = Math.floor(tStart + (totalPts * (b + 1)) / bands);
        var isLast = b === bands - 1;
        if (b1 <= b0 && !isLast) continue;
        var frac = (b + 1) / bands;
        ctx.beginPath();
        ctx.moveTo(X(xs[b0]), Y(ys[b0]));
        for (var k = b0 + 1; k <= b1; k++) ctx.lineTo(X(xs[k]), Y(ys[k]));
        if (isLast && f > 0) ctx.lineTo(hx, hy);

        var segW = w * (0.42 + 0.72 * frac);
        var segA = (opts.alpha || 1) * (0.14 + 0.86 * frac * frac);
        if (frac > 0.6 && opts.glow !== false) {
          ctx.lineWidth = segW * 3.1;
          ctx.globalAlpha = segA * 0.20;
          ctx.stroke();
        }
        ctx.lineWidth = segW;
        ctx.globalAlpha = segA;
        ctx.stroke();
      }

      // Bright core highlight on the leading tip
      var tipStart = Math.max(i0, iHead - 2);
      ctx.beginPath();
      ctx.moveTo(X(xs[tipStart]), Y(ys[tipStart]));
      for (var m = tipStart + 1; m <= iHead; m++) ctx.lineTo(X(xs[m]), Y(ys[m]));
      ctx.lineTo(hx, hy);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = Math.max(0.9, w * 0.45);
      ctx.globalAlpha = (opts.alpha || 1) * 0.55;
      ctx.stroke();
      ctx.restore();
    }

    // Throttle-scaled engine exhaust & pooled particles
    function exhaust(x, y, ang, power01, opts) {
      var pwr = power01 == null ? 1 : Math.max(0, Math.min(1.5, power01));
      if (pwr <= 0.005) return;
      opts = opts || {};
      var scale = opts.scale || 1;
      var col = opts.color || C.amber;
      var offset = opts.offset == null ? 5 * scale : opts.offset;
      var outAng = opts.nozzleAngle ? ang : ang + Math.PI;
      api._mark(x, y, col);

      if (reduceMotion) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(outAng);
        var sLen = (14 + 14 * pwr) * scale, sWid = (2.8 + 1.8 * pwr) * scale;
        ctx.beginPath();
        ctx.moveTo(offset, -sWid);
        ctx.lineTo(offset + sLen, 0);
        ctx.lineTo(offset, sWid);
        ctx.closePath();
        ctx.fillStyle = col;
        ctx.globalAlpha = 0.82;
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(offset, -sWid * 0.5);
        ctx.lineTo(offset + sLen * 0.55, 0);
        ctx.lineTo(offset, sWid * 0.5);
        ctx.closePath();
        ctx.fillStyle = "#fff8e7";
        ctx.globalAlpha = 0.9;
        ctx.fill();
        ctx.restore();
        return;
      }

      // Spawn pooled exhaust particles while playing
      var ca = Math.cos(outAng), sa = Math.sin(outAng);
      var nx = x + ca * offset, ny = y + sa * offset;
      if (state.playing) {
        var count = Math.max(1, Math.round(pwr * 3));
        for (var i = 0; i < count; i++) {
          var spread = (frnd() - 0.5) * (opts.spread || 0.42);
          var pa = outAng + spread;
          var spd = (36 + frnd() * 58) * (0.55 + 0.65 * pwr) * scale;
          var life = (0.18 + frnd() * 0.24) * (0.75 + 0.35 * scale);
          var r0 = (1.4 + frnd() * 1.1) * scale * (0.7 + 0.4 * pwr);
          var r1 = r0 * (2.1 + frnd() * 0.9);
          spawnParticle(0, nx + (frnd() - 0.5) * 2, ny + (frnd() - 0.5) * 2, Math.cos(pa) * spd, Math.sin(pa) * spd, life, r0, r1);
        }
      }

      // Draw active exhaust particles first, then flickering core flame
      drawExhaustParticles();

      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(outAng);
      ctx.globalCompositeOperation = "lighter";

      var phase = state.playing ? (performance.now() * 0.018) : (state.play * 13.7);
      var flick = 0.88 + 0.22 * Math.sin(phase * 3.1);
      var len = (15 + 19 * pwr) * scale * flick;
      var wid = (3.1 + 2.2 * pwr) * scale;

      // Soft outer glow cone
      var pg = ctx.createRadialGradient(offset + len * 0.22, 0, 1, offset + len * 0.35, 0, len * 0.88);
      pg.addColorStop(0, col);
      pg.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = pg;
      ctx.globalAlpha = 0.44 * Math.min(1, pwr + 0.2);
      ctx.beginPath();
      ctx.arc(offset + len * 0.3, 0, len * 0.78, 0, Math.PI * 2);
      ctx.fill();

      // Embedded glowing exhaust puffs along the jet so paused frames also show rich particle structure
      for (var ep = 0; ep < 7; ep++) {
        var eu = ((ep / 7) + (phase * 0.08) % (1 / 7));
        var ex = offset + eu * len * 1.25;
        var ey = Math.sin(ep * 2.7 + phase) * wid * (0.35 + eu * 0.85);
        var er = (1.3 + eu * 2.8) * scale * (0.65 + 0.35 * pwr);
        ctx.fillStyle = eu < 0.3 ? "#fff9e6" : eu < 0.68 ? "#ffb840" : "#e05219";
        ctx.globalAlpha = (1 - eu) * (1 - eu) * 0.62;
        ctx.beginPath();
        ctx.arc(ex, ey, er, 0, Math.PI * 2);
        ctx.fill();
      }

      // Mid amber-orange plume tongue
      ctx.beginPath();
      ctx.moveTo(offset, -wid);
      ctx.quadraticCurveTo(offset + len * 0.55, -wid * 0.45, offset + len, Math.sin(phase * 1.9) * 1.2);
      ctx.quadraticCurveTo(offset + len * 0.55, wid * 0.45, offset, wid);
      ctx.closePath();
      ctx.fillStyle = col;
      ctx.globalAlpha = 0.80;
      ctx.fill();

      // Hot white inner core flame
      var coreLen = len * (0.54 + 0.08 * Math.cos(phase * 2.3));
      ctx.beginPath();
      ctx.moveTo(offset, -wid * 0.52);
      ctx.lineTo(offset + coreLen, 0);
      ctx.lineTo(offset, wid * 0.52);
      ctx.closePath();
      ctx.fillStyle = "#fff9eb";
      ctx.globalAlpha = 0.95;
      ctx.fill();

      ctx.restore();
    }

    // Vector spacecraft silhouettes (crisp at 16-48 px)
    // Angle convention: ang = 0 points right (+x), matching Math.atan2(dy, dx) and plume().
    // Pass opts.upright = true if ang = 0 means nose up (-y).
    function craft(kind, x, y, ang, scale, opts) {
      var k = String(kind || "csm").toLowerCase();
      var s = (scale == null || scale <= 0) ? 1 : (scale >= 8 ? scale / 24 : scale);
      var eng = false, pwr = 0.9, upright = false, col = null;
      if (typeof opts === "boolean") {
        eng = opts;
      } else if (typeof opts === "number") {
        eng = opts > 0; pwr = opts;
      } else if (opts) {
        if (opts.throttle != null) { eng = opts.throttle > 0; pwr = opts.throttle; }
        else if (opts.power != null) { eng = opts.power > 0; pwr = opts.power; }
        else { eng = !!(opts.engine || opts.engineOn || opts.burning || opts.burn || opts.plume); }
        upright = !!opts.upright;
        col = opts.color || null;
      }
      var rot = (ang || 0) - (upright ? Math.PI * 0.5 : 0);
      var isLmKind = k === "lm" || k === "lm-ascent";
      api._mark(x, y, col || (isLmKind ? C.lm : C.csm));

      if (eng) {
        var nozOff = (k === "saturn-v" ? 13 : k === "csm-sivb" || k === "csm-lm" ? 11.5 : k === "lm-ascent" || k === "cm" ? 6.5 : 9.5) * s;
        exhaust(x, y, rot, pwr, { scale: s, offset: nozOff, color: C.amber });
      }

      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(rot);
      ctx.scale(s, s);
      ctx.lineJoin = "round";
      ctx.lineCap = "round";

      var strokeDark = C.bg || "#0d121b";
      var csmCol = col || C.csm || "#6cc3ff";
      var lmCol = col || C.lm || "#f2b13c";
      var whiteCol = "#e6eef8";
      var metalCol = "#9fb0c7";

      if (k === "saturn-v") {
        // 5 F-1 nozzles
        ctx.fillStyle = "#5b677a";
        ctx.fillRect(-14, -3.6, 2.5, 1.8);
        ctx.fillRect(-14, -0.9, 2.5, 1.8);
        ctx.fillRect(-14, 1.8, 2.5, 1.8);
        // S-IC + S-II + S-IVB stages
        ctx.fillStyle = whiteCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.1;
        ctx.beginPath();
        ctx.moveTo(-11.5, -4.0);
        ctx.lineTo(2.5, -4.0);
        ctx.lineTo(4.2, -2.8);
        ctx.lineTo(8.5, -2.8);
        ctx.lineTo(12.2, 0);
        ctx.lineTo(8.5, 2.8);
        ctx.lineTo(4.2, 2.8);
        ctx.lineTo(2.5, 4.0);
        ctx.lineTo(-11.5, 4.0);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        // Iconic black roll-pattern bands & fins
        ctx.fillStyle = strokeDark;
        ctx.fillRect(-10.5, -3.8, 3.2, 2.4);
        ctx.fillRect(-10.5, 1.4, 3.2, 2.4);
        ctx.fillRect(-3.8, -3.9, 1.8, 7.8);
        ctx.fillRect(2.8, -2.8, 1.3, 5.6);
        // Aft fins
        ctx.beginPath();
        ctx.moveTo(-11.5, -4.0); ctx.lineTo(-13.2, -6.2); ctx.lineTo(-8.5, -4.0);
        ctx.moveTo(-11.5, 4.0); ctx.lineTo(-13.2, 6.2); ctx.lineTo(-8.5, 4.0);
        ctx.fillStyle = metalCol; ctx.fill();
        // Launch Escape Tower spire
        ctx.strokeStyle = whiteCol;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(11.8, 0); ctx.lineTo(15.8, 0);
        ctx.stroke();
      } else if (k === "csm-sivb") {
        // J-2 nozzle
        ctx.fillStyle = "#5b677a";
        ctx.beginPath();
        ctx.moveTo(-10.5, -1.6); ctx.lineTo(-13.5, -2.8); ctx.lineTo(-13.5, 2.8); ctx.lineTo(-10.5, 1.6);
        ctx.closePath(); ctx.fill();
        // S-IVB cylinder
        ctx.fillStyle = whiteCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.1;
        ctx.fillRect(-10.5, -3.6, 12.0, 7.2);
        ctx.strokeRect(-10.5, -3.6, 12.0, 7.2);
        ctx.fillStyle = strokeDark;
        ctx.fillRect(-9.5, -3.4, 2.4, 6.8);
        // SLA + CSM forward stack
        ctx.fillStyle = csmCol;
        ctx.beginPath();
        ctx.moveTo(1.5, -3.6);
        ctx.lineTo(7.5, -3.0);
        ctx.lineTo(12.0, 0);
        ctx.lineTo(7.5, 3.0);
        ctx.lineTo(1.5, 3.6);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
      } else if (k === "csm-lm") {
        // Aft SPS bell
        ctx.fillStyle = "#5b677a";
        ctx.beginPath();
        ctx.moveTo(-9.0, -1.6); ctx.lineTo(-12.5, -3.0); ctx.lineTo(-12.5, 3.0); ctx.lineTo(-9.0, 1.6);
        ctx.closePath(); ctx.fill();
        // Service Module
        ctx.fillStyle = metalCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.1;
        ctx.fillRect(-9.0, -3.5, 7.0, 7.0);
        ctx.strokeRect(-9.0, -3.5, 7.0, 7.0);
        // Command Module cone docked to LM
        ctx.fillStyle = csmCol;
        ctx.beginPath();
        ctx.moveTo(-2.0, -3.5); ctx.lineTo(2.4, -1.2); ctx.lineTo(2.4, 1.2); ctx.lineTo(-2.0, 3.5);
        ctx.closePath(); ctx.fill(); ctx.stroke();
        // LM Ascent + Descent stages docked nose-to-nose
        ctx.fillStyle = "#cfd6e3";
        ctx.fillRect(2.4, -3.2, 4.2, 6.4);
        ctx.strokeRect(2.4, -3.2, 4.2, 6.4);
        ctx.fillStyle = lmCol;
        ctx.fillRect(6.6, -4.2, 4.4, 8.4);
        ctx.strokeRect(6.6, -4.2, 4.4, 8.4);
        // Landing legs on LM
        ctx.strokeStyle = lmCol;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(8.5, -4.2); ctx.lineTo(11.8, -7.2);
        ctx.moveTo(8.5, 4.2); ctx.lineTo(11.8, 7.2);
        ctx.stroke();
      } else if (k === "lm") {
        // DPS engine bell at -x
        ctx.fillStyle = "#5b677a";
        ctx.beginPath();
        ctx.moveTo(-6.5, -1.8); ctx.lineTo(-10.0, -3.2); ctx.lineTo(-10.0, 3.2); ctx.lineTo(-6.5, 1.8);
        ctx.closePath(); ctx.fill();
        // Splayed landing legs + footpads
        ctx.strokeStyle = lmCol;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(-3.5, -5.5); ctx.lineTo(-9.2, -9.8);
        ctx.moveTo(-3.5, 5.5); ctx.lineTo(-9.2, 9.8);
        ctx.moveTo(-6.2, -4.5); ctx.lineTo(-9.2, -9.8);
        ctx.moveTo(-6.2, 4.5); ctx.lineTo(-9.2, 9.8);
        // Footpads
        ctx.moveTo(-9.6, -11.2); ctx.lineTo(-9.6, -8.4);
        ctx.moveTo(-9.6, 8.4); ctx.lineTo(-9.6, 11.2);
        ctx.stroke();
        // Gold descent stage
        ctx.fillStyle = lmCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.1;
        ctx.fillRect(-6.8, -5.6, 5.8, 11.2);
        ctx.strokeRect(-6.8, -5.6, 5.8, 11.2);
        // Faceted ascent stage cabin
        ctx.fillStyle = "#d4dce8";
        ctx.beginPath();
        ctx.moveTo(-1.0, -4.6);
        ctx.lineTo(4.2, -5.2);
        ctx.lineTo(7.2, -2.6);
        ctx.lineTo(7.2, 2.6);
        ctx.lineTo(4.2, 5.2);
        ctx.lineTo(-1.0, 4.6);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Triangular crew windows
        ctx.fillStyle = strokeDark;
        ctx.beginPath();
        ctx.moveTo(4.6, -3.4); ctx.lineTo(2.0, -1.6); ctx.lineTo(2.0, -3.6); ctx.closePath();
        ctx.moveTo(4.6, 3.4); ctx.lineTo(2.0, 1.6); ctx.lineTo(2.0, 3.6); ctx.closePath();
        ctx.fill();
      } else if (k === "lm-ascent") {
        // Recessed APS nozzle
        ctx.fillStyle = "#5b677a";
        ctx.beginPath();
        ctx.moveTo(-4.2, -1.4); ctx.lineTo(-6.8, -2.4); ctx.lineTo(-6.8, 2.4); ctx.lineTo(-4.2, 1.4);
        ctx.closePath(); ctx.fill();
        // Faceted ascent stage cabin
        ctx.fillStyle = lmCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.1;
        ctx.beginPath();
        ctx.moveTo(-4.5, -4.6);
        ctx.lineTo(2.2, -5.6);
        ctx.lineTo(6.2, -2.8);
        ctx.lineTo(6.2, 2.8);
        ctx.lineTo(2.2, 5.6);
        ctx.lineTo(-4.5, 4.6);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // RCS pods
        ctx.fillStyle = metalCol;
        ctx.fillRect(-0.5, -7.0, 2.6, 1.5);
        ctx.fillRect(-0.5, 5.5, 2.6, 1.5);
        // Crew windows
        ctx.fillStyle = strokeDark;
        ctx.beginPath();
        ctx.moveTo(3.6, -3.6); ctx.lineTo(0.8, -1.6); ctx.lineTo(0.8, -3.8); ctx.closePath();
        ctx.moveTo(3.6, 3.6); ctx.lineTo(0.8, 1.6); ctx.lineTo(0.8, 3.8); ctx.closePath();
        ctx.fill();
      } else if (k === "cm") {
        // Blunt-cone Command Module capsule
        ctx.fillStyle = csmCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(-4.5, -6.6);
        ctx.quadraticCurveTo(-6.8, 0, -4.5, 6.6);
        ctx.lineTo(5.8, 2.0);
        ctx.lineTo(5.8, -2.0);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Heat shield rim
        ctx.strokeStyle = C.amber || "#f2b13c";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(-4.5, -6.4);
        ctx.quadraticCurveTo(-6.8, 0, -4.5, 6.4);
        ctx.stroke();
        // Crew window
        ctx.fillStyle = strokeDark;
        ctx.fillRect(0.2, -2.4, 2.2, 1.6);
      } else {
        // Default: 'csm' (Columbia Command + Service Module)
        // SPS engine bell
        ctx.fillStyle = "#5b677a";
        ctx.beginPath();
        ctx.moveTo(-6.2, -1.8); ctx.lineTo(-10.8, -3.5); ctx.lineTo(-10.8, 3.5); ctx.lineTo(-6.2, 1.8);
        ctx.closePath(); ctx.fill();
        // Cylindrical Service Module
        ctx.fillStyle = metalCol;
        ctx.strokeStyle = strokeDark;
        ctx.lineWidth = 1.1;
        ctx.fillRect(-6.2, -4.0, 8.4, 8.0);
        ctx.strokeRect(-6.2, -4.0, 8.4, 8.0);
        // Conical Command Module
        ctx.fillStyle = csmCol;
        ctx.beginPath();
        ctx.moveTo(2.2, -4.0);
        ctx.lineTo(9.2, -1.2);
        ctx.lineTo(9.2, 1.2);
        ctx.lineTo(2.2, 4.0);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Docking probe
        ctx.strokeStyle = whiteCol;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(9.2, 0); ctx.lineTo(11.4, 0);
        ctx.stroke();
      }
      ctx.restore();
    }

    function ping(x, y, color) {
      if (reduceMotion) return;
      for (var i = 0; i < MAX_PINGS; i++) {
        if (!pings[i].active) {
          pings[i].active = true;
          pings[i].x = x;
          pings[i].y = y;
          pings[i].age = 0;
          pings[i].life = 0.95;
          pings[i].color = color || C.amber;
          activePings++;
          state.dirty = true;
          return;
        }
      }
    }

    function flash(color, strength) {
      if (reduceMotion) return;
      flashColor = color || C.amber;
      flashAlpha = Math.max(flashAlpha, Math.min(0.45, strength == null ? 0.16 : strength));
      state.dirty = true;
    }

    function shake(strength) {
      if (reduceMotion) return;
      shakeAmp = Math.max(shakeAmp, Math.min(14, strength == null ? 4 : strength));
      state.dirty = true;
    }

    function dust(x, y, strength, burst) {
      var str = strength == null ? 1 : Math.max(0, Math.min(2, strength));
      if (str <= 0.01) return;
      ctx.save();
      ctx.fillStyle = C.moon || "#b9bcc4";
      ctx.globalAlpha = 0.20 * Math.min(1, str);
      ctx.beginPath();
      ctx.ellipse(x, y, 24 * str, 3.8 * str, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      if (reduceMotion) return;

      var count = (state.playing || burst) ? Math.max(2, Math.round(5 * str)) : 0;
      for (var i = 0; i < count; i++) {
        var dir = (i % 2 === 0 ? 1 : -1) * (0.5 + frnd() * 0.7);
        var svx = dir * (24 + frnd() * 44) * str;
        var svy = -(3 + frnd() * 12) * str;
        var life = 0.38 + frnd() * 0.42;
        var r0 = 1.5 + frnd() * 1.5;
        var r1 = r0 * (2.4 + frnd() * 1.2);
        spawnParticle(1, x + dir * 4, y, svx, svy, life, r0, r1);
      }
      drawDustParticles();
    }

    function glowDot(x, y, r, color) {
      var rad = r || 3.5;
      var col = color || C.amber;
      var g = ctx.createRadialGradient(x, y, rad * 0.2, x, y, rad * 3.2);
      g.addColorStop(0, col);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.save();
      ctx.globalAlpha = 0.34;
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, rad * 3.2, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#ffffff";
      ctx.globalAlpha = 0.82;
      ctx.beginPath(); ctx.arc(x, y, rad * 0.42, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }

    // Offscreen cache for vignette & scanlines
    var vigCache = null, scanCache = null;
    function vignette() {
      // Flush any remaining particles, pings, and flash before drawing vignette
      drawExhaustParticles();
      drawDustParticles();

      if (!reduceMotion && activePings > 0) {
        ctx.save();
        for (var i = 0; i < MAX_PINGS; i++) {
          var pg = pings[i];
          if (!pg.active) continue;
          var u = pg.age / pg.life;
          var ease = 1 - Math.pow(1 - u, 3);
          var r1 = 5 + ease * 44;
          ctx.strokeStyle = pg.color;
          ctx.globalAlpha = (1 - u) * 0.82;
          ctx.lineWidth = 2.2 * (1 - u * 0.6);
          ctx.beginPath(); ctx.arc(pg.x, pg.y, r1, 0, Math.PI * 2); ctx.stroke();
          if (u > 0.14) {
            var u2 = (u - 0.14) / 0.86;
            var r2 = 4 + (1 - Math.pow(1 - u2, 2)) * 30;
            ctx.globalAlpha = (1 - u2) * 0.48;
            ctx.lineWidth = 1.3;
            ctx.beginPath(); ctx.arc(pg.x, pg.y, r2, 0, Math.PI * 2); ctx.stroke();
          }
        }
        ctx.restore();
      }

      if (!reduceMotion && flashAlpha > 0.004) {
        ctx.save();
        ctx.fillStyle = flashColor;
        ctx.globalAlpha = flashAlpha;
        ctx.fillRect(0, 0, W, H);
        ctx.restore();
      }

      var cw = Math.round(W), ch = Math.round(H);
      if (!vigCache || vigCache.w !== cw || vigCache.h !== ch) {
        var vc = document.createElement("canvas");
        vc.width = Math.max(1, cw); vc.height = Math.max(1, ch);
        var vg = vc.getContext("2d");
        var cx = cw * 0.5, cy = ch * 0.5;
        var maxR = Math.hypot(cx, cy);
        var rad = vg.createRadialGradient(cx, cy, maxR * 0.56, cx, cy, maxR * 1.02);
        rad.addColorStop(0, "rgba(7, 10, 16, 0)");
        rad.addColorStop(0.65, "rgba(7, 10, 16, 0.12)");
        rad.addColorStop(1, "rgba(4, 7, 12, 0.46)");
        vg.fillStyle = rad;
        vg.fillRect(0, 0, cw, ch);
        vigCache = { w: cw, h: ch, canvas: vc };
      }
      ctx.drawImage(vigCache.canvas, 0, 0, W, H);
    }

    function scanline(opts) {
      opts = opts || {};
      var cw = Math.round(W), ch = Math.round(H);
      if (!scanCache || scanCache.w !== cw || scanCache.h !== ch) {
        var sc = document.createElement("canvas");
        sc.width = Math.max(1, cw); sc.height = Math.max(1, ch);
        var sg = sc.getContext("2d");
        sg.fillStyle = "rgba(160, 195, 255, 0.025)";
        for (var y = 0; y < ch; y += 3) sg.fillRect(0, y, cw, 1);
        scanCache = { w: cw, h: ch, canvas: sc };
      }
      ctx.save();
      if (opts.alpha != null) ctx.globalAlpha = opts.alpha;
      ctx.drawImage(scanCache.canvas, 0, 0, W, H);
      ctx.restore();
    }

    function grid(opts) {
      opts = opts || {};
      var step = opts.step || 80;
      ctx.save();
      ctx.strokeStyle = opts.color || C.line;
      ctx.globalAlpha = opts.alpha == null ? 0.16 : opts.alpha;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (var x = step; x < W; x += step) {
        for (var y = step; y < H; y += step) {
          ctx.moveTo(x - 3, y); ctx.lineTo(x + 3, y);
          ctx.moveTo(x, y - 3); ctx.lineTo(x, y + 3);
        }
      }
      ctx.stroke();
      ctx.restore();
    }

    function onEvent(ev) {
      if (!ev || reduceMotion) return;
      var ex = lastMarkValid ? lastMarkX : W * 0.5;
      var ey = lastMarkValid ? lastMarkY : H * 0.5;
      var id = ev.id || "";
      if (id === "alarm-1202" || id === "alarm-1201") {
        ping(ex, ey, C.alarm);
        flash(C.alarm, 0.18);
        shake(4.5);
      } else if (id === "launch" || id === "touchdown" || id === "liftoff") {
        ping(ex, ey, C.amber);
        flash(C.amber, 0.14);
        shake(4.8);
        if (id === "touchdown" || id === "liftoff") dust(ex, ey + 6, 1.2, true);
      } else if (id === "tli" || id === "loi-1" || id === "doi" || id === "pdi" || id === "tpi" || id === "tei" || id === "entry-interface" || id === "splashdown") {
        ping(ex, ey, C.amber);
        flash(C.amber, 0.10);
        shake(2.4);
      } else {
        var col = ev.computer === "LM" ? C.lm : C.csm;
        ping(ex, ey, col);
        flash(col, 0.06);
      }
    }

    var api = {
      tick: tick,
      reset: reset,
      isActive: isActive,
      trail: trail,
      exhaust: exhaust,
      craft: craft,
      ping: ping,
      flash: flash,
      shake: shake,
      dust: dust,
      glowDot: glowDot,
      vignette: vignette,
      scanline: scanline,
      scanlines: scanline,
      grid: grid,
      onEvent: onEvent,
      shakeX: 0,
      shakeY: 0,
      _mark: function (x, y) {
        lastMarkX = x;
        lastMarkY = y;
        lastMarkValid = true;
      }
    };
    return api;
  })();
