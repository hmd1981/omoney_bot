from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None

_FORMS = {
    "ا": ("ﺍ", "ﺎ", "ﺍ", "ﺎ"), "ب": ("ﺏ", "ﺐ", "ﺑ", "ﺒ"), "پ": ("ﭖ", "ﭗ", "ﭘ", "ﭙ"),
    "ت": ("ﺕ", "ﺖ", "ﺗ", "ﺘ"), "ث": ("ﺙ", "ﺚ", "ﺛ", "ﺜ"), "ج": ("ﺝ", "ﺞ", "ﺟ", "ﺠ"),
    "چ": ("ﭺ", "ﭻ", "ﭼ", "ﭽ"), "ح": ("ﺡ", "ﺢ", "ﺣ", "ﺤ"), "خ": ("ﺥ", "ﺦ", "ﺧ", "ﺨ"),
    "د": ("ﺩ", "ﺪ", "ﺩ", "ﺪ"), "ذ": ("ﺫ", "ﺬ", "ﺫ", "ﺬ"), "ر": ("ﺭ", "ﺮ", "ﺭ", "ﺮ"),
    "ز": ("ﺯ", "ﺰ", "ﺯ", "ﺰ"), "ژ": ("ﮊ", "ﮋ", "ﮊ", "ﮋ"), "س": ("ﺱ", "ﺲ", "ﺳ", "ﺴ"),
    "ش": ("ﺵ", "ﺶ", "ﺷ", "ﺸ"), "ص": ("ﺹ", "ﺺ", "ﺻ", "ﺼ"), "ض": ("ﺽ", "ﺾ", "ﺿ", "ﻀ"),
    "ط": ("ﻁ", "ﻂ", "ﻃ", "ﻄ"), "ظ": ("ﻅ", "ﻆ", "ﻇ", "ﻈ"), "ع": ("ﻉ", "ﻊ", "ﻋ", "ﻌ"),
    "غ": ("ﻍ", "ﻎ", "ﻏ", "ﻐ"), "ف": ("ﻑ", "ﻒ", "ﻓ", "ﻔ"), "ق": ("ﻕ", "ﻖ", "ﻗ", "ﻘ"),
    "ک": ("ﮎ", "ﮏ", "ﮐ", "ﮑ"), "گ": ("ﮒ", "ﮓ", "ﮔ", "ﮕ"), "ل": ("ﻝ", "ﻞ", "ﻟ", "ﻠ"),
    "م": ("ﻡ", "ﻢ", "ﻣ", "ﻤ"), "ن": ("ﻥ", "ﻦ", "ﻧ", "ﻨ"), "و": ("ﻭ", "ﻮ", "ﻭ", "ﻮ"),
    "ه": ("ﻩ", "ﻪ", "ﻫ", "ﻬ"), "ی": ("ﯼ", "ﯽ", "ﯾ", "ﯿ"),
}
_RIGHT_JOIN_ONLY = {"ا", "د", "ذ", "ر", "ز", "ژ", "و"}

WIDTH = 1080
HEIGHT = 1920
SCALE = 2
W = WIDTH * SCALE
H = HEIGHT * SCALE
ASSETS_DIR = Path("/app/assets")
FONTS_DIR = ASSETS_DIR / "fonts"

BG = "#050505"
PANEL = "#0D0D0F"
PANEL_INNER = "#121214"
GLASS = "#171414"
WHITE = "#F8F4EC"
MUTED = "#C4B8A2"
GOLD = "#E2BD72"
GOLD_BRIGHT = "#F3D48E"
GOLD_DIM = "#765A25"
LINE = "#3E3018"
SHADOW = "#000000"

DISPLAY = {
    "usd_sell": {"code": "USD", "name": "US Dollar", "icon": "$", "kind": "fiat"},
    "usd": {"code": "USD", "name": "US Dollar", "icon": "$", "kind": "fiat"},
    "cad": {"code": "CAD", "name": "Canadian Dollar", "icon": "C$", "kind": "fiat"},
    "aed_sell": {"code": "AED", "name": "UAE Dirham", "icon": "د.إ", "kind": "fiat"},
    "aed": {"code": "AED", "name": "UAE Dirham", "icon": "د.إ", "kind": "fiat"},
    "try": {"code": "TRY", "name": "Turkish Lira", "icon": "₺", "kind": "fiat"},
    "omr": {"code": "OMR", "name": "Omani Rial", "icon": "ر.ع", "kind": "fiat"},
    "btc": {"code": "BTC", "name": "Bitcoin", "icon": "₿", "kind": "crypto"},
    "usdt": {"code": "USDT", "name": "Tether", "icon": "₮", "kind": "crypto"},
    "18ayar": {"code": "18K", "name": "Gold 18K", "icon": "Au", "kind": "gold"},
    "gold_18k": {"code": "18K", "name": "Gold 18K", "icon": "Au", "kind": "gold"},
    "sekkeh": {"code": "COIN", "name": "Gold Coin", "icon": "◉", "kind": "gold"},
}
ORDER = ("usd_sell", "usd", "cad", "aed_sell", "aed", "try", "omr", "btc", "usdt")


