"""
Apollo 11 Command Module — Conic Subroutines & Translunar Coast
===============================================================
Translates the AGC's orbital mechanics and numerical integration routines from
Comanche055:
  * CONIC_SUBROUTINES.agc — Universal-variable Kepler solver (KEPLERN, KEPLOOP,
    DELTIME, ITERATOR, NEWSTATE) and Lambert two-point boundary-value solver
    (LAMBERT, GEOM, GETX, LAMBLOOP, INITV).
  * TIME_OF_FREE_FALL.agc — Closed-form time-of-free-fall to entry interface
    (TFFCONIC, TFFRP/RA, CALCTFF, T(X)).
  * ORBITAL_INTEGRATION.agc — Encke's method coasting integration (KEPPREP,
    TIMESTEP, ACCOMP, GAMCOMP, OBLATE, RECTEST, RECTIFY, CHKSWTCH, ORIGCHNG).

During the 3-day translunar coast from Trans-Lunar Injection (TLI) to Lunar
Orbit Insertion (LOI-1), the Command Module computer propagated its state vector
using Encke's method (measuring only the small deviation from a reference
Keplerian conic) and switched the coordinate origin from Earth to the Moon at
the AGC's Sphere of Influence radius RSPHERE = 64,373.76 km.
"""

import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from common import (
    MU_EARTH,
    MU_MOON,
    R_EARTH,
    R_MOON,
    src,
    step,
    save,
)


# ---------------------------------------------------------------------------
# 1. Universal-Variable Stumpff Functions & Kepler Time Equation (DELTIME)
# ---------------------------------------------------------------------------

def stumpff_s_and_c(xi):
    """
    Evaluate the universal Stumpff functions S(xi) and C(xi).

    Citation:
        {c_deltime}

    In the AGC's DELTIME routine (CONIC_SUBROUTINES.agc, lines 851-903),
    xi = alpha * x^2 is bounded so |xi| <= 50, and S(xi) and C(xi) are evaluated
    using 9-term nested Horner polynomials without branching into trig/hyperbolic
    functions:
        S(xi) = 1/3! - xi/5! + xi^2/7! - xi^3/9! + ...
        C(xi) = 1/2! - xi/4! + xi^2/6! - xi^3/8! + ...
    (In the AGC assembly, the table coefficients are stored as S(xi)/2 and
    C(xi)/16 with powers of 2 absorbed into xi to prevent fixed-point overflow.)
    """.format(c_deltime=src("Comanche055/CONIC_SUBROUTINES.agc", "DELTIME"))
    if abs(xi) <= 50.0:
        # 10-term Taylor/Stumpff series (matching AGC DELTIME polynomial order)
        s_val = 0.0
        c_val = 0.0
        for k in range(9, -1, -1):
            s_val = -xi * s_val + 1.0 / math.factorial(2 * k + 3)
            c_val = -xi * c_val + 1.0 / math.factorial(2 * k + 2)
        return s_val, c_val

    if xi > 0.0:
        sqrt_xi = math.sqrt(xi)
        s_val = (sqrt_xi - math.sin(sqrt_xi)) / (xi * sqrt_xi)
        c_val = (1.0 - math.cos(sqrt_xi)) / xi
    else:
        sqrt_neg_xi = math.sqrt(-xi)
        s_val = (math.sinh(sqrt_neg_xi) - sqrt_neg_xi) / (-xi * sqrt_neg_xi)
        c_val = (math.cosh(sqrt_neg_xi) - 1.0) / (-xi)
    return s_val, c_val


def kepler_deltime(x, r0_mag, r0_dot_v0, alpha, sqrt_mu):
    """
    Compute elapsed time t(x) as a function of universal anomaly x.

    Citation:
        {c_deltime}

    Evaluates the universal Kepler time-of-flight equation:
        xi   = alpha * x^2
        t(x) = (1 / sqrt(mu)) * [ x^3 * S(xi)
                                + (r0 . v0 / sqrt(mu)) * x^2 * C(xi)
                                + r0 * x * (1 - xi * S(xi)) ]
    """.format(c_deltime=src("Comanche055/CONIC_SUBROUTINES.agc", "DELTIME"))
    xi = alpha * x * x
    s_xi, c_xi = stumpff_s_and_c(xi)
    sigma0 = r0_dot_v0 / sqrt_mu
    t_x = (
        (x ** 3) * s_xi
        + sigma0 * (x ** 2) * c_xi
        + r0_mag * x * (1.0 - xi * s_xi)
    ) / sqrt_mu
    return t_x, xi, s_xi, c_xi


# ---------------------------------------------------------------------------
# 2. Universal Kepler Solver & Bounded Secant Iterator (KEPLERN / KEPLOOP)
# ---------------------------------------------------------------------------

