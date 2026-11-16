from __future__ import annotations

import agc_03_dsky as agc03


def test_v16_n68_entr_display_state() -> None:
    dsky = agc03.DSKYModel(
        prog="63",
        erasable={"RANGEDSP_NM": 15.7, "TTFDISP_MS": (4, 12), "DELTAH_FT": -2700},
    )
    dsky.set_background_display("06", "63", "+04216", "-00842", "+38400")
    dsky.press_sequence(["VERB", "1", "6", "NOUN", "6", "8", "ENTR"])

    assert dsky.prog == "63"
    assert dsky.verb == "16"
    assert dsky.noun == "68"
    assert dsky.r1 == "+00157"
    assert dsky.r2 == " 04 12"
    assert dsky.r3 == "-02700"
    assert dsky.vn_flash is False
    assert dsky.lamps["OPR ERR"] is False


def test_v05_n09_entr_alarm_inspection_and_recovery() -> None:
    dsky = agc03.DSKYModel(
        prog="63",
        erasable={"RANGEDSP_NM": 15.7, "TTFDISP_MS": (4, 12), "DELTAH_FT": -2700},
    )
    dsky.press_sequence(["VERB", "1", "6", "NOUN", "6", "8", "ENTR"])
    dsky.trigger_alarm(0o01202, restart=True)
    assert dsky.lamps["PROG"] is True
    assert dsky.lamps["RESTART"] is True

    dsky.press_sequence(["VERB", "0", "5", "NOUN", "0", "9", "ENTR"])
    assert dsky.verb == "05"
    assert dsky.noun == "09"
    assert dsky.r1 == " 01202"
    assert dsky.r2 == " 00000"
    assert dsky.r3 == " 00000"
    assert dsky.lamps["KEY REL"] is True

    # RSET clears PROG and RESTART; KEY REL restores background V16 N68 display
    dsky.press_sequence(["RSET", "KEY REL"])
    assert dsky.lamps["PROG"] is False
    assert dsky.lamps["RESTART"] is False
    assert dsky.lamps["KEY REL"] is False
    assert (dsky.verb, dsky.noun, dsky.r1, dsky.r2, dsky.r3) == (
        "16", "68", "+00157", " 04 12", "-02700"
    )