def _s(value: int | float) -> int:
    return int(value * SCALE)


def _font_path(candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        path = FONTS_DIR / candidate
        if path.exists():
            return str(path)
    return None


def _font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ("Cinzel-Bold.ttf", "PlayfairDisplay-Bold.ttf", "DejaVuSerif-Bold.ttf")
        if serif and bold
        else ("Cinzel-Regular.ttf", "PlayfairDisplay-Regular.ttf", "DejaVuSerif.ttf")
        if serif
        else (
            "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf",
            "IRANSansX-Bold.ttf" if bold else "IRANSansX-Regular.ttf",
            "NotoSansArabic-Bold.ttf" if bold else "NotoSansArabic-Regular.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        )
    )
    return ImageFont.truetype(_font_path(candidates) or candidates[-1], size=_s(size))


def _rtl(text: str) -> str:
    if arabic_reshaper and get_display:
        return get_display(arabic_reshaper.reshape(text))
    shaped: list[str] = []
    chars = list(text)
    for index, char in enumerate(chars):
        if char not in _FORMS:
            shaped.append(char)
            continue
        previous = chars[index - 1] if index > 0 else ""
        following = chars[index + 1] if index + 1 < len(chars) else ""
        joins_previous = previous in _FORMS and previous not in _RIGHT_JOIN_ONLY
        joins_next = following in _FORMS and char not in _RIGHT_JOIN_ONLY
        isolated, final, initial, medial = _FORMS[char]
        if joins_previous and joins_next:
            shaped.append(medial)
        elif joins_previous:
            shaped.append(final)
        elif joins_next:
            shaped.append(initial)
        else:
            shaped.append(isolated)
    return "".join(shaped)[::-1]


def _size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    return x1 - x0, y1 - y0


def _fmt(value: object) -> str:
    raw = str(value).replace(",", "").strip()
    try:
        if "." in raw:
            return f"{float(raw):,.2f}".rstrip("0").rstrip(".")
        return f"{int(float(raw)):,}"
    except (TypeError, ValueError):
        return str(value)


def _normalize(rates: list[dict]) -> tuple[list[dict], list[dict]]:
    rows: dict[str, dict] = {}
    gold: list[dict] = []
    for item in rates:
        symbol = str(item.get("symbol") or item.get("label") or "").lower().replace(" ", "_")
        meta = DISPLAY.get(symbol)
        if not meta:
            continue
        row = {
            **meta,
            "symbol": symbol,
            "value": _fmt(item.get("value", "")),
            "unit": str(item.get("unit") or "IRR").strip(),
        }
        if meta["kind"] == "gold":
            gold.append(row)
        else:
            rows[symbol] = row
    ordered: list[dict] = []
    seen: set[str] = set()
    for symbol in ORDER:
        row = rows.get(symbol)
        if row and row["code"] not in seen:
            ordered.append(row)
            seen.add(row["code"])
    return ordered, gold


def _radial_glow() -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((_s(560), _s(-260), _s(1320), _s(500)), fill=(226, 189, 114, 62))
    draw.ellipse((_s(-320), _s(1220), _s(420), _s(1980)), fill=(226, 189, 114, 34))
    return layer.filter(ImageFilter.GaussianBlur(_s(120)))


def _rounded(base: Image.Image, box: tuple[int, int, int, int], radius: int, fill: str, outline: str, width: int = 2) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x0, y0, x1, y1 = box
    sd.rounded_rectangle((x0 + _s(8), y0 + _s(18), x1 + _s(8), y1 + _s(18)), radius=_s(radius), fill=(0, 0, 0, 150))
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(_s(22))))
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle(box, radius=_s(radius), fill=fill, outline=outline, width=_s(width))


def _row(draw: ImageDraw.ImageDraw, row: dict, top: int, *, large: bool = False) -> None:
    icon_font = _font(35 if not large else 40, bold=True)
    name_font = _font(37 if not large else 41, bold=True)
    badge_font = _font(24, bold=True)
    price_font = _font(46 if not large else 53, bold=True, serif=True)
    unit_font = _font(26, bold=True)
    x = _s(96)
    y = _s(top)
    icon_box = (x, y + _s(15), x + _s(70), y + _s(85))
    draw.ellipse(icon_box, fill=PANEL_INNER, outline=GOLD_DIM, width=_s(2))
    iw, ih = _size(draw, row["icon"], icon_font)
    draw.text((icon_box[0] + (_s(70) - iw) / 2, icon_box[1] + (_s(70) - ih) / 2 - _s(4)), row["icon"], fill=GOLD_BRIGHT, font=icon_font)
    draw.text((_s(188), y + _s(20)), row["name"], fill=WHITE, font=name_font)
    badge_x = _s(188)
    badge_y = y + _s(62)
    bw, _ = _size(draw, row["code"], badge_font)
    draw.rounded_rectangle((badge_x, badge_y, badge_x + bw + _s(26), badge_y + _s(30)), radius=_s(15), fill=GLASS, outline=GOLD_DIM, width=_s(1))
    draw.text((badge_x + _s(13), badge_y + _s(3)), row["code"], fill=GOLD, font=badge_font)
    price = row["value"]
    pw, _ = _size(draw, price, price_font)
    ux, _ = _size(draw, "IRR", unit_font)
    right = _s(932)
    draw.text((right - pw, y + _s(18)), price, fill=GOLD_BRIGHT, font=price_font)
    draw.text((right - ux, y + _s(70)), "IRR", fill=MUTED, font=unit_font)


