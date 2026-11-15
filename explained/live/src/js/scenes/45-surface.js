  var s3_surfPrevG = null;
  var s3_surfLandscapeCache = null;

  function s3_surfCrossed(t, g, prevG) {
    if (!state.playing || prevG === null || t == null) return false;
    var dp = getToPlay(g) - getToPlay(prevG);
    return prevG < t && g >= t && (dp > 0 && dp < 0.75 * (state.speed || 1));
  }

  function s3_buildSurfaceLandscape(w, h, dpr) {
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w * dpr));
    c.height = Math.max(1, Math.round(h * dpr));
    var g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);

    var gy = Math.round(h * 0.68);
    var s = Math.min(w, h) / 380;

    // Subtle low-sun horizon backscatter glow
    var hg = g.createLinearGradient(0, gy - 54 * s, 0, gy + 10 * s);
    hg.addColorStop(0, "rgba(120, 140, 175, 0)");
    hg.addColorStop(0.75, "rgba(135, 152, 182, 0.075)");
    hg.addColorStop(1, "rgba(165, 178, 200, 0.14)");
    g.fillStyle = hg;
    g.fillRect(0, gy - 54 * s, w, 64 * s);

    // 3 layered distant lunar mountain/ridge silhouettes above horizon
    var ridges = [
      { hMax: 32 * s, hMin: 11 * s, f1: 5.2, f2: 13.7, p1: 0.4, p2: 2.1, fill0: "#222834", fill1: "#161b24", rim: "rgba(145, 158, 182, 0.25)" },
      { hMax: 21 * s, hMin: 6 * s, f1: 7.8, f2: 19.3, p1: 1.9, p2: 0.7, fill0: "#2e3544", fill1: "#1d232e", rim: "rgba(170, 182, 205, 0.34)" },
      { hMax: 11 * s, hMin: 2 * s, f1: 11.4, f2: 27.1, p1: 3.1, p2: 4.2, fill0: "#3c4454", fill1: "#262c39", rim: "rgba(198, 208, 226, 0.42)" }
    ];
    var steps = Math.max(64, Math.round(w / 6));
    for (var ri = 0; ri < ridges.length; ri++) {
      var r = ridges[ri];
      g.beginPath();
      g.moveTo(0, gy + 2);
      for (var i = 0; i <= steps; i++) {
        var u = i / steps;
        var wv = 0.55 * (Math.sin(u * r.f1 + r.p1) * 0.5 + 0.5) + 0.45 * (Math.cos(u * r.f2 + r.p2) * 0.5 + 0.5);
        // Gentle dip near landing site (u ~ 0.42) so Eagle stands proud against sky
        var dip = 1 - 0.35 * Math.exp(-Math.pow((u - 0.42) / 0.14, 2));
        var ry = gy - (r.hMin + (r.hMax - r.hMin) * wv) * dip;
        g.lineTo(u * w, ry);
      }
      g.lineTo(w, gy + 2);
      g.closePath();
      var rg = g.createLinearGradient(0, gy - r.hMax, 0, gy + 2);
      rg.addColorStop(0, r.fill0);
      rg.addColorStop(1, r.fill1);
      g.fillStyle = rg;
      g.fill();
      g.strokeStyle = r.rim;
      g.lineWidth = 1;
      g.stroke();
    }

    // Main regolith ground base with low-sun directional gradient (sun in eastern sky on the right)
    var gg = g.createLinearGradient(0, gy, 0, h);
    gg.addColorStop(0, "#4c5260");
    gg.addColorStop(0.28, "#434956");
    gg.addColorStop(0.72, "#353b47");
    gg.addColorStop(1, "#272c36");
    g.fillStyle = gg;
    g.fillRect(0, gy, w, h - gy);

    // Subtle undulating regolith shadow bands across the plains
    for (var bi = 0; bi < 6; bi++) {
      var by = gy + (bi + 0.5) / 6 * (h - gy);
      var bh = (8 + bi * 5) * s;
      var bg = g.createLinearGradient(0, by - bh, 0, by + bh);
      bg.addColorStop(0, "rgba(20, 24, 32, 0)");
      bg.addColorStop(0.5, bi % 2 === 0 ? "rgba(18, 22, 30, 0.18)" : "rgba(185, 195, 212, 0.06)");
      bg.addColorStop(1, "rgba(20, 24, 32, 0)");
      g.fillStyle = bg;
      g.fillRect(0, by - bh, w, bh * 2);
    }

    // Soft sunlit ground glow around Tranquility Base LM & EVA area
    var lx = w * 0.42;
    var spot = g.createRadialGradient(lx + 36 * s, gy + 18 * s, 8 * s, lx + 36 * s, gy + 24 * s, Math.max(w, h) * 0.42);
    spot.addColorStop(0, "rgba(215, 210, 198, 0.22)");
    spot.addColorStop(0.45, "rgba(175, 180, 192, 0.10)");
    spot.addColorStop(1, "rgba(30, 35, 45, 0)");
    g.fillStyle = spot;
    g.fillRect(0, gy, w, h - gy);

    // Procedural craters with soft low-sun gradient shading & sunlit western inner walls
    var seed = 907;
    function rnd() {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    }
    for (var k = 0; k < 22; k++) {
      var v = Math.pow((k + 0.3 * rnd()) / 22, 1.3);
      var cy = gy + 10 * s + v * (h - gy - 18 * s);
      var cx = ((k * 0.381966 + 0.17 * rnd()) % 1) * w;
      // Keep immediate LM pad and astronaut walk zone uncluttered
      if (cx > lx - 60 * s && cx < lx + 175 * s && cy < gy + 24 * s) {
        cy += 26 * s;
      }
      var persp = 0.35 + 0.65 * v;
      var rw = (6 + (k * 17 % 20) + rnd() * 7) * persp * s;
      var rh = rw * (0.19 + 0.06 * persp);

      // Soft outer ejecta rim
      var ej = g.createRadialGradient(cx, cy, rw * 0.6, cx, cy, rw * 1.35);
      ej.addColorStop(0, "rgba(155, 162, 178, 0.11)");
      ej.addColorStop(1, "rgba(155, 162, 178, 0)");
      g.fillStyle = ej;
      g.beginPath();
      g.ellipse(cx, cy, rw * 1.35, rh * 1.35, 0, 0, Math.PI * 2);
      g.fill();

      // Smoothly shaded crater bowl (sun from right casts shadow inside right half, illuminates left inner wall)
      var cg = g.createLinearGradient(cx - rw, cy, cx + rw, cy);
      cg.addColorStop(0, "rgba(150, 158, 175, 0.42)");
      cg.addColorStop(0.42, "rgba(62, 68, 80, 0.38)");
      cg.addColorStop(0.72, "rgba(18, 22, 31, 0.62)");
      cg.addColorStop(1, "rgba(14, 18, 26, 0.72)");
      g.fillStyle = cg;
      g.beginPath();
      g.ellipse(cx, cy, rw, rh, 0, 0, Math.PI * 2);
      g.fill();

      // Subtle sunlit left inner rim arc
      g.strokeStyle = "rgba(205, 214, 230, 0.34)";
      g.lineWidth = Math.max(0.8, 1.1 * persp * s);
      g.beginPath();
      g.ellipse(cx, cy, rw, rh, 0, Math.PI * 0.62, Math.PI * 1.38);
      g.stroke();

      // Soft external rim shadow to the left
      g.fillStyle = "rgba(12, 16, 24, 0.24)";
      g.beginPath();
      g.ellipse(cx - rw * 1.08, cy, rw * 0.26, rh * 0.55, 0, 0, Math.PI * 2);
      g.fill();
    }

    // Scattered lunar regolith rocks with long low-sun shadows to the left
    for (var rk = 0; rk < 22; rk++) {
      var rkx = rnd() * w;
      var rkv = rnd();
      var rky = gy + 6 * s + rkv * (h - gy - 10 * s);
      if (Math.abs(rkx - lx) < 55 * s && rky < gy + 18 * s) continue;
      var rkr = (1.2 + rnd() * 2.4) * (0.5 + 0.5 * rkv) * s;
      // Long shadow to the left
      g.fillStyle = "rgba(10, 14, 21, 0.62)";
      g.beginPath();
      g.moveTo(rkx, rky - rkr * 0.5);
      g.lineTo(rkx - rkr * 6.5, rky);
      g.lineTo(rkx, rky + rkr * 0.6);
      g.closePath();
      g.fill();
      // Rock body (shadowed left, sunlit right)
      g.fillStyle = "#353c4a";
      g.beginPath();
      g.arc(rkx, rky, rkr, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = "#b8c2d4";
      g.beginPath();
      g.arc(rkx + rkr * 0.25, rky - rkr * 0.15, rkr * 0.7, 0, Math.PI * 2);
      g.fill();
    }

    return c;
  }

  // The US flag (13 stripes, 50 stars in rows of 6 and 5), drawn once per size into an offscreen canvas.
  function s3_usFlag(w, h) {
    var key = w.toFixed(2) + "x" + h.toFixed(2) + "@" + DPR;
    if (s3_usFlag.key === key) return s3_usFlag.canvas;
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w * DPR)); c.height = Math.max(1, Math.round(h * DPR));
    var x = c.getContext("2d"), red = "#b22234", white = "#f4f3ee", blue = "#3c3b6e";
    x.scale(c.width / w, c.height / h);
    var sh = h / 13, cw = w * 0.4, ch = sh * 7;
    for (var i = 0; i < 13; i++) { x.fillStyle = i % 2 ? white : red; x.fillRect(0, i * sh, w, sh + 0.05); }
    x.fillStyle = blue; x.fillRect(0, 0, cw, ch);
    x.fillStyle = white;
    for (var row = 0; row < 9; row++) {
      for (var col = row % 2 ? 2 : 1; col <= 11; col += 2) {
        x.beginPath(); x.arc(col * cw / 12, (row + 1) * ch / 10, Math.max(0.3, ch / 34), 0, Math.PI * 2); x.fill();
      }
    }
    s3_usFlag.key = key; s3_usFlag.canvas = c;
    return c;
  }

  function s3_drawSurfaceAstronaut(x, y, s, k, bob, isOnLadder) {
    ctx.save();
    ctx.translate(x, y - bob);
    ctx.scale(s, s);

    if (!isOnLadder) {
      // Long low-sun shadow to the left on the regolith (stays on ground y)
      ctx.save();
      ctx.translate(0, bob / s);
      var sg = ctx.createLinearGradient(0, 0, -42, 0);
      sg.addColorStop(0, "rgba(8, 11, 18, 0.72)");
      sg.addColorStop(1, "rgba(8, 11, 18, 0)");
      ctx.fillStyle = sg;
      ctx.beginPath();
      ctx.ellipse(-20, 0.5, 21, 2.6, -0.04, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // PLSS Backpack
    ctx.fillStyle = "#aeb8c8";
    ctx.fillRect(-5.8, -23.5, 4.5, 13.5);
    ctx.fillStyle = "#dce4f0";
    ctx.fillRect(-4.2, -25.2, 7.2, 2.2); // OPS top module
    // Remote control chest unit & suit torso
    ctx.fillStyle = "#b7c2d2";
    ctx.fillRect(-4.2, -22.5, 8.4, 13.5);
    ctx.fillStyle = "#eef3fa";
    ctx.fillRect(-1.2, -22.5, 5.4, 13.5); // sunlit right half of torso
    // Chest RCU + Hasselblad camera
    ctx.fillStyle = "#5c6678";
    ctx.fillRect(-1.8, -19.2, 4.2, 3.8);
    ctx.fillStyle = C.amber;
    ctx.fillRect(-0.8, -18.2, 1.6, 1.6);

    // Legs & lunar overshoes
    ctx.fillStyle = "#9aa6b8";
    ctx.fillRect(-3.6, -9.2, 3.0, 8.2);
    ctx.fillStyle = "#e4ecf7";
    ctx.fillRect(0.6, -9.2, 3.0, 8.2);
    // Knee/joint rings
    ctx.fillStyle = "#6c7688";
    ctx.fillRect(-3.6, -5.2, 3.0, 1.0);
    ctx.fillRect(0.6, -5.2, 3.0, 1.0);
    // Lunar boots
    ctx.fillStyle = "#5e6778";
    ctx.fillRect(-4.4, -1.6, 4.0, 2.0);
    ctx.fillRect(0.4, -1.6, 4.2, 2.0);

    // Arms
    ctx.strokeStyle = "#e2eaf6";
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.beginPath();
    if (isOnLadder) {
      ctx.moveTo(-3.5, -20.5);
      ctx.lineTo(-7.2, -24.0);
      ctx.moveTo(3.5, -20.5);
      ctx.lineTo(-2.5, -23.0);
    } else if (k === 0) {
      ctx.moveTo(-3.8, -20.5);
      ctx.lineTo(-6.2, -13.5);
      ctx.moveTo(3.8, -20.5);
      ctx.lineTo(7.4, -15.0);
    } else {
      ctx.moveTo(-3.8, -20.5);
      ctx.lineTo(-5.8, -13.5);
      ctx.moveTo(3.8, -20.5);
      ctx.lineTo(6.8, -22.5); // salute / visor gesture toward flag
    }
    ctx.stroke();

    // LEVA Helmet & gold sun visor
    ctx.fillStyle = "#edf2fa";
    ctx.beginPath();
    ctx.arc(0, -26.5, 5.0, 0, Math.PI * 2);
    ctx.fill();
    // Gold reflective sun visor
    var vg = ctx.createLinearGradient(-3, -29, 4, -24);
    vg.addColorStop(0, "#ffe494");
    vg.addColorStop(0.55, "#d89228");
    vg.addColorStop(1, "#6b430b");
    ctx.fillStyle = vg;
    ctx.beginPath();
    ctx.arc(0.8, -26.5, 3.7, -Math.PI * 0.48, Math.PI * 0.48);
    ctx.closePath();
    ctx.fill();
    // Visor specular glint
    ctx.fillStyle = "#ffffff";
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.arc(2.0, -27.8, 0.9, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.restore();
  }

  SCENES.surface = function (g, dt) {
    var tr = T.surface;
    var cw = Math.round(W), ch = Math.round(H);
    var gy = Math.round(H * 0.68);
    var s = Math.min(W, H) / 380;
    var lx = W * 0.42;
    var eva = g >= EV["eva-start"].get && g < EV["eva-end"].get;
    var up = g >= EV.liftoff.get;

    // 1. Starfield sky + Earth via body()
    drawStars();
    var er = Math.max(12, Math.min(W, H) * 0.045);
    var ex = W * 0.78;
    var ey = Math.max(88, H * 0.21);
    body(ex, ey, er, C.earth, "Earth");

    // 2. Cached low-sun lunar landscape with layered ridgelines & crater ellipses
    if (!s3_surfLandscapeCache || s3_surfLandscapeCache.w !== cw || s3_surfLandscapeCache.h !== ch || s3_surfLandscapeCache.dpr !== DPR) {
      s3_surfLandscapeCache = {
        w: cw,
        h: ch,
        dpr: DPR,
        canvas: s3_buildSurfaceLandscape(cw, ch, DPR)
      };
    }
    ctx.drawImage(s3_surfLandscapeCache.canvas, 0, 0, W, H);

    // One-shot FX triggers while playing across surface milestones
    if (s3_surfCrossed(EV["eva-start"].get, g, s3_surfPrevG)) {
      FX.ping(lx, gy - 52 * s, C.amber);
    }
    if (s3_surfCrossed(EV["first-step"].get, g, s3_surfPrevG)) {
      FX.ping(lx + 16 * s, gy, C.amber);
      FX.dust(lx + 16 * s, gy, 0.95, true);
    }
    if (s3_surfCrossed(395520, g, s3_surfPrevG)) {
      FX.ping(lx + 160 * s, gy - 26 * s, C.amber);
    }
    if (s3_surfCrossed(EV["eva-end"].get, g, s3_surfPrevG)) {
      FX.ping(lx, gy - 52 * s, C.csm);
    }
    if (s3_surfCrossed(EV.liftoff.get, g, s3_surfPrevG)) {
      FX.ping(lx, gy - 44 * s, C.amber);
      FX.flash(C.amber, 0.16);
      FX.shake(4.8);
      FX.dust(lx, gy, 1.6, true);
    }
    s3_surfPrevG = g;

    // 3. Soft ground glow & long low-sun LM shadow on the lunar surface
    var lmGlow = ctx.createRadialGradient(lx, gy + 2 * s, 4 * s, lx, gy + 2 * s, 92 * s);
    lmGlow.addColorStop(0, "rgba(242, 177, 60, 0.20)");
    lmGlow.addColorStop(0.55, "rgba(242, 177, 60, 0.06)");
    lmGlow.addColorStop(1, "rgba(242, 177, 60, 0)");
    ctx.save();
    ctx.fillStyle = lmGlow;
    ctx.beginPath();
    ctx.ellipse(lx, gy + 2 * s, 92 * s, 16 * s, 0, 0, Math.PI * 2);
    ctx.fill();

    // Long shadow cast to the left by Eagle
    var shGrad = ctx.createLinearGradient(lx + 30 * s, gy, lx - 145 * s, gy);
    shGrad.addColorStop(0, "rgba(7, 10, 16, 0.78)");
    shGrad.addColorStop(0.75, "rgba(7, 10, 16, 0.45)");
    shGrad.addColorStop(1, "rgba(7, 10, 16, 0)");
    ctx.fillStyle = shGrad;
    ctx.beginPath();
    ctx.ellipse(lx - 52 * s, gy + 2 * s, 88 * s, (up ? 5.5 : 8.5) * s, -0.02, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // 4. Bootprint trail in the regolith after first-step
    if (g >= EV["first-step"].get) {
      var maxPrintX = g >= 395520 ? 156 : (g >= EV["first-step"].get + 1200 ? 118 : 68);
      ctx.save();
      for (var bp = 14; bp <= maxPrintX; bp += 7) {
        var bpx = lx + bp * s;
        var bpy = gy + (2.5 + Math.sin(bp * 0.25) * 1.8) * s;
        ctx.fillStyle = "rgba(12, 16, 24, 0.62)";
        ctx.beginPath();
        ctx.ellipse(bpx, bpy, 1.8 * s, 0.85 * s, 0.1, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "rgba(205, 214, 230, 0.32)";
        ctx.beginPath();
        ctx.ellipse(bpx - 0.6 * s, bpy, 0.9 * s, 0.5 * s, 0.1, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // Footprint ping ring at the base of the ladder right around first-step
      var dpStep = getToPlay(g) - getToPlay(EV["first-step"].get);
      if (dpStep >= 0 && dpStep <= 4.2) {
        var fpX = lx + 16 * s, fpY = gy + 1 * s;
        var fpU = Math.min(1, dpStep / 2.2);
        ctx.save();
        ctx.strokeStyle = C.amber;
        ctx.lineWidth = 1.6;
        ctx.globalAlpha = (1 - fpU * 0.65) * 0.88;
        ctx.beginPath();
        ctx.ellipse(fpX, fpY, (7 + fpU * 18) * s, (2.8 + fpU * 6.5) * s, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }

    // 5. Detailed Vector Lunar Module (Descent Stage + Ascent Stage)
    ctx.save();
    ctx.translate(lx, gy);
    ctx.scale(s, s);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    // --- DESCENT STAGE ---
    // DPS engine bell beneath center bay
    ctx.fillStyle = "#2b3240";
    ctx.strokeStyle = "#5c667a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(-6, -22);
    ctx.lineTo(-10.5, -7);
    ctx.lineTo(10.5, -7);
    ctx.lineTo(6, -22);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Landing gear outriggers, primary/secondary struts & shock absorbers
    ctx.strokeStyle = "#b88228";
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    // Left leg A-frame + outrigger
    ctx.moveTo(-30, -34);
    ctx.lineTo(-39, -34);
    ctx.moveTo(-36, -34);
    ctx.lineTo(-47, -1.5);
    ctx.moveTo(-28, -22);
    ctx.lineTo(-43, -11);
    ctx.moveTo(-28, -26);
    ctx.lineTo(-36, -34);
    // Right leg A-frame + outrigger
    ctx.moveTo(30, -34);
    ctx.lineTo(39, -34);
    ctx.moveTo(36, -34);
    ctx.lineTo(47, -1.5);
    ctx.moveTo(28, -22);
    ctx.lineTo(43, -11);
    ctx.moveTo(28, -26);
    ctx.lineTo(36, -34);
    ctx.stroke();

    //Gold foil wrapping highlights on upper struts
    ctx.strokeStyle = "#f5bd47";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(-36, -34);
    ctx.lineTo(-42, -16);
    ctx.moveTo(36, -34);
    ctx.lineTo(42, -16);
    ctx.stroke();

    // Wide dish footpads & lunar contact probes
    ctx.fillStyle = "#9a6c1f";
    ctx.strokeStyle = "#e8b03e";
    ctx.lineWidth = 1;
    // Left footpad
    ctx.beginPath();
    ctx.ellipse(-47, -1.2, 6.8, 1.8, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    // Right footpad
    ctx.beginPath();
    ctx.ellipse(47, -1.2, 6.8, 1.8, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    // Center/forward footpad
    ctx.beginPath();
    ctx.ellipse(0, -0.5, 6.2, 1.6, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    // Bent lunar contact sensing probes
    ctx.strokeStyle = "#8a96aa";
    ctx.lineWidth = 0.9;
    ctx.beginPath();
    ctx.moveTo(-47, -1.0);
    ctx.lineTo(-54, 0.2);
    ctx.moveTo(47, -1.0);
    ctx.lineTo(54, 0.2);
    ctx.stroke();

    // Octagonal Descent Stage body panels (shaded Kapton gold foil + thermal panels)
    // Left angled bay (shadowed gold)
    ctx.fillStyle = "#8f5f16";
    ctx.fillRect(-31, -44, 14, 22);
    // Center bay (mid gold foil)
    var dgMid = ctx.createLinearGradient(-17, -44, 17, -22);
    dgMid.addColorStop(0, "#cf8c24");
    dgMid.addColorStop(0.5, "#f2b13c");
    dgMid.addColorStop(1, "#c4821e");
    ctx.fillStyle = dgMid;
    ctx.fillRect(-17, -44, 34, 22);
    // Right angled bay (bright sunlit gold foil)
    var dgRight = ctx.createLinearGradient(17, -44, 31, -22);
    dgRight.addColorStop(0, "#ffd470");
    dgRight.addColorStop(1, "#e5a230");
    ctx.fillStyle = dgRight;
    ctx.fillRect(17, -44, 14, 22);

    // Black anodized MESA / thermal equipment panels & structural deck flanges
    ctx.fillStyle = "#232834";
    ctx.fillRect(-28, -41, 8, 8);
    ctx.fillRect(20, -33, 8, 8);
    ctx.strokeStyle = "#181d26";
    ctx.lineWidth = 1.2;
    ctx.strokeRect(-31, -44, 62, 22);
    ctx.beginPath();
    ctx.moveTo(-17, -44);
    ctx.lineTo(-17, -22);
    ctx.moveTo(17, -44);
    ctx.lineTo(17, -22);
    ctx.moveTo(-31, -33);
    ctx.lineTo(31, -33);
    ctx.stroke();

    // Forward landing gear strut & 9-rung ladder + porch platform
    ctx.fillStyle = "#3a4252";
    ctx.fillRect(-3.8, -43, 7.6, 42);
    ctx.strokeStyle = "#cfd8e6";
    ctx.lineWidth = 1.1;
    ctx.beginPath();
    ctx.moveTo(-3.2, -41);
    ctx.lineTo(-3.2, -3);
    ctx.moveTo(3.2, -41);
    ctx.lineTo(3.2, -3);
    for (var rg = 0; rg < 9; rg++) {
      var rgy = -38 + rg * 4.0;
      ctx.moveTo(-3.2, rgy);
      ctx.lineTo(3.2, rgy);
    }
    ctx.stroke();
    // Ladder porch rails at top of descent stage
    ctx.strokeStyle = "#aeb8c8";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(-5.5, -44);
    ctx.lineTo(-5.5, -48);
    ctx.lineTo(5.5, -48);
    ctx.lineTo(5.5, -44);
    ctx.stroke();

    ctx.restore();

    // --- ASCENT STAGE (on descent stage before liftoff, or climbing at liftoff) ---
    var preLaunchRem = EV.liftoff.get - g;
    var climbPx = 0;
    if (up) {
      climbPx = Math.min(H * 0.45, 18 * s + (g - EV.liftoff.get) * 14 * s);
      FX.exhaust(lx, gy - 44 * s - climbPx, -Math.PI * 0.5, 1.0, { scale: s * 1.15, color: C.amber });
      FX.dust(lx, gy, 1.35);
    }

    ctx.save();
    ctx.translate(lx, gy - climbPx);
    ctx.scale(s, s);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    // Ascent stage aft equipment bay & side pods
    ctx.fillStyle = "#5c6577";
    ctx.beginPath();
    ctx.moveTo(-25, -46);
    ctx.lineTo(-29, -58);
    ctx.lineTo(-24, -71);
    ctx.lineTo(24, -71);
    ctx.lineTo(29, -58);
    ctx.lineTo(25, -46);
    ctx.closePath();
    ctx.fill();

    // Main faceted pressurized cabin
    var cabGrad = ctx.createLinearGradient(-24, -82, 24, -44);
    cabGrad.addColorStop(0, "#7d8799");
    cabGrad.addColorStop(0.45, "#b3bdd0");
    cabGrad.addColorStop(1, "#dce4f2");
    ctx.fillStyle = cabGrad;
    ctx.strokeStyle = "#1c222e";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(-22, -44);
    ctx.lineTo(-26, -68);
    ctx.lineTo(-14, -81);
    ctx.lineTo(0, -84);
    ctx.lineTo(14, -81);
    ctx.lineTo(26, -68);
    ctx.lineTo(22, -44);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Sunlit right cabin facet highlight
    ctx.fillStyle = "rgba(235, 242, 255, 0.35)";
    ctx.beginPath();
    ctx.moveTo(0, -84);
    ctx.lineTo(14, -81);
    ctx.lineTo(26, -68);
    ctx.lineTo(22, -44);
    ctx.lineTo(6, -44);
    ctx.lineTo(6, -83);
    ctx.closePath();
    ctx.fill();

    // Dark thermal shield panels on lower cabin & forehead
    ctx.fillStyle = "#2b3240";
    ctx.fillRect(-19, -50, 11, 5.5);
    ctx.fillRect(8, -50, 11, 5.5);
    ctx.fillRect(-8, -81, 16, 4.5);

    // Canted triangular crew windows (Commander left, LMP right)
    ctx.fillStyle = "#0b1018";
    ctx.strokeStyle = "#525c6e";
    ctx.lineWidth = 1;
    // Left window
    ctx.beginPath();
    ctx.moveTo(-16, -69);
    ctx.lineTo(-4, -73);
    ctx.lineTo(-4, -64);
    ctx.lineTo(-14, -63);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    // Right window
    ctx.beginPath();
    ctx.moveTo(16, -69);
    ctx.lineTo(4, -73);
    ctx.lineTo(4, -64);
    ctx.lineTo(14, -63);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    // Window glass glints
    ctx.strokeStyle = "rgba(150, 205, 255, 0.45)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(-13, -68);
    ctx.lineTo(-6, -71);
    ctx.moveTo(6, -71);
    ctx.lineTo(13, -68);
    ctx.stroke();

    // Forward EVA Hatch (opens during EVA!)
    if (eva && !up) {
      // Open hatch doorway with warm interior cabin rim glow
      ctx.fillStyle = "#080c14";
      ctx.fillRect(-5.2, -59, 10.4, 14);
      ctx.strokeStyle = C.amber;
      ctx.lineWidth = 1.2;
      ctx.strokeRect(-5.2, -59, 10.4, 14);
      // Interior cabin light glow
      var hg2 = ctx.createRadialGradient(0, -52, 1, 0, -52, 9);
      hg2.addColorStop(0, "rgba(242, 177, 60, 0.42)");
      hg2.addColorStop(1, "rgba(242, 177, 60, 0)");
      ctx.fillStyle = hg2;
      ctx.beginPath();
      ctx.arc(0, -52, 9, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.fillStyle = "#8a95a8";
      ctx.strokeStyle = "#2b3240";
      ctx.lineWidth = 1;
      ctx.fillRect(-5.2, -59, 10.4, 14);
      ctx.strokeRect(-5.2, -59, 10.4, 14);
    }

    // RCS thruster quad pods & nozzles (left and right)
    ctx.fillStyle = "#cfd8e6";
    ctx.strokeStyle = "#232834";
    ctx.lineWidth = 1;
    ctx.fillRect(-30, -65, 5, 7);
    ctx.strokeRect(-30, -65, 5, 7);
    ctx.fillRect(25, -65, 5, 7);
    ctx.strokeRect(25, -65, 5, 7);
    // Tiny RCS bells
    ctx.fillStyle = "#454e60";
    ctx.fillRect(-29, -67.5, 2.2, 2.5);
    ctx.fillRect(-29, -58, 2.2, 2.5);
    ctx.fillRect(26.8, -67.5, 2.2, 2.5);
    ctx.fillRect(26.8, -58, 2.2, 2.5);

    // Docking tunnel collar, S-band steerable dish antenna & VHF antennas on roof
    ctx.fillStyle = "#7c8698";
    ctx.fillRect(-8, -86.5, 16, 3);
    // Rendezvous radar & S-band dish mast
    ctx.strokeStyle = "#cfd8e6";
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    ctx.moveTo(9, -83);
    ctx.lineTo(13, -93);
    ctx.moveTo(-6, -84);
    ctx.lineTo(-10, -95);
    ctx.stroke();
    // Parabolic S-band dish pointed toward Earth (upper right)
    ctx.strokeStyle = "#eef4fc";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(14, -94, 5.2, -Math.PI * 0.72, Math.PI * 0.18);
    ctx.stroke();
    ctx.fillStyle = C.amber;
    ctx.beginPath();
    ctx.arc(15.8, -95.8, 1.2, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();

    // 6. EVA Astronaut Choreography (ladder descent -> first step -> surface EVA)
    var bob0 = (state.playing && !reduceMotion) ? Math.abs(Math.sin(performance.now() * 0.0042)) * 2.4 * s : 0;
    var bob1 = (state.playing && !reduceMotion) ? Math.abs(Math.sin(performance.now() * 0.0042 + 1.8)) * 2.2 * s : 0;

    if (eva && !up) {
      if (g < EV["first-step"].get) {
        // Between eva-start and first-step: Armstrong emerges from open hatch and descends the ladder
        var spanStep = Math.max(1, EV["first-step"].get - EV["eva-start"].get);
        var uLad = Math.max(0, Math.min(1, (g - EV["eva-start"].get) / spanStep));
        var ladX = lx + (2 + uLad * 12) * s;
        var ladY = gy - (36 * (1 - uLad)) * s;
        s3_drawSurfaceAstronaut(ladX, ladY, s * 0.92, 0, bob0 * 0.4, true);
        s3_drawPillTag("HATCH OPEN · ON PORCH / LADDER", lx, gy - 98 * s, C.amber, "center", 0.82);
      } else {
        // Armstrong on the surface; Aldrin joins ~20 min later (first-step + 1200)
        s3_drawSurfaceAstronaut(lx + 70 * s, gy, s, 0, bob0, false);
        if (g >= EV["first-step"].get + 1200) {
          s3_drawSurfaceAstronaut(lx + 120 * s, gy, s, 1, bob1, false);
        }
      }
    }

    // 7. US Flag planted at g >= 395520 (~109:52 GET); blown over at liftoff
    if (g >= 395520) {
      var fx = lx + 160 * s, fy = gy;
      ctx.save();
      ctx.translate(fx, fy);
      ctx.scale(s, s);
      if (up) {
        // Blown over by ascent engine exhaust at liftoff
        ctx.rotate(1.32);
      } else {
        // Long low-sun flag shadow to the left
        ctx.fillStyle = "rgba(8, 11, 18, 0.65)";
        ctx.fillRect(-58, -0.5, 58, 1.5);
        ctx.fillRect(-56, -4.5, 22, 4.0);
      }
      // Flagpole + top telescopic crossbar
      ctx.fillStyle = "#e6eef8";
      ctx.fillRect(0, -52, 1.6, 52);
      ctx.fillRect(0, -52, 22, 1.3);
      // US flag (pre-rendered, held out by the rod; no air, so no waving)
      ctx.drawImage(s3_usFlag(20.5 * s, 12.5 * s), 1.6, -51, 20.5, 12.5);
      ctx.restore();
    }

    // 8. Deployed EASEP surface instruments (illustrative) after flag planting
    if (g >= 396600) {
      var eqX = lx + 198 * s, eqY = gy + 4 * s;
      ctx.save();
      ctx.translate(eqX, eqY);
      ctx.scale(s, s);
      // Shadow
      ctx.fillStyle = "rgba(8, 11, 18, 0.6)";
      ctx.fillRect(-18, -0.5, 18, 1.8);
      // Passive Seismic Experiment gold cylindrical body & solar panels
      ctx.fillStyle = "#456496";
      ctx.fillRect(-8, -3, 6, 3);
      ctx.fillRect(2, -3, 6, 3);
      ctx.fillStyle = C.lm;
      ctx.fillRect(-2.5, -5.5, 5, 5.5);
      ctx.restore();
    }

    // 9. Countdown tag just before liftoff (P12 prelaunch window)
    if (preLaunchRem > 0 && preLaunchRem <= 1800) {
      var remMin = Math.floor(preLaunchRem / 60);
      var remSec = Math.floor(preLaunchRem % 60);
      var cdTxt = "P12 LIFTOFF T-" + pad(remMin, 2) + ":" + pad(remSec, 2);
      s3_drawPillTag(cdTxt, lx, gy - 98 * s, C.amber, "center", 0.86);
    } else if (up) {
      s3_drawPillTag("LUNAR LIFTOFF · ASCENT STAGE SEPARATED", lx, gy - 102 * s, C.amber, "center", 0.86);
    }

    // 10. Callout subtitle ("That's one small step...") near bottom of canvas (~4 s of playback)
    var nowPlay = getToPlay(g);
    if (D.callouts && D.callouts.length) {
      var activeCo = null, activeDp = 999;
      for (var ci = 0; ci < D.callouts.length; ci++) {
        var co = D.callouts[ci];
        if (co.get < EV.touchdown.get + 25 || co.get > EV.liftoff.get) continue;
        var dpCo = nowPlay - getToPlay(co.get);
        if (dpCo >= 0 && dpCo <= 4.2) {
          activeCo = co;
          activeDp = dpCo;
        }
      }
      if (activeCo) {
        var coAlpha = activeDp <= 3.2 ? 1 : Math.max(0, 1 - (activeDp - 3.2) / 1.0);
        var spk = activeCo.speaker.toUpperCase() + ": ";
        var quote = "\u201c" + activeCo.text + "\u201d";
        var approxTag = activeCo.approx ? " (time approx.)" : "";
        ctx.save();
        ctx.font = "500 12px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
        var wQuote = ctx.measureText(quote).width;
        ctx.font = "700 12px Barlow Condensed, Arial Narrow, sans-serif";
        var wSpk = ctx.measureText(spk).width;
        ctx.font = "400 10px IBM Plex Sans, Helvetica Neue, Arial, sans-serif";
        var wApp = approxTag ? ctx.measureText(approxTag).width : 0;
        var totalW = Math.min(W - 28, wSpk + wQuote + wApp + 24);
        var scx = W * 0.5;
        var scy = H - 22;

        ctx.globalAlpha = coAlpha;
        ctx.fillStyle = "rgba(9, 13, 21, 0.88)";
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(scx - totalW * 0.5, scy - 15, totalW, 23, 4);
        else ctx.rect(scx - totalW * 0.5, scy - 15, totalW, 23);
        ctx.fill();
        ctx.strokeStyle = C.amber;
        ctx.globalAlpha = coAlpha * 0.45;
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.globalAlpha = coAlpha;
        var tx0 = scx - (wSpk + wQuote + wApp) * 0.5;
        text(spk, tx0, scy + 1, { size: 12, weight: 700, color: C.amber, font: "Barlow Condensed, Arial Narrow, sans-serif" });
        text(quote, tx0 + wSpk, scy + 1, { size: 12, weight: 500, color: C.fg, font: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" });
        if (approxTag) {
          text(approxTag, tx0 + wSpk + wQuote, scy + 1, { size: 10, weight: 400, color: C.muted, font: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" });
        }
        ctx.restore();
      }
    }

    // 11. Header, Note & Surface Clock Readout
    note("Surface view, terrain and astronaut choreography are illustrative; event times from Mission Report.");
    var titleY = W < 520 ? 68 : 48;
    text("TRANQUILITY BASE", 14, titleY, { font: "Barlow Condensed, Arial Narrow, sans-serif", size: 22, weight: 700, color: C.fg });
    text(tr.lat_deg.toFixed(3) + "° N, " + tr.lon_deg.toFixed(3) + "° E · Sea of Tranquility", 14, titleY + 20, { size: 12 });

    var on = Math.max(0, g - EV.touchdown.get);
    var rows = [
      ["On the surface", Math.floor(on / 3600) + " h " + pad(Math.floor(on / 60) % 60, 2) + " m"],
      ["Moonwalk", eva ? "in progress" : g < EV["eva-start"].get ? "not yet" : "done (2 h 31 m)", eva ? C.amber : C.fg]
    ];
    if (preLaunchRem > 0 && preLaunchRem <= 1800) {
      rows.push(["Liftoff", "T-" + pad(Math.floor(preLaunchRem / 60), 2) + ":" + pad(Math.floor(preLaunchRem % 60), 2), C.amber]);
    }
    readout(rows);
  };
