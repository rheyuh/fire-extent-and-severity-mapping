"""Tests for the maths and checks in run.py, on tiny hand-made grids (no network, no data/)."""

import numpy as np
import pytest

from run import SEVERITY_NODATA, agreement, classify, confusion, gap, masked_pct, nbr

THRESHOLDS = [0.10, 0.27, 0.44, 0.66]
CLASSES = [0, 2, 3, 4, 5]


def test_nbr_known_values() -> None:
    # Healthy: (3000 - 900) / 3900. Burnt: SWIR2 above NIR gives a negative NBR.
    result = nbr(np.array([3000, 1200]), np.array([900, 2100]))
    assert result == pytest.approx([2100 / 3900, -900 / 3300])


def test_classify_bins_and_boundaries() -> None:
    dnbr = np.array([-0.03, 0.10, 0.16, 0.27, 0.31, 0.44, 0.65, 0.66, 1.2])
    assert classify(dnbr, THRESHOLDS, CLASSES).tolist() == [0, 2, 2, 3, 3, 4, 4, 5, 5]


def test_classify_nan_is_nodata_not_extreme() -> None:
    # np.digitize alone would put NaN in the top bin, i.e. "extreme".
    result = classify(np.array([np.nan, 0.5]), THRESHOLDS, CLASSES)
    assert result.tolist() == [SEVERITY_NODATA, 4]
    assert result.dtype == np.uint8


def test_confusion_counts_pairs() -> None:
    yours = np.array([[0, 2, 2], [3, 5, 4]])
    fesm = np.array([[0, 2, 3], [3, 4, 4]])
    matrix = confusion(yours, fesm, CLASSES)
    assert matrix.sum() == 6
    assert matrix[0, 0] == 1  # both unburnt
    assert matrix[1, 2] == 1  # yours low (row 1), FESM moderate (column 2)
    assert matrix[4, 3] == 1  # yours extreme, FESM high
    assert np.trace(matrix) == 4


def test_confusion_drops_nodata_and_grassland() -> None:
    yours = np.array([2, 255, 3, 4])
    fesm = np.array([2, 2, 1, 255])  # FESM 1 = grassland, 255 = nodata
    matrix = confusion(yours, fesm, CLASSES)
    assert matrix.sum() == 1  # only the first pixel is comparable


def test_agreement_summary() -> None:
    # 10 pixels: 6 on the diagonal, 3 one class lower than FESM, 1 two classes higher.
    matrix = np.zeros((5, 5), dtype=int)
    matrix[1, 1] = 6
    matrix[1, 2] = 3
    matrix[3, 1] = 1
    stats = agreement(matrix)
    assert stats["pixels"] == 10
    assert stats["exact_pct"] == pytest.approx(60)
    assert stats["within_one_pct"] == pytest.approx(90)
    assert stats["lower_than_fesm_pct"] == pytest.approx(30)
    assert stats["higher_than_fesm_pct"] == pytest.approx(10)


def test_agreement_no_pixels_is_an_error() -> None:
    with pytest.raises(ValueError, match="no pixels"):
        agreement(np.zeros((5, 5), dtype=int))


@pytest.mark.parametrize(
    ("days", "passed"),
    [(0, False), (1, True), (14, True), (15, False), (-3, False)],
)
def test_gap_must_be_outside_fire_and_close(days: int, passed: bool) -> None:
    # 0 or negative: the scene was taken during the fire. Over 14: too far for a fair dNBR.
    assert gap(days, 14)["passed"] is passed


def test_masked_pct_counts_only_inside_outline() -> None:
    nbr_map = np.array([0.5, np.nan, np.nan, 0.2])
    inside = np.array([True, True, False, True])  # the third NaN is outside: not counted
    assert masked_pct(nbr_map, inside) == pytest.approx(100 / 3)