def kepler_propagate(r0_vec, v0_vec, dt, mu, max_iter=30, tol_time=1e-7):
    """
    Propagate state (r0, v0) through elapsed time dt using the AGC's universal
    Kepler solver and bounded secant iterator.

    Citations:
        {c_keplern}
        {c_keploop}
        {c_iterator}
        {c_newstate}

    How the AGC does it:
      1. KEPPREP/KEPLERN computes r0 = |r0|, alpha = 2/r0 - |v0|^2/mu (reciprocal
         semi-major axis), and brackets the universal anomaly x within [x_min, x_max].
      2. KEPLOOP calls DELTIME to evaluate t(x) and uses ITERATOR (a bounded
         secant/regula-falsi root finder):
           - If the time residual err_t = dt - t(x) > 0, x is too small, so
             x_min is raised to x. If err_t < 0, x_max is lowered to x.
           - A secant step dx = err_t * (x - x_prev) / (t(x) - t(x_prev)) is
             computed. If x + dx would step outside [x_min, x_max], ITERATOR
             clamps dx to 0.9 * (x_bound - x) (constant DP9/10 at NDXCHNGE /
             PDXCHNGE).
      3. NEWSTATE evaluates the Lagrange f, g, f_dot, g_dot coefficients from
         the converged x to update r(t0 + dt) and v(t0 + dt).
    """.format(
        c_keplern=src("Comanche055/CONIC_SUBROUTINES.agc", "KEPLERN"),
        c_keploop=src("Comanche055/CONIC_SUBROUTINES.agc", "KEPLOOP"),
        c_iterator=src("Comanche055/CONIC_SUBROUTINES.agc", "ITERATOR"),
        c_newstate=src("Comanche055/CONIC_SUBROUTINES.agc", "NEWSTATE"),
    )
    r0_vec = np.asarray(r0_vec, dtype=float)
    v0_vec = np.asarray(v0_vec, dtype=float)
    sqrt_mu = math.sqrt(mu)

    r0_mag = float(np.linalg.norm(r0_vec))
    v0_sq = float(np.dot(v0_vec, v0_vec))
    r0_dot_v0 = float(np.dot(r0_vec, v0_vec))
    alpha = 2.0 / r0_mag - v0_sq / mu

    # Bracket universal variable x (mirrors KEPLERN XMIN / XMAX setup)
    if alpha > 0.0:
        # Elliptic orbit: one full revolution corresponds to x_period = 2*pi / sqrt(alpha)
        x_period = 2.0 * math.pi / math.sqrt(alpha)
        if dt >= 0.0:
            x_min = 0.0
            x_max = max(x_period * 1.5, sqrt_mu * abs(dt) / r0_mag * 4.0)
        else:
            x_min = -max(x_period * 1.5, sqrt_mu * abs(dt) / r0_mag * 4.0)
            x_max = 0.0
        # Initial guess from circular mean motion approximation
        x = sqrt_mu * dt * alpha
        x = max(x_min + 0.05 * (x_max - x_min), min(x_max - 0.05 * (x_max - x_min), x))
    else:
        # Parabolic or hyperbolic orbit: xi = alpha * x^2 >= -50 in DELTIME
        x_lim = 7.0 / math.sqrt(max(abs(alpha), 1e-18))
        if dt >= 0.0:
            x_min, x_max = 0.0, x_lim
        else:
            x_min, x_max = -x_lim, 0.0
        x = np.clip(sqrt_mu * dt / r0_mag, 0.1 * x_min, 0.5 * (x_min + x_max))

    history = []
    x_prev = None
    t_prev = None

    for it in range(1, max_iter + 1):
        t_x, xi, s_xi, c_xi = kepler_deltime(x, r0_mag, r0_dot_v0, alpha, sqrt_mu)
        err_t = dt - t_x
        history.append({
            "iter": it,
            "x": x,
            "t_x": t_x,
            "err_t": err_t,
            "x_min": x_min,
            "x_max": x_max,
        })

        if abs(err_t) <= tol_time:
            break

        # Update bracket bounds [x_min, x_max] (ITERATOR in CONIC_SUBROUTINES.agc)
        if err_t > 0.0:
            x_min = max(x_min, x)
        else:
            x_max = min(x_max, x)

        # First iteration uses local slope dt/dx = r(x)/sqrt(mu); subsequent
        # iterations use the secant slope delta_x / delta_t (ITERATOR).
        if x_prev is None or abs(t_x - t_prev) < 1e-15:
            sigma0 = r0_dot_v0 / sqrt_mu
            r_est = (
                (x ** 2) * c_xi
                + sigma0 * x * (1.0 - xi * s_xi)
                + r0_mag * (1.0 - xi * c_xi)
            )
            dt_dx = max(r_est / sqrt_mu, 1e-6)
            dx = err_t / dt_dx
        else:
            dx = err_t * (x - x_prev) / (t_x - t_prev)

        # AGC DP9/10 clamp (NDXCHNGE / PDXCHNGE): never let x + dx cross x_min or x_max
        if dx > 0.0 and (x + dx) >= x_max:
            dx = 0.9 * (x_max - x)
        elif dx < 0.0 and (x + dx) <= x_min:
            dx = 0.9 * (x_min - x)

        x_prev, t_prev = x, t_x
        x = x + dx

    # NEWSTATE (CONIC_SUBROUTINES.agc, line 1019): evaluate f, g, fdot, gdot
    t_x, xi, s_xi, c_xi = kepler_deltime(x, r0_mag, r0_dot_v0, alpha, sqrt_mu)
    sigma0 = r0_dot_v0 / sqrt_mu
    r_mag = (
        (x ** 2) * c_xi
        + sigma0 * x * (1.0 - xi * s_xi)
        + r0_mag * (1.0 - xi * c_xi)
    )

    f = 1.0 - (x ** 2) * c_xi / r0_mag
    g = t_x - (x ** 3) * s_xi / sqrt_mu
    f_dot = (sqrt_mu / (r0_mag * r_mag)) * x * (xi * s_xi - 1.0)
    g_dot = 1.0 - (x ** 2) * c_xi / r_mag

    r_new = f * r0_vec + g * v0_vec
    v_new = f_dot * r0_vec + g_dot * v0_vec
    return r_new, v_new, history


# ---------------------------------------------------------------------------
# 3. Lambert Solver (LAMBERT / GEOM / GETX / LAMBLOOP / INITV)
# ---------------------------------------------------------------------------

