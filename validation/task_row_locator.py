"""Read-only pixel location of the work-board task input and submit button.

Coordinates are relative to the packaged Windows EXE window; no Tk imports.
"""
from __future__ import annotations


def task_entry_row_y(image, left: int, top: int, height: int) -> int | None:
    """Find the white task-entry row beside the blue task-create button.

    Requiring both the entry and its adjacent blue action button avoids
    mistaking the task-list scrollbar or unrelated white controls for input.
    """
    points_x = (320, 650, 900)
    if any(not 0 <= left + x < image.width for x in points_x):
        return None
    band_start = None
    end = min(height - 45, 690)
    for relative_y in range(520, end):
        y = top + relative_y
        if not 0 <= y < image.height:
            continue
        first, second, button = (image.getpixel((left + x, y)) for x in points_x)
        entry_white = all(min(rgb) >= 225 and max(rgb) - min(rgb) <= 30 for rgb in (first, second))
        r, g, b = button
        button_blue = 40 <= r <= 130 and 85 <= g <= 200 and b >= 175 and b > r + 60
        if entry_white and button_blue:
            if band_start is None:
                band_start = relative_y
        elif band_start is not None:
            if relative_y - band_start >= 14:
                return (band_start + relative_y - 1) // 2
            band_start = None
    if band_start is not None and end - band_start >= 14:
        return (band_start + end - 1) // 2
    return None
