"""Synthetic pixel tests for Windows task-entry row detection."""
from PIL import Image, ImageDraw
from task_row_locator import task_entry_row_y


def work_screen(blue=True, entry=True, top=9):
    im = Image.new('RGB', (1024, 768), (21, 31, 48))
    draw = ImageDraw.Draw(im)
    if entry:
        draw.rectangle((57, top + 586, 878, top + 620), fill=(246, 248, 252))
    if blue:
        draw.rectangle((887, top + 586, 981, top + 620), fill=(70, 139, 250))
    return im


def test_task_row_is_observed_below_stale_fixed_click():
    assert task_entry_row_y(work_screen(), 8, 9, 711) == 603


def test_no_task_button_is_not_detected():
    assert task_entry_row_y(work_screen(blue=False), 8, 9, 711) is None


def test_no_white_entry_is_not_detected():
    assert task_entry_row_y(work_screen(entry=False), 8, 9, 711) is None


def test_short_unrelated_band_is_not_detected():
    im = work_screen()
    draw = ImageDraw.Draw(im)
    draw.rectangle((57, 595, 981, 629), fill=(21, 31, 48))
    draw.rectangle((57, 595, 878, 601), fill=(246, 248, 252))
    draw.rectangle((887, 595, 981, 601), fill=(70, 139, 250))
    assert task_entry_row_y(im, 8, 9, 711) is None
