from __future__ import annotations

import os
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONTS_REGISTERED = False
UNICODE_FONT_FAMILY = "CareerOS-Sans"
UNICODE_FONT_BOLD = "CareerOS-Sans-Bold"
UNICODE_FONT_ITALIC = "CareerOS-Sans-Italic"
UNICODE_FONT_BOLD_ITALIC = "CareerOS-Sans-BoldItalic"


def _candidate_font_paths() -> list[tuple[str, str, str, str]]:
    """Return candidates for (regular, bold, italic, bold_italic) font paths across platforms."""
    candidates: list[tuple[str, str, str, str]] = []

    # 1. Local bundled directory inside backend/resumes/fonts/
    bundled_dir = Path(__file__).resolve().parent.parent / "fonts"
    if (bundled_dir / "regular.ttf").exists():
        candidates.append(
            (
                str(bundled_dir / "regular.ttf"),
                str(bundled_dir / "bold.ttf")
                if (bundled_dir / "bold.ttf").exists()
                else str(bundled_dir / "regular.ttf"),
                str(bundled_dir / "italic.ttf")
                if (bundled_dir / "italic.ttf").exists()
                else str(bundled_dir / "regular.ttf"),
                str(bundled_dir / "bold_italic.ttf")
                if (bundled_dir / "bold_italic.ttf").exists()
                else str(bundled_dir / "regular.ttf"),
            )
        )

    # 2. Windows standard Arial
    win_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if (win_dir / "arial.ttf").exists():
        candidates.append(
            (
                str(win_dir / "arial.ttf"),
                str(win_dir / "arialbd.ttf")
                if (win_dir / "arialbd.ttf").exists()
                else str(win_dir / "arial.ttf"),
                str(win_dir / "ariali.ttf")
                if (win_dir / "ariali.ttf").exists()
                else str(win_dir / "arial.ttf"),
                str(win_dir / "arialbi.ttf")
                if (win_dir / "arialbi.ttf").exists()
                else str(win_dir / "arial.ttf"),
            )
        )

    # 3. Linux DejaVuSans
    for dejavu_dir in [
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/TTF"),
        Path("/usr/local/share/fonts"),
    ]:
        if (dejavu_dir / "DejaVuSans.ttf").exists():
            candidates.append(
                (
                    str(dejavu_dir / "DejaVuSans.ttf"),
                    str(dejavu_dir / "DejaVuSans-Bold.ttf")
                    if (dejavu_dir / "DejaVuSans-Bold.ttf").exists()
                    else str(dejavu_dir / "DejaVuSans.ttf"),
                    str(dejavu_dir / "DejaVuSans-Oblique.ttf")
                    if (dejavu_dir / "DejaVuSans-Oblique.ttf").exists()
                    else str(dejavu_dir / "DejaVuSans.ttf"),
                    str(dejavu_dir / "DejaVuSans-BoldOblique.ttf")
                    if (dejavu_dir / "DejaVuSans-BoldOblique.ttf").exists()
                    else str(dejavu_dir / "DejaVuSans.ttf"),
                )
            )

    # 4. Linux LiberationSans
    liberation_dir = Path("/usr/share/fonts/truetype/liberation")
    if (liberation_dir / "LiberationSans-Regular.ttf").exists():
        candidates.append(
            (
                str(liberation_dir / "LiberationSans-Regular.ttf"),
                str(liberation_dir / "LiberationSans-Bold.ttf")
                if (liberation_dir / "LiberationSans-Bold.ttf").exists()
                else str(liberation_dir / "LiberationSans-Regular.ttf"),
                str(liberation_dir / "LiberationSans-Italic.ttf")
                if (liberation_dir / "LiberationSans-Italic.ttf").exists()
                else str(liberation_dir / "LiberationSans-Regular.ttf"),
                str(liberation_dir / "LiberationSans-BoldItalic.ttf")
                if (liberation_dir / "LiberationSans-BoldItalic.ttf").exists()
                else str(liberation_dir / "LiberationSans-Regular.ttf"),
            )
        )

    # 5. macOS Arial
    mac_arial = Path("/Library/Fonts/Arial.ttf")
    if mac_arial.exists():
        candidates.append(
            (
                str(mac_arial),
                str(Path("/Library/Fonts/Arial Bold.ttf"))
                if Path("/Library/Fonts/Arial Bold.ttf").exists()
                else str(mac_arial),
                str(Path("/Library/Fonts/Arial Italic.ttf"))
                if Path("/Library/Fonts/Arial Italic.ttf").exists()
                else str(mac_arial),
                str(Path("/Library/Fonts/Arial Bold Italic.ttf"))
                if Path("/Library/Fonts/Arial Bold Italic.ttf").exists()
                else str(mac_arial),
            )
        )

    return candidates


def ensure_unicode_font_registered() -> tuple[str, str, str]:
    """Register and return (normal_font, bold_font, italic_font) names for ReportLab."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return UNICODE_FONT_FAMILY, UNICODE_FONT_BOLD, UNICODE_FONT_ITALIC

    candidates = _candidate_font_paths()
    for regular, bold, italic, bold_italic in candidates:
        try:
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_FAMILY, regular))
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_BOLD, bold))
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_ITALIC, italic))
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_BOLD_ITALIC, bold_italic))
            pdfmetrics.registerFontFamily(
                UNICODE_FONT_FAMILY,
                normal=UNICODE_FONT_FAMILY,
                bold=UNICODE_FONT_BOLD,
                italic=UNICODE_FONT_ITALIC,
                boldItalic=UNICODE_FONT_BOLD_ITALIC,
            )
            _FONTS_REGISTERED = True
            return UNICODE_FONT_FAMILY, UNICODE_FONT_BOLD, UNICODE_FONT_ITALIC
        except Exception:
            continue

    from backend.resumes.quality import ResumeQualityError

    raise ResumeQualityError(
        "A local Unicode font is unavailable. Install Arial, DejaVu Sans or Liberation Sans "
        "locally, then retry PDF export. No font was downloaded."
    )
