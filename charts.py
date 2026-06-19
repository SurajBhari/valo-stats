"""charts.py — pure helpers for inline SVG charts (no I/O)."""


def polyline_points(values, width, height, pad=4):
    """Map a numeric series to an SVG polyline points string "x,y x,y ...".

    x is spread evenly across [pad, width-pad]; y scales so the max value sits at
    the top (y=pad) and the min at the bottom (y=height-pad). A flat multi-point
    series renders on the vertical midline. Empty → "". Single value → top-left.
    """
    n = len(values)
    if n == 0:
        return ""
    if n == 1:
        return f"{pad},{pad}"

    vmin, vmax = min(values), max(values)
    span = vmax - vmin
    usable_w = width - 2 * pad
    usable_h = height - 2 * pad
    mid_y = pad + usable_h / 2

    pts = []
    for i, v in enumerate(values):
        x = pad + i * usable_w / (n - 1)
        if span == 0:
            y = mid_y
        else:
            y = pad + (vmax - v) / span * usable_h
        pts.append(f"{round(x, 2)},{round(y, 2)}")
    return " ".join(pts)
