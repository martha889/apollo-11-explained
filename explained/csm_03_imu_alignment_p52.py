"""
Apollo 11 Command Module — Program 52 IMU Alignment by Star Sightings
=====================================================================
Translates the Command Module's optical star-sighting and Inertial Measurement
Unit (IMU) platform alignment routines from Comanche055:
  * STAR_TABLES.agc — The 37-star onboard catalog (CATLOG) stored as half-unit
    vectors (scaled B-1) in Basic Reference coordinates.
  * SXTMARK.agc & CSM_GEOMETRY.agc — Sextant mark interrupt processing
    (SXTMARK, MARKRUPT) and transformation of shaft/trunnion + IMU CDU angles
    into Stable Member star vectors (SXTNB, SXTSM).
  * P51-P53.agc — Program 52 (PROG52) Realign IMU workflow, star-pair auto
    selection (PICAPAR), Star Angle Difference check Noun 05 (CHKSDATA), and
    fine gyro torquing pulse command (R55).
  * INFLIGHT_ALIGNMENT_ROUTINES.agc — The triad orthonormal basis builder
    (AXISGEN) and Gyro Torquing Angle solver Noun 93 (CALCGTA, ARCTRIG).

Why P52 was essential:
  The IMU's three-axis gyro-stabilized platform ("Stable Member") slowly drifted
  by ~1 milliradian/hour (~0.05 deg/hr). Before every major SPS burn (TLI, MCCs,
  LOI, TEI) and before atmospheric entry, the navigator sighted two catalog
  stars through the 28x magnification Sextant (SXT) to measure the platform's
  drift and torque the gyros back to the desired REFSMMAT orientation.
"""

import math
import numpy as np
import matplotlib.pyplot as plt

from common import (
    src,
    step,
    save,
)


# ---------------------------------------------------------------------------
# 1. Onboard Star Catalog (Comanche055/STAR_TABLES.agc @ CATLOG)
# ---------------------------------------------------------------------------
# Exact 2DEC half-unit vector entries from Comanche055/STAR_TABLES.agc.
# In the AGC, each star vector is stored scaled B-1 (components divided by 2)
# so that values near 1.0 never overflow a signed 14-bit fixed-point word.

AGC_STAR_TABLE_RAW = {
    1:  ("Alpheratz",  (+0.4374329459, +0.0130439587, +0.2418310835)),
    2:  ("Diphda",     (+0.4671320200, +0.0867536571, -0.1557609669)),
    3:  ("Navi (Cas)", (+0.2356455290, +0.0724109523, +0.4342764623)),
    4:  ("Achernar",   (+0.2647463675, +0.1190647840, -0.4096993138)),
    7:  ("Menkar",     (+0.3654450539, +0.3413913761, +0.0329980710)),
    10: ("Mirfak",     (+0.2317572429, +0.2738370562, +0.3482841450)),
    12: ("Rigel",      (-0.0307468615, +0.3015781643, -0.3976244978)),
    14: ("Canopus",    (-0.0761975285, +0.2504274814, -0.4259953207)),
    15: ("Sirius",     (-0.1806254266, +0.2873635420, -0.3671466327)),
    16: ("Vega",       (-0.2328973970, +0.2387392516, +0.3725082175)),
    20: ("Alphard",    (-0.4243176734, +0.2421265028, -0.1064390364)),
    22: ("Regulus",    (-0.4375741083, +0.2194265468, +0.1018866468)),
    25: ("Spica",      (-0.4622473915, -0.1753827564, -0.0746206247)),
    26: ("Arcturus",   (-0.3792761057, -0.2564109356, +0.2009802685)),
    30: ("Menkent",    (+0.0608646846, -0.3851366423, +0.3129940205)),
    31: ("Antares",    (-0.1306332231, -0.4408862229, -0.1958425377)),
    34: ("Atria",      (+0.2286614772, -0.3698891519, -0.2468115559)),
    36: ("Altair",     (+0.2298916722, -0.4384110661, +0.0702249894)),
    37: ("Deneb",      (+0.4171485704, -0.1196240757, -0.2483488487)),
}