def generate_rate_image(
    rates: list[dict],
    image_path: Path,
    title: str,
    subtitle: str,
    website: str,
    phone: str,
    published_at: datetime,
    update_note: str = "",
) -> None:
    image = Image.new("RGBA", (W, H), BG)
    image.alpha_composite(_radial_glow())
    draw = ImageDraw.Draw(image)

    outer = (_s(38), _s(36), _s(1042), _s(1884))
    draw.rounded_rectangle(outer, radius=_s(42), outline=GOLD_DIM, width=_s(2))

    brand_font = _font(42, bold=True, serif=True)
    title_font = _font(77, bold=True, serif=True)
    subtitle_font = _font(40, bold=True)
    meta_font = _font(27, bold=True)
    draw.text((_s(540) - _size(draw, "OMONEY", brand_font)[0] / 2, _s(78)), "OMONEY", fill=GOLD, font=brand_font)
    h = "EXCHANGE RATES"
    draw.text((_s(540) - _size(draw, h, title_font)[0] / 2, _s(132)), h, fill=WHITE, font=title_font)
    fa = _rtl("نرخ لحظه‌ای ارز و طلا")
    draw.text((_s(540) - _size(draw, fa, subtitle_font)[0] / 2, _s(224)), fa, fill=GOLD_BRIGHT, font=subtitle_font)
    pill = published_at.strftime("%Y/%m/%d  %H:%M")
    pw, _ = _size(draw, pill, meta_font)
    draw.rounded_rectangle((_s(540) - pw / 2 - _s(24), _s(278), _s(540) + pw / 2 + _s(24), _s(326)), radius=_s(24), fill=GLASS, outline=GOLD_DIM, width=_s(1))
    draw.text((_s(540) - pw / 2, _s(287)), pill, fill=MUTED, font=meta_font)
    draw.line((_s(94), _s(356), _s(986), _s(356)), fill=GOLD_DIM, width=_s(2))

    rows, gold_rows = _normalize(rates)
    _rounded(image, (_s(70), _s(402), _s(1010), _s(1348)), 42, PANEL, GOLD_DIM)
    draw = ImageDraw.Draw(image)
    row_top = 446
    for index, row in enumerate(rows[:7]):
        _row(draw, row, row_top)
        if index < min(len(rows), 7) - 1:
            draw.line((_s(96), _s(row_top + 106), _s(932), _s(row_top + 106)), fill=LINE, width=_s(1))
        row_top += 123

    gold_box = (_s(70), _s(1390), _s(1010), _s(1636))
    _rounded(image, gold_box, 38, "#151007", GOLD)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle(gold_box, radius=_s(38), fill=(226, 189, 114, 38))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(_s(18))))
    draw = ImageDraw.Draw(image)
    section_font = _font(29, bold=True)
    draw.text((_s(96), _s(1416)), "GOLD MARKET", fill=GOLD_BRIGHT, font=section_font)
    if gold_rows:
        gold_top = 1452
        for idx, row in enumerate(gold_rows[:2]):
            _row(draw, row, gold_top, large=True)
            if idx == 0 and len(gold_rows) > 1:
                draw.line((_s(96), _s(gold_top + 112), _s(932), _s(gold_top + 112)), fill=GOLD_DIM, width=_s(1))
            gold_top += 112
    else:
        muted = "Gold feed unavailable"
        draw.text((_s(96), _s(1488)), muted, fill=MUTED, font=_font(41, bold=True))

    draw.line((_s(94), _s(1698), _s(986), _s(1698)), fill=GOLD_DIM, width=_s(2))
    footer_font = _font(35, bold=True)
    tiny = _font(27, bold=True)
    draw.text((_s(94), _s(1730)), website, fill=WHITE, font=footer_font)
    ph_w, _ = _size(draw, phone, footer_font)
    draw.text((_s(986) - ph_w, _s(1730)), phone, fill=GOLD_BRIGHT, font=footer_font)
    footer = "OMONEY LIVE MARKET"
    fw, _ = _size(draw, footer, tiny)
    draw.text((_s(540) - fw / 2, _s(1792)), footer, fill=MUTED, font=tiny)
    if update_note:
        uw, _ = _size(draw, update_note, tiny)
        draw.text((_s(540) - uw / 2, _s(1830)), update_note, fill=GOLD, font=tiny)

    final = image.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(image_path, format="PNG")
