  // ---------- transport UI ----------
  var bands = $("bands"), ticks = $("ticks");
  var bandPlay = [], tickEls = [], labelEls = [];
  D.phases.forEach(function (p, i) {
    var a = getToPlay(p.get_start), b = getToPlay(p.get_end);
    var d = document.createElement("div");
    d.className = p.active_computer === "LM" ? "lm" : "cm";
    d.style.width = ((b - a) / TOTAL * 100) + "%";
    d.title = p.name;
    bands.appendChild(d);
    bandPlay.push(a);
  });
  var MAJOR = { launch: 1, tli: 1, "loi-1": 1, pdi: 1, touchdown: 1, liftoff: 1, docking: 1, tei: 1, splashdown: 1 };
  EVENTS.forEach(function (e) {
    var x = getToPlay(e.get) / TOTAL * 100;
    var t = document.createElement("i"); t.style.left = x + "%"; if (MAJOR[e.id]) t.className = "major"; ticks.appendChild(t);
    tickEls.push({ el: t, p: x / 100 * TOTAL, id: e.id, on: false, lab: null, x: x });
    if (MAJOR[e.id]) { var s = document.createElement("span"); s.textContent = e.short; s.style.left = Math.min(97, Math.max(2, x)) + "%"; ticks.appendChild(s); tickEls[tickEls.length - 1].lab = s; labelEls.push({ el: s, id: e.id }); }
  });
  var jump = $("jump");
  jump.innerHTML = '<option value="">Jump to event…</option>' + EVENTS.map(function (e) { return '<option value="' + e.id + '">' + fmtGET(e.get) + "  " + esc(e.label) + "</option>"; }).join("");
  jump.addEventListener("change", function () { if (jump.value) { seekEvent(jump.value, true); jump.value = ""; } });
  var scrub = $("scrub");
  scrub.max = TOTAL;
  scrub.addEventListener("input", function () { state.play = parseFloat(scrub.value); view = null; state.dirty = true; voiceSeeked(); });

  function setPlaying(p) {
    state.playing = p && state.play < TOTAL;
    if (!state.playing && voice.el && !voice.manual) { try { voice.el.pause(); } catch (e) {} } // resumes with Play
    $("play-text").textContent = state.playing ? "Pause" : "Play";
    $("play").setAttribute("aria-label", state.playing ? "Pause" : "Play");
    $("play").classList.toggle("is-playing", state.playing);
    $("rec").classList.toggle("live", state.playing);
  }
  $("play").addEventListener("click", function () { if (state.play >= TOTAL) state.play = 0; setPlaying(!state.playing); });
  function seekEvent(id, keepPlaying) {
    var e = EV[id]; if (!e) return;
    state.play = Math.min(TOTAL, getToPlay(e.get) + 0.002);
    view = null;
    voiceSeeked();
    state.lastEvent = e; state.dirty = true;
    showToast(e);
    if (!keepPlaying) setPlaying(false);
  }
  function stepEvent(dir) {
    var g = playToGet(state.play), list = EVENTS;
    var target = null;
    if (dir > 0) { for (var i = 0; i < list.length; i++) if (list[i].get > g + 1) { target = list[i]; break; } }
    else { for (i = list.length - 1; i >= 0; i--) if (list[i].get < g - 1) { target = list[i]; break; } }
    if (target) seekEvent(target.id, state.playing);
  }
  $("prev").addEventListener("click", function () { stepEvent(-1); });
  $("next").addEventListener("click", function () { stepEvent(1); });
  Array.prototype.forEach.call(document.querySelectorAll(".speed button"), function (b) {
    b.addEventListener("click", function () {
      state.speed = parseFloat(b.getAttribute("data-s"));
      Array.prototype.forEach.call(document.querySelectorAll(".speed button"), function (o) { o.setAttribute("aria-pressed", o === b); });
    });
  });
  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "SELECT" || tag === "BUTTON" && (e.key === " " || e.key === "Enter")) return;
    if (e.key === " " && tag !== "INPUT") { e.preventDefault(); if (state.play >= TOTAL) state.play = 0; setPlaying(!state.playing); }
    else if (e.key === "ArrowRight" && tag !== "INPUT") { e.preventDefault(); stepEvent(1); }
    else if (e.key === "ArrowLeft" && tag !== "INPUT") { e.preventDefault(); stepEvent(-1); }
  });
  function showDsky(c) {
    $("dskys").setAttribute("data-show", c);
    $("show-cm").setAttribute("aria-selected", c === "CM"); $("show-lm").setAttribute("aria-selected", c === "LM");
    state.userDsky = c;
  }
  $("show-cm").addEventListener("click", function () { showDsky("CM"); });
  $("show-lm").addEventListener("click", function () { showDsky("LM"); });

  var toastTimer = null;
  function showToast(e) {
    var t = $("toast");
    t.innerHTML = "<b>" + esc(e.short) + '</b><span class="t">' + fmtGET(e.get) + "</span><span>" + esc(e.detail) + "</span>";
    t.title = e.detail;
    t.classList.add("new");
    restartAnim(t, "enter");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 3500);
  }
  function hideToast() { $("toast").classList.remove("new"); }

  function fromHash() {
    var h = (location.hash || "").slice(1);
    if (!h) return false;
    if (EV[h]) { seekEvent(h, false); return true; }
    var mT = /^t=([0-9]+(?:\.[0-9]+)?)$/i.exec(h);
    if (mT) {
      var p = Math.max(0, Math.min(TOTAL, parseFloat(mT[1])));
      state.play = p;
      view = null;
      voiceSeeked();
      state.lastEvent = lastEvent(playToGet(p));
      state.dirty = true;
      setPlaying(false);
      return true;
    }
    var mG = /^get=(\d{1,3}):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/i.exec(h);
    if (mG) {
      var g = parseInt(mG[1], 10) * 3600 + parseInt(mG[2], 10) * 60 + parseFloat(mG[3]);
      g = Math.max(0, Math.min(GET_END, g));
      state.play = Math.max(0, Math.min(TOTAL, getToPlay(g)));
      view = null;
      voiceSeeked();
      state.lastEvent = lastEvent(g);
      state.dirty = true;
      setPlaying(false);
      return true;
    }
    return false;
  }
  window.addEventListener("hashchange", fromHash);


  // ---------- polish: progress, ticks, phase swap, tooltip, shortcuts, theatre ----------
  var transport = document.querySelector(".transport"), appEl = document.querySelector(".app");
  var barH = -1;
  function syncBar() {
    var h = Math.ceil(transport.getBoundingClientRect().height);
    if (h > 0 && h !== barH) { barH = h; document.documentElement.style.setProperty("--bar-h", h + "px"); }
  }
  if (window.ResizeObserver) new ResizeObserver(syncBar).observe(transport);
  window.addEventListener("resize", syncBar);
  syncBar();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(syncBar);
  setTimeout(function () { document.body.classList.add("booted"); }, 620);

  var uiQ = -1, uiPlayQ = -1, uiPhase = -1, mbarEl = $("mbar"), playedEl = $("played"), mpctEl = $("mpct");
  function uiTick() {
    var play = state.play, g = playToGet(play);
    var q = Math.round(Math.max(0, Math.min(1, g / GET_END)) * 2000);
    if (q !== uiQ) {
      uiQ = q;
      mpctEl.textContent = (q / 20).toFixed(1) + "%";
      mbarEl.style.transform = "scaleX(" + (q / 2000) + ")";
    }
    var pq = Math.round(Math.max(0, Math.min(1, play / TOTAL)) * 2000);
    if (pq !== uiPlayQ) {
      uiPlayQ = pq;
      playedEl.style.transform = "scaleX(" + (pq / 2000) + ")";
    }
    for (var i = 0; i < tickEls.length; i++) {
      var t = tickEls[i], on = t.p <= play + 0.01;
      if (on !== t.on) { t.on = on; t.el.classList.toggle("passed", on); if (t.lab) t.lab.classList.toggle("passed", on); }
    }
    var pi = phaseAt(g);
    if (pi !== uiPhase) {
      if (uiPhase >= 0) { restartAnim($("phase"), "swap"); restartAnim($("phase-step"), "swap"); }
      uiPhase = pi;
    }
    requestAnimationFrame(uiTick);
  }
  requestAnimationFrame(uiTick);

  // scrubber hover tooltip, phase-band hover, click-to-seek on bands / ticks / labels
  var scrubWrap = scrub.parentNode, tip = $("scrub-tip"), tipB = tip.querySelector("b"), tipS = tip.querySelector("span");
  var tipPending = null, tipRaf = 0, hoverBand = -1, down = null;
  function bandIndexAt(play) { var r = 0; for (var i = 0; i < bandPlay.length; i++) if (bandPlay[i] <= play + 1e-6) r = i; return r; }
  function nearestTick(px, width, ry) {
    if (ry < 6 || ry > 30) return null;
    var best = null, bd = 6;
    for (var i = 0; i < tickEls.length; i++) { var d = Math.abs(tickEls[i].x / 100 * width - px); if (d <= bd) { bd = d; best = tickEls[i]; } }
    return best;
  }
  function flushTip() {
    tipRaf = 0;
    var m = tipPending; if (!m) return;
    var r = scrubWrap.getBoundingClientRect(), w = r.width || 1;
    var px = Math.max(0, Math.min(w, m.x - r.left)), ry = m.y - r.top, f = px / w, p = f * TOTAL, g = playToGet(p);
    var bi = bandIndexAt(p), tk = nearestTick(px, w, ry), ev = tk ? EV[tk.id] : lastEvent(g);
    var inBand = ry >= 12 && ry <= 26;
    tipB.textContent = "GET " + fmtGET(g);
    tipS.textContent = (tk ? "▸ " + ev.short + " · " : "") + "Phase " + (bi + 1) + " · " + D.phases[bi].name + (!tk && ev ? " · " + ev.short : "") + (tk ? "  (click to jump)" : inBand ? "  (click: phase start)" : "");
    var half = tip.offsetWidth / 2;
    tip.style.left = Math.max(half, Math.min(w - half, px)) + "px";
    tip.classList.add("show");
    if (bi !== hoverBand) {
      if (hoverBand >= 0 && bands.children[hoverBand]) bands.children[hoverBand].classList.remove("hover");
      hoverBand = bi; if (bands.children[bi]) bands.children[bi].classList.add("hover");
    }
  }
  function moveTip(e) { tipPending = { x: e.clientX, y: e.clientY }; if (!tipRaf) tipRaf = requestAnimationFrame(flushTip); }
  function hideTip() {
    tipPending = null; tip.classList.remove("show");
    if (hoverBand >= 0 && bands.children[hoverBand]) bands.children[hoverBand].classList.remove("hover");
    hoverBand = -1;
  }
  scrub.addEventListener("pointermove", moveTip);
  scrub.addEventListener("pointerenter", moveTip);
  scrub.addEventListener("pointerleave", hideTip);
  scrub.addEventListener("pointercancel", hideTip);
  scrub.addEventListener("pointerdown", function (e) { down = { x: e.clientX, y: e.clientY }; moveTip(e); });
  scrub.addEventListener("pointerup", function (e) { if (e.pointerType && e.pointerType !== "mouse") setTimeout(hideTip, 600); });
  scrub.addEventListener("click", function (e) {
    var moved = down ? Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y) : 99;
    down = null;
    if (moved > 4) { scrub.blur(); return; }
    var r = scrubWrap.getBoundingClientRect(), px = e.clientX - r.left, ry = e.clientY - r.top, keep = state.playing, done = false;
    var i, lr;
    for (i = 0; i < labelEls.length && !done; i++) {
      lr = labelEls[i].el.getBoundingClientRect();
      if (lr.width && e.clientX >= lr.left - 2 && e.clientX <= lr.right + 2 && e.clientY >= lr.top - 2 && e.clientY <= lr.bottom + 2) { seekEvent(labelEls[i].id, keep); done = true; }
    }
    if (!done) { var tk = nearestTick(px, r.width, ry); if (tk) { seekEvent(tk.id, keep); done = true; } }
    if (!done && ry >= 12 && ry <= 26) {
      var bi = bandIndexAt(px / r.width * TOTAL);
      state.play = Math.min(TOTAL, bandPlay[bi] + 0.002); view = null; voiceSeeked(); state.dirty = true; done = true;
    }
    if (done) scrub.value = state.play;
    scrub.blur(); // so Space / arrow keys keep working after a mouse click
  });

  // shortcuts popover + theatre mode
  var pop = $("shortcuts"), helpBtn = $("help"), theatreBtn = $("theatre");
  function setHelp(on) { pop.classList.toggle("open", on); helpBtn.setAttribute("aria-expanded", on); }
  function setTheatre(on) {
    appEl.classList.toggle("theatre", on);
    theatreBtn.setAttribute("aria-pressed", on);
    state.dirty = true;
    if (window.dispatchEvent) setTimeout(function () { state.dirty = true; syncBar(); }, 60);
  }
  helpBtn.addEventListener("click", function (e) { e.stopPropagation(); setHelp(!pop.classList.contains("open")); });
  theatreBtn.addEventListener("click", function () { setTheatre(!appEl.classList.contains("theatre")); });
  document.addEventListener("click", function (e) { if (pop.classList.contains("open") && !pop.contains(e.target) && e.target !== helpBtn) setHelp(false); });
  (function () { // document the DSKY keys in the popover
    var dl = pop.querySelector("dl");
    if (!dl) return;
    dl.insertAdjacentHTML("beforeend",
      '<dt><kbd>Keys</kbd></dt><dd>Pause, then click a DSKY key (or press one) for crew mode</dd>' +
      '<dt><kbd>0</kbd>–<kbd>9</kbd> <kbd>V</kbd> <kbd>N</kbd></dt><dd>In crew mode: digits, Verb, Noun</dd>' +
      '<dt><kbd>+</kbd> <kbd>−</kbd> <kbd>C</kbd> <kbd>P</kbd></dt><dd>In crew mode: plus, minus, Clear, Proceed</dd>' +
      '<dt><kbd>Enter</kbd> <kbd>R</kbd> <kbd>K</kbd></dt><dd>In crew mode: Enter, Reset, Key Rel (back to the timeline)</dd>' +
      '<dt></dt><dd>In crew mode 1–4, F, M and ? are DSKY keys; only Space and Esc stay global</dd>');
  })();
  var SPEED_KEY = { "1": "speed-0-5", "2": "speed-1", "3": "speed-2", "4": "speed-4" };
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var tag = (e.target && e.target.tagName) || "";
    if (e.key === "Escape") {
      if (pop.classList.contains("open")) setHelp(false);
      else if (appEl.classList.contains("theatre")) setTheatre(false);
      return;
    }
    if (dskyKeyEvent(e)) return; // DSKY keys take priority while a DSKY is in crew mode or its keypad has focus
    if (tag === "SELECT" || tag === "TEXTAREA" || (tag === "INPUT" && e.target !== scrub)) return;
    if (SPEED_KEY[e.key]) { $(SPEED_KEY[e.key]).click(); }
    else if (e.key === "m" || e.key === "M") { e.preventDefault(); setSound(!voice.on); }
    else if (e.key === "f" || e.key === "F") { e.preventDefault(); setTheatre(!appEl.classList.contains("theatre")); }
    else if (e.key === "?") { e.preventDefault(); setHelp(!pop.classList.contains("open")); }
  });