def decode_star_catalog():
    """
    Decode the AGC's B-1 scaled half-unit star vectors from STAR_TABLES.agc
    into full unit vectors in Basic Reference coordinates.

    Citation:
        {c_catlog}

    In STAR_TABLES.agc, each star entry consists of three double-precision words
    (6 erasable/fixed words per star) representing 0.5 * [u_x, u_y, u_z].
    Multiplying by 2 (or normalizing via UNIT in the AGC interpreter) yields the
    inertial line-of-sight unit vector.
    """.format(c_catlog=src("Comanche055/STAR_TABLES.agc", "CATLOG"))
    catalog = {}
    for code, (name, half_vec) in AGC_STAR_TABLE_RAW.items():
        vec = 2.0 * np.array(half_vec, dtype=float)
        vec = vec / np.linalg.norm(vec)
        catalog[code] = {"name": name, "octal": f"{code:03o}", "u_ref": vec}
    return catalog


# ---------------------------------------------------------------------------
# 2. Star-Pair Selection (P51-P53.agc @ PICAPAR)
# ---------------------------------------------------------------------------

def score_star_pair(u1, u2):
    """
    Evaluate how suitable two catalog stars are for IMU alignment.

    Citation:
        {c_picapar}

    In P51-P53.agc @ PICAPAR (line 781), the AGC checks that two candidate stars
    are neither nearly collinear nor nearly antiparallel. The cross product
    |u1 x u2| = sin(theta) measures geometric conditioning: a separation near
    60-90 deg maximizes |u1 x u2| and minimizes 3-axis attitude dilution of
    precision. PICAPAR rejects any pair with separation outside ~[19 deg, 161 deg]
    (|u1 . u2| > cos(19 deg)).
    """.format(c_picapar=src("Comanche055/P51-P53.agc", "PICAPAR"))
    dot = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
    sep_deg = math.degrees(math.acos(dot))
    cross_mag = math.sqrt(max(1.0 - dot * dot, 0.0))
    valid = abs(dot) < math.cos(math.radians(19.0))
    return sep_deg, cross_mag, valid


# ---------------------------------------------------------------------------
# 3. Sextant Sighting & Mark Processing (SXTMARK.agc, CSM_GEOMETRY.agc)
# ---------------------------------------------------------------------------

def sxt_angles_from_nb_vector(u_nb):
    """
    Convert a unit star vector in Navigation Base (NB) coordinates into Sextant
    shaft (CDUS) and trunnion (CDUT) angles.

    Citation:
        {c_calcsxa}

    Inverse of SXTNB (CSM_GEOMETRY.agc, lines 48-120):
        u_nb = [ cos(trunnion),
                 sin(trunnion) * sin(shaft),
                 sin(trunnion) * cos(shaft) ]
    """.format(c_calcsxa=src("Comanche055/CSM_GEOMETRY.agc", "CALCSXA"))
    cos_t = float(np.clip(u_nb[0], -1.0, 1.0))
    trunnion = math.acos(cos_t)
    shaft = math.atan2(u_nb[1], u_nb[2])
    return shaft, trunnion


def sxt_nb_vector_from_angles(shaft, trunnion):
    """
    Reconstruct the star line-of-sight unit vector in Navigation Base (NB)
    coordinates from Sextant shaft and trunnion angles.

    Citation:
        {c_sxtnb}

    Translates SXTNB in CSM_GEOMETRY.agc (line 48).
    """.format(c_sxtnb=src("Comanche055/CSM_GEOMETRY.agc", "SXTNB"))
    sin_t = math.sin(trunnion)
    cos_t = math.cos(trunnion)
    return np.array([
        cos_t,
        sin_t * math.sin(shaft),
        sin_t * math.cos(shaft),
    ])


