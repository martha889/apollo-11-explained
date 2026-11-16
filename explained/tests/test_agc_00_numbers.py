from __future__ import annotations

import numpy as np
import pytest

import agc_00_numbers as agc00


def test_ones_complement_full_15bit_roundtrip() -> None:
    # Full signed integer range -16383 .. +16383
    for n in range(-agc00.MAG_MASK, agc00.MAG_MASK + 1):
        w = agc00.encode_ones_complement(n)
        assert 0 <= w <= agc00.MASK15
        dec, is_neg_zero = agc00.decode_ones_complement(w)
        assert dec == n
        assert is_neg_zero is False

    # Also verify every 15-bit word 0..0o77777 decodes and re-encodes cleanly
    for word in range(0, agc00.MASK15 + 1):
        val, is_neg_zero = agc00.decode_ones_complement(word)
        reencoded = agc00.encode_ones_complement(val, allow_neg_zero=is_neg_zero)
        assert reencoded == word


def test_pos_and_neg_zero_sentinels() -> None:
    assert agc00.POS_ZERO == 0o00000
    assert agc00.NEG_ZERO == 0o77777

    assert agc00.encode_ones_complement(0, allow_neg_zero=False) == 0o00000
    assert agc00.encode_ones_complement(0, allow_neg_zero=True) == 0o77777

    assert agc00.decode_ones_complement(0o00000) == (0, False)
    assert agc00.decode_ones_complement(0o77777) == (0, True)

    with pytest.raises(ValueError):
        agc00.encode_ones_complement(agc00.MAG_MASK + 1)
    with pytest.raises(ValueError):
        agc00.encode_ones_complement(-agc00.MAG_MASK - 1)


def test_odd_parity_and_word_to_bits() -> None:
    sample_words = [
        0o00000,
        0o77777,
        0o37777,
        0o40000,
        0o25252,
        0o52525,
        0o01202,
        0o01201,
    ]
    for w in sample_words:
        p = agc00.odd_parity_bit(w)
        bits = agc00.word_to_bits(w)
        assert len(bits) == 15
        total_ones = sum(bits) + p
        assert total_ones % 2 == 1


def test_sp_and_dp_fraction_roundtrip_within_one_lsb() -> None:
    rng = np.random.default_rng(42)
    for scale_exp in (0, 5, 16, 24):
        sp_lsb = (2.0 ** scale_exp) / (1 << 14)
        dp_lsb = (2.0 ** scale_exp) / (1 << 28)
        fracs = rng.uniform(-0.999, 0.999, size=50)
        for f in fracs:
            val = float(f * (2.0 ** scale_exp))
            w_sp = agc00.encode_sp_fraction(val, scale_exp=scale_exp)
            dec_sp = agc00.decode_sp_fraction(w_sp, scale_exp=scale_exp)
            assert abs(dec_sp - val) <= 0.5 * sp_lsb + 1e-12

            maj, min_w = agc00.encode_dp_fraction(val, scale_exp=scale_exp)
            dec_dp = agc00.decode_dp_fraction(maj, min_w, scale_exp=scale_exp)
            assert abs(dec_dp - val) <= 0.5 * dp_lsb + 1e-9

            # Sign agreement between major and minor non-zero words
            if maj != 0 and min_w != 0:
                assert (maj & agc00.SIGN_BIT) == (min_w & agc00.SIGN_BIT)
