# Mission data additions (explained/live/build.py)

All GETs are seconds from liftoff. "Approx" = not from a simulation or the Mission Report; the JSON carries `approx: true` or the note says so. Everything below is additive; pre-existing keys are unchanged.

| Key (under `data`) | Shape / units | Source | Approx? |
|---|---|---|---|
| `tracks.launch.telemetry` | list of `{key,label,unit,get[],v[]}`: `speed` (m/s inertial), `alt` (km), `hdot` (m/s), `accel_g` (g) | csm_01 `simulate_saturn_v_ascent`, 2 s samples; `accel_g` is the model's sensed thrust acceleration | sim (accel profile is csm_01's labelled 3-stage approximation) |
| `tracks.launch.fpa_deg` | deg, aligned with `launch.get` | sim `gamma_deg` (inertial velocity above local horizontal) | sim |
| `tracks.launch.stages` | list `{id,get,label,approx}`: `ceco` 135, `oeco` 162, `s2-ign` 162, `let` 198, `secoa` 548, `s4-ign` 548, `seco` 700 | csm_01 stage boundaries (sim clock = GET); `s2-ign`/`s4-ign` share the boundary time (no coast modelled); `let` is from memory of the flight plan | `let`, `s2-ign`, `s4-ign`: true |
| `tracks.launch` max-q | omitted | sim has no atmosphere/dynamic pressure | n/a |
| `tracks.lunar-orbit.telemetry` | LOI-1 burn series, `get` = loi-1 + burn time: `loi1_vgo` (m/s), `loi1_dv` (m/s), `loi1_tgo` (s) | csm_04 `simulate_p40_burn` | sim |
| `tracks.lunar-orbit.earth_dir` | unit `[x,y]` in the Moon-centred frame, direction to Earth | chosen so the LOI-1 burn midpoint is behind the Moon | approx |
| `tracks.lunar-orbit.los` | list `{get0,get1,approx}` windows with the CSM behind the Moon (cylinder shadow test along `earth_dir`) around LOI-1 and TEI only | computed from the drawn CSM path | approx (all) |
| `tracks.descent.telemetry` | `alt` (m), `sink` (m/s, negative down), `vh` (m/s), `throttle` (%), `pitch` (deg), `delta_h` (m, radar minus computed; own `get`, only valid samples) | lm_01 `simulate_powered_descent` | sim |
| `tracks.descent.fpa_deg` | deg, aligned with `descent.get` = atan2(v_vert, v_horiz) | sim | sim |
| `tracks.descent.marks` | `radar_lock_get` (first valid delta_h), `throttle_down_get` (first sample < 90 % after >= 90 %), `phases[{id:"P63"..,get}]` start GETs | sim time + PDI | sim |
| `tracks.ascent.telemetry` | `alt` (km), `speed` (m/s, hypot of r_dot and z_dot), `pitch` (deg) | lm_02 `simulate_ascent_p12` | sim |
| `tracks.ascent.fpa_deg` | deg, aligned with `ascent.get` = atan2(r_dot, z_dot) | sim | sim |
| `tracks.rendezvous.telemetry` | `range` (km, hypot of relative x,z), `range_rate` (m/s by finite differencing of range) | lm_03 relative-motion legs on the existing retimed GETs | sim geometry; retiming and braking tail as in the track note (approx) |
| `tracks.entry.telemetry` | `g` (g), `bank` (deg), `speed` (m/s), `alt` (km), `range_to_go` (km); 2 s samples, ends at `sim_end` | csm_05 `simulate_lunar_return_entry` | sim |
| `tracks.entry.fpa_deg`, `roll_deg` | deg, aligned with `entry.get`; after `sim_end` fpa = -90 and roll held at its last value | sim `gamma_deg`, `roll_deg`; tail see `entry.tail_note` | tail: approx |
| `tracks.cislunar.soi_get` / `soi_radius_km` | GET s / 64373.76 km: outbound leg crosses that distance from the Moon | csm_02 samples, retimed, linear interpolation | sim shape, retimed |
| `tracks.cislunar.legs[].v` | m/s, speed relative to Earth, aligned with each leg's `get` | csm_02 `v_earth` | sim |
| `callouts` | list `{get,speaker,text,approx}`, sorted by GET: Eagle has wings, 1202 reading, "go on that alarm", 60 s, 30 s, contact light, Eagle has landed, one small step | air-to-ground transcript wording; GETs tied to `events` where one exists (undocking, touchdown, first-step) | other lines: true |

`validate()` checks: telemetry `get`/`v` lengths equal and `get` strictly increasing, `fpa_deg`/`roll_deg`/`v` align with their `get`, stages/marks/soi/los/callouts sorted and within [0, END], `earth_dir` unit length.