def simulate_sextant_marks(
    u_ref,
    r_sm_true_from_ref,
    r_nb_from_sm_true,
    n_marks=5,
    noise_arcsec=10.0,
    rng=None,
):
    """
    Simulate n_marks optical sightings of a star through the CSM Sextant (SXT)
    and average the reconstructed Stable Member vectors.

    Citations:
        {c_sxtmark}
        {c_markrupt}
        {c_sxtsm}
        {c_s52_2}

    How the AGC does it:
      1.SXTMARK arms the optics mark system for up to 5 sightings.
      2. When the astronaut centers the star in the 28x sextant reticle and
         presses the mark button, MARKRUPT immediately snapshots the 3 IMU CDU
         angles (CDUX, CDUY, CDUZ) and 2 Optics CDU angles (shaft CDUS, trunnion
         CDUT) into the VAC mark area.
      3. SXTSM calls SXTNB to convert (shaft, trunnion) into a Navigation Base
         unit vector u_NB, then calls NBSM to transform u_NB through the IMU
         gimbal angles into current (drifted) Stable Member coordinates u_SM.
      4. S52.2 averages all accepted marks and normalizes via UNIT.
    """.format(
        c_sxtmark=src("Comanche055/SXTMARK.agc", "SXTMARK"),
        c_markrupt=src("Comanche055/SXTMARK.agc", "MARKRUPT"),
        c_sxtsm=src("Comanche055/P51-P53.agc", "SXTSM"),
        c_s52_2=src("Comanche055/P51-P53.agc", "S52.2"),
    )
    if rng is None:
        rng = np.random.default_rng(1969)

    # True star direction in the drifted Stable Member frame, then in the NB frame
    u_sm_true = r_sm_true_from_ref @ u_ref
    u_nb_true = r_nb_from_sm_true @ u_sm_true
    shaft_true, trunnion_true = sxt_angles_from_nb_vector(u_nb_true)

    sigma_rad = math.radians(noise_arcsec / 3600.0)
    marks_sm = []
    marks_angles = []

    # Inverse of r_nb_from_sm_true transforms NB back to current Stable Member (NBSM)
    r_sm_from_nb = r_nb_from_sm_true.T

    for _ in range(n_marks):
        shaft_m = shaft_true + rng.normal(0.0, sigma_rad)
        trunnion_m = trunnion_true + rng.normal(0.0, sigma_rad)
        u_nb_m = sxt_nb_vector_from_angles(shaft_m, trunnion_m)
        u_sm_m = r_sm_from_nb @ u_nb_m
        u_sm_m = u_sm_m / np.linalg.norm(u_sm_m)
        marks_sm.append(u_sm_m)
        marks_angles.append((shaft_m, trunnion_m))

    marks_sm = np.array(marks_sm)
    u_sm_avg = np.mean(marks_sm, axis=0)
    u_sm_avg = u_sm_avg / np.linalg.norm(u_sm_avg)
    return u_sm_avg, marks_sm, marks_angles


# ---------------------------------------------------------------------------
# 4. Star Angle Difference Check — Noun 05 (P51-P53.agc @ CHKSDATA)
# ---------------------------------------------------------------------------

def check_star_angle_difference(u1_ref, u2_ref, u1_sm, u2_sm):
    """
    Compute the Star Angle Difference (Noun 05) between the catalog star pair
    and the measured Stable Member star pair.

    Citation:
        {c_chksdata}

    In P51-P53.agc @ CHKSDATA (line 1114):
      - Because a rigid rotation preserves the angle between any two vectors,
        the dot product (u1_SM . u2_SM) measured on the drifted IMU platform
        must equal the catalog dot product (u1_REF . u2_REF) regardless of how
        far the platform has drifted.
      - The AGC computes both angles via ARCCOS, subtracts them, and flashes
        Verb 06 Noun 05 in hundredths of a degree (0.01 deg).
      - Mission rules required Noun 05 <= 0.02 deg (00002 on DSKY); a larger
        value told the astronaut they sighted the wrong star or made a bad mark.
    """.format(c_chksdata=src("Comanche055/P51-P53.agc", "CHKSDATA"))
    ang_cat_deg = math.degrees(math.acos(np.clip(np.dot(u1_ref, u2_ref), -1.0, 1.0)))
    ang_sm_deg = math.degrees(math.acos(np.clip(np.dot(u1_sm, u2_sm), -1.0, 1.0)))
    diff_deg = abs(ang_cat_deg - ang_sm_deg)
    dsky_n05 = int(round(diff_deg * 100.0))
    return ang_cat_deg, ang_sm_deg, diff_deg, dsky_n05


# ---------------------------------------------------------------------------
# 5. AXISGEN & CALCGTA (INFLIGHT_ALIGNMENT_ROUTINES.agc)
# ---------------------------------------------------------------------------

