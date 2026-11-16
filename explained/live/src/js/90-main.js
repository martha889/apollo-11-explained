  // ---------- frame ----------
  var last = performance.now(), lastSecond = -1, lastPhase = -1, lastScene = null, autoDsky = null;
  var lastPlay = -10, fadeTimer = 0, FADE_DUR = 0.45, drawnFrames = 0;
  var snapCanvas = document.createElement("canvas"), snapCtx = snapCanvas.getContext("2d");

  function sampleCanvasInk() {
    var sw = 64, sh = 40;
    var ic = document.createElement("canvas");
    ic.width = sw; ic.height = sh;
    var ix = ic.getContext("2d");
    ix.fillStyle = C.panel || "#131a26";
    ix.fillRect(0, 0, sw, sh);
    var bg = ix.getImageData(0, 0, 1, 1).data;
    var br = bg[0], bgG = bg[1], bb = bg[2];
    ix.drawImage(canvas, 0, 0, sw, sh);
    var d = ix.getImageData(0, 0, sw, sh).data;
    var ink = 0;
    for (var i = 0; i < d.length; i += 4) {
      if (Math.abs(d[i] - br) + Math.abs(d[i + 1] - bgG) + Math.abs(d[i + 2] - bb) > 24) ink++;
    }
    return ink;
  }

  function frame(now) {
    var dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (lastPlay >= 0 && Math.abs(state.play - lastPlay) > 1.5) {
      if (typeof FX !== "undefined" && FX.reset) FX.reset();
    }
    if (state.playing) {
      if (!voiceHolding()) state.play += dt * state.speed; // the clock waits while someone is speaking
      if (state.play >= TOTAL) { state.play = TOTAL; setPlaying(false); }
      state.dirty = true;
    }
    lastPlay = state.play;
    var g = playToGet(state.play);
    var pi = phaseAt(g), ph = D.phases[pi];
    // events crossed while playing
    var ev = lastEvent(g);
    if (ev && ev !== state.lastEvent) {
      showToast(ev);
      if (!state.playing) hideToast();
      else if (typeof FX !== "undefined" && FX.onEvent) FX.onEvent(ev);
      state.lastEvent = ev;
    }
    if (Math.floor(g) !== lastSecond || pi !== lastPhase) {
      lastSecond = Math.floor(g);
      $("get").textContent = fmtGET(g);
      $("utc").textContent = fmtUTC(g);
      $("ptime").textContent = fmtPlay(state.play) + " / " + fmtPlay(TOTAL);
    }
    if (pi !== lastPhase) {
      lastPhase = pi;
      $("phase").textContent = ph.name;
      $("phase-step").textContent = "Phase " + (pi + 1) + " of " + D.phases.length;
      Array.prototype.forEach.call(bands.children, function (b, i) { b.classList.toggle("cur", i === pi); });
    }
    $("event").innerHTML = ev ? "<b>" + esc(ev.short) + "</b> " + fmtGET(ev.get) + " · " + esc(ev.label) : "";
    voiceTick(g);
    updateVoice(g, state.play);
    var codeComp = D.code.filter(function (c) { return g >= c.get_start && g < c.get_end; })[0];
    var active = codeComp ? codeComp.computer : ph.active_computer;
    if (active !== autoDsky) { autoDsky = active; if (window.innerWidth <= 700) showDsky(active); }
    var blinkOn = Math.floor(now / 380) % 2 === 0;
    updateDsky("CM", g, active, blinkOn);
    updateDsky("LM", g, active, blinkOn);
    updateCode(g, state.play);
    var pct = state.play / TOTAL * 100;
    $("progress").style.left = "calc(" + pct + "% - 1px)";
    if (document.activeElement !== scrub) scrub.value = state.play;

    var fxAlive = (typeof FX !== "undefined" && FX.tick) ? FX.tick(dt, state.playing) : false;
    if (fadeTimer > 0) {
      fadeTimer = reduceMotion ? 0 : Math.max(0, fadeTimer - dt);
    }

    if (state.dirty || state.playing || fxAlive || fadeTimer > 0 || viewMoving || drawnFrames < 3) {
      applyResize();
      if (ph.scene !== lastScene) {
        if (lastScene !== null && !reduceMotion && !canvasResized && canvas.width > 0 && canvas.height > 0) {
          if (snapCanvas.width !== canvas.width || snapCanvas.height !== canvas.height) {
            snapCanvas.width = canvas.width;
            snapCanvas.height = canvas.height;
          }
          snapCtx.clearRect(0, 0, snapCanvas.width, snapCanvas.height);
          snapCtx.drawImage(canvas, 0, 0);
          fadeTimer = FADE_DUR;
        }
        lastScene = ph.scene;
        $("scene-title").textContent = SCENE_TITLE[ph.scene];
        $("scene-frame").textContent = SCENE_FRAME[ph.scene];
      }
      canvasResized = false;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = C.panel; ctx.fillRect(0, 0, W, H);
      ctx.save();
      if (typeof FX !== "undefined" && (FX.shakeX || FX.shakeY)) ctx.translate(FX.shakeX, FX.shakeY);
      try { SCENES[ph.scene](g, dt); } catch (err) { document.documentElement.setAttribute("data-draw-error", ph.scene + ": " + err.message); text("Drawing error: " + err.message, 14, 20, { color: C.alarm }); if (window.console) console.error(err); }
      ctx.restore();
      if (fadeTimer > 0 && !reduceMotion) {
        var fa = fadeTimer / FADE_DUR;
        ctx.save();
        ctx.globalAlpha = fa * fa * (3 - 2 * fa);
        ctx.drawImage(snapCanvas, 0, 0, W, H);
        ctx.restore();
      }
      if (typeof FX !== "undefined" && FX.vignette) FX.vignette();
      state.dirty = false;
      drawnFrames++;
      document.documentElement.setAttribute("data-frames", String(drawnFrames));
      if (drawnFrames < 3) {
        state.dirty = true;
        setTimeout(function () { if (drawnFrames < 3) { state.dirty = true; frame(performance.now()); } }, 20);
      }
      if (drawnFrames === 3) {
        document.documentElement.setAttribute("data-canvas-ink", String(sampleCanvasInk()));
        document.documentElement.setAttribute("data-ready", "1");
      }
    }
    requestAnimationFrame(frame);
  }
  var hashed = fromHash();
  if (!hashed) { state.play = 0; state.lastEvent = EV.launch; showToast(EV.launch); }
  setSound(voice.on);
  setPlaying(!hashed && !reduceMotion);
  if (window.innerWidth <= 700) showDsky("CM");
  requestAnimationFrame(frame);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { state.dirty = true; });
})();