def lambert_solve(r1_vec, r2_vec, dt, mu, transfer_less_than_pi=True, max_iter=35, tol_time=1e-4):
    """
    Solve Lambert's orbital boundary-value problem using the AGC's cot(gamma)
    formulation.

    Citations:
        {c_lambert}
        {c_geom}
        {c_getx}
        {c_lambloop}
        {c_initv}

    How the AGC does it:
      - Rather than iterating on semi-major axis or universal variable z directly,
        the AGC's LAMBERT iterates on COGA = cot(gamma_1), the cotangent of the
        initial flight-path angle measured from the local vertical.
      - GEOM computes |r1|, |r2|, cos(dnu), sin(dnu), and the asymptote bound
        COGAMIN or COGAMAX = (cos(dnu) - r1/r2) / sin(dnu) where semi-latus
        rectum p -> infinity.
      - For each trial COGA in LAMBLOOP:
          1. GETX computes the normalized semi-latus rectum:
               p / r1 = (1 - cos(dnu)) / (r1/r2 - cos(dnu) + COGA * sin(dnu))
             and alpha = (1/r1) * [2 - (p/r1) * (1 + COGA^2)], together with the
             universal anomaly x between r1 and r2.
          2. DELTIME evaluates the resulting transit time t(COGA).
          3. ITERATOR adjusts COGA within [COGAMIN, COGAMAX] using the bounded
             secant rule until |dt - t(COGA)| converges.
      - INITV reconstructs the initial velocity vector v1 from the converged
        COGA and p/r1.
    """.format(
        c_lambert=src("Comanche055/CONIC_SUBROUTINES.agc", "LAMBERT"),
        c_geom=src("Comanche055/CONIC_SUBROUTINES.agc", "GEOM"),
        c_getx=src("Comanche055/CONIC_SUBROUTINES.agc", "GETX"),
        c_lambloop=src("Comanche055/CONIC_SUBROUTINES.agc", "LAMBLOOP"),
        c_initv=src("Comanche055/CONIC_SUBROUTINES.agc", "INITV"),
    )
    r1_vec = np.asarray(r1_vec, dtype=float)
    r2_vec = np.asarray(r2_vec, dtype=float)
    sqrt_mu = math.sqrt(mu)

    r1 = float(np.linalg.norm(r1_vec))
    r2 = float(np.linalg.norm(r2_vec))
    u1 = r1_vec / r1
    u2 = r2_vec / r2

    cos_dnu = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
    sin_mag = math.sqrt(max(1.0 - cos_dnu * cos_dnu, 1e-16))
    sin_dnu = sin_mag if transfer_less_than_pi else -sin_mag

    # Transverse in-plane unit vector u_theta (INITV geometry)
    cross_12 = np.cross(u1, u2)
    if not transfer_less_than_pi:
        cross_12 = -cross_12
    u_normal = cross_12 / np.linalg.norm(cross_12)
    u_theta = np.cross(u_normal, u1)

    # Asymptote bound on COGA where denominator r1/r2 - cos_dnu + coga * sin_dnu = 0
    coga_asymp = (cos_dnu - r1 / r2) / sin_dnu
    # Upper bound on COGA where orbit remains open/valid before hitting zero-p limit
    if sin_dnu > 0.0:
        coga_min = coga_asymp + 1e-4
        coga_max = 1.2
    else:
        coga_min = -1.2
        coga_max = coga_asymp - 1e-4

    # Initial guess inside [coga_min, coga_max]
    coga = 0.5 * (coga_min + coga_max)
    coga_prev = None
    t_prev = None
    history = []

    for it in range(1, max_iter + 1):
        denom = (r1 / r2) - cos_dnu + coga * sin_dnu
        p_over_r1 = (1.0 - cos_dnu) / denom
        p = r1 * p_over_r1
        alpha = (2.0 - p_over_r1 * (1.0 + coga * coga)) / r1
        r1_dot_v1 = sqrt_mu * math.sqrt(p) * coga

        # Universal anomaly x from f and g conic identities (GETX)
        if alpha > 1e-12:
            cos_de = np.clip(1.0 - alpha * r1 * r2 * (1.0 - cos_dnu) / p, -1.0, 1.0)
            sin_de = math.sqrt(alpha) * r2 / math.sqrt(p) * (sin_dnu - coga * (1.0 - cos_dnu))
            delta_e = math.atan2(sin_de, cos_de)
            if delta_e < 0.0:
                delta_e += 2.0 * math.pi
            x = delta_e / math.sqrt(alpha)
        elif alpha < -1e-12:
            sinh_dh = math.sqrt(-alpha) * r2 / math.sqrt(p) * (sin_dnu - coga * (1.0 - cos_dnu))
            delta_h = math.asinh(sinh_dh)
            x = delta_h / math.sqrt(-alpha)
        else:
            x = (r2 / math.sqrt(p)) * (sin_dnu - coga * (1.0 - cos_dnu))

        t_guess, _, _, _ = kepler_deltime(x, r1, r1_dot_v1, alpha, sqrt_mu)
        err_t = dt - t_guess
        history.append({"iter": it, "coga": coga, "t_guess": t_guess, "err_t": err_t})

        if abs(err_t) <= tol_time:
            break

        # For sin_dnu > 0, increasing COGA increases denom, decreases p, and INCREASES transit time t_guess.
        # Thus if err_t = dt - t_guess > 0 (t_guess too small), we must increase COGA (raise coga_min).
        if (err_t > 0.0 and sin_dnu > 0.0) or (err_t < 0.0 and sin_dnu < 0.0):
            coga_min = max(coga_min, coga)
        else:
            coga_max = min(coga_max, coga)

        if coga_prev is None or abs(t_guess - t_prev) < 1e-12:
            dcoga = 0.08 * math.copysign(1.0, err_t * sin_dnu)
        else:
            dcoga = err_t * (coga - coga_prev) / (t_guess - t_prev)

        # Bounded secant clamp (DP9/10 in ITERATOR)
        if dcoga > 0.0 and (coga + dcoga) >= coga_max:
            dcoga = 0.5 * (coga_max - coga)
        elif dcoga < 0.0 and (coga + dcoga) <= coga_min:
            dcoga = 0.5 * (coga_min - coga)

        coga_prev, t_prev = coga, t_guess
        coga = coga + dcoga

    # Reconstruct initial velocity v1 via INITV (CONIC_SUBROUTINES.agc, line 1583)
    denom = (r1 / r2) - cos_dnu + coga * sin_dnu
    p_over_r1 = (1.0 - cos_dnu) / denom
    v_transverse = math.sqrt(mu * p_over_r1 / r1)
    v1_vec = v_transverse * (coga * u1 + u_theta)
    return v1_vec, history


# ---------------------------------------------------------------------------
# 4. Time of Free Fall to Entry Interface (TIME_OF_FREE_FALL.agc)
# ---------------------------------------------------------------------------

