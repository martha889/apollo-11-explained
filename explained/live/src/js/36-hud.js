  // ---------- live telemetry strip charts (HUD) ----------
  var HUD = (function () {
    var cache = {};

    var SCENE_CONFIG = {
      launch: {
        craft: "csm",
        series: [
          { key: "speed", label: "SPEED", unit: "m/s", dec: 0 },
          { key: "alt", label: "ALTITUDE", unit: "km", dec: 1 },
          { key: "accel_g", label: "ACCEL", unit: "g", dec: 2, alarmAbove: 5.0 }
        ]
      },
      descent: {
        craft: "lm",
        series: [
          { key: "alt", label: "ALTITUDE", unit: "m", dec: 0 },
          { key: "sink", label: "SINK RATE", unit: "m/s", dec: 1 },
          { key: "throttle", label: "THROTTLE", unit: "%", dec: 0 },
          { key: "pitch", label: "PITCH", unit: "°", dec: 1 }
        ]
      },
      ascent: {
        craft: "lm",
        series: [
          { key: "alt", label: "ALTITUDE", unit: "km", dec: 1 },
          { key: "speed", label: "SPEED", unit: "m/s", dec: 0 },
          { key: "pitch", label: "PITCH", unit: "°", dec: 1 }
        ]
      },
      rendezvous: {
        craft: "lm",
        series: [
          { key: "range", label: "RANGE", unit: "km", dec: 1 },
          { key: "range_rate", label: "RANGE RATE", unit: "m/s", dec: 1 }
        ]
      },
      entry: {
        craft: "csm",
        series: [
          { key: "g", label: "G-LOAD", unit: "g", dec: 2, alarmAbove: 5.0 },
          { key: "bank", label: "BANK", unit: "°", dec: 0 },
          { key: "speed", label: "SPEED", unit: "m/s", dec: 0 }
        ]
      },
      "lunar-orbit": {
        craft: "csm",
        windowOnly: true,
        series: [
          { key: "loi1_vgo", label: "LOI-1 VGO", unit: "m/s", dec: 1 },
          { key: "loi1_dv", label: "LOI-1 ΔV", unit: "m/s", dec: 1 }
        ]
      }
    };

    function findRawSeries(tr, key) {
      if (!tr || !tr.telemetry) return null;
      for (var i = 0; i < tr.telemetry.length; i++) {
        var sr = tr.telemetry[i];
        if (sr.key === key) return sr;
      }
      if (key === "altitude") return findRawSeries(tr, "alt");
      if (key === "vgo") return findRawSeries(tr, "loi1_vgo");
      if (key === "dv") return findRawSeries(tr, "loi1_dv");
      return null;
    }

    function ensureSceneCache(sceneName) {
      if (cache[sceneName]) return cache[sceneName];
      var cfg = SCENE_CONFIG[sceneName];
      var tr = T && T[sceneName];
      if (!cfg || !tr || !tr.telemetry) return null;

      var items = [];
      for (var i = 0; i < cfg.series.length; i++) {
        var sc = cfg.series[i];
        var raw = findRawSeries(tr, sc.key);
        if (!raw || !raw.get || !raw.v || raw.get.length < 2) continue;

        var gArr = raw.get, vArr = raw.v, n = gArr.length;
        var vMin = Infinity, vMax = -Infinity;
        for (var j = 0; j < n; j++) {
          var vj = vArr[j];
          if (vj < vMin) vMin = vj;
          if (vj > vMax) vMax = vj;
        }
        if (!isFinite(vMin) || !isFinite(vMax)) continue;

        // Decimate to ~96 points max while preserving min/max peaks and endpoints
        var maxPts = 96;
        var decIdx = [];
        if (n <= maxPts) {
          for (var k = 0; k < n; k++) decIdx.push(k);
        } else {
          var step = (n - 1) / (maxPts - 1);
          var prevIdx = -1;
          for (var m = 0; m < maxPts; m++) {
            var idx = Math.min(n - 1, Math.round(m * step));
            if (idx !== prevIdx) {
              decIdx.push(idx);
              prevIdx = idx;
            }
          }
          // Ensure exact global extrema indices are included
          var iMin = 0, iMax = 0;
          for (var q = 0; q < n; q++) {
            if (vArr[q] === vMin) iMin = q;
            if (vArr[q] === vMax) iMax = q;
          }
          if (decIdx.indexOf(iMin) < 0) decIdx.push(iMin);
          if (decIdx.indexOf(iMax) < 0) decIdx.push(iMax);
          decIdx.sort(function (a, b) { return a - b; });
        }

        var dGet = new Array(decIdx.length);
        var dU = new Array(decIdx.length);
        var dN = new Array(decIdx.length);
        var dV = new Array(decIdx.length);
        var g0 = gArr[0], g1 = gArr[n - 1];
        var gSpan = Math.max(1e-6, g1 - g0);
        var vSpan = Math.max(1e-6, vMax - vMin);

        for (var p = 0; p < decIdx.length; p++) {
          var di = decIdx[p];
          dGet[p] = gArr[di];
          dV[p] = vArr[di];
          dU[p] = (gArr[di] - g0) / gSpan;
          dN[p] = (vArr[di] - vMin) / vSpan;
        }

        items.push({
          key: sc.key,
          label: sc.label,
          unit: sc.unit || raw.unit || "",
          dec: sc.dec || 0,
          alarmAbove: sc.alarmAbove || null,
          get: gArr,
          v: vArr,
          g0: g0,
          g1: g1,
          gSpan: gSpan,
          vMin: vMin,
          vMax: vMax,
          vSpan: vSpan,
          dGet: dGet,
          dV: dV,
          dU: dU,
          dN: dN
        });
      }

      var entry = {
        craft: cfg.craft,
        windowOnly: !!cfg.windowOnly,
        items: items
      };
      cache[sceneName] = entry;
      return entry;
    }

    function fmtVal(v, dec) {
      if (!isFinite(v)) return "0";
      if (Math.abs(v) < 1e-4) v = 0;
      if (dec <= 0) return Math.round(v).toLocaleString("en-US");
      return v.toFixed(dec);
    }

    function fmtBound(v, dec) {
      if (!isFinite(v)) return "0";
      if (Math.abs(v) < 1e-4) v = 0;
      if (Math.abs(v) >= 100 || dec <= 0) return String(Math.round(v));
      return v.toFixed(1);
    }

    function computePlacement(sceneName, count, sw, sh, gap, g) {
      var totalH = count * sh + (count - 1) * gap;
      var x = W - sw - 24;
      var y = H - 52 - totalH;

      if (sceneName === "launch") {
        // Bottom-right inside plot area (above sea band yGround ~ H - 62)
        x = W - sw - 26;
        y = H - 68 - totalH;
      } else if (sceneName === "descent") {
        // Bottom-left above the existing mini-HUD box (which sits at gy - 84 .. gy - 26)
        x = 70;
        y = Math.min(H - 138 - totalH, Math.max(82, H - 142 - totalH));
      } else if (sceneName === "ascent") {
        // Bottom-right inside plot area above lunar terrain silhouette
        x = W - sw - 26;
        y = H - 66 - totalH;
      } else if (sceneName === "rendezvous") {
        // Upper-right neatly stacked directly under the readout block (readout ends at ~y=88)
        // Keeps the right margin uncluttered, leaves the craft at center untouched,
        // and keeps the bottom-right completely clear for Earthrise and the Moon.
        x = W - sw - 14;
        y = 100;
      } else if (sceneName === "entry") {
        // Bottom-left inside plot area above Pacific Ocean band
        x = 70;
        y = H - 68 - totalH;
      } else if (sceneName === "lunar-orbit") {
        // Bottom-left above the 500 km scaleBar (which sits at y = H - 16)
        x = 14;
        y = H - 38 - totalH;
      }

      // Never overlap top-right readout (y < 126 on right side) or top-left note (y < 52 on left side)
      // When placed under the readout in rendezvous, y = 100 is intentional and safe
      if (sceneName !== "rendezvous") {
        var minTop = (x + sw > W * 0.55) ? 124 : 52;
        if (y < minTop) y = minTop;
      }
      return { x: Math.round(x), y: Math.round(y), totalH: totalH };
    }

    function drawStripCard(item, x, y, sw, sh, g, baseColor) {
      var s = sampleTrack(item.get, [["v", item.v]], g);
      var val = s.v;
      var uNow = Math.max(0, Math.min(1, (g - item.g0) / item.gSpan));
      var nNow = Math.max(0, Math.min(1, (val - item.vMin) / item.vSpan));

      var isAlarm = item.alarmAbove !== null && val > item.alarmAbove;
      var strokeCol = isAlarm ? C.alarm : baseColor;

      // Translucent dark rounded backing
      ctx.save();
      ctx.fillStyle = "rgba(9, 13, 21, 0.80)";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, sw, sh, 4);
      else ctx.rect(x, y, sw, sh);
      ctx.fill();
      ctx.strokeStyle = isAlarm ? C.alarm : C.line;
      ctx.globalAlpha = isAlarm ? 0.65 : 0.75;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();

      // Header row: label on left, current value + unit on right
      text(item.label, x + 6, y + 10.5, {
        size: 9.5,
        weight: 600,
        color: isAlarm ? C.alarm : C.muted,
        font: "Barlow Condensed, Arial Narrow, sans-serif",
        align: "left"
      });
      var valStr = fmtVal(val, item.dec) + (item.unit ? " " + item.unit : "");
      text(valStr, x + sw - 6, y + 10.5, {
        size: 10.5,
        weight: 500,
        color: isAlarm ? C.alarm : C.fg,
        font: "IBM Plex Mono, monospace",
        align: "right"
      });

      // Sparkline plot box
      var px0 = x + 6, px1 = x + sw - 30;
      var py0 = y + 14.5, py1 = y + sh - 4.5;
      var pw = Math.max(10, px1 - px0), ph = Math.max(6, py1 - py0);

      // Faint min / max labels at right margin of sparkline
      text(fmtBound(item.vMax, item.dec), x + sw - 5, py0 + 5, {
        size: 8,
        weight: 400,
        color: C.faint,
        font: "IBM Plex Mono, monospace",
        align: "right"
      });
      text(fmtBound(item.vMin, item.dec), x + sw - 5, py1, {
        size: 8,
        weight: 400,
        color: C.faint,
        font: "IBM Plex Mono, monospace",
        align: "right"
      });

      // Subtle zero reference line if range spans negative to positive
      if (item.vMin < 0 && item.vMax > 0) {
        var nZero = (0 - item.vMin) / item.vSpan;
        var yZero = py1 - nZero * ph;
        ctx.save();
        ctx.strokeStyle = C.line;
        ctx.globalAlpha = 0.5;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(px0, yZero);
        ctx.lineTo(px1, yZero);
        ctx.stroke();
        ctx.restore();
      }

      // 5g threshold line on g-load strips if max > 5
      if (item.alarmAbove !== null && item.vMax >= item.alarmAbove) {
        var n5 = (item.alarmAbove - item.vMin) / item.vSpan;
        var y5 = py1 - n5 * ph;
        ctx.save();
        ctx.strokeStyle = C.alarm;
        ctx.globalAlpha = 0.32;
        ctx.lineWidth = 0.8;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(px0, y5);
        ctx.lineTo(px1, y5);
        ctx.stroke();
        ctx.restore();
      }

      var dU = item.dU, dN = item.dN, dGet = item.dGet, dLen = dU.length;

      // 1. Full series as a dim line
      ctx.save();
      ctx.beginPath();
      for (var i = 0; i < dLen; i++) {
        var sx = px0 + dU[i] * pw;
        var sy = py1 - dN[i] * ph;
        if (i === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      }
      ctx.strokeStyle = baseColor;
      ctx.globalAlpha = 0.24;
      ctx.lineWidth = 1.1;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.restore();

      // 2. Part already flown as a bright glowing line up to exact interpolated cursor (cx, cy)
      var cx = px0 + uNow * pw;
      var cy = py1 - nNow * ph;

      if (g > item.g0) {
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(px0 + dU[0] * pw, py1 - dN[0] * ph);
        for (var j = 1; j < dLen; j++) {
          if (dGet[j] >= g) break;
          ctx.lineTo(px0 + dU[j] * pw, py1 - dN[j] * ph);
        }
        ctx.lineTo(cx, cy);
        ctx.strokeStyle = strokeCol;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        // Soft glow pass
        ctx.lineWidth = 3.8;
        ctx.globalAlpha = 0.22;
        ctx.stroke();
        // Crisp bright core pass
        ctx.lineWidth = 1.65;
        ctx.globalAlpha = 0.95;
        ctx.stroke();
        ctx.restore();
      }

      // 3. Moving cursor dot
      ctx.save();
      ctx.fillStyle = strokeCol;
      ctx.globalAlpha = 0.28;
      ctx.beginPath();
      ctx.arc(cx, cy, 4.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, 2.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(cx, cy, 1.0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    var api = {
      enabled: true,
      strips: function (sceneName, g) {
        if (!api.enabled) return;
        if (W < 380 || H < 280) return;

        var entry = ensureSceneCache(sceneName);
        if (!entry || !entry.items.length) return;

        // For lunar-orbit, only draw while g is inside the LOI-1 telemetry window
        if (entry.windowOnly) {
          var w0 = entry.items[0].g0, w1 = entry.items[0].g1;
          if (g < w0 || g > w1) return;
        }

        var maxCount = (W < 560 || H < 420) ? 2 : entry.items.length;
        var count = Math.min(maxCount, entry.items.length);
        if (count <= 0) return;

        var sw = W < 560 ? 152 : 168;
        var sh = 34;
        var gap = 4;
        var pos = computePlacement(sceneName, count, sw, sh, gap, g);
        var baseColor = entry.craft === "lm" ? C.lm : C.csm;

        ctx.save();
        for (var i = 0; i < count; i++) {
          var sy = pos.y + i * (sh + gap);
          drawStripCard(entry.items[i], pos.x, sy, sw, sh, g, baseColor);
        }
        ctx.restore();
      }
    };

    return api;
  })();
