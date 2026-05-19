from __future__ import annotations

import json
import math
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.content_posts.content_themes import HEADLINES, THEMES, VISUAL_PRESETS
from app.content_posts.rotation_memory import pick_theme, pick_visual, record_theme, record_visual

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None

WIDTH = 1080
HEIGHT = 1920
SCALE = 2
W = WIDTH * SCALE
H = HEIGHT * SCALE
ASSETS_DIR = Path("/app/assets")
FONTS_DIR = ASSETS_DIR / "fonts"
BG = "#050505"
WHITE = "#F8F4EC"
MUTED = "#C9BCA5"
GOLD = "#E7C16F"
DEEP = "#0B0B0C"
_PERSIAN_CHARS = set("اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئءةۀ")


def _s(value: int | float) -> int:
    return int(value * SCALE)


def _font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    if serif:
        candidates = ["Cinzel-Bold.ttf" if bold else "Cinzel-Regular.ttf", "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"]
    else:
        candidates = [
            "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf",
            "IRANSansX-Bold.ttf" if bold else "IRANSansX-Regular.ttf",
            "NotoSansArabic-Bold.ttf" if bold else "NotoSansArabic-Regular.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
    for candidate in candidates:
        path = FONTS_DIR / candidate
        if path.exists():
            return ImageFont.truetype(str(path), _s(size))
    return ImageFont.truetype(candidates[-1], _s(size))


def _size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    return x1 - x0, y1 - y0


def _center(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont, fill: str) -> None:
    w, h = _size(draw, text, font)
    draw.text((xy[0] - w / 2, xy[1] - h / 2), text, font=font, fill=fill)


def _rtl(text: str) -> str:
    if not any(char in _PERSIAN_CHARS for char in text):
        return text
    if arabic_reshaper and get_display:
        return get_display(arabic_reshaper.reshape(text))
    return text[::-1]


def _glow(base: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int, int], blur: int) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(box, fill=color)
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(_s(blur))))


def _rounded_panel(base: Image.Image, box: tuple[int, int, int, int], radius: int, fill: str, outline: str) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x0, y0, x1, y1 = box
    sd.rounded_rectangle((x0 + _s(10), y0 + _s(18), x1 + _s(10), y1 + _s(18)), radius=_s(radius), fill=(0, 0, 0, 145))
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(_s(24))))
    ImageDraw.Draw(base).rounded_rectangle(box, radius=_s(radius), fill=fill, outline=outline, width=_s(2))