def calc_time_of_free_fall(r_vec, v_vec, r_target=R_EARTH + 121_920.0, mu=MU_EARTH):
    """
    Compute conic parameters (apogee, perigee) and time of free fall (TFF) down
    to a target radius (default: 400,000 ft = 121.92 km Entry Interface).

    Citations:
        {c_tffconic}
        {c_tffrpra}
        {c_calctff}
        {c_tx}

    In TIME_OF_FREE_FALL.agc:
      - TFFCONIC computes specific angular momentum, semi-major axis a, and
        eccentricity e.
      - TFFRP/RA computes apocenter r_a = a*(1 + e) and pericenter r_p = a*(1 - e).
      - CALCTFF computes the eccentric anomaly E(r) at current radius r and at
        target radius r_target using cos(E) = (1 - r/a) / e, and evaluates
        Kepler's equation (using the Chebyshev polynomial T(X) near e -> 1 so
        near-parabolic lunar returns do not lose precision).
    """.format(
        c_tffconic=src("Comanche055/TIME_OF_FREE_FALL.agc", "TFFCONIC"),
        c_tffrpra=src("Comanche055/TIME_OF_FREE_FALL.agc", "TFFRP/RA"),
        c_calctff=src("Comanche055/TIME_OF_FREE_FALL.agc", "CALCTFF"),
        c_tx=src("Comanche055/TIME_OF_FREE_FALL.agc", "T(X)"),
    )
    r_mag = float(np.linalg.norm(r_vec))
    v_sq = float(np.dot(v_vec, v_vec))
    r_dot_v = float(np.dot(r_vec, v_vec))
    h_vec = np.cross(r_vec, v_vec)
    p = float(np.dot(h_vec, h_vec)) / mu

    alpha = 2.0 / r_mag - v_sq / mu
    a = 1.0 / alpha
    e = math.sqrt(max(1.0 - p * alpha, 0.0))
    r_apogee = a * (1.0 + e)
    r_perigee = a * (1.0 - e)

    # Eccentric anomaly at current position and at target radius (inbound, E < 0 or > pi)
    cos_e0 = np.clip((1.0 - r_mag * alpha) / max(e, 1e-12), -1.0, 1.0)
    cos_ef = np.clip((1.0 - r_target * alpha) / max(e, 1e-12), -1.0, 1.0)
    e0 = math.acos(cos_e0)
    ef = math.acos(cos_ef)
    if r_dot_v < 0.0:
        # Inbound toward perigee: M decreases from E0 down to Ef
        m0 = e0 - e * math.sin(e0)
        mf = ef - e * math.sin(ef)
        tff = math.sqrt((a ** 3) / mu) * (m0 - mf)
    else:
        # Outbound: goes through apogee (M = pi) then down to Ef
        m0 = e0 - e * math.sin(e0)
        mf = ef - e * math.sin(ef)
        tff = math.sqrt((a ** 3) / mu) * ((2.0 * math.pi - m0) - mf)

    return {
        "a": a,
        "e": e,
        "r_apogee": r_apogee,
        "r_perigee": r_perigee,
        "tff_sec": tff,
    }


# ---------------------------------------------------------------------------
# 5. Encke's Method Coasting Integration (ORBITAL_INTEGRATION.agc)
# ---------------------------------------------------------------------------

RSPHERE_MOON_M = 64_373_760.0  # AGC sphere of influence radius RSPHERE (64,373.76 km)


def encke_gamcomp(q):
    """
    Evaluate Encke's differential gravity function f(q) = [(1 + q)^(3/2) - 1] / q
    avoiding catastrophic cancellation when |q| << 1.

    Citation:
        {c_gamcomp}

    In ORBITAL_INTEGRATION.agc @ GAMCOMP, the position deviation delta(r) is much
    smaller than the reference conic radius r_conic, so |r|^2 and |r_conic|^2 are
    nearly equal. Computing 1/|r_conic|^3 - 1/|r|^3 directly in finite precision
    would lose most significant bits. Instead, the AGC computes:
        q = (delta . (r + r_conic)) / |r|^2
    and evaluates the polynomial factor so the differential two-body gravity is
    found cleanly from delta directly.
    """.format(c_gamcomp=src("Comanche055/ORBITAL_INTEGRATION.agc", "GAMCOMP"))
    if abs(q) < 1e-4:
        return 1.5 + q * (0.375 - q * (0.0625 - 0.0234375 * q))
    return ((1.0 + q) ** 1.5 - 1.0) / q


