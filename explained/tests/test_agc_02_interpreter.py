from __future__ import annotations

import numpy as np

import agc_02_interpreter as agc02


def test_rgvgcalc_interpreter_agrees_with_direct_numpy() -> None:
    interp, erasable = agc02.run_rgvgcalc_demo()

    r_lm = erasable["R"]
    v_lm = erasable["V"]
    land = erasable["LAND"]
    wm = erasable["WM"]
    cg = erasable["CG"]
    xnbpip = erasable["XNBPIP"]

    # Direct numpy computation of RGVGCALC equations:
    angterm_np = v_lm + np.cross(r_lm, wm)
    vgu_np = cg @ angterm_np
    vhoriz_np = float(np.hypot(vgu_np[1], vgu_np[2]))
    r_minus_land = r_lm - land
    rgu_np = cg @ r_minus_land
    rangedsp_np = float(np.linalg.norm(rgu_np))
    half_unit_los = r_minus_land / (2.0 * np.linalg.norm(r_minus_land))
    sin_look_div4_np = float(np.dot(half_unit_los, xnbpip))
    lookangl_np = float(np.rad2deg(np.arcsin(4.0 * sin_look_div4_np)))

    np.testing.assert_allclose(erasable["ANGTERM"], angterm_np, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(erasable["VGU"], vgu_np, rtol=1e-12, atol=1e-12)
    assert np.isclose(erasable["VHORIZ"], vhoriz_np, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(erasable["RGU"], rgu_np, rtol=1e-12, atol=1e-12)
    assert np.isclose(erasable["RANGEDSP"], rangedsp_np, rtol=1e-12, atol=1e-12)
    assert np.isclose(erasable["SIN_LOOK_DIV4"], sin_look_div4_np, rtol=1e-12, atol=1e-12)
    assert np.isclose(erasable["LOOKANGL"], lookangl_np, rtol=1e-12, atol=1e-12)

    # Check stack pointer lifecycle across RGVGCALC
    assert len(interp.trace) == 22
    assert interp.pushloc == 2  # before Basic CA FIXLOC / TS PUSHLOC
