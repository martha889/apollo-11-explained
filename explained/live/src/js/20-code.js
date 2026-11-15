  // ---------- code panel ----------
  var codeState = { idx: -1, tab: "agc", cur: -1, lines: [], hl: null, lh: 18, prog: -1 };
  function highlightAGC(line) {
    var hashAt = line.indexOf("#");
    var body = hashAt >= 0 ? line.slice(0, hashAt) : line, cm = hashAt >= 0 ? line.slice(hashAt) : "";
    var out = "";
    if (body && !/^\s/.test(body)) {
      var m = body.match(/^(\S+)(.*)$/);
      out += '<span class="lb">' + esc(m[1]) + "</span>";
      body = m[2];
    }
    out += body.replace(/^(\s+)(\S+)/, function (_, sp, op) { return esc(sp) + '<span class="kw">' + esc(op) + "</span>"; }).replace(/&(?!amp;|lt;|gt;)/g, "&amp;");
    if (cm) out += '<span class="cm">' + esc(cm) + "</span>";
    return out;
  }
  function highlightPy(line) {
    var t = esc(line);
    var hashAt = line.indexOf("#");
    if (/^\s*(\"\"\"|''')/.test(line) || /^\s*#/.test(line)) return '<span class="cm">' + t + "</span>";
    t = t.replace(/\b(def|return|for|in|if|elif|else|while|import|from|with|as|and|or|not|None|True|False|lambda)\b/g, '<span class="kw">$1</span>');
    if (hashAt > 0) {
      var e = esc(line.slice(hashAt));
      var ix = t.lastIndexOf(e);
      if (ix >= 0) t = t.slice(0, ix) + '<span class="cm">' + e + "</span>";
    }
    return t;
  }
  function renderListing() {
    var step = D.code[codeState.idx];
    var src = codeState.tab === "agc" ? step.agc : step.python;
    var L = $("listing");
    if (!src) {
      L.innerHTML = '<span class="ln"><span class="no"></span><span class="cm">No Python translation of this routine in explained/. The AGC listing is on the other tab.</span></span>';
      $("code-file").textContent = "";
      codeState.lines = []; codeState.exec = []; codeState.hl = null; codeState.cur = -1;
      return;
    }
    var h = "", exec = [];
    src.lines.forEach(function (ln, i) {
      var isCode = codeState.tab === "agc" ? (ln.trim() !== "" && !/^\s*#/.test(ln)) : (ln.trim() !== "" && !/^\s*(#|\"\"\"|''')/.test(ln));
      if (isCode) exec.push(i);
      h += '<span class="ln' + (i === 0 ? " entry" : "") + '" data-i="' + i + '"><span class="no">' + (src.line + i) + "</span>" + (codeState.tab === "agc" ? highlightAGC(ln) : highlightPy(ln)) + "\n</span>";
    });
    L.innerHTML = h + '<div class="hl snap" aria-hidden="true"></div>';
    L.style.scrollBehavior = "auto";
    L.scrollTop = 0; L.scrollLeft = 0;
    L.style.scrollBehavior = "";
    codeState.hl = L.lastChild;
    codeState.lines = L.querySelectorAll(".ln");
    codeState.lh = codeState.lines.length ? codeState.lines[0].offsetHeight || 18 : 18;
    codeState.hl.style.height = codeState.lh + "px";
    codeState.hl.style.width = Math.max(L.scrollWidth, L.clientWidth) + "px";
    codeState.exec = exec;
    codeState.cur = -1;
    restartAnim(L, "swap-fade");
    $("code-file").textContent = src.file + " · line " + src.line + (codeState.tab === "agc" ? " · label " + src.label : " · " + src.name + "()");
  }
  function updateCode(g, p) {
    var idx = 0;
    for (var i = 0; i < D.code.length; i++) if (g >= D.code[i].get_start) idx = i;
    var step = D.code[idx];
    if (idx !== codeState.idx) {
      var firstStep = codeState.idx < 0;
      codeState.idx = idx;
      $("code-title").textContent = step.title;
      $("code-comp").textContent = step.computer === "CM" ? "Columbia · Comanche055" : "Eagle · Luminary099";
      $("code-explain").textContent = step.explain;
      renderListing();
      if (!firstStep) {
        restartAnim($("code-title"), "swap-fade"); restartAnim($("code-explain"), "swap-fade"); restartAnim($("code-comp"), "swap-fade"); restartAnim($("code-file"), "swap-fade");
      }
    }
    var p0 = getToPlay(step.get_start), p1 = getToPlay(step.get_end);
    var f = p1 > p0 ? Math.max(0, Math.min(0.999, (p - p0) / (p1 - p0))) : 0;
    var fq = Math.round(f * 1000);
    if (fq !== codeState.prog) { codeState.prog = fq; $("code-prog").style.transform = "scaleX(" + (fq / 1000) + ")"; }
    if (!codeState.exec || !codeState.exec.length) return;
    var n = codeState.exec.length;
    // walk the routine a few times over the step's playback window
    var loops = Math.max(1, Math.round((p1 - p0) / 12));
    var k = codeState.exec[Math.floor(((f * loops) % 1) * n)];
    if (k !== codeState.cur) {
      if (codeState.cur >= 0 && codeState.lines[codeState.cur]) codeState.lines[codeState.cur].classList.remove("cur");
      codeState.cur = k;
      var el = codeState.lines[k];
      if (el) {
        el.classList.add("cur");
        var L = $("listing");
        var top = el.offsetTop, h = L.clientHeight;
        var hl = codeState.hl;
        if (hl) {
          hl.style.transform = "translateY(" + top + "px)";
          if (hl.classList.contains("snap")) { hl.classList.add("on"); void hl.offsetWidth; hl.classList.remove("snap"); }
        }
        if (top < L.scrollTop + 8 || top > L.scrollTop + h - 40) L.scrollTop = Math.max(0, top - h / 3);
      }
    }
  }
  function setTab(t) {
    codeState.tab = t;
    $("tab-agc").setAttribute("aria-selected", t === "agc");
    $("tab-py").setAttribute("aria-selected", t === "py");
    if (codeState.idx >= 0) renderListing();
    state.dirty = true;
  }
  $("tab-agc").addEventListener("click", function () { setTab("agc"); });
  $("tab-py").addEventListener("click", function () { setTab("py"); });