def encke_translunar_propagate(r0_earth, v0_earth, moon_pos_fn, t_end, dt=60.0):
    """
    Propagate a translunar trajectory using the AGC's Encke method with
    reference-conic rectification and Earth/Moon sphere-of-influence switching.

    Citations:
        {c_kepprep}
        {c_accomp}
        {c_gamcomp}
        {c_rectest}
        {c_rectify}
        {c_chkswtch}
        {c_origchng}
        {c_rsphere}

    How the AGC's Encke integrator works:
      - Rather than integrating the huge central-body acceleration -mu*r/|r|^3
        directly, the AGC maintains a reference two-body conic (r_conic, v_conic)
        propagated analytically via KEPLERN, plus a small deviation vector
        (delta_r, delta_v) caused by third-body gravity and oblateness:
            r_true(t) = r_conic(t) + delta_r(t)
            v_true(t) = v_conic(t) + delta_v(t)
      - At each step (TIMESTEP / DIFEQ), KEPLERN advances (r_conic, v_conic), and
        ACCOMP + GAMCOMP integrate:
            d^2(delta_r)/dt^2 = -(mu / |r_conic|^3) * [ delta_r + f(q) * q * r_true ]
                                + a_perturbing
      - RECTEST checks if |delta_r| / |r_conic| > 0.0075 or |delta_v| / |v_conic| > 0.0075.
        When exceeded, RECTIFY resets the reference conic to the current true
        state (r_conic <- r_true, delta_r <- 0).
      - CHKSWTCH & ORIGCHNG monitor the spacecraft's distance to the Moon and
        switch the central-body origin between Earth and Moon at
        RSPHERE = 64,373.76 km.
    """.format(
        c_kepprep=src("Comanche055/ORBITAL_INTEGRATION.agc", "KEPPREP"),
        c_accomp=src("Comanche055/ORBITAL_INTEGRATION.agc", "ACCOMP"),
        c_gamcomp=src("Comanche055/ORBITAL_INTEGRATION.agc", "GAMCOMP"),
        c_rectest=src("Comanche055/ORBITAL_INTEGRATION.agc", "RECTEST"),
        c_rectify=src("Comanche055/ORBITAL_INTEGRATION.agc", "RECTIFY"),
        c_chkswtch=src("Comanche055/ORBITAL_INTEGRATION.agc", "CHKSWTCH"),
        c_origchng=src("Comanche055/ORBITAL_INTEGRATION.agc", "ORIGCHNG"),
        c_rsphere=src("Comanche055/ORBITAL_INTEGRATION.agc", "RSPHERE"),
    )
    # Primary body: 0 = Earth, 1 = Moon
    origin = 0
    mu_primary = MU_EARTH
    mu_secondary = MU_MOON

    r_conic = np.array(r0_earth, dtype=float)
    v_conic = np.array(v0_earth, dtype=float)
    delta_r = np.zeros(3)
    delta_v = np.zeros(3)
    t_since_rect = 0.0
    r_rect0 = r_conic.copy()
    v_rect0 = v_conic.copy()

    def encke_accel(t_cur, r_con, d_r):
        r_true = r_con + d_r
        r_con_mag = np.linalg.norm(r_con)
        r_true_sq = np.dot(r_true, r_true)

        # GAMCOMP differential two-body term
        q = np.dot(d_r, r_true + r_con) / (r_con_mag ** 2)
        fq = encke_gamcomp(q)
        a_diff_2body = -(mu_primary / (np.linalg.norm(r_true) ** 3)) * (d_r - fq * q * r_con)

        # Secondary body third-body perturbation (ACCOMP)
        r_moon_e, _ = moon_pos_fn(t_cur)
        if origin == 0:
            # Central body = Earth, perturbing body = Moon at +r_moon_e
            r_sec = r_moon_e
        else:
            # Central body = Moon, perturbing body = Earth at -r_moon_e
            r_sec = -r_moon_e

        d_to_sec = r_true - r_sec
        q_sec = np.dot(r_true, r_true - 2.0 * r_sec) / np.dot(r_sec, r_sec)
        fq_sec = encke_gamcomp(q_sec)
        a_third = -(mu_secondary / (np.linalg.norm(d_to_sec) ** 3)) * (
            r_true + fq_sec * q_sec * r_sec
        )
        return a_diff_2body + a_third

    times = [0.0]
    pos_earth = [r_conic.copy()]
    vel_earth = [v_conic.copy()]
    origins = [origin]
    delta_mags = [0.0]
    rect_events = []
    soi_switches = []

    n_steps = int(round(t_end / dt))
    t = 0.0

    for _ in range(n_steps):
        # Advance reference conic across [t, t + dt] and midpoint t + dt/2 (KEPPREP)
        r_con_mid, _, _ = kepler_propagate(r_rect0, v_rect0, t_since_rect + 0.5 * dt, mu_primary)
        r_con_next, v_con_next, _ = kepler_propagate(r_rect0, v_rect0, t_since_rect + dt, mu_primary)

        # Integrate Encke deviation (delta_r, delta_v) over step dt (DIFEQ+0/+1/+2 Nystrom/RK4)
        a1 = encke_accel(t, r_conic, delta_r)
        dr2 = delta_r + 0.5 * dt * delta_v + 0.125 * (dt ** 2) * a1
        dv2 = delta_v + 0.5 * dt * a1
        a2 = encke_accel(t + 0.5 * dt, r_con_mid, dr2)
        dr3 = delta_r + 0.5 * dt * delta_v + 0.125 * (dt ** 2) * a2
        dv3 = delta_v + 0.5 * dt * a2
        a3 = encke_accel(t + 0.5 * dt, r_con_mid, dr3)
        dr4 = delta_r + dt * delta_v + 0.5 * (dt ** 2) * a3
        dv4 = delta_v + dt * a3
        a4 = encke_accel(t + dt, r_con_next, dr4)

        delta_r = delta_r + dt * (delta_v + (dt / 6.0) * (a1 + a2 + a3))
        delta_v = delta_v + (dt / 6.0) * (a1 + 2.0 * a2 + 2.0 * a3 + a4)
        r_conic = r_con_next
        v_conic = v_con_next
        t += dt
        t_since_rect += dt

        r_true = r_conic + delta_r
        v_true = v_conic + delta_v
        delta_mag = float(np.linalg.norm(delta_r))

        # Reconstruct Earth-centered state for logging
        r_moon_e, v_moon_e = moon_pos_fn(t)
        if origin == 0:
            r_e = r_true
            v_e = v_true
            dist_moon = float(np.linalg.norm(r_e - r_moon_e))
        else:
            r_e = r_true + r_moon_e
            v_e = v_true + v_moon_e
            dist_moon = float(np.linalg.norm(r_true))

        # RECTEST & RECTIFY (ORBITAL_INTEGRATION.agc, lines 502 & 620)
        if (
            np.linalg.norm(delta_r) / np.linalg.norm(r_conic) > 0.0075
            or np.linalg.norm(delta_v) / np.linalg.norm(v_conic) > 0.0075
        ):
            rect_events.append((t, r_e.copy(), delta_mag))
            r_conic = r_true.copy()
            v_conic = v_true.copy()
            r_rect0 = r_conic.copy()
            v_rect0 = v_conic.copy()
            delta_r[:] = 0.0
            delta_v[:] = 0.0
            t_since_rect = 0.0

        # CHKSWTCH & ORIGCHNG (ORBITAL_INTEGRATION.agc, lines 546 & 583):
        # Switch coordinate origin at RSPHERE = 64,373.76 km
        if origin == 0 and dist_moon < RSPHERE_MOON_M:
            origin = 1
            mu_primary, mu_secondary = MU_MOON, MU_EARTH
            r_conic = r_e - r_moon_e
            v_conic = v_e - v_moon_e
            r_rect0 = r_conic.copy()
            v_rect0 = v_conic.copy()
            delta_r[:] = 0.0
            delta_v[:] = 0.0
            t_since_rect = 0.0
            soi_switches.append(("Enter Moon SOI", t, r_e.copy()))
        elif origin == 1 and dist_moon > RSPHERE_MOON_M:
            origin = 0
            mu_primary, mu_secondary = MU_EARTH, MU_MOON
            r_conic = r_e.copy()
            v_conic = v_e.copy()
            r_rect0 = r_conic.copy()
            v_rect0 = v_conic.copy()
            delta_r[:] = 0.0
            delta_v[:] = 0.0
            t_since_rect = 0.0
            soi_switches.append(("Exit Moon SOI", t, r_e.copy()))

        times.append(t)
        pos_earth.append(r_e.copy())
        vel_earth.append(v_e.copy())
        origins.append(origin)
        delta_mags.append(delta_mag)

    return {
        "t": np.array(times),
        "r_earth": np.array(pos_earth),
        "v_earth": np.array(vel_earth),
        "origin": np.array(origins),
        "delta_mag": np.array(delta_mags),
        "rect_events": rect_events,
        "soi_switches": soi_switches,
    }


# ---------------------------------------------------------------------------
# 6. Visualization
# ---------------------------------------------------------------------------