def axisgen(u1_ref, u2_ref, u1_sm, u2_sm):
    """
    Compute the 3x3 orthogonal transformation matrix from desired REFSMMAT
    coordinates to current Stable Member coordinates using the AGC's AXISGEN
    triad algorithm.

    Citation:
        {c_axisgen}

    In INFLIGHT_ALIGNMENT_ROUTINES.agc @ AXISGEN (line 225):
      Given two star unit vectors (s1, s2) in Reference coordinates and their
      measured counterparts (m1, m2) in Stable Member coordinates, AXISGEN builds
      two orthonormal right-handed triads:
          U_A = s1,   U_C = UNIT(s1 x s2),   U_B = UNIT(U_C x U_A)
          V_A = m1,   V_C = UNIT(m1 x m2),   V_B = UNIT(V_C x V_A)
      and forms the rotation matrix:
          R_SM_from_REF = V_A * U_A^T + V_B * U_B^T + V_C * U_C^T
    """.format(c_axisgen=src("Comanche055/INFLIGHT_ALIGNMENT_ROUTINES.agc", "AXISGEN"))
    ua = u1_ref / np.linalg.norm(u1_ref)
    uc = np.cross(ua, u2_ref)
    uc = uc / np.linalg.norm(uc)
    ub = np.cross(uc, ua)
    ub = ub / np.linalg.norm(ub)

    va = u1_sm / np.linalg.norm(u1_sm)
    vc = np.cross(va, u2_sm)
    vc = vc / np.linalg.norm(vc)
    vb = np.cross(vc, va)
    vb = vb / np.linalg.norm(vb)

    u_mat = np.column_stack((ua, ub, uc))
    v_mat = np.column_stack((va, vb, vc))
    r_sm_from_ref = v_mat @ u_mat.T
    return r_sm_from_ref, (ua, ub, uc), (va, vb, vc)


def calcgta(r_sm_from_ref):
    """
    Compute the three IMU Gyro Torquing Angles (Noun 93:OG, IG, MG / X, Y, Z)
    required to drive the current Stable Member into alignment with the desired
    REFSMMAT.

    Citations:
        {c_calcgta}
        {c_arctrig}
        {c_r55}

    In INFLIGHT_ALIGNMENT_ROUTINES.agc @ CALCGTA (line 47):
      Let R be the orthogonal matrix mapping desired Stable Member (REFSMMAT)
      vectors into current Stable Member coordinates. CALCGTA extracts the
      Euler torquing angles (theta_X, theta_Y, theta_Z) via ARCTRIG so that
      torquing the X, Y, and Z IMU gyros through (-theta_X, -theta_Y, -theta_Z)
      in routine R55 (GENTRAN) brings the Stable Member axes onto REFSMMAT.
    """.format(
        c_calcgta=src("Comanche055/INFLIGHT_ALIGNMENT_ROUTINES.agc", "CALCGTA"),
        c_arctrig=src("Comanche055/INFLIGHT_ALIGNMENT_ROUTINES.agc", "ARCTRIG"),
        c_r55=src("Comanche055/P51-P53.agc", "R55"),
    )
    # Extract Euler angles from R_SM_from_REF (CALCGTA lines 62-99)
    sin_y = float(np.clip(r_sm_from_ref[0, 2], -1.0, 1.0))
    theta_y = math.asin(sin_y)
    theta_x = math.atan2(-r_sm_from_ref[1, 2], r_sm_from_ref[2, 2])
    theta_z = math.atan2(-r_sm_from_ref[0, 1], r_sm_from_ref[0, 0])
    return np.array([theta_x, theta_y, theta_z])


def euler_xyz_matrix(angles_rad):
    """Construct 3x3 rotation matrix from small X-Y-Z Euler angles."""
    tx, ty, tz = angles_rad
    cx, sx = math.cos(tx), math.sin(tx)
    cy, sy = math.cos(ty), math.sin(ty)
    cz, sz = math.cos(tz), math.sin(tz)

    rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    return rx @ ry @ rz


# ---------------------------------------------------------------------------
# 6. Visualization
# ---------------------------------------------------------------------------

