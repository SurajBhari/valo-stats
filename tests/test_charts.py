"""Tests for charts.polyline_points (pure)."""

import charts


def _coords(s):
    return [tuple(float(n) for n in pt.split(",")) for pt in s.split()]


def test_empty_series():
    assert charts.polyline_points([], 100, 40) == ""


def test_single_value_centered_vertically_at_top():
    # one value → single point at left pad; max maps to top (pad)
    pts = _coords(charts.polyline_points([50], 100, 40, pad=4))
    assert len(pts) == 1
    assert pts[0][0] == 4.0          # x = pad
    assert pts[0][1] == 4.0          # y = pad (the only/max value sits at top)


def test_x_spread_across_width():
    pts = _coords(charts.polyline_points([0, 0, 0], 100, 40, pad=4))
    xs = [p[0] for p in pts]
    assert xs[0] == 4.0
    assert xs[-1] == 96.0            # width - pad
    assert xs[1] == 50.0             # midpoint


def test_y_scales_max_to_top_min_to_bottom():
    pts = _coords(charts.polyline_points([0, 100], 100, 40, pad=4))
    # value 100 (max) → y = pad (top); value 0 (min) → y = height - pad (bottom)
    ys = {round(p[0]): p[1] for p in pts}
    assert ys[4] == 36.0             # first point (value 0) at bottom
    assert ys[96] == 4.0             # last point (value 100) at top


def test_flat_series_renders_midline():
    # all equal, nonzero → avoid div by zero; place at vertical middle
    pts = _coords(charts.polyline_points([50, 50, 50], 100, 40, pad=4))
    ys = [p[1] for p in pts]
    assert all(y == ys[0] for y in ys)
    assert 4.0 <= ys[0] <= 36.0