def plot_kepler_and_lambert(kep_hist, lamb_hist, r1, r2, v1_lamb, dt_lamb):
    """Create Figure 1: AGC KEPLERN and LAMBERT convergence diagnostics."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.suptitle(
        "Comanche055 CONIC_SUBROUTINES.agc — Universal Kepler & Lambert Solvers",
        fontsize=13,
        fontweight="bold",
    )

    # Panel 1: Universal Kepler bounded secant convergence
    iters_k = [h["iter"] for h in kep_hist]
    errs_k = [max(abs(h["err_t"]), 1e-10) for h in kep_hist]
    xs_k = [h["x"] for h in kep_hist]
    xmins_k = [h["x_min"] for h in kep_hist]
    xmaxs_k = [h["x_max"] for h in kep_hist]

    color_err = "#2563eb"
    color_x = "#d97706"
    ax1.semilogy(
        iters_k,
        errs_k,
        "o-",
        color=color_err,
        lw=2.2,
        label="|dt - t(x)| Time Residual (s)",
    )
    ax1.set_xlabel("KEPLOOP Iteration")
    ax1.set_ylabel("Time Residual |dt - t(x)| (s)", color=color_err)
    ax1.tick_params(axis="y", labelcolor=color_err)
    ax1.set_xticks(iters_k)
    ax1.set_title("KEPLERN / KEPLOOP Universal Variable Convergence")

    ax1_r = ax1.twinx()
    ax1_r.plot(iters_k, xs_k, "s--", color=color_x, lw=1.8, label="Trial x (m^(1/2))")
    ax1_r.fill_between(
        iters_k,
        xmins_k,
        xmaxs_k,
        color=color_x,
        alpha=0.12,
        label="[XMIN, XMAX] Bracket",
    )
    ax1_r.set_ylabel("Universal Variable x (m^(1/2))", color=color_x)
    ax1_r.tick_params(axis="y", labelcolor=color_x)
    ax1_r.grid(False)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_r.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8.5)

    # Panel 2: Lambert COGA = cot(gamma_1) convergence and resulting transfer arc
    iters_l = [h["iter"] for h in lamb_hist]
    errs_l = [max(abs(h["err_t"]), 1e-6) for h in lamb_hist]
    cogas_l = [h["coga"] for h in lamb_hist]

    ax2.semilogy(
        iters_l,
        errs_l,
        "o-",
        color="#dc2626",
        lw=2.2,
        label="|dt - t(COGA)| Residual (s)",
    )
    ax2.set_xlabel("LAMBLOOP Iteration")
    ax2.set_ylabel("Transit Time Residual (s)", color="#dc2626")
    ax2.tick_params(axis="y", labelcolor="#dc2626")
    ax2.set_xticks(iters_l)
    ax2.set_title("LAMBERT / ITERATOR cot(gamma_1) Convergence")

    ax2_r = ax2.twinx()
    ax2_r.plot(
        iters_l,
        cogas_l,
        "^--",
        color="#059669",
        lw=1.8,
        label="COGA = cot(gamma_1)",
    )
    ax2_r.set_ylabel("COGA = cot(gamma_1)", color="#059669")
    ax2_r.tick_params(axis="y", labelcolor="#059669")
    ax2_r.grid(False)

    l1, lb1 = ax2.get_legend_handles_labels()
    l2, lb2 = ax2_r.get_legend_handles_labels()
    ax2.legend(l1 + l2, lb1 + lb2, loc="upper right", fontsize=8.5)

    fig.tight_layout()
    save(fig, "csm_02_kepler_convergence")


def plot_translunar_free_return(encke_data, moon_pos_fn):
    """Create Figure 2: Free-return figure-8 trajectory and Encke rectification."""
    t_arr = encke_data["t"]
    r_earth = encke_data["r_earth"]
    origins = encke_data["origin"]
    delta_km = encke_data["delta_mag"] / 1e3

    # Rotate each point into the Earth-Moon synodic (rotating) frame so the classic
    # figure-8 free-return geometry is clearly visible
    r_syn = np.zeros((len(t_arr), 2))
    r_moon_0, _ = moon_pos_fn(0.0)
    d_em_km = np.linalg.norm(r_moon_0) / 1e3

    for i, t in enumerate(t_arr):
        rm, _ = moon_pos_fn(t)
        theta_m = math.atan2(rm[1], rm[0])
        c, s = math.cos(-theta_m), math.sin(-theta_m)
        x_e, y_e = r_earth[i, 0] / 1e3, r_earth[i, 1] / 1e3
        r_syn[i, 0] = c * x_e - s * y_e
        r_syn[i, 1] = s * x_e + c * y_e

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(13.5, 6.0), gridspec_kw={"width_ratios": [1.35, 1.0]}
    )
    fig.suptitle(
        "Comanche055 ORBITAL_INTEGRATION.agc — Encke Free-Return Coast & SOI Switching",
        fontsize=13,
        fontweight="bold",
    )

    # Panel 1: Figure-8 trajectory in Earth-Moon rotating frame
    earth_Mask = origins == 0
    moon_Mask = origins == 1

    ax1.plot(
        r_syn[:, 0],
        r_syn[:, 1],
        color="#94a3b8",
        lw=1.0,
        zorder=1,
    )
    ax1.scatter(
        r_syn[earth_Mask, 0],
        r_syn[earth_Mask, 1],
        s=6,
        color="#2563eb",
        label="Earth-Centered Conic + Encke (Origin = Earth)",
        zorder=2,
    )
    ax1.scatter(
        r_syn[moon_Mask, 0],
        r_syn[moon_Mask, 1],
        s=8,
        color="#d97706",
        label="Moon-Centered Conic + Encke (Origin = Moon)",
        zorder=3,
    )

    # Plot Earth, Moon, and AGC RSPHERE circle around Moon
    ax1.add_patch(Circle((0.0, 0.0), R_EARTH / 1e3, color="#1d4ed8", alpha=0.85, zorder=4))
    ax1.plot(0.0, 0.0, "o", color="#1d4ed8", ms=8, label="Earth")
    ax1.plot(d_em_km, 0.0, "o", color="#475569", ms=6, label="Moon")
    soi_circle = Circle(
        (d_em_km, 0.0),
        RSPHERE_MOON_M / 1e3,
        fill=False,
        ls="--",
        color="#d97706",
        lw=1.4,
        label=f"AGC RSPHERE ({RSPHERE_MOON_M/1e3:,.0f} km)",
    )
    ax1.add_patch(soi_circle)

    # Mark rectification points in rotating frame
    rect_syn = []
    for t_r, r_e_r, _ in encke_data["rect_events"]:
        rm, _ = moon_pos_fn(t_r)
        th = math.atan2(rm[1], rm[0])
        c, s = math.cos(-th), math.sin(-th)
        rect_syn.append((c * r_e_r[0] / 1e3 - s * r_e_r[1] / 1e3, s * r_e_r[0] / 1e3 + c * r_e_r[1] / 1e3))
    if rect_syn:
        rect_syn = np.array(rect_syn)
        ax1.plot(
            rect_syn[:, 0],
            rect_syn[:, 1],
            "x",
            color="#dc2626",
            ms=6,
            mew=1.5,
            label=f"RECTIFY Events ({len(rect_syn)} conic resets)",
            zorder=5,
        )

    # Annotate outbound, perilune, and return branches
    mid_out = int(len(t_arr) * 0.22)
    mid_ret = int(len(t_arr) * 0.78)
    idx_peri = int(len(t_arr) * 0.50)
    ax1.annotate(
        "Outbound Coast\n(Post-TLI, ~3 days)",
        xy=(r_syn[mid_out, 0], r_syn[mid_out, 1]),
        xytext=(r_syn[mid_out, 0] - 55000, r_syn[mid_out, 1] + 38000),
        arrowprops=dict(arrowstyle="->", color="#2563eb", lw=1.2),
        fontsize=8.5,
        color="#1e40af",
        fontweight="bold",
    )
    ax1.annotate(
        "Transearth Return\n(Free-Return, ~3 days)",
        xy=(r_syn[mid_ret, 0], r_syn[mid_ret, 1]),
        xytext=(r_syn[mid_ret, 0] + 5000, r_syn[mid_ret, 1] - 50000),
        arrowprops=dict(arrowstyle="->", color="#0f766e", lw=1.2),
        fontsize=8.5,
        color="#0f766e",
        fontweight="bold",
    )
    ax1.annotate(
        "Pericynthion\n(Far-Side, h = 210 km)",
        xy=(r_syn[idx_peri, 0], r_syn[idx_peri, 1]),
        xytext=(r_syn[idx_peri, 0] + 18000, r_syn[idx_peri, 1] + 32000),
        arrowprops=dict(arrowstyle="->", color="#b45309", lw=1.2),
        fontsize=8.5,
        color="#b45309",
        fontweight="bold",
    )

    ax1.set_xlim(-35000, 520000)
    ax1.set_xlabel("Earth-Moon Rotating X (km)")
    ax1.set_ylabel("Earth-Moon Rotating Y (km)")
    ax1.set_title("Circum-Lunar Free-Return Figure-8 (Coplanar Circular Moon Approx.)")
    ax1.set_aspect("equal", adjustable="datalim")
    ax1.legend(loc="lower left", fontsize=8)

    # Panel 2: Encke deviation |delta_r| sawtooth and RECTIFY resets vs time
    t_hours = t_arr / 3600.0
    ax2.plot(
        t_hours,
        delta_km,
        color="#dc2626",
        lw=1.5,
        label="Encke Deviation |delta_r| (km)",
    )
    y_fracs = [0.84, 0.64]
    for idx_sw, (label_sw, t_sw, _) in enumerate(encke_data["soi_switches"]):
        ax2.axvline(t_sw / 3600.0, color="#d97706", ls="--", lw=1.4)
        yf = y_fracs[idx_sw % len(y_fracs)]
        ax2.text(
            t_sw / 3600.0 + 1.5,
            max(delta_km) * yf,
            f"ORIGCHNG:\n{label_sw}\n(t={t_sw/3600:.1f} h)",
            fontsize=8,
            color="#b45309",
            fontweight="bold",
        )

    ax2.set_xlabel("Mission Elapsed Time Since TLI Cutoff (hours)")
    ax2.set_ylabel("Encke Deviation |delta_r(t)| (km)")
    ax2.set_title("Encke Deviation Sawtooth (RECTEST & RECTIFY Resets)")
    ax2.legend(loc="upper left", fontsize=8.5)

    fig.tight_layout()
    save(fig, "csm_02_translunar_coast")


# ---------------------------------------------------------------------------
# 7. Main Walkthrough
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("Apollo 11 CSM — Conic Subroutines & Translunar Coast (Comanche055)")
    print("=" * 72)

    # Step 1: Universal Kepler propagation after TLI
    r_park = R_EARTH + 185_200.0  # 100 NM parking orbit
    v_tli = 10_842.0              # Post-TLI speed (~10.84 km/s)
    r0_tli = np.array([r_park, 0.0, 0.0])
    v0_tli = np.array([0.0, v_tli, 0.0])
    dt_test = 6.0 * 3600.0        # Propagate 6 hours post-TLI

    r_6h, v_6h, kep_hist = kepler_propagate(r0_tli, v0_tli, dt_test, MU_EARTH)
    step(
        1,
        "Universal Kepler Propagation (CONIC_SUBROUTINES.agc @ KEPLERN / DELTIME)",
        f"Propagated post-TLI state (r0 = {r_park/1e3:,.1f} km, v0 = {v_tli:,.1f} m/s) "
        f"forward by 6.0 hours.\n"
        f"KEPLOOP bounded secant iterator converged in {len(kep_hist)} iterations to "
        f"|dt - t(x)| = {abs(kep_hist[-1]['err_t']):.2e} s.\n"
        f"New radius |r(6h)| = {np.linalg.norm(r_6h)/1e3:,.1f} km, "
        f"speed |v(6h)| = {np.linalg.norm(v_6h):,.1f} m/s.",
    )

    # Step 2: Lambert two-point boundary-value problem
    v1_lamb, lamb_hist = lambert_solve(
        r0_tli, r_6h, dt_test, MU_EARTH, transfer_less_than_pi=True
    )
    r_check, _, _ = kepler_propagate(r0_tli, v1_lamb, dt_test, MU_EARTH)
    pos_err_m = np.linalg.norm(r_check - r_6h)
    step(
        2,
        "Lambert Boundary-Value Solver (CONIC_SUBROUTINES.agc @ LAMBERT / INITV)",
        f"Solved for initial velocity v1 given r1, r2, and dt = 6.0 h by iterating on "
        f"COGA = cot(gamma_1).\n"
        f"LAMBLOOP converged in {len(lamb_hist)} iterations; recovered |v1 - v0_tli| = "
        f"{np.linalg.norm(v1_lamb - v0_tli):.4f} m/s (endpoint error = {pos_err_m:.2f} m).",
    )

    # Step 3: Time of Free Fall (TIME_OF_FREE_FALL.agc)
    # Test from an inbound return state 100,000 km from Earth
    r_inbound = np.array([100_000_000.0, 0.0, 0.0])
    v_inbound = np.array([-2_650.0, 820.0, 0.0])
    tff_info = calc_time_of_free_fall(r_inbound, v_inbound)
    step(
        3,
        "Time of Free Fall to Entry Interface (TIME_OF_FREE_FALL.agc @ CALCTFF)",
        f"From inbound return radius {np.linalg.norm(r_inbound)/1e3:,.0f} km: "
        f"conic perigee radius r_p = {tff_info['r_perigee']/1e3:,.1f} km, "
        f"apogee radius r_a = {tff_info['r_apogee']/1e3:,.0f} km, "
        f"eccentricity e = {tff_info['e']:.4f}.\n"
        f"Predicted Time of Free Fall to 400,000 ft Entry Interface: "
        f"{tff_info['tff_sec']/3600:.2f} hours ({tff_info['tff_sec']:,.1f} s).",
    )

    # Step 4: Encke Translunar Coast & Circum-Lunar Free-Return Trajectory
    # Simplified coplanar circular Moon orbit at 384,400 km (labelled approximation).
    # We construct the exact symmetric circumlunar free-return trajectory that passes
    # 210 km above the lunar far side at t = 69.33 h and returns symmetrically to
    # Earth perigee (~185 km) at t = 138.67 h (~3 days out, ~3 days back).
    d_moon = 384_400_000.0
    omega_moon = math.sqrt((MU_EARTH + MU_MOON) / (d_moon ** 3))
    t_perilune = 69.3167 * 3600.0
    theta_moon_0 = math.radians(52.8757)  # Moon lead angle at TLI cutoff

    def moon_ephemeris(t_sec):
        th = theta_moon_0 + omega_moon * t_sec
        rm = np.array([d_moon * math.cos(th), d_moon * math.sin(th), 0.0])
        vm = d_moon * omega_moon * np.array([-math.sin(th), math.cos(th), 0.0])
        return rm, vm

    # Shoot backward from far-side perilune (h_p = 210.0 km, retrograde relative speed
    # v_rel = 2,494.12 m/s) to get the exact post-TLI injection state at t = 0
    th_mp = theta_moon_0 + omega_moon * t_perilune
    u_mp = np.array([math.cos(th_mp), math.sin(th_mp), 0.0])
    t_mp = np.array([-math.sin(th_mp), math.cos(th_mp), 0.0])
    h_perilune_target = 210_000.0
    r_peri_e = (d_moon + R_MOON + h_perilune_target) * u_mp
    v_peri_e = (d_moon * omega_moon - 2_494.12) * t_mp

    # Back-propagate to t = 0 with 60 s RK4 steps to obtain exact TLI state (r0_fr, v0_fr)
    r_tmp, v_tmp = r_peri_e.copy(), v_peri_e.copy()
    dt_back = -60.0
    for idx_b in range(int(round(t_perilune / 60.0))):
        t_cur = t_perilune + idx_b * dt_back
        def three_body_acc(pos, ts):
            rm, _ = moon_ephemeris(ts)
            d_m_vec = pos - rm
            return (
                -MU_EARTH * pos / (np.linalg.norm(pos) ** 3)
                - MU_MOON * (d_m_vec / (np.linalg.norm(d_m_vec) ** 3) + rm / (d_moon ** 3))
            )
        a1 = three_body_acc(r_tmp, t_cur)
        r2 = r_tmp + 0.5 * dt_back * v_tmp
        v2 = v_tmp + 0.5 * dt_back * a1
        a2 = three_body_acc(r2, t_cur + 0.5 * dt_back)
        r3 = r_tmp + 0.5 * dt_back * v2
        v3 = v_tmp + 0.5 * dt_back * a2
        a3 = three_body_acc(r3, t_cur + 0.5 * dt_back)
        r4 = r_tmp + dt_back * v3
        v4 = v_tmp + dt_back * a3
        a4 = three_body_acc(r4, t_cur + dt_back)
        r_tmp = r_tmp + (dt_back / 6.0) * (v_tmp + 2.0 * v2 + 2.0 * v3 + v4)
        v_tmp = v_tmp + (dt_back / 6.0) * (a1 + 2.0 * a2 + 2.0 * a3 + a4)
    r0_fr, v0_fr = r_tmp, v_tmp

    encke_data = encke_translunar_propagate(
        r0_fr, v0_fr, moon_ephemeris, t_end=2.0 * t_perilune, dt=60.0
    )

    # Compute perilune altitude and Earth return perigee altitude
    moon_dists = []
    for i, t_s in enumerate(encke_data["t"]):
        rm, _ = moon_ephemeris(t_s)
        moon_dists.append(np.linalg.norm(encke_data["r_earth"][i] - rm))
    min_moon_alt_km = (min(moon_dists) - R_MOON) / 1e3
    return_earth_alt_km = (np.linalg.norm(encke_data["r_earth"][-1]) - R_EARTH) / 1e3

    soi_summary = ", ".join(
        f"{lbl} at t={ts/3600:.1f} h" for lbl, ts, _ in encke_data["soi_switches"]
    )
    step(
        4,
        "Encke Translunar Integration (ORBITAL_INTEGRATION.agc @ TIMESTEP / RECTIFY / ORIGCHNG)",
        f"Propagated {2.0*t_perilune/3600:.1f}-hour circum-lunar free-return trajectory "
        f"(coplanar circular Moon approx., dt = 60 s).\n"
        f"Post-TLI state: |r0| = {np.linalg.norm(r0_fr)/1e3:,.1f} km "
        f"(alt {(np.linalg.norm(r0_fr)-R_EARTH)/1e3:.1f} km), |v0| = {np.linalg.norm(v0_fr):,.2f} m/s.\n"
        f"Performed {len(encke_data['rect_events'])} reference-conic rectifications (RECTIFY) "
        f"when |delta_r|/|r| exceeded 0.0075.\n"
        f"SOI origin switches at RSPHERE = {RSPHERE_MOON_M/1e3:,.2f} km: {soi_summary}.\n"
        f"Far-side perilune (pericynthion) altitude = {min_moon_alt_km:,.1f} km above lunar surface; "
        f"Earth return perigee altitude = {return_earth_alt_km:,.1f} km.",
    )

    plot_kepler_and_lambert(kep_hist, lamb_hist, r0_tli, r_6h, v1_lamb, dt_test)
    plot_translunar_free_return(encke_data, moon_ephemeris)


if __name__ == "__main__":
    main()
