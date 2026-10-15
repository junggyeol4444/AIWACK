"""Read-only screenshot detection of the selected company navigation tab.

Uses only pixels from the packaged EXE. Never calls Tkinter or application
internals; returned coordinates are relative to the observed window.
"""
from __future__ import annotations


def selected_company_tab_y(image, left: int, top: int, height: int) -> int | None:
    """Find the solid selected-blue navigation band despite Windows DPI shifts."""
    for relative_x in (45, 48, 50):
        x = left + relative_x
        if not 0 <= x < image.width:
            continue
        band_start = None
        for relative_y in range(185, min(height - 70, 365)):
            y = top + relative_y
            if not 0 <= y < image.height:
                continue
            r, g, b = image.getpixel((x, y))
            selected_blue = 40 <= r <= 130 and 80 <= g <= 200 and b >= 170 and b > r + 60
            if selected_blue:
                if band_start is None:
                    band_start = relative_y
            elif band_start is not None:
                if relative_y - band_start >= 20:
                    return (band_start + relative_y - 1) // 2
                band_start = None
    return None
