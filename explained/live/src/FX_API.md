# Apollo 11 Live Canvas & FX API Reference

All helpers in `30-canvas.js` and the `FX` object in `35-fx.js` share the single IIFE scope.
- **Coordinates & Units**: Screen positions (`x`, `y`) and radii (`r`, `rpx`) are in **CSS pixels** (`0..W`, `0..H`, origin top-left, **canvas `+y` is down**, `+x` is right; HiDPI scaling `DPR` is already applied to `ctx`).
- **Angles**: `ang` is in **radians** (`0` = right `+x`, `Math.PI / 2` = down `+y`, `-Math.PI / 2` = up `-y`, matching `Math.atan2(dy, dx)`).
- **Reduced Motion**: When the global `reduceMotion` is `true`, all `FX` calls degrade automatically to static renders or no-ops.

---

## 1. `FX` Object (`35-fx.js`)

### `FX.trail(xs, ys, X, Y, i0, iHead, fHead, color, opts)`
Draws a comet trajectory trail from index `i0` to the exact interpolated head `(iHead, fHead)` where width and alpha ramp up toward the spacecraft, with a soft glow near the head.
- **Units**: `xs, ys` world arrays; `X, Y` world-to-CSS-px functions; `i0, iHead` integer indices; `fHead` fraction `0..1` (`s.f` from `sampleTrack`); `opts`: `{ width: 2.4, tail: 60, alpha: 1, baseAlpha: 0.25, glow: true }`.
```js
var s = sampleTrack(tr.get, [["x", tr.x], ["y", tr.y]], g);
FX.trail(tr.x, tr.y, c.X, c.Y, 0, s.i, s.f, C.csm, { width: 2.4, tail: 50 });
```

### `FX.exhaust(x, y, ang, power01, opts)`
Renders a flickering additive (`'lighter'`) core flame (hot white to amber) and spawns throttle-scaled pooled exhaust particles streaming behind the spacecraft.
- **Units**: `x, y` CSS px; `ang` craft forward/thrust heading in radians (exhaust shoots along `ang + Math.PI`; pass `opts.nozzleAngle: true` if `ang` is already the nozzle exit direction); `power01` throttle `0..1`; `opts`: `{ color: C.amber, scale: 1, offset: 5, spread: 0.42, nozzleAngle: false }`.
```js
var ang = Math.atan2(c.Y(tr.y[j]) - py, c.X(tr.x[j]) - px);
FX.exhaust(px, py, ang, s.th, { color: C.amber, scale: 1.1 });
```

### `FX.craft(kind, x, y, ang, scale, opts)`
Draws a crisp vector spacecraft silhouette centered at `(x, y)` rotated by `ang`, optionally firing its engine plume.
- **Kinds**: `'saturn-v'`, `'csm-sivb'`, `'csm-lm'`, `'csm'`, `'lm'`, `'lm-ascent'`, `'cm'`.
- **Units**: `x, y` CSS px; `ang` nose heading in radians (`0` = `+x` right; pass `opts.upright: true` if `ang = 0` means nose up `-y`); `scale` multiplier (`1` = 24 px) or pixel size (`16..48`); `opts`: boolean (`engineOn`), number (`throttle 0..1`), or `{ engine: bool, throttle: 0..1, upright: bool, color: hex }`.
```js
var ang = Math.atan2(M.Y(tr.y[j]) - py, M.X(tr.x[j]) - px);
FX.craft("csm-lm", px, py, ang, 1.1, { engine: !!burnActive(tr.burns, g), throttle: 1.0 });
```

### `FX.ping(x, y, color)`
Spawns an expanding dual-ring telemetry pulse at `(x, y)` in CSS px (auto-drawn in the post-scene overlay pass).
```js
var ex = c.X(q.x), ey = c.Y(q.y);
FX.ping(ex, ey, C.amber);
```

### `FX.flash(color, strength)`
Triggers a brief full-canvas tint overlay that decays over ~350 ms (`strength` alpha `0..0.45`, default `0.16`).
```js
if (g >= EV.touchdown.get && g - dt < EV.touchdown.get) FX.flash(C.amber, 0.14);
```