def plot_star_catalog_and_marks(catalog, code1, code2, marks1_sm, u1_sm_true, n05_info):
    """Create Figure 1: Onboard star catalog sky map and Sextant mark scatter."""
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(13.5, 5.8), gridspec_kw={"width_ratios": [1.45, 1.0]}
    )
    fig.suptitle(
        "Comanche055 STAR_TABLES.agc & SXTMARK.agc — P52 Star Sightings & Noun 05 Check",
        fontsize=13,
        fontweight="bold",
    )

    # Panel 1: Sky map (Right Ascension vs Declination) of decoded AGC catalog stars
    ras, decs, labels = [], [], []
    for code, entry in catalog.items():
        u = entry["u_ref"]
        ra_deg = math.degrees(math.atan2(u[1], u[0])) % 360.0
        dec_deg = math.degrees(math.asin(np.clip(u[2], -1.0, 1.0)))
        ras.append(ra_deg)
        decs.append(dec_deg)
        labels.append((code, entry["name"], ra_deg, dec_deg))

    ax1.scatter(ras, decs, s=45, color="#2563eb", alpha=0.8, label="AGC CATLOG Stars (B-1 Scaled)")

    for code, name, ra_d, dec_d in labels:
        if code in (code1, code2):
            continue
        dx_pt, dy_pt = 4, 3
        if code == 14:  # Canopus: place label to the right above legend
            dx_pt, dy_pt = 8, -4
        elif code == 12:  # Rigel: place label to the left so it doesn't touch Sirius star
            dx_pt, dy_pt = -52, 4
        ax1.annotate(
            f"#{code:02d} {name}",
            xy=(ra_d, dec_d),
            xytext=(dx_pt, dy_pt),
            textcoords="offset points",
            fontsize=7.5,
            color="#334155",
        )

    # Highlight the sighted star pair
    s1 = catalog[code1]
    s2 = catalog[code2]
    ra1 = math.degrees(math.atan2(s1["u_ref"][1], s1["u_ref"][0])) % 360.0
    dec1 = math.degrees(math.asin(s1["u_ref"][2]))
    ra2 = math.degrees(math.atan2(s2["u_ref"][1], s2["u_ref"][0])) % 360.0
    dec2 = math.degrees(math.asin(s2["u_ref"][2]))

    ax1.plot(
        [ra1, ra2],
        [dec1, dec2],
        "--",
        color="#dc2626",
        lw=1.8,
        label=f"P52 Sighted Pair (Sep = {n05_info[0]:.2f} deg)",
    )
    ax1.scatter(
        [ra1, ra2],
        [dec1, dec2],
        s=130,
        marker="*",
        color="#dc2626",
        zorder=5,
        label=f"Star #{code1} ({s1['name']}) & Star #{code2} ({s2['name']})",
    )
    ax1.annotate(
        f"Star #{code1} ({s1['name']})\nOctal {s1['octal']}",
        xy=(ra1, dec1),
        xytext=(ra1 + 14, dec1 - 14),
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.2),
        fontsize=8.5,
        fontweight="bold",
        color="#b91c1c",
    )
    ax1.annotate(
        f"Star #{code2} ({s2['name']})\nOctal {s2['octal']}",
        xy=(ra2, dec2),
        xytext=(ra2 - 75, dec2 + 10),
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.2),
        fontsize=8.5,
        fontweight="bold",
        color="#b91c1c",
    )

    ax1.set_xlim(0, 365)
    ax1.set_ylim(-78, 75)
    ax1.set_xlabel("Right Ascension (deg)")
    ax1.set_ylabel("Declination (deg)")
    ax1.set_title("Subset of Decoded Comanche055 STAR_TABLES.agc Catalog")
    ax1.legend(loc="upper right", fontsize=8)

    # Panel 2: Sextant reticle mark scatter (arcsec) for Star #1 + Noun 05 summary box
    # Build tangent plane basis around u1_sm_true
    e_az = np.cross(np.array([0.0, 0.0, 1.0]), u1_sm_true)
    e_az = e_az / np.linalg.norm(e_az)
    e_el = np.cross(u1_sm_true, e_az)

    d_az_arcsec = [math.degrees(np.dot(m - u1_sm_true, e_az)) * 3600.0 for m in marks1_sm]
    d_el_arcsec = [math.degrees(np.dot(m - u1_sm_true, e_el)) * 3600.0 for m in marks1_sm]
    avg_az = np.mean(d_az_arcsec)
    avg_el = np.mean(d_el_arcsec)

    # Draw reticle crosshairs and 10 / 20 arcsec rings
    for rad_as, ls in [(10.0, "--"), (20.0, ":")]:
        th = np.linspace(0, 2 * math.pi, 120)
        ax2.plot(rad_as * np.cos(th), rad_as * np.sin(th), ls=ls, color="#94a3b8", lw=1.0)

    ax2.axhline(0.0, color="#64748b", lw=0.8)
    ax2.axvline(0.0, color="#64748b", lw=0.8)
    ax2.scatter(
        d_az_arcsec,
        d_el_arcsec,
        s=65,
        color="#2563eb",
        zorder=4,
        label="5 Individual SXT Marks (MARKRUPT)",
    )
    for idx, (x_as, y_as) in enumerate(zip(d_az_arcsec, d_el_arcsec), start=1):
        ax2.annotate(f"M{idx}", (x_as, y_as), xytext=(4, 4), textcoords="offset points", fontsize=8)

    ax2.plot(
        avg_az,
        avg_el,
        "P",
        color="#dc2626",
        ms=10,
        label=f"S52.2 Averaged Centroid ({math.hypot(avg_az, avg_el):.1f} arcsec)",
        zorder=5,
    )
    ax2.plot(0.0, 0.0, "+", color="#0f766e", ms=12, mew=2, label="True Star Line of Sight")

    ang_cat, ang_sm, diff_deg, dsky_n05 = n05_info
    n05_box = (
        f"CHKSDATA — Verb 06 Noun 05:\n"
        f"  Catalog Star Angle : {ang_cat:7.4f} deg\n"
        f"  Measured SXT Angle : {ang_sm:7.4f} deg\n"
        f"  |Delta Angle|      : {diff_deg:7.4f} deg ({diff_deg*3600:.1f}\")\n"
        f"  DSKY N05 R1        : {dsky_n05:05d} (0.01 deg)"
    )
    ax2.text(
        0.03,
        0.04,
        n05_box,
        transform=ax2.transAxes,
        fontsize=8.2,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8fafc", edgecolor="#cbd5e1"),
    )

    ax2.set_xlim(-28, 28)
    ax2.set_ylim(-28, 28)
    ax2.set_aspect("equal")
    ax2.set_xlabel("Reticle Azimuth Offset (arcsec)")
    ax2.set_ylabel("Reticle Elevation Offset (arcsec)")
    ax2.set_title(f"28x Sextant Reticle Marks on Star #{code1} ({s1['name']})")
    ax2.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    save(fig, "csm_03_star_catalog_sky")


