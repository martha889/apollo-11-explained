  // ---------- DSKY ----------
  var SEGS = { a: [2.4, 0.6, 7.2, 1.7], b: [9.7, 2.3, 1.7, 7.2], c: [9.7, 10.5, 1.7, 7.2], d: [2.4, 17.7, 7.2, 1.7], e: [0.6, 10.5, 1.7, 7.2], f: [0.6, 2.3, 1.7, 7.2], g: [2.4, 9.15, 7.2, 1.7] };
  var DIG = { "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg" };
  function digitSVG(kind) {
    var s = '<svg viewBox="0 0 12 20" aria-hidden="true">';
    if (kind === "sign") {
      s += '<rect class="seg" data-s="h" x="1.4" y="9.15" width="9.2" height="1.7" rx="0.8"/>';
      s += '<rect class="seg" data-s="v" x="5.15" y="4.6" width="1.7" height="10.8" rx="0.8"/>';
    } else {
      for (var k in SEGS) { var r = SEGS[k]; s += '<rect class="seg" data-s="' + k + '" x="' + r[0] + '" y="' + r[1] + '" width="' + r[2] + '" height="' + r[3] + '" rx="0.8"/>'; }
    }
    return s + "</svg>";
  }
  function setDigit(svg, ch) {
    var lit = DIG[ch] || "";
    var segs = svg.querySelectorAll(".seg");
    for (var i = 0; i < segs.length; i++) segs[i].classList.toggle("on", lit.indexOf(segs[i].getAttribute("data-s")) >= 0);
  }
  function setSign(svg, ch) {
    var segs = svg.querySelectorAll(".seg");
    segs[0].classList.toggle("on", ch === "+" || ch === "-");
    segs[1].classList.toggle("on", ch === "+");
  }
  var LAMPS = {
    CM: [["UPLINK ACTY", "white"], ["TEMP", "amber"], ["NO ATT", "white"], ["GIMBAL LOCK", "amber"], ["STBY", "white"], ["PROG", "amber"], ["KEY REL", "white"], ["RESTART", "amber"], ["OPR ERR", "white"], ["TRACKER", "amber"], ["", "white"], ["", "amber"], ["", "white"], ["", "amber"]],
    LM: [["UPLINK ACTY", "white"], ["TEMP", "amber"], ["NO ATT", "white"], ["GIMBAL LOCK", "amber"], ["STBY", "white"], ["PROG", "amber"], ["KEY REL", "white"], ["RESTART", "amber"], ["OPR ERR", "white"], ["TRACKER", "amber"], ["", "white"], ["ALT", "amber"], ["", "white"], ["VEL", "amber"]]
  };
  var DS = {};
  // restart a CSS animation class (only called on rare events, so the forced reflow is fine)
  var animTimers = new WeakMap();
  function restartAnim(el, cls, dur) {
    if (!el || reduceMotion) return;
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
    var prev = animTimers.get(el);
    if (prev) clearTimeout(prev);
    animTimers.set(el, setTimeout(function () { el.classList.remove(cls); }, dur || 560));
  }
  var alarmTimers = {}, blankTimers = {}, flickTimers = {};
  function triggerAlarm(c) {
    var card = $("card-" + c), lamp = DS[c].lamps.filter(function (l) { return l.getAttribute("data-l") === "PROG"; })[0];
    card.classList.remove("alarm-pulse"); if (lamp) lamp.classList.remove("flashing");
    void card.offsetWidth;
    card.classList.add("alarm-pulse"); if (lamp) lamp.classList.add("flashing");
    clearTimeout(alarmTimers[c]);
    alarmTimers[c] = setTimeout(function () { card.classList.remove("alarm-pulse"); if (lamp) lamp.classList.remove("flashing"); }, 3200);
  }
  function blankBeat(c) { // the real DSKY blanked its digits for an instant, then repainted
    if (reduceMotion) return;
    var r = DS[c].root;
    r.classList.add("blanking");
    clearTimeout(blankTimers[c]);
    blankTimers[c] = setTimeout(function () { r.classList.remove("blanking"); }, 70);
  }
  function flicker(c, up) {
    if (reduceMotion) return;
    var r = DS[c].root;
    r.classList.remove("flick-on", "flick-off");
    void r.offsetWidth;
    r.classList.add(up ? "flick-on" : "flick-off");
    clearTimeout(flickTimers[c]);
    flickTimers[c] = setTimeout(function () { r.classList.remove("flick-on", "flick-off"); }, 440);
  }
  function buildDsky(c) {
    var root = $("dsky-" + c);
    var h = '<div class="lamps">';
    LAMPS[c].forEach(function (l) { h += '<div class="lamp ' + l[1] + (l[0] ? "" : " blank") + '" data-l="' + l[0] + '">' + (l[0] ? l[0].replace(" ", "<br>") : "&nbsp;") + "</div>"; });
    h += '</div><div class="el">';
    h += '<div class="compacty" data-x="ca">COMP<br>ACTY</div>';
    h += '<div class="cell"><span class="tag">PROG</span><div class="digits" data-x="prog">' + digitSVG() + digitSVG() + "</div></div>";
    h += '<div class="cell"><span class="tag">VERB</span><div class="digits" data-x="verb">' + digitSVG() + digitSVG() + "</div></div>";
    h += '<div class="cell"><span class="tag">NOUN</span><div class="digits" data-x="noun">' + digitSVG() + digitSVG() + "</div></div>";
    for (var r = 0; r < 3; r++) {
      h += '<div class="reg"><div class="bar"></div><div class="digits" data-x="r' + r + '">' + digitSVG("sign") + digitSVG() + digitSVG() + digitSVG() + digitSVG() + digitSVG() + "</div></div>";
    }
    h += "</div>";
    root.innerHTML = h;
    var q = function (x) { return root.querySelector('[data-x="' + x + '"]'); };
    DS[c] = {
      root: root, ca: q("ca"), prog: q("prog"), verb: q("verb"), noun: q("noun"), r: [q("r0"), q("r1"), q("r2")],
      lamps: Array.prototype.slice.call(root.querySelectorAll(".lamp")), key: null, frames: [], gets: [], on: undefined, pvn: undefined, progOn: false, alarm: null, hide: false, busy: false, act: null, badge: "",
      crewMode: false, model: null, crewSig: "", crewCap: false, keysOpen: false
    };
    buildKeyboard(c);
  }

  // ---------- interactive keypad ("crew mode"): key verbs and nouns as the crew did ----------
  var KEYPAD_DEFS = {
    sideLeft: [
      { k: "VERB", id: "VERB", label: "Verb", text: "VERB" },
      { k: "NOUN", id: "NOUN", label: "Noun", text: "NOUN" }
    ],
    grid: [
      { k: "+", id: "plus", label: "Plus", text: "+" },
      { k: "7", id: "7", label: "7", text: "7" },
      { k: "8", id: "8", label: "8", text: "8" },
      { k: "9", id: "9", label: "9", text: "9" },
      { k: "CLR", id: "CLR", label: "Clear", text: "CLR" },

      { k: "-", id: "minus", label: "Minus", text: "&minus;" },
      { k: "4", id: "4", label: "4", text: "4" },
      { k: "5", id: "5", label: "5", text: "5" },
      { k: "6", id: "6", label: "6", text: "6" },
      { k: "PRO", id: "PRO", label: "Proceed", text: "PRO" },

      { k: "0", id: "0", label: "0", text: "0" },
      { k: "1", id: "1", label: "1", text: "1" },
      { k: "2", id: "2", label: "2", text: "2" },
      { k: "3", id: "3", label: "3", text: "3" },
      { k: "KEY REL", id: "KEYREL", label: "Key Release", text: "KEY<br>REL" }
    ],
    sideRight: [
      { k: "ENTR", id: "ENTR", label: "Enter", text: "ENTR" },
      { k: "RSET", id: "RSET", label: "Reset", text: "RSET" }
    ]
  };
  function renderKeyButton(c, item) {
    return '<button type="button" class="kbtn' + (item.k.length > 1 ? " word" : "") + '" id="key-' + c + '-' + item.id + '" data-k="' + item.k + '" aria-label="' + item.label + '">' + item.text + '</button>';
  }
  function setKeysOpen(c, open) {
    var d = DS[c];
    d.keysOpen = !!open;
    d.kbWrap.classList.toggle("open", d.keysOpen);
    d.kbToggle.setAttribute("aria-expanded", d.keysOpen ? "true" : "false");
  }
  function buildKeyboard(c) {
    var d = DS[c];
    var wrap = document.createElement("div");
    wrap.className = "dsky-keys";
    var tg = document.createElement("button");
    tg.type = "button"; tg.className = "kbtoggle"; tg.id = "kbt-" + c;
    tg.setAttribute("aria-expanded", "false"); tg.setAttribute("aria-controls", "kb-" + c);
    tg.title = "Show the DSKY keypad (pause and key verbs and nouns)";
    tg.innerHTML = '<span class="kbt-ico" aria-hidden="true"></span>Keys';
    var title = $("card-" + c).querySelector(".dsky-title");
    title.insertBefore(tg, $("badge-" + c));
    var h = "";
    h += '<div class="dsky-keyboard" id="kb-' + c + '" role="group" aria-label="' + (c === "CM" ? "Columbia" : "Eagle") + ' DSKY keypad"><div class="kcol-side">';
    KEYPAD_DEFS.sideLeft.forEach(function (it) { h += renderKeyButton(c, it); });
    h += '</div><div class="kgrid">';
    KEYPAD_DEFS.grid.forEach(function (it) { h += renderKeyButton(c, it); });
    h += '</div><div class="kcol-side">';
    KEYPAD_DEFS.sideRight.forEach(function (it) { h += renderKeyButton(c, it); });
    h += '</div></div>';
    wrap.innerHTML = h;
    d.root.parentNode.insertBefore(wrap, d.root.nextSibling);
    d.kbWrap = wrap; d.kbToggle = tg; d.kb = wrap.querySelector(".dsky-keyboard");
    d.kbToggle.addEventListener("click", function () { setKeysOpen(c, !d.keysOpen); });
    d.kb.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest("button") : null;
      if (!btn) return;
      var k = btn.getAttribute("data-k");
      if (k) onDskyKey(c, k);
    });
  }

  function initDskyModel(c, g) {
    var d = DS[c];
    var i = bsearch(d.gets, g);
    var k = (c === "CM" || lmOn(g)) && i >= 0 ? d.frames[i] : null;
    var lamps = {};
    LAMPS[c].forEach(function (l) {
      if (l[0]) lamps[l[0]] = k ? (k.lights.indexOf(l[0]) >= 0) : false;
    });
    return {
      computer: c,
      prog: k ? k.prog : "00",
      verb: k ? k.verb : "  ",
      noun: k ? k.noun : "  ",
      r: k ? [k.r[0] || "      ", k.r[1] || "      ", k.r[2] || "      "] : ["      ", "      ", "      "],
      lamps: lamps,
      vnFlash: k ? !!k.flash : false,
      compActy: false,
      entryTarget: "",
      entryBuf: "",
      monitor: null,
      lampTestTimer: null,
      lampTestRunning: false,
      savedDisplay: null,
      resetPressed: false
    };
  }
  function formatClockRegs(g) {
    var t = Math.max(0, g);
    var h = Math.floor(t / 3600);
    var rem = t - h * 3600;
    var m = Math.floor(rem / 60);
    var s = rem - m * 60;
    var s100 = Math.floor((s + 0.0001) * 100) % 6000;
    return [
      "+" + "00" + pad(h % 1000, 3),
      "+" + "000" + pad(m % 100, 2),
      "+" + pad(s100, 5)
    ];
  }
  function restoreSaved(m) {
    var sd = m.savedDisplay;
    m.prog = sd.prog; m.verb = sd.verb; m.noun = sd.noun;
    m.r = sd.r.slice(); m.compActy = sd.compActy; m.vnFlash = sd.vnFlash;
    m.lamps = Object.assign({}, sd.lamps);
  }
  function executeEnter(c, m) {
    if (m.entryTarget === "MM") {
      var mmNum = parseInt(m.entryBuf, 10);
      if (m.entryBuf.length > 0 && mmNum === 0) {
        m.prog = "00";
      } else {
        m.lamps["OPR ERR"] = true;
      }
      m.vnFlash = false;
      m.entryTarget = "";
      m.entryBuf = "";
      return;
    }

    m.entryTarget = "";
    m.entryBuf = "";

    var v = parseInt(m.verb.trim(), 10);
    var n = parseInt(m.noun.trim(), 10);
    if (isNaN(v)) v = 0;
    if (isNaN(n)) n = 0;

    // V37E: Change Major Mode
    if (v === 37) {
      m.vnFlash = true;
      m.noun = "  ";
      m.entryTarget = "MM";
      m.entryBuf = "";
      return;
    }

    // V35E: Lamp Test
    if (v === 35) {
      m.savedDisplay = {
        prog: m.prog, verb: m.verb, noun: m.noun, r: m.r.slice(),
        compActy: m.compActy, vnFlash: m.vnFlash, lamps: Object.assign({}, m.lamps)
      };
      m.lampTestRunning = true;
      m.prog = "88";
      m.verb = "88";
      m.noun = "88";
      m.r = ["+88888", "+88888", "+88888"];
      m.compActy = true;
      m.vnFlash = false;
      LAMPS[c].forEach(function (l) {
        if (l[0]) m.lamps[l[0]] = true;
      });
      if (m.lampTestTimer) clearTimeout(m.lampTestTimer);
      m.lampTestTimer = setTimeout(function () {
        m.lampTestTimer = null;
        m.lampTestRunning = false;
        if (DS[c].crewMode && DS[c].model === m && m.savedDisplay) {
          restoreSaved(m);
          state.dirty = true;
        }
      }, 5000);
      return;
    }

    var curGet = playToGet(state.play);

    // V06N36E / V16N36E: AGC clock
    if ((v === 6 || v === 16) && n === 36) {
      m.r = formatClockRegs(curGet);
      m.vnFlash = false;
      m.monitor = (v === 16) ? "N36" : null;
      return;
    }

    // V05N09E: Alarm codes in octal
    if (v === 5 && n === 9) {
      var alarms = [];
      if (c === "LM") {
        if (EV["alarm-1202"] && curGet >= EV["alarm-1202"].get) alarms.push("01202");
        if (EV["alarm-1201"] && curGet >= EV["alarm-1201"].get) alarms.push("01201");
      }
      m.r = [
        alarms[0] ? " " + alarms[0] : "      ",
        alarms[1] ? " " + alarms[1] : "      ",
        alarms[2] ? " " + alarms[2] : "      "
      ];
      m.vnFlash = false;
      m.monitor = null;
      if (alarms.length > 0 && !m.resetPressed) {
        m.lamps["PROG"] = true;
      }
      return;
    }

    // V06Nxx / V16Nxx matching timeline keyframe noun
    if (v === 6 || v === 16) {
      var i = bsearch(DS[c].gets, curGet);
      var k = (c === "CM" || lmOn(curGet)) && i >= 0 ? DS[c].frames[i] : null;
      if (k && k.noun && parseInt(k.noun, 10) === n) {
        m.r = [k.r[0] || "      ", k.r[1] || "      ", k.r[2] || "      "];
        m.vnFlash = false;
        m.monitor = (v === 16) ? "TIMELINE" : null;
        return;
      }
    }

    // Anything else: OPR ERR light
    m.lamps["OPR ERR"] = true;
  }
  function activeCompAt(g) {
    var ph = D.phases[phaseAt(g)];
    var codeComp = D.code.filter(function (x) { return g >= x.get_start && g < x.get_end; })[0];
    return codeComp ? codeComp.computer : (ph ? ph.active_computer : "CM");
  }
  function onDskyKey(c, key) {
    var g = playToGet(state.play);
    var on = c === "CM" || lmOn(g);
    if (!on) return; // LM DSKY is off outside D.lm_power, so its keys do nothing then

    setPlaying(false);

    var d = DS[c];
    if (!d.crewMode || !d.model) {
      d.crewMode = true;
      d.model = initDskyModel(c, g);
      d.crewSig = ""; d.crewCap = false;
      setKeysOpen(c, true);
    }
    var m = d.model;

    // If lamp test is running and user presses a key, cancel lamp test
    if (m.lampTestRunning) {
      if (m.lampTestTimer) clearTimeout(m.lampTestTimer);
      m.lampTestTimer = null;
      m.lampTestRunning = false;
      if (m.savedDisplay) restoreSaved(m);
    }

    if (key === "VERB") {
      m.entryTarget = "VERB";
      m.entryBuf = "";
      m.verb = "  ";
      m.monitor = null;
    } else if (key === "NOUN") {
      m.entryTarget = "NOUN";
      m.entryBuf = "";
      m.noun = "  ";
      m.monitor = null;
    } else if (key >= "0" && key <= "9") {
      if (m.entryTarget === "VERB") {
        m.entryBuf = (m.entryBuf + key).slice(0, 2);
        m.verb = (m.entryBuf + "  ").slice(0, 2);
      } else if (m.entryTarget === "NOUN" || m.entryTarget === "MM") {
        m.entryBuf = (m.entryBuf + key).slice(0, 2);
        m.noun = (m.entryBuf + "  ").slice(0, 2);
      } else {
        m.lamps["OPR ERR"] = true;
      }
    } else if (key === "CLR") {
      m.entryBuf = "";
      if (m.entryTarget === "VERB") {
        m.verb = "  ";
      } else if (m.entryTarget === "NOUN" || m.entryTarget === "MM") {
        m.noun = "  ";
      }
    } else if (key === "RSET") {
      m.lamps["OPR ERR"] = false;
      m.lamps["PROG"] = false;
      m.lamps["RESTART"] = false;
      m.resetPressed = true;
    } else if (key === "PRO") {
      m.vnFlash = false;
    } else if (key === "KEY REL") {
      if (m.lampTestTimer) clearTimeout(m.lampTestTimer);
      m.lampTestTimer = null;
      m.lampTestRunning = false;
      d.crewMode = false;
      d.model = null;
      d.crewCap = false;
      d.key = null; // force redraw from the timeline
      if (d.kb.contains(document.activeElement)) d.kbToggle.focus();
      setKeysOpen(c, false);
      updateDsky(c, g, activeCompAt(g), Math.floor(performance.now() / 380) % 2 === 0);
      state.dirty = true;
      return;
    } else if (key === "ENTR") {
      executeEnter(c, m);
    } else {
      m.lamps["OPR ERR"] = true;
    }

    updateDsky(c, g, activeCompAt(g), Math.floor(performance.now() / 380) % 2 === 0);
    state.dirty = true;
  }

  // physical keyboard -> DSKY. Returns true when the event was consumed (or must be kept away from global shortcuts).
  var KEY_MAP = { "v": "VERB", "n": "NOUN", "+": "+", "-": "-", "c": "CLR", "p": "PRO", "k": "KEY REL", "r": "RSET", "Enter": "ENTR" };
  function dskyKeyTarget(e) {
    var t = e.target, kb = t && t.closest ? t.closest(".dsky-keyboard, .dsky-keys") : null;
    if (kb) return kb.id.indexOf("-LM") > 0 ? "LM" : "CM";
    var cm = DS.CM.crewMode, lm = DS.LM.crewMode;
    if (!cm && !lm) return null;
    if (cm !== lm) return cm ? "CM" : "LM";
    var cmVis = DS.CM.root.offsetParent !== null, lmVis = DS.LM.root.offsetParent !== null;
    if (cmVis !== lmVis) return cmVis ? "CM" : "LM"; // single-DSKY (mobile) layout: the visible one
    return DS.CM.act || !DS.LM.act ? "CM" : "LM";
  }
  function dskyKeyEvent(e) {
    if (e.key === " " || e.key === "Escape") return false;
    var c = dskyKeyTarget(e);
    if (!c) return false;
    var tag = (e.target && e.target.tagName) || "";
    var inPad = !!(e.target.closest && e.target.closest(".dsky-keys"));
    if (e.key.length > 1 && e.key !== "Enter") return false; // arrows, Tab, Backspace, F-keys, etc.
    if (e.key === "Enter" && (tag === "BUTTON" || tag === "A" || tag === "SELECT")) return inPad; // native click handles it
    var k = /^[0-9]$/.test(e.key) ? e.key : KEY_MAP[e.key.length === 1 ? e.key.toLowerCase() : e.key];
    if (k) {
      e.preventDefault();
      onDskyKey(c, k);
      var b = DS[c].kb.querySelector('[data-k="' + k + '"]');
      if (b) restartAnim(b, "kpress", 140);
    }
    return true; // printable keys never fall through to the global shortcuts while the DSKY owns the keyboard
  }
  buildDsky("CM"); buildDsky("LM");
  D.dsky.forEach(function (k) { DS[k.computer].frames.push(k); });
  ["CM", "LM"].forEach(function (c) { DS[c].frames.sort(function (a, b) { return a.get - b.get; }); DS[c].gets = DS[c].frames.map(function (k) { return k.get; }); });

  function writePair(el, s) {
    var svgs = el.querySelectorAll("svg");
    s = s || "  ";
    setDigit(svgs[0], s[0]); setDigit(svgs[1], s[1]);
  }
  function writeReg(el, s) {
    var svgs = el.querySelectorAll("svg");
    if (!s) s = "      ";
    setSign(svgs[0], s[0]);
    for (var i = 1; i < 6; i++) setDigit(svgs[i], s[i]);
  }
  function lmOn(g) { return D.lm_power.some(function (p) { return g >= p[0] && g < p[1]; }); }
  function lampSig(m) { return LAMPS.CM.map(function (l) { return l[0] && m.lamps[l[0]] ? 1 : 0; }).join(""); }
  function updateCrewDsky(c, g, activeComp, blinkOn, on) {
    var d = DS[c], m = d.model;
    if (!on) {
      if (d.on !== false) {
        d.on = false; d.crewSig = ""; d.crewCap = false;
        flicker(c, false);
        writePair(d.prog, ""); writePair(d.verb, ""); writePair(d.noun, "");
        d.r.forEach(function (el) { writeReg(el, ""); });
        d.lamps.forEach(function (l) { l.classList.remove("on"); });
        d.root.classList.add("off");
        d.ca.classList.remove("on"); d.busy = false;
        d.verb.classList.remove("blink-hidden"); d.noun.classList.remove("blink-hidden"); d.hide = false;
        $("cap-" + c).innerHTML = '<span class="src">Off</span>Eagle\'s computer is powered down.';
        $("card-" + c).classList.remove("active"); d.act = false;
        $("badge-" + c).textContent = "Off"; d.badge = "Off";
      }
      return;
    }
    if (d.on !== true) { // powered (back) up while keyed: repaint
      if (d.on === false) flicker(c, true);
      d.on = true; d.crewSig = ""; d.crewCap = false;
      d.root.classList.remove("off");
    }
    if (m.monitor === "N36") {
      m.r = formatClockRegs(g);
    } else if (m.monitor === "TIMELINE") {
      var mi = bsearch(d.gets, g);
      var mk = mi >= 0 ? d.frames[mi] : null;
      if (mk) m.r = [mk.r[0] || "      ", mk.r[1] || "      ", mk.r[2] || "      "];
    }
    var sig = m.prog + "|" + m.verb + "|" + m.noun + "|" + m.r.join(",") + "|" + lampSig(m) + "|" + (m.compActy ? 1 : 0);
    if (sig !== d.crewSig) {
      var prevProg = d.crewSig ? d.crewSig.split("|")[4].charAt(5) === "1" : d.progOn;
      d.crewSig = sig;
      writePair(d.prog, m.prog);
      writePair(d.verb, m.verb);
      writePair(d.noun, m.noun);
      for (var r = 0; r < 3; r++) writeReg(d.r[r], m.r[r]);
      d.lamps.forEach(function (l) {
        var lname = l.getAttribute("data-l");
        l.classList.toggle("on", !!(lname && m.lamps[lname]));
      });
      d.ca.classList.toggle("on", !!m.compActy); d.busy = !!m.compActy;
      var progNow = !!m.lamps["PROG"];
      if (progNow && !prevProg) triggerAlarm(c);
      d.progOn = progNow;
    }
    var hide = m.vnFlash && !blinkOn && !reduceMotion;
    if (hide !== d.hide) {
      d.hide = hide;
      d.verb.classList.toggle("blink-hidden", hide);
      d.noun.classList.toggle("blink-hidden", hide);
    }
    if (!d.crewCap) {
      d.crewCap = true;
      $("cap-" + c).innerHTML = '<span class="src sim">Crew mode</span>You are keying this DSKY. KEY REL returns to the mission display.';
    }
    var act = c === activeComp;
    if (act !== d.act) { d.act = act; $("card-" + c).classList.toggle("active", act); }
    var bt = act ? "Active" : "Standby";
    if (bt !== d.badge) { d.badge = bt; $("badge-" + c).textContent = bt; }
  }
  function updateDsky(c, g, activeComp, blinkOn) {
    var d = DS[c];
    var on = c === "CM" || lmOn(g);
    if (d.crewMode && d.model) { updateCrewDsky(c, g, activeComp, blinkOn, on); return; }
    var i = bsearch(d.gets, g);
    var k = on && i >= 0 ? d.frames[i] : null;
    var key = on ? (k ? k.get + "|" + k.prog + k.verb + k.noun + k.r.join(",") + k.lights.join(",") : "idle") : "off";
    if (key !== d.key) {
      d.key = key;
      var pvn = on ? (k ? k.prog + "|" + k.verb + "|" + k.noun : "idle") : "off";
      if (d.on !== undefined && d.on !== on) flicker(c, on);
      else if (on && d.pvn !== undefined && pvn !== d.pvn) blankBeat(c);
      d.on = on; d.pvn = pvn;
      var progNow = !!(on && k && k.lights.indexOf("PROG") >= 0);
      if (on && ((k && k.alarm && k.alarm !== d.alarm) || (progNow && !d.progOn))) triggerAlarm(c);
      d.alarm = on && k ? (k.alarm || null) : null; d.progOn = progNow;
      d.root.classList.toggle("off", !on);
      var src = "";
      if (!on) {
        writePair(d.prog, ""); writePair(d.verb, ""); writePair(d.noun, "");
        d.r.forEach(function (el) { writeReg(el, ""); });
        d.lamps.forEach(function (l) { l.classList.remove("on"); });
        $("cap-" + c).innerHTML = '<span class="src">Off</span>Eagle\'s computer is powered down.';
      } else if (!k) {
        writePair(d.prog, "00"); writePair(d.verb, ""); writePair(d.noun, "");
        d.r.forEach(function (el) { writeReg(el, ""); });
        d.lamps.forEach(function (l) { l.classList.remove("on"); });
        $("cap-" + c).innerHTML = '<span class="src">Not simulated</span>P00: idle.';
      } else {
        writePair(d.prog, k.prog); writePair(d.verb, k.verb); writePair(d.noun, k.noun);
        for (var r = 0; r < 3; r++) writeReg(d.r[r], k.r[r]);
        d.lamps.forEach(function (l) { l.classList.toggle("on", k.lights.indexOf(l.getAttribute("data-l")) >= 0 && l.getAttribute("data-l") !== ""); });
        src = k.simulated ? '<span class="src sim">Simulated</span>' : '<span class="src">Not simulated</span>';
        $("cap-" + c).innerHTML = src + esc(k.caption);
      }
      d.flash = !!(k && k.flash);
    }
    // Flashing verb/noun (the real DSKY flashed them to ask for crew input)
    var hide = d.flash && !blinkOn && !reduceMotion;
    if (hide !== d.hide) {
      d.hide = hide;
      d.verb.classList.toggle("blink-hidden", hide);
      d.noun.classList.toggle("blink-hidden", hide);
    }
    // COMP ACTY flickers while the computer is busy (simulated phases) or while burning
    var busy = on && k && k.simulated && state.playing ? (Math.random() < 0.35) : (on && k && k.simulated && (Math.floor(performance.now() / 700) % 3 === 0));
    if (reduceMotion) busy = on && k && k.simulated;
    busy = !!busy;
    if (busy !== d.busy) { d.busy = busy; d.ca.classList.toggle("on", busy); }
    var act = c === activeComp;
    if (act !== d.act) { d.act = act; $("card-" + c).classList.toggle("active", act); }
    var bt = !on ? "Off" : act ? "Active" : "Standby";
    if (bt !== d.badge) { d.badge = bt; $("badge-" + c).textContent = bt; }
  }

