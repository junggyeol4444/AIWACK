"""Guard against the Windows 2022/2025 company-tab fixed-coordinate failure."""
from PIL import Image, ImageDraw
from company_tab_locator import selected_company_tab_y


def test_detects_tab_below_old_fixed_coordinate():
    im = Image.new("RGB", (1024, 768), (11, 18, 32))
    ImageDraw.Draw(im).rectangle((44, 251, 159, 288), fill=(70, 139, 250))
    assert selected_company_tab_y(im, 8, 9, 711) == 260


def test_ignores_short_blue_highlight():
    im = Image.new("RGB", (1024, 768), (11, 18, 32))
    ImageDraw.Draw(im).rectangle((44, 240, 159, 250), fill=(70, 139, 250))
    assert selected_company_tab_y(im, 8, 9, 711) is None