def _draw_routes(draw: ImageDraw.ImageDraw, color: str, seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(11):
        x0 = _s(rng.randint(80, 980))
        y0 = _s(rng.randint(350, 1350))
        x1 = _s(rng.randint(80, 980))
        y1 = _s(rng.randint(350, 1350))
        midx = (x0 + x1) // 2 + _s(rng.randint(-130, 130))
        midy = (y0 + y1) // 2 + _s(rng.randint(-130, 130))
        draw.line((x0, y0, midx, midy, x1, y1), fill=color, width=_s(1), joint="curve")
        draw.ellipse((x1 - _s(4), y1 - _s(4), x1 + _s(4), y1 + _s(4)), fill=color)


def _draw_motif(draw: ImageDraw.ImageDraw, motif: str, primary: str, secondary: str, seed: int) -> None:
    rng = random.Random(seed)
    if motif in {"skyline", "columns"}:
        base_y = _s(1340)
        for index in range(10):
            x = _s(92 + index * 92)
            h = _s(rng.randint(130, 390))
            draw.rounded_rectangle((x, base_y - h, x + _s(44), base_y), radius=_s(6), fill=secondary, outline=primary, width=_s(1))
    elif motif in {"chart", "candles"}:
        points = []
        for index in range(18):
            points.append((_s(100 + index * 52), _s(rng.randint(720, 1130))))
        draw.line(points, fill=primary, width=_s(4), joint="curve")
        for x, y in points[::3]:
            draw.ellipse((x - _s(7), y - _s(7), x + _s(7), y + _s(7)), fill=primary)
    elif motif in {"globe", "network"}:
        cx, cy, r = _s(540), _s(1020), _s(315)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=primary, width=_s(2))
        for offset in [-180, -90, 0, 90, 180]:
            draw.arc((cx - r, cy - r + _s(offset / 3), cx + r, cy + r - _s(offset / 3)), 0, 360, fill=secondary, width=_s(1))
        _draw_routes(draw, primary, seed)
    elif motif in {"coins", "currency"}:
        for index in range(9):
            x = _s(rng.randint(120, 890))
            y = _s(rng.randint(700, 1300))
            rr = _s(rng.randint(34, 82))
            draw.ellipse((x - rr, y - rr, x + rr, y + rr), outline=primary, width=_s(3))
            _center(draw, (x, y), rng.choice(["$", "€", "د.إ", "﷼"]), _font(28, True), primary)
    elif motif == "marble":
        for _ in range(20):
            y = _s(rng.randint(360, 1500))
            draw.line((_s(70), y, _s(1010), y + _s(rng.randint(-260, 260))), fill=secondary, width=_s(2))
    elif motif == "silhouette":
        draw.ellipse((_s(430), _s(740), _s(650), _s(960)), fill=secondary, outline=primary, width=_s(2))
        draw.rounded_rectangle((_s(340), _s(940), _s(740), _s(1370)), radius=_s(130), fill=secondary, outline=primary, width=_s(2))
    elif motif == "arches":
        for index in range(4):
            x0 = _s(140 + index * 210)
            draw.arc((x0, _s(710), x0 + _s(170), _s(1080)), 180, 360, fill=primary, width=_s(4))
            draw.line((x0, _s(895), x0, _s(1280)), fill=secondary, width=_s(3))
            draw.line((x0 + _s(170), _s(895), x0 + _s(170), _s(1280)), fill=secondary, width=_s(3))
    else:
        _draw_routes(draw, primary, seed)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if _size(draw, candidate, font)[0] <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _draw_rtl_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    right_x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: str,
    line_height: int,
) -> None:
    for index, line in enumerate(lines):
        shaped = _rtl(line)
        width, _ = _size(draw, shaped, font)
        draw.text((right_x - width, y + _s(index * line_height)), shaped, font=font, fill=fill)


def _last_combo(history_path: Path) -> tuple[str, str] | None:
    if not history_path.exists():
        return None
    for line in reversed(history_path.read_text(encoding="utf-8").splitlines()):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        theme = data.get("selected_theme")
        preset = data.get("selected_visual_preset")
        if theme and preset:
            return str(theme), str(preset)
    return None


def choose_content(history_path: Path, seed: int | None = None) -> tuple[dict, dict, str]:
    rng = random.Random(seed or random.SystemRandom().randint(1, 10_000_000))
    last = _last_combo(history_path)
    for _ in range(24):
        theme = pick_theme(THEMES, lambda item: str(item["id"]), rng)
        preset = pick_visual(VISUAL_PRESETS, lambda item: str(item["id"]), rng)
        if not last or (theme["id"], preset["id"]) != last:
            return theme, preset, rng.choice(HEADLINES)
    theme = pick_theme(THEMES, lambda item: str(item["id"]), rng)
    preset = pick_visual(VISUAL_PRESETS, lambda item: str(item["id"]), rng)
    return theme, preset, rng.choice(HEADLINES)


