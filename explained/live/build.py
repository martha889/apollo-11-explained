"""Build the Apollo 11 live mission viewer.

Runs the simulations in explained/, samples them onto the real Apollo 11
timeline (ground elapsed time, GET, in seconds from launch at
1969-07-16 13:32:00 UTC), pulls the matching AGC source lines straight out of
Comanche055/ and Luminary099/, and injects everything into template.html.

    python explained/live/build.py                     # -> explained/live/apollo11_live.html
    python explained/live/build.py --fragment OUT.html # page without <html>/<head>/<body>
    python explained/live/build.py --json OUT.json     # also dump the data

Event times come from the Apollo 11 Mission Report. Where a simulation's
internal clock differs from the real flight, its samples are retimed
piecewise-linearly onto the real GET; the page says so wherever that happens.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import inspect
import io
import json
import math
import sys
from pathlib import Path

import numpy as np

LIVE = Path(__file__).resolve().parent
EXPLAINED = LIVE.parent
REPO = EXPLAINED.parent
sys.path.insert(0, str(EXPLAINED))

import csm_01_earth_orbit_p11 as m_p11  # noqa: E402
import csm_02_conics_coast as m_coast  # noqa: E402
import csm_03_imu_alignment_p52 as m_p52  # noqa: E402
import csm_04_burns_p30_p40 as m_burn  # noqa: E402
import csm_05_entry_p61_p67 as m_entry  # noqa: E402
import lm_01_powered_descent as m_desc  # noqa: E402
import lm_02_ascent_p12 as m_asc  # noqa: E402
import lm_03_rendezvous as m_rdz  # noqa: E402
import agc_01_executive_waitlist as m_exec  # noqa: E402
from common import MU_EARTH, MU_MOON, R_EARTH, R_MOON  # noqa: E402

FT = 3.280839895
NMI = 1852.0


def get(h: int, m: int, s: float) -> float:
    return h * 3600 + m * 60 + s


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def r1(a, nd=1):
    return [round(float(v), nd) for v in a]


# ---------------------------------------------------------------------------
# Real timeline (Apollo 11 Mission Report, GET)
# ---------------------------------------------------------------------------
PDI = get(102, 33, 5)
LIFTOFF = get(124, 22, 1)
EI = get(195, 3, 6)
EVENTS = [
    ("launch", 0, "Launch", "Launch", "CM", "Saturn V lifts off from Pad 39A at 13:32 UTC; the CM computer runs P11 to monitor the climb."),
    ("orbit-insertion", get(0, 11, 49), "Earth orbit insertion", "Orbit", "CM", "S-IVB cutoff leaves Apollo 11 in a ~185 km parking orbit."),
    ("tli", get(2, 44, 16), "Translunar injection", "TLI", "CM", "The S-IVB fires for 5 min 47 s, raising speed to ~10.8 km/s toward the Moon."),
    ("docking-lm", get(3, 24, 3), "Transposition and docking", "T&D", "CM", "Collins turns Columbia around and docks with Eagle on top of the S-IVB."),
    ("mcc-2", get(26, 44, 58), "Midcourse correction 2", "MCC-2", "CM", "A 3-second SPS burn (~6.4 m/s) trims the path toward the Moon."),
    ("loi-1", get(75, 49, 50), "Lunar orbit insertion 1", "LOI-1", "CM", "Behind the Moon, the SPS burns 357.5 s to brake into lunar orbit."),
    ("loi-2", get(80, 11, 36), "Lunar orbit insertion 2", "LOI-2", "CM", "A 17-second burn rounds the orbit to roughly 100 x 122 km."),
    ("undocking", get(100, 12, 0), "Undocking", "Undock", "LM", "Eagle undocks from Columbia: \"The Eagle has wings.\""),
    ("doi", get(101, 36, 14), "Descent orbit insertion", "DOI", "LM", "Eagle's descent engine lowers perilune to ~15 km, ahead of the landing site."),
    ("pdi", PDI, "Powered descent initiation", "PDI", "LM", "At ~15 km altitude the descent engine lights for the 12.5-minute landing."),
    ("alarm-1202", PDI + 317, "Program alarm 1202", "1202", "LM", "The Executive runs out of core sets and restarts; guidance carries on."),
    ("p64", get(102, 41, 32), "P64 approach phase", "P64", "LM", "High gate: Eagle pitches up and the crew sees the landing area."),
    ("alarm-1201", PDI + 553, "Program alarm 1201", "1201", "LM", "The Executive runs out of VAC areas; another software restart."),
    ("p66", get(102, 43, 20), "P66 manual descent", "P66", "LM", "Armstrong takes semi-manual control to fly past a boulder field."),
    ("touchdown", get(102, 45, 40), "Touchdown", "Landing", "LM", "\"Houston, Tranquility Base here. The Eagle has landed.\""),
    ("eva-start", get(109, 7, 33), "EVA begins", "EVA", "LM", "The hatch opens for the moonwalk."),
    ("first-step", get(109, 24, 20), "First step", "Step", "LM", "Armstrong steps onto the surface."),
    ("eva-end", get(111, 39, 13), "EVA ends", "EVA end", "LM", "Hatch closed after 2 h 31 min outside."),
    ("liftoff", LIFTOFF, "Lunar liftoff", "Liftoff", "LM", "The ascent stage lifts off; P12 steers it into lunar orbit."),
    ("csi", get(125, 19, 35), "Concentric sequence initiation", "CSI", "LM", "First rendezvous burn, near apolune, sets up a constant height below Columbia."),
    ("cdh", get(126, 17, 46), "Constant delta height", "CDH", "LM", "Small burn that makes Eagle's orbit coelliptic with Columbia's."),
    ("tpi", get(126, 57, 0), "Terminal phase initiation", "TPI", "LM", "Eagle thrusts along the line of sight to intercept Columbia."),
    ("docking", get(128, 3, 0), "Docking in lunar orbit", "Dock", "CM", "Eagle and Columbia dock again; the crew transfers with the samples."),
    ("lm-jettison", get(130, 9, 31), "LM jettison", "Jettison", "CM", "The empty ascent stage is released and its computer goes quiet."),
    ("tei", get(135, 23, 42), "Transearth injection", "TEI", "CM", "Behind the Moon, a 2.5-minute SPS burn heads Columbia home."),
    ("mcc-5", get(150, 29, 57), "Midcourse correction 5", "MCC-5", "CM", "The only return correction: a 10-second burn."),
    ("cm-sm-sep", get(194, 49, 12), "CM/SM separation", "CM/SM sep", "CM", "The service module is jettisoned; the CM turns heat-shield forward."),
    ("entry-interface", EI, "Entry interface", "EI", "CM", "400,000 ft at 11.0 km/s: the computer flies the entry with P63 to P67."),
    ("splashdown", get(195, 18, 35), "Splashdown", "Splash", "CM", "Columbia lands in the Pacific near USS Hornet."),
]
EV = {e[0]: e[1] for e in EVENTS}
END = EV["splashdown"] + 60
LM_ON = get(96, 0, 0)  # approx.: LM computer powered up for checkout
LM_OFF = EV["lm-jettison"]


# ---------------------------------------------------------------------------
# Phases and the playback time map
# ---------------------------------------------------------------------------
def build_phases():
    P = [
        ("launch", "Launch and climb to orbit", 0, EV["orbit-insertion"], "launch", "CM", 28),
        ("earth-orbit", "Earth parking orbit and TLI", EV["orbit-insertion"], EV["tli"] + 347 + 1800, "earth-orbit", "CM", 26),
        ("translunar", "Translunar coast", EV["tli"] + 347 + 1800, EV["loi-1"] - 1800, "cislunar", "CM", 36),
        ("loi", "Lunar orbit insertion", EV["loi-1"] - 1800, EV["loi-2"] + 1800, "lunar-orbit", "CM", 26),
        ("lunar-orbit", "Lunar orbit, undocking and DOI", EV["loi-2"] + 1800, PDI, "lunar-orbit", "LM", 22),
        ("descent", "Powered descent and landing", PDI, EV["touchdown"] + 30, "descent", "LM", 95),
        ("surface", "Tranquility Base", EV["touchdown"] + 30, LIFTOFF, "surface", "LM", 18),
        ("ascent", "Ascent to lunar orbit", LIFTOFF, LIFTOFF + 494, "ascent", "LM", 24),
        ("rendezvous", "Rendezvous and docking", LIFTOFF + 494, EV["docking"] + 300, "rendezvous", "LM", 32),
        ("lunar-orbit-2", "Last lunar orbits and TEI", EV["docking"] + 300, EV["tei"] + 151 + 1800, "lunar-orbit", "CM", 20),
        ("transearth", "Transearth coast", EV["tei"] + 151 + 1800, EV["cm-sm-sep"], "cislunar", "CM", 28),
        ("entry", "Entry and splashdown", EV["cm-sm-sep"], END, "entry", "CM", 42),
    ]
    phases = [dict(id=i, name=n, get_start=a, get_end=b, scene=s, active_computer=c, playback_s=p) for i, n, a, b, s, c, p in P]
    # Time map knots: (GET, playback seconds). Linear inside each phase, except
    # short burns get extra playback time so they don't flash past.
    slow = {  # (get_start, get_end, playback seconds)
        "earth-orbit": [(EV["tli"] - 120, EV["tli"] + 347 + 120, 10)],
        "loi": [(EV["loi-1"] - 60, EV["loi-1"] + 358 + 60, 12), (EV["loi-2"] - 30, EV["loi-2"] + 47, 3)],
        "lunar-orbit": [(EV["undocking"] - 60, EV["undocking"] + 600, 4), (EV["doi"] - 60, EV["doi"] + 90, 4)],
        "lunar-orbit-2": [(EV["lm-jettison"] - 120, EV["lm-jettison"] + 600, 3), (EV["tei"] - 60, EV["tei"] + 151 + 60, 8)],
        "translunar": [(EV["mcc-2"] - 300, EV["mcc-2"] + 300, 3)],
        "transearth": [(EV["mcc-5"] - 300, EV["mcc-5"] + 300, 3)],
        "surface": [(EV["eva-start"], EV["eva-end"], 7)],
        "rendezvous": [(EV["tpi"] - 60, EV["docking"] + 300, 14)],
    }
    knots = [(0.0, 0.0)]
    tp = 0.0
    for ph in phases:
        a, b, total = ph["get_start"], ph["get_end"], ph["playback_s"]
        segs = slow.get(ph["id"], [])
        slow_play = sum(s[2] for s in segs)
        slow_get = sum(s[1] - s[0] for s in segs)
        rate = (total - slow_play) / ((b - a) - slow_get)  # playback s per GET s outside slow segments
        cur = a
        for s0, s1, sp in sorted(segs):
            tp += (s0 - cur) * rate
            knots.append((s0, tp))
            tp += sp
            knots.append((s1, tp))
            cur = s1
        tp += (b - cur) * rate
        knots.append((b, tp))
    out = []
    for g, t in knots:
        if out and abs(out[-1][0] - g) < 1e-9:
            continue
        out.append([round(g, 1), round(t, 3)])
    return phases, out


def retime(t_sim, sim_knots, real_knots):
    """Piecewise-linear map from simulation time to real GET."""
    return np.interp(t_sim, sim_knots, real_knots)


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------
def track_launch(dsky):
    s = quiet(m_p11.simulate_saturn_v_ascent)
    t = s["t"]
    # Downrange (approx.): integrate horizontal speed relative to the rotating
    # Earth (KSC surface speed ~408 m/s; 72 deg azimuth -> ~390 m/s eastward along track),
    # projected to the surface.
    vh = np.sqrt(np.maximum(s["vi_m_s"] ** 2 - s["hdot_m_s"] ** 2, 0.0)) - 390.0
    vh = np.maximum(vh, 0.0)
    alt = s["alt_km"] * 1000.0
    ds = vh * R_EARTH / (R_EARTH + alt)
    x = np.concatenate([[0.0], np.cumsum(0.5 * (ds[1:] + ds[:-1]) * np.diff(t))]) / 1000.0
    idx = np.arange(0, len(t), 2)
    tr = dict(frame="Altitude vs downrange from the launch pad", x_label="Downrange (km, approx.)", y_label="Altitude (km)",
              get=r1(t[idx]), x=r1(x[idx]), y=r1(s["alt_km"][idx], 2), v=r1(s["vi_m_s"][idx], 0),
              note="Saturn V climb from the P11 simulation (csm_01). Downrange is reconstructed from speed, approx.")
    for i in range(0, len(t), 1):
        if t[i] % 2:
            continue
        dsky.append(dict(get=float(t[i]), computer="CM", prog="11", verb="06", noun="62",
                         r=[reg(s["vi_fps"][i], 0), reg(s["hdot_fps"][i], 0), reg(s["alt_nm"][i] * 10, 0)],
                         lights=[], flash=False, simulated=True,
                         caption="P11 launch monitor, V06N62: inertial velocity (ft/s), altitude rate (ft/s), altitude (nmi, xxxx.x)."))
    return tr


def free_return():
    """Reproduce the csm_02 free-return figure-8 (see csm_02_conics_coast.main)."""
    d_moon = 384_400_000.0
    omega = math.sqrt((MU_EARTH + MU_MOON) / d_moon ** 3)
    t_peri = 69.3167 * 3600.0
    th0 = math.radians(52.8757)

    def moon(ts):
        th = th0 + omega * ts
        return (np.array([d_moon * math.cos(th), d_moon * math.sin(th), 0.0]),
                d_moon * omega * np.array([-math.sin(th), math.cos(th), 0.0]))

    th_mp = th0 + omega * t_peri
    u = np.array([math.cos(th_mp), math.sin(th_mp), 0.0])
    tv = np.array([-math.sin(th_mp), math.cos(th_mp), 0.0])
    r = (d_moon + R_MOON + 210_000.0) * u
    v = (d_moon * omega - 2_494.12) * tv

    def acc(p, ts):
        rm, _ = moon(ts)
        dm = p - rm
        return -MU_EARTH * p / np.linalg.norm(p) ** 3 - MU_MOON * (dm / np.linalg.norm(dm) ** 3 + rm / d_moon ** 3)

    h = -60.0
    for k in range(int(round(t_peri / 60.0))):
        tc = t_peri + k * h
        a1 = acc(r, tc)
        r2, v2 = r + 0.5 * h * v, v + 0.5 * h * a1
        a2 = acc(r2, tc + 0.5 * h)
        r3, v3 = r + 0.5 * h * v2, v + 0.5 * h * a2
        a3 = acc(r3, tc + 0.5 * h)
        r4, v4 = r + h * v3, v + h * a3
        a4 = acc(r4, tc + h)
        r = r + (h / 6) * (v + 2 * v2 + 2 * v3 + v4)
        v = v + (h / 6) * (a1 + 2 * a2 + 2 * a3 + a4)
    data = quiet(m_coast.encke_translunar_propagate, r, v, moon, 2.0 * t_peri, 60.0)
    return data, moon, th0, omega, t_peri


def track_cislunar_and_orbit(fr):
    data, moon, th0, omega, t_peri = fr
    t = data["t"]
    re = data["r_earth"]
    th = th0 + omega * t
    c, s = np.cos(-th), np.sin(-th)
    xr = (c * re[:, 0] - s * re[:, 1]) / 1000.0
    yr = (s * re[:, 0] + c * re[:, 1]) / 1000.0
    dist_moon = np.hypot(xr - 384_400.0, yr)
    keep = np.zeros(len(t), bool)
    keep[::6] = True
    keep[dist_moon < 60_000] = True
    keep[np.hypot(xr, yr) < 40_000] = True
    keep[-1] = True
    out_m = keep & (t <= t_peri)
    ret_m = keep & (t >= t_peri)
    tli_end = EV["tli"] + 347
    g_out = retime(t[out_m], [0, t_peri], [tli_end, EV["loi-1"]])
    g_ret = retime(t[ret_m], [t_peri, t[-1]], [EV["tei"] + 151, EI])
    cis = dict(frame="Earth-Moon rotating frame (Moon fixed on the right), km", earth=[0, 0], moon=[384_400, 0],
               r_earth=6378, r_moon=1737,
               legs=[dict(id="outbound", get=r1(g_out), x=r1(xr[out_m], 0), y=r1(yr[out_m], 0)),
                     dict(id="return", get=r1(g_ret), x=r1(xr[ret_m], 0), y=r1(yr[ret_m], 0))],
               note="Shape from the free-return simulation (csm_02), retimed to the real GET. "
                    "Apollo 11 left the free-return path after MCC-2 and returned from lunar orbit, so the real path differs in detail.")

    # Earth parking orbit (185 km circle) + the first hours after TLI, Earth-centred inertial.
    r_pk = (R_EARTH + 185_200.0) / 1000.0
    n = math.sqrt(MU_EARTH / (r_pk * 1000.0) ** 3)
    phi_tli = math.atan2(data["r_earth"][0, 1], data["r_earth"][0, 0])
    g_park = np.arange(EV["orbit-insertion"], tli_end, 30.0)
    ang = phi_tli + n * (g_park - tli_end)
    after = t <= 4 * 3600
    g_aft = retime(t[after], [0, t_peri], [tli_end, EV["loi-1"]])
    eo = dict(frame="Earth-centred inertial, km", r_earth=6378,
              get=r1(np.concatenate([g_park, g_aft[1:]])),
              x=r1(np.concatenate([r_pk * np.cos(ang), re[after][1:, 0] / 1000.0]), 0),
              y=r1(np.concatenate([r_pk * np.sin(ang), re[after][1:, 1] / 1000.0]), 0),
              burns=[dict(id="tli", get0=EV["tli"], get1=tli_end)],
              note="185 km parking orbit (1.5 revolutions), then the start of the translunar path. "
                   "The TLI burn is drawn on the circle; the path after cutoff comes from csm_02.")
    return cis, eo


def kepler_ellipse(rp, ra, n_pts=240):
    """One revolution of a Moon-centred ellipse, sampled uniformly in time. Periapsis on +x."""
    a = 0.5 * (rp + ra)
    e = (ra - rp) / (ra + rp)
    T = 2 * math.pi * math.sqrt(a ** 3 / MU_MOON)
    M = np.linspace(0, 2 * math.pi, n_pts, endpoint=False)
    E = M.copy()
    for _ in range(30):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    x = a * (np.cos(E) - e)
    y = a * math.sqrt(1 - e * e) * np.sin(E)
    return T, x / 1000.0, y / 1000.0


def rot(x, y, ang):
    c, s = math.cos(ang), math.sin(ang)
    return c * x - s * y, s * x + c * y


def periodic_pos(orbit, g):
    k = ((g - orbit["epoch"]) / orbit["period"]) % 1.0
    i = int(k * len(orbit["x"])) % len(orbit["x"])
    return orbit["x"][i], orbit["y"][i]


def track_lunar(dsky):
    # --- LOI-1 (csm_04 call sequence) ---
    h_p = 112_786.8
    rpv = np.array([R_MOON + h_p, 0.0, 0.0])
    vpv = np.array([0.0, 2_556.8, 0.0])
    r, v = rpv.copy(), vpv.copy()
    for _ in range(193):
        a1 = -MU_MOON * r / np.linalg.norm(r) ** 3
        r2, v2 = r + 0.5 * -1.0 * v, v + 0.5 * -1.0 * a1
        a2 = -MU_MOON * r2 / np.linalg.norm(r2) ** 3
        r, v = r + -1.0 * v2, v + -1.0 * a2
    r_tig, v_tig = r, v
    m0 = 43_700.0
    p30 = quiet(m_burn.p30_external_delta_v, r_tig, v_tig, np.array([-889.0, 0.0, 0.0]), m0, r_peri_nom=rpv, v_peri_nom=vpv)
    hist = quiet(m_burn.simulate_p40_burn, r_tig, v_tig, p30, m0)
    burn_dur = float(hist["t"][-1])

    loi = EV["loi-1"]
    # approach: back-propagate the hyperbola 30 min before TIG (two-body)
    t_back = np.linspace(-1800.0, 0.0, 90)
    app = m_burn.propagate_two_body_arc(r_tig, -v_tig, -t_back[::-1], mu=MU_MOON)[::-1]  # reversed-time trick
    seg_csm = [dict(kind="arc", get=r1(loi + t_back), x=r1(app[:, 0] / 1000), y=r1(app[:, 1] / 1000))]
    seg_csm.append(dict(kind="arc", burn="loi-1", get=r1(loi + hist["t"]), x=r1(hist["r"][:, 0] / 1000), y=r1(hist["r"][:, 1] / 1000)))
    # post-LOI-1 ellipse: one revolution from cutoff, repeated
    r_c, v_c = hist["r"][-1], hist["v"][-1]
    eps = 0.5 * np.dot(v_c, v_c) - MU_MOON / np.linalg.norm(r_c)
    a = -MU_MOON / (2 * eps)
    T1 = 2 * math.pi * math.sqrt(a ** 3 / MU_MOON)
    ts = np.linspace(0, T1, 241)[:-1]
    pts = m_burn.propagate_two_body_arc(r_c, v_c, ts, mu=MU_MOON)
    orb1 = dict(kind="periodic", get_start=round(loi + burn_dur, 1), get_end=EV["loi-2"], epoch=round(loi + burn_dur, 1),
                period=round(T1, 1), x=r1(pts[:, 0] / 1000), y=r1(pts[:, 1] / 1000))
    seg_csm.append(orb1)
    # LOI-2: ~100 x 122 km (approx., Mission Report 54.4 x 65.7 nmi). Periapsis kept on +x.
    T2, ex, ey = kepler_ellipse(R_MOON + 100_700.0, R_MOON + 121_700.0)
    # phase so that at LOI-2 the CSM is where the LOI-1 ellipse put it
    px, py = periodic_pos(orb1, EV["loi-2"])
    ang_now = math.atan2(py, px)
    j = int(np.argmin(np.abs(np.angle(np.exp(1j * (np.arctan2(ey, ex) - ang_now))))))
    epoch2 = EV["loi-2"] - j / len(ex) * T2
    orb2 = dict(kind="periodic", get_start=EV["loi-2"], get_end=EV["tei"], epoch=round(epoch2, 1), period=round(T2, 1),
                x=r1(ex), y=r1(ey))
    seg_csm.append(orb2)
    # TEI departure hyperbola (approx.): +1000 m/s prograde from the CSM orbit
    gx, gy = periodic_pos(orb2, EV["tei"])
    rr = np.array([gx, gy, 0.0]) * 1000.0
    vt = np.array([-gy, gx, 0.0]) / math.hypot(gx, gy)
    v_circ = math.sqrt(MU_MOON / np.linalg.norm(rr))
    tt = np.linspace(0, 5400, 120)
    dep = m_burn.propagate_two_body_arc(rr, vt * (v_circ + 1000.0), tt, mu=MU_MOON)
    seg_csm.append(dict(kind="arc", burn="tei", get=r1(EV["tei"] + tt), x=r1(dep[:, 0] / 1000), y=r1(dep[:, 1] / 1000)))

    # --- LM: with the CSM until DOI, then a ~15 x 107 km descent orbit (approx.) ---
    Td, dx, dy = kepler_ellipse(R_MOON + 15_700.0, R_MOON + 107_000.0)
    cx, cy = periodic_pos(orb2, EV["doi"])
    ang_doi = math.atan2(cy, cx)
    dx, dy = rot(np.array(dx), np.array(dy), ang_doi + math.pi)  # apolune at the DOI point
    orb_doi = dict(kind="periodic", get_start=EV["doi"], get_end=PDI, epoch=round(EV["doi"] - Td / 2, 1), period=round(Td, 1),
                   x=r1(dx), y=r1(dy))
    peri_ang = ang_doi + math.pi
    land_ang = peri_ang + 480.0 / 1737.4  # ~480 km of powered descent past perilune (approx.)
    seg_lm = [dict(kind="follow", get_start=EV["undocking"], get_end=EV["doi"]),
              orb_doi,
              dict(kind="surface", get_start=PDI, get_end=LIFTOFF + 494,
                   x=round(1737.4 * math.cos(land_ang), 1), y=round(1737.4 * math.sin(land_ang), 1)),
              dict(kind="follow", get_start=LIFTOFF + 494, get_end=EV["lm-jettison"])]
    lun = dict(frame="Moon-centred inertial, km", r_moon=1737.4, csm=seg_csm, lm=seg_lm,
               burns=[dict(id="loi-1", get0=loi, get1=round(loi + burn_dur, 1)),
                      dict(id="loi-2", get0=EV["loi-2"], get1=EV["loi-2"] + 17),
                      dict(id="doi", get0=EV["doi"], get1=EV["doi"] + 30),
                      dict(id="tei", get0=EV["tei"], get1=EV["tei"] + 151)],
               site=dict(x=round(1737.4 * math.cos(land_ang), 1), y=round(1737.4 * math.sin(land_ang), 1)),
               note="LOI-1 from the P40 simulation (csm_04). Later orbits are Kepler ellipses with Mission Report apsides "
                    "(approx.); the Moon's rotation and orbit-plane details are left out.")

    # LOI-1 DSKY: V06N40 before ignition (time from ignition) and during the burn (time to cutoff)
    vg0 = hist["vgo_mag"][0] * FT
    for k in range(-120, 0, 2):
        dsky.append(dict(get=loi + k, computer="CM", prog="40", verb="06", noun="40",
                         r=[mmss(k), reg(vg0 * 10, 0), reg(0, 0)], lights=[], flash=False, simulated=True,
                         caption="P40 SPS burn, V06N40: time from ignition (min sec), velocity to be gained (ft/s), ΔV so far (ft/s)."))
    for i in range(len(hist["t"])):
        dsky.append(dict(get=round(loi + float(hist["t"][i]), 1), computer="CM", prog="40", verb="06", noun="40",
                         r=[mmss(hist["tgo"][i]), reg(hist["vgo_mag"][i] * FT * 10, 0), reg(hist["dv_total"][i] * FT * 10, 0)],
                         lights=[], flash=False, simulated=True,
                         caption="LOI-1 burning, V06N40: time to cutoff (min sec), velocity still to gain (ft/s), ΔV accumulated (ft/s)."))
    dsky.append(dict(get=round(loi + burn_dur + 2, 1), computer="CM", prog="40", verb="16", noun="40",
                     r=[mmss(0), reg(hist["vgo_mag"][-1] * FT * 10, 0), reg(hist["dv_total"][-1] * FT * 10, 0)],
                     lights=[], flash=False, simulated=True,
                     caption="Cutoff. V16N40 shows the residual velocity to gain and the total ΔV of LOI-1."))
    return lun, burn_dur


def track_descent(dsky):
    s = quiet(m_desc.simulate_powered_descent)
    t = s["t"]
    g = PDI + t
    tr = dict(frame="Altitude vs distance to the landing site", x_label="Distance from landing site (km)", y_label="Altitude (km)",
              get=r1(g), x=r1(s["downrange"], 3), y=r1(s["alt_true"] / 1000.0, 3), phase=[int(p) for p in s["phase"]],
              pitch_deg=r1(s["pitch_deg"], 1), throttle=r1(s["throttle"], 3), v_vert=r1(s["v_vert"], 1),
              note="Powered descent from the P63/P64/P66 simulation (lm_01).")
    valid = np.nonzero(s["delta_h"] < 90_000.0)[0]
    first_lock = int(valid[0]) if len(valid) else len(t)
    for i in range(len(t)):
        ph = int(s["phase"][i])
        ti = float(t[i])
        # ALT/VEL stay lit until the landing radar first locks on
        lr_bad = i < first_lock
        lights = ["ALT", "VEL"] if lr_bad else []
        hdot = s["v_vert"][i] * FT * 10
        hcalc = s["alt_nav"][i] * FT
        if ph == 63:
            row = dict(prog="63", verb="06", noun="63", r=[reg(s["abvel"][i] * FT * 10, 0), reg(hdot, 0), reg(hcalc, 0)],
                       caption="P63 braking, V06N63: speed (ft/s, xxxx.x), altitude rate (ft/s, xxxx.x), computed altitude (ft).")
            if ti >= 340:  # after the first alarm the crew watched V16N68
                rng_nm = math.hypot(s["downrange"][i] * 1000.0, s["alt_true"][i]) / NMI
                ttg = -float(s["ttf"][i])
                row = dict(prog="63", verb="16", noun="68",
                           r=[reg(rng_nm * 10, 0), mmss(max(ttg, 0)), "" if s["delta_h"][i] >= 90_000.0 else reg(s["delta_h"][i] * FT, 0)],
                           caption="V16N68: slant range to the site (nmi, xxxx.x), time to go in braking (min sec), radar minus computed altitude (ft).")
        elif ph == 64:
            tre = max(0, min(99, int(round(s["tredes"][i]))))
            lpd = max(0, min(99, int(round(s["lpd_deg"][i]))))
            row = dict(prog="64", verb="06", noun="64", r=[f"+{tre:02d} {lpd:02d}", reg(hdot, 0), reg(hcalc, 0)],
                       caption="P64 approach, V06N64: seconds left to redesignate and LPD angle (deg) for the window scale, altitude rate, altitude.")
        else:
            row = dict(prog="66", verb="06", noun="60", r=[reg(s["v_horiz"][i] * FT * 10, 0), reg(hdot, 0), reg(hcalc, 0)],
                       caption="P66 rate of descent, V06N60: horizontal speed (ft/s), altitude rate (ft/s), altitude (ft).")
        dsky.append(dict(get=round(PDI + ti, 1), computer="LM", lights=lights, flash=False, simulated=True, **row))
    # Program alarms (real times). V05N09 shows the alarm code in octal.
    for at, code, caption in [(317, "01202", "1202: Executive overflow, no core sets. BAILOUT restarts the jobs from their last phase point."),
                              (553, "01201", "1201: Executive overflow, no VAC areas. Another restart; guidance keeps running.")]:
        prog = "63" if at < 506 else "64"
        dsky.append(dict(get=PDI + at, computer="LM", prog=prog, verb="05", noun="09", r=[" " + code, "", ""],
                         lights=["PROG"], flash=True, simulated=False, caption=caption + " (V05N09, PROG light.)", alarm=code))
        # resume the regular display after ~15 s: copy the next simulated keyframe
    dsky.append(dict(get=EV["touchdown"] + 1, computer="LM", prog="68", verb="06", noun="43", r=["+00067", "+02347", ""],
                     lights=[], flash=False, simulated=False,
                     caption="P68 landing confirmation, V06N43: latitude 0.67° N, longitude 23.47° E (deg, xxx.xx). Altitude blank here."))
    return tr


def track_ascent(dsky):
    s = quiet(m_asc.simulate_ascent_p12)
    t = s["t"]
    tr = dict(frame="Altitude vs downrange from Tranquility Base", x_label="Downrange (km)", y_label="Altitude (km)",
              get=r1(LIFTOFF + t), x=r1(s["downrange_km"], 2), y=r1(s["alt_km"], 3), pitch_deg=r1(s["pitch_deg"], 1),
              perilune_km=round(float(s["perilune_km"]), 1), apolune_km=round(float(s["apolune_km"]), 1),
              note="P12 powered ascent from the simulation (lm_02).")
    for i in range(0, len(t)):
        ab = math.hypot(s["r_dot"][i], s["z_dot"][i]) * FT
        dsky.append(dict(get=round(LIFTOFF + float(t[i]), 1), computer="LM", prog="12", verb="16", noun="63",
                         r=[reg(ab * 10, 0), reg(s["r_dot"][i] * FT * 10, 0), reg(s["alt_km"][i] * 1000 * FT, 0)],
                         lights=[], flash=False, simulated=True,
                         caption="P12 ascent, V16N63: speed (ft/s, xxxx.x), altitude rate (ft/s, xxxx.x), altitude (ft)."))
    return tr


def track_rendezvous(dsky):
    s = quiet(m_rdz.simulate_rendezvous)
    b = s["burns"]
    ins = LIFTOFF + 434  # insertion (124:29:15)
    tpf = EV["tpi"] + 2580  # ~43 min transfer to braking (approx.)
    legs = [("x_ins_csi", "z_ins_csi", ins, EV["csi"]), ("x_csi_cdh", "z_csi_cdh", EV["csi"], EV["cdh"]),
            ("x_cdh_tpi", "z_cdh_tpi", EV["cdh"], EV["tpi"]), ("x_tpi_tpf", "z_tpi_tpf", EV["tpi"], tpf)]
    G, X, Z = [], [], []
    for xk, zk, g0, g1 in legs:
        n = len(s[xk])
        G += list(np.linspace(g0, g1, n))
        X += list(s[xk])
        Z += list(s[zk])
    G += [EV["docking"]]
    X += [0.0]
    Z += [0.0]
    tr = dict(frame="Eagle relative to Columbia (CSM-centred LVLH), km", x_label="Along track (km, + ahead of Columbia)",
              y_label="Radial (km, + above Columbia)", get=r1(G), x=r1(X, 2), z=r1(Z, 2),
              burns=[dict(id="csi", get=EV["csi"], dv_ms=round(b["dv_csi"], 1)),
                     dict(id="cdh", get=EV["cdh"], dv_ms=round(b["dv_cdh"], 1)),
                     dict(id="tpi", get=EV["tpi"], dv_ms=round(float(np.hypot(*s["dv_tpi"])), 1))],
              note="Relative motion from the rendezvous simulation (lm_03), each leg retimed to the real burn times. "
                   "Braking at ~127:40 GET is approx.")
    for bid, prog, dv in [("csi", "32", (b["dv_csi"], 0.0)), ("cdh", "33", (b["dv_cdh"], 0.0)), ("tpi", "34", tuple(s["dv_tpi"]))]:
        dsky.append(dict(get=EV[bid] - 600, computer="LM", prog=prog, verb="06", noun="81",
                         r=[reg(dv[0] * FT * 10, 0), reg(0, 0), reg(-dv[1] * FT * 10, 0)], lights=[], flash=True, simulated=True,
                         caption=f"P{prog} targeting, V06N81: ΔV in local-vertical axes (ft/s, xxxx.x) for the {bid.upper()} burn, flashing for the crew to accept."))
        dsky.append(dict(get=EV[bid] + 60, computer="LM", prog="20", verb="16", noun="45", r=["", "", ""], lights=[],
                         flash=False, simulated=False, caption="P20 rendezvous navigation in the background: the radar marks Columbia and the filter updates the state (registers not simulated)."))
    return tr


def track_entry(dsky):
    h, transitions, steeroff = quiet(m_entry.simulate_lunar_return_entry)
    t = h["t"]
    idx = np.arange(0, len(t), 2)
    G = list(EI + t[idx])
    X = list(h["downrange_km"][idx])
    Y = list(h["alt_km"][idx])
    gl = list(h["g_load"][idx])
    # under the parachutes to splashdown (not simulated): straight line down, approx.
    tail = np.linspace(t[-1], EV["splashdown"] - EI, 12)[1:]
    G += list(EI + tail)
    X += list(np.linspace(h["downrange_km"][-1], h["downrange_km"][-1] + 3, 12)[1:])
    Y += list(np.linspace(h["alt_km"][-1], 0, 12)[1:])
    gl += [1.0] * 11
    prog_at = []
    for name, ts, _x, _h in transitions:
        prog_at.append(dict(get=round(EI + ts, 1), program=name.split()[0]))
    tr = dict(frame="Altitude vs range flown from entry interface", x_label="Range flown (km)", y_label="Altitude (km)",
              get=r1(G), x=r1(X), y=r1(Y, 2), g=r1(gl, 2), transitions=prog_at, target_km=2320.0,
              steeroff=dict(get=round(EI + steeroff[0], 1)), sim_end=round(EI + float(t[-1]), 1),
              note="Entry from the P63-P67 simulation (csm_05). Below ~24,000 ft (drogue chutes) the line to splashdown is not simulated.")
    names = [p for p in h["phase"]]
    for i in range(0, len(t), 4):
        ph = names[i]
        g, v, rtg, roll = h["g_load"][i], h["v_ms"][i] * FT, h["range_to_go_km"][i] * 1000 / NMI, h["roll_deg"][i]
        if ph.startswith("P63"):
            row = dict(prog="63", verb="06", noun="64", r=[reg(g * 100, 0), reg(v, 0), reg(rtg * 10, 0)],
                       caption="P63 entry initialisation, V06N64: drag (g, xxx.xx), inertial velocity (ft/s), range to splash (nmi, xxxx.x).")
        elif ph.startswith("P64"):
            row = dict(prog="64", verb="06", noun="74", r=[reg(roll * 100, 0), reg(v, 0), reg(g * 100, 0)],
                       caption="P64 post-0.05 g, V06N74: commanded bank angle (deg), inertial velocity (ft/s), drag (g).")
        elif ph.startswith("P65"):
            row = dict(prog="65", verb="16", noun="69", r=[reg(roll * 100, 0), reg(g * 100, 0), ""],
                       caption="P65 upcontrol, V16N69: bank angle (deg), drag (g); the exit velocity VL is not simulated (blank).")
        elif ph.startswith("P66"):
            row = dict(prog="66", verb="06", noun="64", r=[reg(g * 100, 0), reg(v, 0), reg(rtg * 10, 0)],
                       caption="P66 Kepler (ballistic) phase, shown as V06N64: drag (g), velocity (ft/s), range to splash (nmi). The real P66 put up V06N22 and V06N66.")
        else:
            row = dict(prog="67", verb="16", noun="67", r=[reg(rtg * 10, 0), "", ""],
                       caption="P67 final phase, V16N67: range to target (nmi, xxxx.x); latitude and longitude not simulated (blank).")
        dsky.append(dict(get=round(EI + float(t[i]), 1), computer="CM", lights=[], flash=False, simulated=True, **row))
    dsky.append(dict(get=EV["cm-sm-sep"] - 900, computer="CM", prog="61", verb="06", noun="61", r=["+01330", "-16915", ""],
                     lights=[], flash=False, simulated=False,
                     caption="P61 entry preparation, V06N61: target splash latitude 13.30° N, longitude 169.15° W (approx.)."))
    dsky.append(dict(get=EV["cm-sm-sep"] - 60, computer="CM", prog="62", verb="50", noun="25", r=["+00041", "", ""],
                     lights=[], flash=True, simulated=False,
                     caption="P62 CM/SM separation, V50N25 (flashing): please perform the separation and turn heads-down."))
    dsky.append(dict(get=round(EI + float(t[-1]) + 2, 1), computer="CM", prog="67", verb="16", noun="67", r=["", "", ""],
                     lights=[], flash=False, simulated=False,
                     caption="Below 1,000 ft/s the computer has stopped steering (STEEROFF); the Earth Landing System deploys the parachutes."))
    return tr


# ---------------------------------------------------------------------------
# DSKY formatting
# ---------------------------------------------------------------------------
def reg(value, _nd=0):
    """Sign + five digits, as on a DSKY register (implied decimal point)."""
    n = int(round(float(value)))
    n = max(-99999, min(99999, n))
    return ("+" if n >= 0 else "-") + f"{abs(n):05d}"


def mmss(seconds):
    """xxBxx minutes/seconds format (middle digit blank)."""
    sgn = "+" if seconds >= 0 else "-"
    s = int(round(abs(float(seconds))))
    m, s = divmod(s, 60)
    return f"{sgn}{min(m, 99):02d} {s:02d}"


def idle_keyframes():
    K = []

    def k(g, comp, prog, verb, noun, r, caption, flash=False, lights=None, simulated=False):
        K.append(dict(get=g, computer=comp, prog=prog, verb=verb, noun=noun, r=r, lights=lights or [], flash=flash,
                      simulated=simulated, caption=caption))

    blank = ["", "", ""]
    k(EV["orbit-insertion"] + 1, "CM", "00", "", "", blank,
      "P00, the idle program: the CMC keeps time, runs attitude control and integrates the state vector when asked. (Display not simulated.)")
    k(EV["tli"] - 600, "CM", "47", "16", "83", blank,
      "TLI is flown by the Saturn V's own guidance. P47, the CMC's thrust monitor, counts the velocity added (registers not simulated).")
    k(EV["tli"] + 347 + 60, "CM", "00", "", "", blank, "P00 after TLI. Collins flies transposition and docking by hand.")
    k(get(24, 30, 0), "CM", "52", "51", "", blank,
      "P52 IMU realignment (one of several; time approx.). V51 flashing: please mark the star in the sextant.", flash=True)
    k(get(24, 40, 0), "CM", "52", "06", "93", blank,
      "P52 V06N93: gyro torquing angles (deg) to null the platform drift (registers not simulated).", flash=True)
    k(get(24, 50, 0), "CM", "00", "", "", blank, "P00: coasting, the platform realigned.")
    k(EV["mcc-2"] - 900, "CM", "40", "06", "40", blank, "P40 for MCC-2: a 3-second SPS burn (registers not simulated).")
    k(EV["mcc-2"] + 60, "CM", "00", "", "", blank, "P00: coasting toward the Moon.")
    k(EV["loi-1"] - 3600, "CM", "30", "06", "81", [reg(-889.0 * FT * 10), "+00000", "+00000"],
      "P30 external ΔV, V06N81: the LOI-1 burn as loaded, -2916.7 ft/s along the local horizontal (as in the P30 simulation).",
      flash=True, simulated=True)
    k(EV["loi-1"] + 600, "CM", "00", "", "", blank, "P00: in lunar orbit.")
    k(EV["loi-2"] - 600, "CM", "40", "06", "40", blank, "P40 for LOI-2, a 17-second circularisation burn (registers not simulated).")
    k(EV["loi-2"] + 120, "CM", "00", "", "", blank, "P00: in a ~100 x 122 km lunar orbit.")
    k(LM_ON, "LM", "00", "", "", blank, "Eagle's computer is powered up and loaded for the descent (display not simulated).")
    k(EV["undocking"], "LM", "00", "", "", blank, "Eagle flies free. The LGC runs P00 between burns.")
    k(EV["doi"] - 600, "LM", "40", "06", "40", blank, "P40 descent-engine burn for DOI, ~30 s (registers not simulated).")
    k(EV["doi"] + 60, "LM", "00", "", "", blank, "P00: coasting down to perilune at ~15 km.")
    k(PDI - 300, "LM", "63", "06", "62", blank,
      "P63 counting down to ignition, V06N62: speed, time from ignition, ΔV (registers not simulated).")
    k(EV["touchdown"] + 900, "LM", "00", "", "", blank, "P00 on the surface; the LGC stays up for a quick liftoff if needed.")
    k(LIFTOFF - 900, "LM", "12", "06", "76", blank, "P12 prelaunch, V06N76: desired horizontal and radial velocity, cross-range (registers not simulated).",
      flash=True)
    k(LIFTOFF + 440, "LM", "12", "16", "85", blank, "Engine cutoff. V16N85: residual velocity to trim with the RCS (registers not simulated).")
    k(EV["docking"] + 60, "LM", "00", "", "", blank, "Eagle docked; the LGC idles until it is powered down.")
    k(EV["undocking"], "CM", "00", "", "", blank, "Columbia alone: Collins tracks Eagle and can mirror any burn (P76).")
    k(EV["docking"] + 60, "CM", "00", "", "", blank, "P00: Columbia and Eagle docked again.")
    k(EV["tei"] - 3600, "CM", "30", "06", "81", blank, "P30 external ΔV for TEI, loaded from the ground (registers not simulated).", flash=True)
    k(EV["tei"] - 600, "CM", "40", "06", "40", blank, "P40 for TEI, 2.5 minutes on the SPS behind the Moon (registers not simulated).")
    k(EV["tei"] + 200, "CM", "00", "", "", blank, "P00: homeward bound.")
    k(EV["mcc-5"] - 900, "CM", "40", "06", "40", blank, "P40 for MCC-5, a 10-second burn (registers not simulated).")
    k(EV["mcc-5"] + 60, "CM", "00", "", "", blank, "P00: coasting home.")
    return K


# ---------------------------------------------------------------------------
# Code steps: real AGC excerpts + Python translations
# ---------------------------------------------------------------------------
def agc_excerpt(folder, label, n=32):
    matches = []
    for f in sorted((REPO / folder).glob("*.agc")):
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, ln in enumerate(lines):
            tok = ln.split()[0] if ln.strip() and not ln[0].isspace() else ""
            if tok == label:
                matches.append((f, i, lines))
                break
    if not matches:
        raise SystemExit(f"build.py: AGC label {label!r} not found in {folder}/")
    f, i, lines = matches[0]
    return dict(file=str(f.relative_to(REPO)), label=label, line=i + 1, lines=[ln.expandtabs(8).rstrip() for ln in lines[i:i + n]])


def py_excerpt(fn, n=34):
    if fn is None:
        return None
    src, start = inspect.getsourcelines(fn)
    lines = [ln.rstrip("\n") for ln in src]
    # skip the docstring body to get to the code faster, but keep the signature
    out = lines[:n]
    return dict(file=str(Path(inspect.getsourcefile(fn)).resolve().relative_to(REPO)), name=fn.__name__, line=start, lines=out)


def code_steps(burn_dur):
    C, L = "Comanche055", "Luminary099"
    S = [
        (0, C, "P11", m_p11.compute_noun62_s11_1, "CM", "P11 Earth orbit insertion monitor",
         "During the climb the Saturn V's own computer steers; the CMC only watches. P11 reads the accelerometers every two seconds, "
         "updates the state vector and shows inertial velocity, altitude rate and altitude (V06N62) so the crew can back up the booster."),
        (EV["orbit-insertion"], C, "KEPLERN", m_coast.kepler_propagate, "CM", "Kepler's equation in parking orbit",
         "In orbit the CMC predicts where it will be with the universal-variable Kepler routine: one equation, solved by iteration, that works for "
         "circles, ellipses and hyperbolas alike."),
        (EV["tli"] - 600, C, "P47CSM", None, "CM", "Watching the TLI burn",
         "The S-IVB flew TLI under its own Instrument Unit. The CMC stood by with its thrust-monitor logic counting the velocity gained, "
         "ready to show the crew whether the burn was good."),
        (EV["tli"] + 347 + 1800, C, "KEPPREP", m_coast.encke_translunar_propagate, "CM", "Encke integration of the coast",
         "Between Earth and Moon the CMC integrates the trajectory by Encke's method: it follows a simple conic and only integrates the small "
         "difference caused by the Moon's and Sun's pull, rectifying when the difference grows."),
        (get(24, 20, 0), C, "PROG52", m_p52.axisgen, "CM", "P52 star alignment",
         "The inertial platform drifts, so Collins sights two stars with the sextant. AXISGEN builds the rotation between where the platform thinks "
         "the stars are and where they really are, and the gyros are torqued to fix it."),
        (get(25, 0, 0), C, "RECTIFY", m_coast.encke_gamcomp, "CM", "Rectifying the reference conic",
         "When the integrated deviation from the reference conic gets too large, RECTIFY starts a new conic from the current state so the "
         "small-number arithmetic stays accurate in 15-bit words."),
        (get(61, 39, 55), C, "ORIGCHNG", m_coast.encke_translunar_propagate, "CM", "Switching to the Moon's sphere of influence",
         "About 62,000 km from the Moon the integrator switches its origin from Earth to Moon (ORIGCHNG), so the main attraction is again the "
         "body at the centre of the coordinates."),
        (EV["loi-1"] - 4000, C, "P30", m_burn.p30_external_delta_v, "CM", "P30 external ΔV targeting",
         "Mission Control computes the LOI burn and voices it up. P30 turns the ΔV given in local-vertical axes into the platform frame and "
         "predicts the resulting apolune and perilune."),
        (EV["loi-1"] - 300, C, "P40CSM", m_burn.s40_1_initial_thrust_direction, "CM", "P40 SPS burn setup",
         "P40 points the spacecraft for the burn, checks the gimbals and counts down. S40.1 picks the thrust direction, leading the impulsive "
         "direction a little because the burn lasts six minutes."),
        (EV["loi-1"], C, "S40.8", m_burn.simulate_p40_burn, "CM", "Cross-product steering during LOI-1",
         "Every two seconds the burn loop updates the velocity still to be gained (VG) and steers the engine so the thrust lines up with it; "
         "the engine shuts down when VG is used up."),
        (EV["loi-1"] + burn_dur + 600, C, "KEPLERN", m_coast.kepler_propagate, "CM", "Coasting in lunar orbit",
         "In lunar orbit the CMC again predicts its motion with Kepler's equation, now with the Moon's gravitational parameter."),
        (EV["doi"] - 600, L, "P40LM", None, "LM", "DOI with the descent engine",
         "Eagle's first burn: about 30 seconds on the descent engine to lower perilune to ~15 km, half an orbit before the landing site."),
        (PDI - 600, L, "BURNBABY", None, "LM", "BURN, BABY, BURN: the master ignition routine",
         "BURNBABY runs the countdown common to every LM burn: average-G navigation starts at TIG-30 s, ullage, then ignition at 10% "
         "throttle for 26 s so the gimbal can trim before full throttle."),
        (PDI + 26, L, "SERVICER", m_desc.servicer_step, "LM", "SERVICER: the 2-second navigation cycle",
         "Every two seconds SERVICER reads the accelerometers, updates position and velocity with average-G, folds in landing radar data once it "
         "locks on, and calls the guidance equations."),
        (PDI + 200, L, "TTF/8CL", m_desc.compute_ttf, "LM", "Time to go (TTF/8)",
         "The guidance targets a point in time as well as space. TTF/8CL solves a cubic for the time remaining in the phase, scaled by 1/8 to fit "
         "the AGC's fixed-point range."),
        (PDI + 317, L, "BAILOUT", None, "LM", "Program alarm 1202 and BAILOUT",
         "The Executive found no free core set for a new job. Instead of crashing, BAILOUT abandons all jobs and restarts them from their last "
         "protected phase points: the landing continues and only some display updates are lost."),
        (PDI + 345, L, "QUADGUID", m_desc.quadguid_accel, "LM", "Quadratic guidance (QUADGUID)",
         "The heart of the descent: the commanded acceleration is a quadratic in time-to-go, chosen so position, velocity and acceleration all "
         "hit their targets together. The throttle and attitude follow from it."),
        (EV["p64"] - 1, L, "STARTP64", m_desc.compute_lpd_look_angle, "LM", "P64 approach and the LPD",
         "At high gate Eagle pitches up so the crew can see the landing area. The computer shows a look angle on the window scale (the landing "
         "point designator) and the commander can nudge the target with the hand controller."),
        (PDI + 553, L, "FINDVAC", None, "LM", "Program alarm 1201",
         "This time the Executive ran out of VAC areas for interpreter jobs. The same restart logic recovered, and Mission Control called \"Go\"."),
        (PDI + 575, L, "POSUPDAT", m_desc.servicer_step, "LM", "Landing radar updates",
         "Below about 10 km the landing radar's altitude and velocity are blended into the state vector, weighted by how far down Eagle is."),
        (EV["p66"] - 1, L, "STARTP66", m_desc.p66_rod_guidance, "LM", "P66: rate of descent",
         "Armstrong flies the attitude by hand; each click of the ROD switch changes the commanded sink rate by 1 ft/s, and RODCOMP sets the "
         "throttle to hold it."),
        (EV["touchdown"], L, "LANDJUNK", None, "LM", "P68 landing confirmation",
         "After contact light and engine stop, P68 records the landing site and puts up the latitude, longitude and altitude for the crew."),
        (LIFTOFF - 900, L, "P12LM", None, "LM", "P12 powered ascent",
         "P12 sets up the ascent: target orbit, cross-range and the engine-on sequence. The ascent engine has no throttle, so guidance steers only."),
        (LIFTOFF + 10, L, "ATMAG", m_asc.ascent_guidance_step, "LM", "Ascent guidance (ATMAG)",
         "Every two seconds the ascent guidance computes the thrust direction needed to reach the insertion velocity and altitude at cutoff."),
        (LIFTOFF + 494, L, "LSR22.3", m_rdz.lsr22_3_radar_mark, "LM", "Rendezvous radar marks",
         "The rendezvous radar measures range, range rate and angles to Columbia. Each mark is checked and then offered to the navigation filter."),
        (EV["csi"] - 1200, L, "P32", m_rdz.compute_csi_cdh_burns, "LM", "P32 concentric sequence initiation",
         "P32 computes the CSI burn near apolune that sets up a constant height difference with Columbia."),
        (EV["csi"] + 300, L, "INCORP1", m_rdz.incorp1_potter, "LM", "Measurement incorporation",
         "INCORP1 is the AGC's Kalman-style filter: it weighs each radar mark against the predicted measurement and corrects position and "
         "velocity using the W matrix."),
        (EV["cdh"] - 1200, L, "P33", m_rdz.compute_csi_cdh_burns, "LM", "P33 constant delta height",
         "The CDH burn makes Eagle's orbit coelliptic with Columbia's, a fixed ~28 km below, so the final approach always looks the same."),
        (EV["tpi"] - 1200, L, "P34", m_rdz.solve_tpi_cw_lambert, "LM", "P34 terminal phase initiation",
         "When Columbia is 26.6° above the horizon, P34 computes the burn that intercepts it about 130° of orbit later."),
        (EV["docking"] + 300, C, "P30", m_burn.p30_external_delta_v, "CM", "P30 for TEI",
         "Back in Columbia, the crew loads the TEI burn from the ground. P30 converts it and predicts the return conditions."),
        (EV["tei"] - 300, C, "P40CSM", m_burn.s40_1_initial_thrust_direction, "CM", "P40 for TEI",
         "The same SPS burn program used for LOI now sends Columbia home: 2.5 minutes behind the Moon."),
        (EV["tei"] + 151 + 1800, C, "TFFCONIC", m_coast.calc_time_of_free_fall, "CM", "Time of free fall",
         "On the way home the CMC can predict the time to entry interface from the current conic: the time of free fall."),
        (EV["cm-sm-sep"] - 1200, C, "P61", m_entry.p61_entry_interface_params, "CM", "P61/P62 entry preparation",
         "P61 predicts entry conditions and the splash point; P62 handles CM/SM separation and turns the CM heat shield first."),
        (EI - 60, C, "P63", m_entry.p61_entry_interface_params, "CM", "P63 entry initialisation",
         "From 400,000 ft P63 holds attitude and waits for 0.05 g of drag, then picks the steering mode for the rest of entry."),
        (EI + 26, C, "P64", m_entry.entry_guidance_step, "CM", "P64 post-0.05 g",
         "The CM flies by rolling its lift vector. P64 controls the pull-out from the dive and decides whether a skip (upcontrol) is needed."),
        (EI + 104, C, "UPCONTRL", m_entry.entry_guidance_step, "CM", "P65 upcontrol",
         "To reach the 2,320 km target the CM rises slightly in the atmosphere. UPCONTRL steers the climb toward a predicted exit velocity."),
        (EI + 174, C, "P67.1", m_entry.p67_final_phase_reference, "CM", "P67 final phase",
         "The last steering phase follows a stored reference trajectory (VREFER), correcting range with bank angle until speed drops below "
         "1,000 ft/s, when steering stops."),
    ]
    S.sort(key=lambda r: r[0])
    out = []
    for i, (g0, folder, label, fn, comp, title, explain) in enumerate(S):
        g1 = S[i + 1][0] if i + 1 < len(S) else END
        out.append(dict(id=f"{label.lower().replace('/', '-').replace('.', '-')}-{i}", get_start=round(g0, 1), get_end=round(g1, 1),
                        computer=comp, title=title, agc=agc_excerpt(folder, label), python=py_excerpt(fn), explain=explain))
    out[0]["get_start"] = 0
    return out


# ---------------------------------------------------------------------------
def build_data():
    dsky = []
    phases, timemap = build_phases()
    fr = free_return()
    cis, eo = track_cislunar_and_orbit(fr)
    tracks = {"launch": track_launch(dsky), "earth-orbit": eo, "cislunar": cis}
    lun, burn_dur = track_lunar(dsky)
    tracks["lunar-orbit"] = lun
    tracks["descent"] = track_descent(dsky)
    tracks["surface"] = dict(site="Tranquility Base", lat_deg=0.674, lon_deg=23.473)
    tracks["ascent"] = track_ascent(dsky)
    tracks["rendezvous"] = track_rendezvous(dsky)
    tracks["entry"] = track_entry(dsky)
    dsky += idle_keyframes()
    # after each program alarm, return to the regular display ~15 s later
    for at in (317, 553):
        # drop simulated frames inside the alarm window so the alarm stays up
        dsky = [k for k in dsky if not (k["computer"] == "LM" and k.get("simulated") and PDI + at < k["get"] < PDI + at + 15)]
    dsky.sort(key=lambda k: (k["get"], k["computer"]))
    data = dict(
        meta=dict(launch_utc="1969-07-16T13:32:00Z", generated_by="explained/live/build.py",
                  notes=["Event times: Apollo 11 Mission Report (GET).",
                         "Trajectories and most DSKY values come from the simulations in explained/; displays marked "
                         "'not simulated' show the program and verb/noun the crew would have seen, without register values.",
                         "LM computer power-up at 096:00 GET is approximate."]),
        events=[dict(id=i, get=g, label=lab, short=sh, computer=c, detail=d) for i, g, lab, sh, c, d in EVENTS],
        phases=phases, timemap=timemap, tracks=tracks, dsky=dsky, lm_power=[[LM_ON, LM_OFF]],
        code=code_steps(burn_dur),
    )
    return data


def validate(d):
    ev = [e["get"] for e in d["events"]]
    assert ev == sorted(ev), "events out of order"
    ph = d["phases"]
    assert ph[0]["get_start"] == 0 and ph[-1]["get_end"] == END
    for a, b in zip(ph, ph[1:]):
        assert a["get_end"] == b["get_start"], (a["id"], b["id"])
    tm = d["timemap"]
    assert all(b[0] > a[0] and b[1] > a[1] for a, b in zip(tm, tm[1:])), "time map not monotonic"
    import re
    pat = re.compile(r"^([+-]\d{5}|[+-]\d\d \d\d| \d{5})?$")
    for k in d["dsky"]:
        for r in k["r"]:
            assert pat.match(r), (k["get"], k["noun"], r)
    for name, tr in d["tracks"].items():
        if "get" in tr:
            n = len(tr["get"])
            for key in ("x", "y", "z", "g", "phase", "pitch_deg", "throttle"):
                if key in tr:
                    assert len(tr[key]) == n, (name, key)
            assert all(b >= a for a, b in zip(tr["get"], tr["get"][1:])), f"{name} get not monotonic"
    for c in d["code"]:
        f = (REPO / c["agc"]["file"]).read_text(encoding="utf-8", errors="replace").splitlines()
        assert f[c["agc"]["line"] - 1].split()[0] == c["agc"]["label"], c["id"]
    cs = d["code"]
    for a, b in zip(cs, cs[1:]):
        assert a["get_end"] == b["get_start"] and a["get_start"] < a["get_end"], (a["id"], b["id"])


FONTS_DIR = LIVE / "fonts"

EXPECTED_FONTS = [
    ("barlow-condensed-500.woff2", "Barlow Condensed", 500),
    ("barlow-condensed-600.woff2", "Barlow Condensed", 600),
    ("barlow-condensed-700.woff2", "Barlow Condensed", 700),
    ("ibm-plex-mono-400.woff2", "IBM Plex Mono", 400),
    ("ibm-plex-mono-500.woff2", "IBM Plex Mono", 500),
    ("ibm-plex-mono-600.woff2", "IBM Plex Mono", 600),
    ("ibm-plex-sans-400-600.woff2", "IBM Plex Sans", "400 600"),  # one variable font
]

UNICODE_RANGE = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, "
    "U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, "
    "U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"
)


def bundle_fonts(template: str) -> str:
    placeholder = "/*__FONTS__*/"
    if placeholder not in template:
        raise ValueError(f"Missing font placeholder {placeholder!r} in template")

    missing = [name for name, _, _ in EXPECTED_FONTS if not (FONTS_DIR / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing required font files: {missing}")

    rules = []
    font_files = sorted(FONTS_DIR.glob("*.woff2"))
    if len(font_files) != len(EXPECTED_FONTS):
        raise FileNotFoundError(f"Expected {len(EXPECTED_FONTS)} font files, found {len(font_files)} in {FONTS_DIR}")

    for name, family, weight in EXPECTED_FONTS:
        font_path = FONTS_DIR / name
        b64_data = base64.b64encode(font_path.read_bytes()).decode("ascii")
        rule = (
            "@font-face {\n"
            f'  font-family: "{family}";\n'
            "  font-style: normal;\n"
            f"  font-weight: {weight};\n"
            "  font-display: swap;\n"
            f'  src: url(data:font/woff2;base64,{b64_data}) format("woff2");\n'
            f"  unicode-range: {UNICODE_RANGE};\n"
            "}"
        )
        rules.append(rule)

    return template.replace(placeholder, "\n".join(rules))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fragment", metavar="PATH", help="also write the page without the html/head/body wrapper")
    ap.add_argument("--json", metavar="PATH", help="also write the data as JSON")
    args = ap.parse_args(argv)

    data = build_data()
    validate(data)
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    tpl = (LIVE / "template.html").read_text(encoding="utf-8")
    frag = bundle_fonts(tpl).replace("__MISSION_DATA__", blob)
    full = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
            "body{margin:0;font:14px system-ui,-apple-system,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>\n"
            "</head>\n<body>\n" + frag + "\n</body>\n</html>\n")
    out = LIVE / "apollo11_live.html"
    out.write_text(full, encoding="utf-8")
    if args.fragment:
        Path(args.fragment).write_text(frag, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {out.relative_to(REPO)} ({out.stat().st_size / 1e6:.2f} MB): {len(data['events'])} events, "
          f"{len(data['dsky'])} DSKY frames, {len(data['code'])} code steps, playback {data['timemap'][-1][1]:.0f} s")


if __name__ == "__main__":
    main()