def plot_imu_alignment_axes(
    drift_deg_true,
    torquing_deg_est,
    residual_arcsec,
    u1_ref,
    u2_ref,
):
    """Create Figure 2: 3D Stable Member axes alignment & CALCGTA Noun 93 angles."""
    fig = plt.figure(figsize=(13.5, 5.8))
    fig.suptitle(
        "Comanche055 INFLIGHT_ALIGNMENT_ROUTINES.agc — AXISGEN Triad & CALCGTA (Noun 93)",
        fontsize=13,
        fontweight="bold",
    )

    # Panel 1: 3D view of REFSMMAT axes, exaggerated drifted SM axes, and star vectors
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")

    # Exaggerate the visual drift angle by 12x on the 3D quiver plot so the pre-alignment
    # offset is clearly visible to the naked eye (annotated on plot)
    r_vis_drift = euler_xyz_matrix(np.radians(drift_deg_true * 12.0))
    axis_names = ["X_SM", "Y_SM", "Z_SM"]
    colors_ref = ["#dc2626", "#059669", "#2563eb"]

    for i in range(3):
        e_axis = np.zeros(3)
        e_axis[i] = 1.0
        e_drifted = r_vis_drift.T @ e_axis

        # Desired REFSMMAT axis (solid)
        ax1.quiver(
            0, 0, 0,
            e_axis[0], e_axis[1], e_axis[2],
            color=colors_ref[i],
            lw=2.4,
            arrow_length_ratio=0.12,
            label=f"Desired {axis_names[i]} (Aligned)" if i == 0 else f"Desired {axis_names[i]}",
        )
        # Drifted Stable Member axis before P52 torquing (dashed)
        ax1.quiver(
            0, 0, 0,
            e_drifted[0], e_drifted[1], e_drifted[2],
            color=colors_ref[i],
            lw=1.4,
            linestyle="--",
            alpha=0.65,
            arrow_length_ratio=0.12,
            label=f"Drifted {axis_names[i]} (12x visual scale)" if i == 0 else None,
        )
        ax1.text(
            e_axis[0] * 1.12,
            e_axis[1] * 1.12,
            e_axis[2] * 1.12,
            axis_names[i],
            color=colors_ref[i],
            fontweight="bold",
            fontsize=9,
        )

    # Plot the two catalog star vectors used by AXISGEN
    for idx, (u_st, st_lbl, st_col) in enumerate(
        [(u1_ref, "Star #15 (Sirius)", "#d97706"), (u2_ref, "Star #22 (Regulus)", "#7c3aed")]
    ):
        ax1.quiver(
            0, 0, 0,
            u_st[0], u_st[1], u_st[2],
            color=st_col,
            lw=2.0,
            arrow_length_ratio=0.1,
            label=st_lbl,
        )

    ax1.set_xlim([-1.1, 1.1])
    ax1.set_ylim([-1.1, 1.1])
    ax1.set_zlim([-1.1, 1.1])
    ax1.set_xlabel("X_REF")
    ax1.set_ylabel("Y_REF")
    ax1.set_zlabel("Z_REF")
    ax1.set_title("3D Stable Member Axes & Sighted Star Vectors")
    ax1.view_init(elev=22, azim=38)
    ax1.legend(loc="upper left", fontsize=7.8)

    # Panel 2: Bar chart comparing True IMU Drift vs CALCGTA Noun 93 Torquing Angles
    ax2 = fig.add_subplot(1, 2, 2)
    axes_labels = ["X Gyro (OG)\nNoun 93 R1", "Y Gyro (IG)\nNoun 93 R2", "Z Gyro (MG)\nNoun 93 R3"]
    x_pos = np.arange(len(axes_labels))
    width = 0.34

    ax2.bar(
        x_pos - width / 2,
        drift_deg_true,
        width,
        color="#2563eb",
        alpha=0.85,
        label="True IMU Platform Drift (deg)",
    )
    ax2.bar(
        x_pos + width / 2,
        torquing_deg_est,
        width,
        color="#d97706",
        alpha=0.85,
        label="CALCGTA Computed Torquing Angle (deg)",
    )

    for i in range(3):
        y_top = max(abs(drift_deg_true[i]), abs(torquing_deg_est[i]))
        y_pos = drift_deg_true[i] + math.copysign(0.08, drift_deg_true[i])
        ax2.text(
            x_pos[i],
            y_pos,
            f"Residual: {residual_arcsec[i]:+.1f}\"",
            ha="center",
            va="bottom" if drift_deg_true[i] >= 0 else "top",
            fontsize=8.5,
            fontweight="bold",
            color="#0f766e",
        )

    ax2.axhline(0.0, color="#475569", lw=1.0)
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(axes_labels)
    ax2.set_ylabel("Angle (degrees)")
    ax2.set_ylim(-1.6, 1.6)
    ax2.set_title("CALCGTA Gyro Torquing Angles (Noun 93) vs True IMU Drift")
    ax2.legend(loc="upper right", fontsize=8.5)

    # Summary annotation box
    norm_res_arcsec = float(np.linalg.norm(residual_arcsec))
    summary_txt = (
        f"Post-R55 Gyro Torquing Result:\n"
        f"  Initial 3-Axis Drift : {np.linalg.norm(drift_deg_true)*3600:,.1f} arcsec "
        f"({np.linalg.norm(drift_deg_true):.3f} deg)\n"
        f"  Final Residual Error : {norm_res_arcsec:5.1f} arcsec "
        f"({norm_res_arcsec/3600:.5f} deg)"
    )
    ax2.text(
        0.04,
        0.05,
        summary_txt,
        transform=ax2.transAxes,
        fontsize=8.5,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8fafc", edgecolor="#cbd5e1"),
    )

    fig.tight_layout()
    save(fig, "csm_03_imu_alignment_axes")


