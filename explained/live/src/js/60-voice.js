  // ---------- real voices (NASA recordings, see audio/clips.json) ----------
  // Every line the playing clock passes is queued and played in order; the
  // mission clock holds until the queue is empty, so no recording is skipped,
  // however fast the clock runs or however many lines one frame crosses.
  var voice = { on: true, queue: [], el: null, line: null, blocked: false, lastG: null, manual: false };
  try { if (localStorage.getItem("a11-sound") === "off") voice.on = false; } catch (e) {}
  function voiceHolding() { return voice.on && (voice.el !== null || voice.queue.length > 0); }
  function stopVoice() {
    if (voice.el) { try { voice.el.pause(); } catch (e) {} }
    try { player.currentTime = 0; } catch (e) {}
    if (typeof guard !== "undefined") clearTimeout(guard);
    voice.el = null; voice.line = null; voice.queue = []; voice.manual = false; voiceKey = null;
  }
  // After a seek or jump, lines from 2 s before the new position count as "not yet heard",
  // so jumping to an event that starts with a line (e.g. Contact Light at touchdown) plays it.
  function voiceSeeked() { stopVoice(); voice.lastG = playToGet(state.play) - 2; }
  // One shared audio element: browsers (Safari especially) only let a page play
  // sound on an element that was first started from a click or key press, so it
  // is unlocked on the first interaction and reused for every clip.
  var player = new Audio();
  player.preload = "auto";
  var SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
  var unlocked = false;
  function unlockAudio() {
    if (unlocked) return;
    unlocked = true;
    if (voice.el) return;
    try {
      player.src = SILENT;
      var pr = player.play();
      if (pr && pr.catch) pr.catch(function (err) {
        if (err && err.name !== "AbortError") unlocked = false;
      });
    } catch (e) {
      unlocked = false;
    }
  }
  document.addEventListener("pointerdown", unlockAudio, true);
  document.addEventListener("keydown", unlockAudio, true);
  var guard = null;
  function armGuard() {
    clearTimeout(guard);
    if (!voice.line) return;
    var left = (voice.line.dur || 10) - (player.currentTime || 0);
    guard = setTimeout(clipDone, (Math.max(0, left) + 5) * 1000); // in case the end is never reported
  }
  function clipDone() {
    clearTimeout(guard);
    if (!voice.el) return;
    voice.el = null; voice.line = null; voice.manual = false; voiceKey = null;
    nextClip();
  }
  player.addEventListener("ended", function () { if (voice.el) clipDone(); });
  player.addEventListener("error", function () { if (voice.el && player.src.indexOf("data:") !== 0) clipDone(); });
  player.addEventListener("playing", armGuard);
  player.addEventListener("pause", function () { clearTimeout(guard); });
  function startClip(l, manual) {
    voice.el = player; voice.line = l; voice.manual = !!manual; voiceKey = null;
    document.documentElement.dataset.voiceLast = l.audio;
    player.src = l.audio;
    var pr = player.play();
    if (pr && pr.then) {
      pr.then(function () {
        if (voice.line !== l) {
          // stopped while starting: silence it, unless another clip now owns the player
          if (!voice.el) { try { player.pause(); player.currentTime = 0; } catch (e) {} }
          return;
        }
        voice.blocked = false; voiceKey = null;
      }, function (err) {
        if (voice.line !== l) return;
        clearTimeout(guard);
        voice.el = null; voice.line = null; voiceKey = null;
        if (err && err.name === "NotAllowedError") {
          // The browser wants a click before it plays sound: keep the line queued
          // and pause the mission so nothing is missed.
          voice.queue.unshift(l);
          voice.blocked = true;
          unlocked = false;
          setPlaying(false);
        } else if (err && err.name === "AbortError") {
          // superseded by another clip or a seek: nothing to do
        } else {
          nextClip();
        }
      });
    }
  }
  function nextClip() {
    if (voice.el || !voice.queue.length || !voice.on) return;
    if (!state.playing && !voice.manual) return; // resumes when Play is pressed
    startClip(voice.queue.shift(), false);
  }
  // Called every frame.
  function voiceTick(g) {
    // Only advance the "heard up to here" mark while playing, so a jump made while
    // paused still plays the lines at the new position once Play is pressed.
    if (!state.playing) { if (voice.lastG === null) voice.lastG = g; return; }
    var prev = voice.lastG;
    voice.lastG = g;
    if (!voice.on) return;
    if (state.playing && voice.el && voice.el.paused && !voice.blocked) {
      var pr = voice.el.play();
      if (pr && pr.catch) {
        pr.catch(function (err) {
          if (err && err.name === "NotAllowedError") {
            voice.blocked = true;
            unlocked = false;
            setPlaying(false);
            voiceKey = null;
          }
        });
      }
    }
    if (state.playing && prev !== null && g > prev) {
      for (var j = bsearch(TRG, prev) + 1; j < TRG.length && TRG[j] <= g; j++) {
        if (TR.lines[j].audio && voice.queue.indexOf(TR.lines[j]) < 0 && voice.line !== TR.lines[j]) voice.queue.push(TR.lines[j]);
      }
    }
    if (state.playing) { voice.blocked = false; nextClip(); }
  }
  function setSound(on) {
    voice.on = on;
    if (!on) stopVoice();
    voice.blocked = false; voiceKey = null;
    $("sound").setAttribute("aria-pressed", on);
    $("sound").setAttribute("aria-label", on ? "Turn sound off" : "Turn sound on");
    $("sound-text").textContent = on ? "Sound on" : "Sound off";
    $("sound-icon").style.opacity = on ? 1 : 0.45;
    try { localStorage.setItem("a11-sound", on ? "on" : "off"); } catch (e) {}
  }
  $("sound").addEventListener("click", function () { setSound(!voice.on); });
  $("voice").addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".vplay");
    if (!b) return;
    var l = TR.lines[parseInt(b.getAttribute("data-i"), 10)];
    if (voice.line === l) { stopVoice(); return; }
    stopVoice();
    voice.blocked = false;
    startClip(l, true);
  });

  // ---------- voice loop (verbatim transcript lines) ----------
  var TR = D.transcript, TRG = TR.lines.map(function (l) { return l.get; }), voiceKey = null;
  function updateVoice(g, p) {
    var i = bsearch(TRG, g), shown = [];
    // up to three recent lines, each kept for 25 s of playback (and at most 15 min of mission time) after it was said
    for (var j = i; j >= 0 && shown.length < 3; j--) { if (p - getToPlay(TRG[j]) <= 25 && g - TRG[j] <= 900) shown.unshift(TR.lines[j]); else break; }
    var key = (voice.blocked ? "B:" : "") + (voice.line ? voice.line.get : "") + ":" + shown.map(function (l) { return l.get; }).join(",");
    if (key === voiceKey) return;
    voiceKey = key;
    var V = $("voice");
    if (!shown.length) {
      V.innerHTML = '<div class="empty">Voice loop: the crew\'s and Mission Control\'s words appear here at the moment they were spoken, from the NASA transcripts (<a href="' + TR.sources["alsj-landing"] + '" target="_blank" rel="noopener">Apollo Lunar Surface Journal</a> and Apollo Flight Journal).</div>';
      return;
    }
    V.innerHTML = shown.map(function (l, k) {
      var cls = k === shown.length - 1 ? "now" : k === 0 && shown.length === 3 ? "old" : "";
      var role = /CAPCOM|Hornet|Swim/.test(l.who) ? "capcom" : "crew";
      var src = cls === "now" ? ' <a class="src" href="' + TR.sources[l.src] + '" target="_blank" rel="noopener">source</a>' : "";
      var isSpk = voice.line === l;
      var btn = l.audio ? '<button class="vplay" type="button" data-i="' + TR.lines.indexOf(l) + '" aria-label="' + (isSpk ? "Stop this recording" : "Play this recording") + '" title="' + (isSpk ? "Stop the recording" : "Play the recording") + '">' + (isSpk ? "&#9632;" : "&#9654;") + '</button>' : "";
      var sp = isSpk ? " speaking" : "";
      return '<div class="vl ' + cls + sp + '"><span class="vt">' + fmtGET(l.get) + '</span><span class="vw ' + role + '">' + esc(l.who) + '</span><span class="vx">' + btn + esc(l.text) + (l.kind === "onboard" ? '<span class="ob">onboard recorder</span>' : "") + src + "</span></div>";
    }).join("") + (voice.blocked ? '<div class="hint">Your browser held back the sound. Press Play to continue with the real voices.</div>' : "");
  }