### `FX.shake(strength)`
Triggers a decaying camera shake in CSS px (`strength` amplitude `0..14`, default `4`), applied to `ctx` by `90-main.js` via `FX.shakeX` and `FX.shakeY`.
```js
if (alarmTriggered) FX.shake(4.5);
```

### `FX.dust(x, y, strength)`
Sprays low-angle lunar regolith dust particles left and right along the surface from `(x, y)` in CSS px (`strength` `0..2`, default `1`).
```js
if (!landed && s.y < 0.04) FX.dust(px, c.Y(0), (1 - s.y / 0.04) * s.th);
```

### `FX.glowDot(x, y, r, color)`
Draws an immediate glowing telemetry dot at `(x, y)` in CSS px with core radius `r` (CSS px, default `3.5`) and soft radial halo.
```js
var sx = M.X(site.x), sy = M.Y(site.y);
FX.glowDot(sx, sy, 3.5, C.amber);
```

### `FX.vignette()` / `FX.scanline(opts)` / `FX.grid(opts)`
Post-scene scope overlays covering `0..W, 0..H` CSS px (`FX.vignette()` is called automatically by `90-main.js` after every scene and flushes any remaining particles/pings/flashes).
```js
FX.scanline({ alpha: 0.5 });
FX.grid({ step: 80, alpha: 0.15 });
```

### `FX.tick(dt, playing)` / `FX.reset()` / `FX.isActive()` / `FX.onEvent(ev)`
Lifecycle hooks managed by `90-main.js` (`dt` in seconds). `FX.reset()` clears particles on seek jumps `> 1.5 s`; `FX.onEvent(ev)` triggers ping/flash/shake when crossing mission events during playback.
```js
var alive = FX.tick(dt, state.playing);
if (Math.abs(state.play - lastPlay) > 1.5) FX.reset();
```

---

## 2. Upgraded Canvas Helpers (`30-canvas.js`)

### `smooth(target, scene, dt)`
Critically damped spring camera easing per numeric property of `target` (`dt` in seconds); snaps immediately when `scene` changes or under `reduceMotion`.
```js
var v = smooth({ cx: 0, cy: 0, span: Math.max(17000, r * 2.6) }, "earth-orbit", dt);
var M = mapXf(v);
```

### `drawStars()`
Draws a cached 3-layer starfield with a faint diagonal Milky Way band, subtle camera-view parallax, and gentle star twinkle across `0..W, 0..H` CSS px.
```js
drawStars();
body(M.X(0), M.Y(0), 6378 * M.s, C.earth, "Earth");
```

### `body(x, y, rpx, color, name)`
Renders procedural Earth (continents, ocean glint, cloud wisps, terminator, atmosphere rim glow) or Moon (maria, craters, limb darkening) cached by radius bucket; radii `< 6` CSS px render as glowing discs.
```js
body(M.X(0), M.Y(0), tr.r_earth * M.s, C.earth, "Earth");
body(M.X(tr.moon[0]), M.Y(0), tr.r_moon * M.s, C.moon, "Moon");
```

### `polyline(xs, ys, X, Y, i0, i1, color, width, dash, alpha)`
Strokes `xs[i0..i1], ys[i0..i1]` mapped through `X, Y` in CSS px; solid paths (`!dash || !dash.length`) automatically receive a soft dual-layer glow underlay.
```js
polyline(tr.x, tr.y, c.X, c.Y, 0, tr.x.length - 1, C.csm, 1, [4, 5], 0.35);
polyline(tr.x, tr.y, c.X, c.Y, 0, s.i, C.csm, 2.2);
```

### `marker(x, y, color, name, opts)`
Draws a spacecraft reticle at `(x, y)` CSS px with soft glow, pulsing halo ring, and uppercase label over a dark pill backing (`opts`: `{ dx: 10, dy: -10, align: "left" }`).
```js
var px = M.X(s.x), py = M.Y(s.y);
marker(px, py, C.csm, "Columbia", { dx: 10, dy: -10 });
```

### `plume(x, y, ang, color)`
Draws particle-based additive engine exhaust behind `(x, y)` CSS px opposite to `ang` (radians), delegating to `FX.exhaust`.
```js
var ang = Math.atan2(c.Y(tr.y[j]) - py, c.X(tr.x[j]) - px);
plume(px, py, ang, C.amber);
```