def generate_content_image(
    image_path: Path,
    history_path: Path,
    timezone: str = "Asia/Muscat",
    seed: int | None = None,
) -> dict:
    theme, preset, headline = choose_content(history_path, seed)
    rng = random.Random(seed or random.SystemRandom().randint(1, 10_000_000))
    primary = preset["primary"]
    secondary = preset["secondary"]
    image = Image.new("RGBA", (W, H), BG)
    _glow(image, (_s(420), _s(-240), _s(1320), _s(620)), (230, 193, 111, rng.randint(38, 72)), rng.randint(95, 135))
    _glow(image, (_s(-280), _s(1040), _s(520), _s(1940)), (230, 193, 111, rng.randint(24, 44)), rng.randint(110, 160))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((_s(38), _s(36), _s(1042), _s(1884)), radius=_s(42), outline="#7A5A22", width=_s(2))
    _draw_motif(draw, preset["motif"], primary, secondary, rng.randint(1, 999999))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((_s(38), _s(36), _s(1042), _s(1884)), fill=(0, 0, 0, rng.randint(68, 100)))
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)

    layouts = ["top_left", "center_editorial", "lower_panel", "split_luxury"]
    layout = rng.choice(layouts)
    brand_font = _font(rng.randint(34, 42), True, True)
    label_font = _font(rng.randint(20, 25), True)
    title_font = _font(rng.randint(50, 64), True)
    body_font = _font(rng.randint(27, 33), True)
    latin_font = _font(rng.randint(25, 32), True, True)
    date_font = _font(22, True)

    draw.text((_s(92), _s(86)), "OMONEY", font=brand_font, fill=primary)
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%Y/%m/%d  %H:%M")
    sw, _ = _size(draw, stamp, date_font)
    draw.text((_s(988) - sw, _s(96)), stamp, font=date_font, fill=MUTED)
    draw.line((_s(92), _s(158), _s(988), _s(158)), fill="#7A5A22", width=_s(2))

    if layout == "center_editorial":
        panel = (_s(92), _s(480), _s(988), _s(1325))
        title_y = _s(585)
    elif layout == "lower_panel":
        panel = (_s(92), _s(820), _s(988), _s(1588))
        title_y = _s(920)
    elif layout == "split_luxury":
        panel = (_s(92), _s(390), _s(988), _s(1510))
        title_y = _s(500)
    else:
        panel = (_s(92), _s(300), _s(988), _s(1160))
        title_y = _s(410)
    _rounded_panel(image, panel, 38, "#0C0C0DD8", "#8A6728")
    draw = ImageDraw.Draw(image)

    badge = f"{theme['country']}  /  {preset['label']}"
    draw.rounded_rectangle((_s(126), panel[1] + _s(42), _s(126) + _size(draw, badge, label_font)[0] + _s(42), panel[1] + _s(90)), radius=_s(24), fill="#15120D", outline=primary, width=_s(1))
    draw.text((_s(147), panel[1] + _s(52)), badge, font=label_font, fill=primary)

    title_lines = _wrap(draw, headline, title_font, _s(760))[:3]
    _draw_rtl_lines(draw, title_lines, _s(940), title_y, title_font, WHITE, 78)
    y = title_y + _s(250)
    draw.text((_s(126), y), str(theme["subtitle"]), font=latin_font, fill=primary)
    y += _s(75)
    body_lines = _wrap(draw, str(theme["body"]), body_font, _s(760))[:4]
    _draw_rtl_lines(draw, body_lines, _s(940), y, body_font, MUTED, 52)

    draw.line((_s(126), panel[3] - _s(150), _s(940), panel[3] - _s(150)), fill="#7A5A22", width=_s(2))
    draw.text((_s(126), panel[3] - _s(104)), "FAST  •  SECURE  •  RELIABLE", font=latin_font, fill=primary)
    draw.text((_s(92), _s(1734)), "omoney.online", font=_font(32, True), fill=WHITE)
    phone = "+96896129711"
    pw, _ = _size(draw, phone, _font(32, True))
    draw.text((_s(988) - pw, _s(1734)), phone, font=_font(32, True), fill=primary)
    footer = "OMONEY INTERNATIONAL FINANCE"
    fw, _ = _size(draw, footer, _font(23, True, True))
    draw.text((_s(540) - fw / 2, _s(1805)), footer, font=_font(23, True, True), fill=MUTED)

    final = image.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(image_path, "PNG")
    record_theme(str(theme["id"]))
    record_visual(str(preset["id"]))
    return {
        "selected_theme": theme["id"],
        "selected_visual_preset": preset["id"],
        "headline": headline,
        "image_path": str(image_path),
        "layout": layout,
    }