# ---------------------------------------------------------------------------
# 7. Main Walkthrough
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("Apollo 11 CSM — Program 52 IMU Alignment by Star Sightings (Comanche055)")
    print("=" * 72)

    # Step 1: Decode onboard star catalog from STAR_TABLES.agc
    catalog = decode_star_catalog()
    code1, code2 = 15, 22  # Star 15 (Sirius, 017) & Star 22 (Regulus, 026)
    s1, s2 = catalog[code1], catalog[code2]
    sep_deg, cross_mag, valid = score_star_pair(s1["u_ref"], s2["u_ref"])

    step(
        1,
        "Decode Star Catalog & Select Star Pair (STAR_TABLES.agc @ CATLOG, P51-P53.agc @ PICAPAR)",
        f"Decoded {len(catalog)} representative B-1 half-unit star vectors from STAR_TABLES.agc.\n"
        f"Selected Star #{code1} ({s1['name']}, Octal {s1['octal']}) and "
        f"Star #{code2} ({s2['name']}, Octal {s2['octal']}).\n"
        f"Angular separation = {sep_deg:.2f} deg, |u1 x u2| = {cross_mag:.4f} "
        f"(PICAPAR geometry check passed = {valid}).",
    )

    # Step 2: Simulate drifted IMU platform and 5 noisy Sextant marks per star
    # True IMU Stable Member drift: (+1.15 deg, -0.78 deg, +0.92 deg)
    drift_deg_true = np.array([1.15, -0.78, 0.92])
    r_sm_true_from_ref = euler_xyz_matrix(np.radians(drift_deg_true))

    # Spacecraft Navigation Base orientation relative to Stable Member (CDU angles)
    cdu_angles_rad = np.radians([12.0, -8.5, 19.0])
    r_nb_from_sm_true = euler_xyz_matrix(cdu_angles_rad)

    rng = np.random.default_rng(19690720)
    u1_sm_meas, marks1_sm, _ = simulate_sextant_marks(
        s1["u_ref"], r_sm_true_from_ref, r_nb_from_sm_true, n_marks=5, noise_arcsec=10.0, rng=rng
    )
    u2_sm_meas, marks2_sm, _ = simulate_sextant_marks(
        s2["u_ref"], r_sm_true_from_ref, r_nb_from_sm_true, n_marks=5, noise_arcsec=10.0, rng=rng
    )
    u1_sm_true = r_sm_true_from_ref @ s1["u_ref"]

    step(
        2,
        "Sextant Sighting Marks (SXTMARK.agc @ MARKRUPT, CSM_GEOMETRY.agc @ SXTNB)",
        f"Simulated 5 sextant marks per star with 10 arcsec 1-sigma optical noise.\n"
        f"Star #{code1} ({s1['name']}) averaged SM vector: "
        f"[{u1_sm_meas[0]:+.6f}, {u1_sm_meas[1]:+.6f}, {u1_sm_meas[2]:+.6f}]\n"
        f"Star #{code2} ({s2['name']}) averaged SM vector: "
        f"[{u2_sm_meas[0]:+.6f}, {u2_sm_meas[1]:+.6f}, {u2_sm_meas[2]:+.6f}]",
    )

    # Step 3: Star Angle Difference Check (Noun 05)
    n05_info = check_star_angle_difference(
        s1["u_ref"], s2["u_ref"], u1_sm_meas, u2_sm_meas
    )
    ang_cat, ang_sm, diff_deg, dsky_n05 = n05_info
    step(
        3,
        "Star Angle Difference Check — Verb 06 Noun 05 (P51-P53.agc @ CHKSDATA)",
        f"Catalog separation = {ang_cat:.4f} deg vs Measured SM separation = {ang_sm:.4f} deg.\n"
        f"Star Angle Difference |Delta theta| = {diff_deg:.4f} deg ({diff_deg*3600:.1f} arcsec).\n"
        f"DSKY Noun 05 R1 display = {dsky_n05:05d} (hundredths of a degree; limit <= 00002).",
    )

    # Step 4: AXISGEN Triad & CALCGTA Gyro Torquing Angles (Noun 93)
    r_sm_from_ref_est, _, _ = axisgen(
        s1["u_ref"], s2["u_ref"], u1_sm_meas, u2_sm_meas
    )
    torquing_rad = calcgta(r_sm_from_ref_est)
    torquing_deg_est = np.degrees(torquing_rad)

    # Residual misalignment after torquing the platform by -torquing_rad (R55)
    r_residual = r_sm_from_ref_est.T @ r_sm_true_from_ref
    residual_rad = calcgta(r_residual)
    residual_arcsec = np.degrees(residual_rad) * 3600.0

    step(
        4,
        "AXISGEN Alignment Matrix & CALCGTA Gyro Torquing Angles (Noun 93)",
        f"True IMU drift (deg)         : X={drift_deg_true[0]:+.4f}, "
        f"Y={drift_deg_true[1]:+.4f}, Z={drift_deg_true[2]:+.4f}\n"
        f"CALCGTA Noun 93 (deg)        : X={torquing_deg_est[0]:+.4f}, "
        f"Y={torquing_deg_est[1]:+.4f}, Z={torquing_deg_est[2]:+.4f}\n"
        f"Post-torquing residual (arcsec): dX={residual_arcsec[0]:+.1f}\", "
        f"dY={residual_arcsec[1]:+.1f}\", dZ={residual_arcsec[2]:+.1f}\" "
        f"(total = {np.linalg.norm(residual_arcsec):.1f}\").",
    )

    plot_star_catalog_and_marks(catalog, code1, code2, marks1_sm, u1_sm_true, n05_info)
    plot_imu_alignment_axes(
        drift_deg_true,
        torquing_deg_est,
        residual_arcsec,
        s1["u_ref"],
        s2["u_ref"],
    )


if __name__ == "__main__":
    main()
