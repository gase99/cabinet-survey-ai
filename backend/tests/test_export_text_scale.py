"""Phase 5 item 5: bundled font, Persian/Arabic shaping and RTL order, print scale in PDFs.

Glyph *shapes* on paper can only be judged visually (see docs/export-output.md). These tests
verify what is machine-checkable: which fonts are embedded, which code points (contextual
presentation forms, visual order) are drawn, and the exact page geometry at the stated scale.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader
from pypdf.generic import ContentStream

from app.services import export_service, pdf_text
from app.services.export_service import choose_scale, normalized_svg, render_views_pdf, render_views_png
from app.services.geometry_service import walls_and_elements_from_room
from app.services.pdf_text import FontUnavailableError, missing_glyphs, shape

PT_PER_MM = 72 / 25.4
FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "print_scale.json").read_text(encoding="utf-8"))
ARABIC_BASE_LETTERS = re.compile("[\u0621-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc]")
PRESENTATION_FORMS = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]")


def _room(width_mm: int, depth_mm: int, height_mm: int = 2700, first_label: str = "Wall A", elements=()):
    corners = [(0, 0, width_mm, 0), (width_mm, 0, width_mm, depth_mm),
               (width_mm, depth_mm, 0, depth_mm), (0, depth_mm, 0, 0)]
    walls = [
        SimpleNamespace(id=f"w{index}", label=first_label if index == 0 else f"Wall {index}",
                        length_mm=width_mm if index % 2 == 0 else depth_mm, height_mm=height_mm,
                        start_x_mm=sx, start_y_mm=sy, end_x_mm=ex, end_y_mm=ey)
        for index, (sx, sy, ex, ey) in enumerate(corners)
    ]
    result = walls_and_elements_from_room(None, walls, list(elements))
    assert not result.errors
    return result


def _window(label: str):
    return SimpleNamespace(id="e1", wall_id="w0", label=label, kind="window", offset_mm=500,
                           width_mm=900, height_mm=1200, sill_mm=900, depth_mm=100)


def _page_shapes(reader: PdfReader, page_index: int):
    """Rectangles and polylines in PDF page points, with the current transformation applied."""
    page = reader.pages[page_index]
    ctm: tuple[float, ...] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    stack: list[tuple[float, ...]] = []
    rects, paths, current = [], [], []

    def apply(x, y):
        a, b, c, d, e, f = ctm
        return a * x + c * y + e, b * x + d * y + f

    for operands, operator in ContentStream(page.get_contents(), reader).operations:
        if operator == b"q":
            stack.append(ctm)
        elif operator == b"Q":
            ctm = stack.pop()
        elif operator == b"cm":
            a2, b2, c2, d2, e2, f2 = (float(value) for value in operands)
            a, b, c, d, e, f = ctm
            ctm = (a2 * a + b2 * c, a2 * b + b2 * d, c2 * a + d2 * c, c2 * b + d2 * d,
                   e2 * a + f2 * c + e, e2 * b + f2 * d + f)
        elif operator == b"re":
            x, y, w, h = (float(value) for value in operands)
            corners = [apply(x, y), apply(x + w, y + h)]
            rects.append({"user": (w, h), "page_w": abs(corners[1][0] - corners[0][0]),
                          "page_h": abs(corners[1][1] - corners[0][1])})
        elif operator == b"m":
            current = [(float(operands[0]), float(operands[1]), apply(float(operands[0]), float(operands[1])))]
            paths.append(current)
        elif operator == b"l":
            current.append((float(operands[0]), float(operands[1]), apply(float(operands[0]), float(operands[1]))))
    return rects, paths


def _fonts(reader: PdfReader) -> set[str]:
    names = set()
    for page in reader.pages:
        resources: Any = page["/Resources"]
        for font in resources["/Font"].values():
            names.add(str(font.get_object()["/BaseFont"]))
    return names


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda case: case["name"])
def test_print_scale_fixture_measures_exactly_on_the_page(case, tmp_path):
    width_mm, depth_mm = case["room_mm"]
    room = _room(width_mm, depth_mm, case["wall_height_mm"])
    svg = room.svg_plan if case["view"] == "plan" else room.elevations["w0"]
    pdf = render_views_pdf("Scale fixture", None, [("view", svg)], case["layout"], str(tmp_path / "scale.pdf"))
    reader = PdfReader(pdf)
    text = reader.pages[0].extract_text()
    assert f"Scale 1:{case['expected_scale']} on {case['layout']}" in text
    assert "print at 100%" in text and "Dimensions in mm" in text
    rects, paths = _page_shapes(reader, 0)
    expected_w, expected_h = (value * PT_PER_MM for value in case["expected_paper_mm"])
    if case["measure"] == "wall_rect":
        wall = [r for r in rects if r["user"] == (width_mm, case["wall_height_mm"])]
        assert len(wall) == 1
        measured = (wall[0]["page_w"], wall[0]["page_h"])
    else:
        outline = [p for p in paths if {(x, y) for x, y, _ in p} == {(0, 0), (width_mm, 0),
                                                                     (width_mm, depth_mm), (0, depth_mm)}]
        assert len(outline) == 1
        xs = [point[0] for _, _, point in outline[0]]
        ys = [point[1] for _, _, point in outline[0]]
        measured = (max(xs) - min(xs), max(ys) - min(ys))
    # 0.01 pt = 0.0035 mm: far below print/plotter resolution; aspect ratio must be preserved.
    assert measured[0] == pytest.approx(expected_w, abs=0.01)
    assert measured[1] == pytest.approx(expected_h, abs=0.01)
    assert width_mm / case["expected_scale"] == pytest.approx(case["expected_paper_mm"][0])


def test_3000_mm_wall_at_1_to_50_is_60_mm_on_paper():
    page = choose_scale(14000, 3300, *export_service.PAGE_SIZES["A4"])
    assert page.denominator == 100
    forced = export_service.PageScale(50, PT_PER_MM / 50, 0, 0, 0, 0)
    assert 3000 * forced.factor == pytest.approx(170.0787, abs=1e-4)  # 60 mm
    assert 3000 * page.factor == pytest.approx(30 * PT_PER_MM, abs=1e-4)


def test_scale_bar_states_paper_length():
    room = _room(3000, 2000)
    reader = PdfReader(render_views_pdf("Bar", None, [("e", room.elevations["w0"])], "A4", None))
    text = reader.pages[0].extract_text()
    assert "1000 mm" in text and "(1:20, 50 mm on paper)" in text
    _, paths = _page_shapes(reader, 0)
    bar = [p for p in paths if len(p) == 2 and p[0][1] == p[1][1] and
           abs(abs(p[1][0] - p[0][0]) - 50 * PT_PER_MM) < 0.01]
    assert bar, "50 mm scale bar line not found"


def test_svg_without_viewbox_is_never_claimed_to_scale(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="10" height="10"/></svg>'
    assert normalized_svg(svg)[3] is False
    text = PdfReader(render_views_pdf("X", None, [("v", svg)], "A4", str(tmp_path / "x.pdf"))).pages[0].extract_text()
    assert "NOT TO SCALE" in text and "do not measure" in text
    assert "Scale 1:" not in text


def test_elevation_is_not_distorted_by_nominal_pixel_size(tmp_path):
    # The engine SVG says width=800 height=500 for a 3400x3300 viewBox; drawing must keep 1:1 aspect.
    room = _room(3000, 2000)
    assert 'width="800" height="500"' in room.elevations["w0"]
    reader = PdfReader(render_views_pdf("A", None, [("e", room.elevations["w0"])], "A4", str(tmp_path / "a.pdf")))
    rects, _ = _page_shapes(reader, 0)
    wall = next(r for r in rects if r["user"] == (3000, 2700))
    assert wall["page_w"] / wall["page_h"] == pytest.approx(3000 / 2700, rel=1e-6)


def test_shaping_produces_contextual_forms_in_visual_order():
    # سلام → final meem, lam-alef ligature, initial seen (visual left-to-right).
    assert shape("سلام") == "\ufee1\ufefc\ufeb3"
    shaped = shape("دیوار شمالی")
    assert not ARABIC_BASE_LETTERS.search(shaped)
    assert shaped == "\ufbfd\ufedf\ufe8e\ufee4\ufeb7 \ufead\ufe8d\ufeee\ufbfe\ufea9"
    # ZWNJ (نیم‌فاصله) prevents joining: "سانتی‌متر" keeps ی in final form, م initial.
    assert shape("سانتی\u200cمتر") == "\ufeae\ufe98\ufee3\ufbfd\ufe98\ufee7\ufe8e\ufeb3"
    assert shape("Wall A 3000 mm") == "Wall A 3000 mm"


@pytest.mark.parametrize(
    "logical,visual_tail",
    [
        ("دیوار شمالی — 3000 mm × 2700 mm", "3000 mm × 2700 mm — "),
        ("پنجره 900×1200", "900×1200 "),
        ("دیوار شمالی (3000mm)", "(3000mm) "),
        ("کابینت 600 mm، عمق 560 mm", "560 mm "),
    ],
)
def test_numbers_and_mm_units_keep_left_to_right_order_inside_rtl_text(logical, visual_tail):
    visual = shape(logical)
    assert visual.startswith(visual_tail)
    assert "\u202a" not in visual and "\u202c" not in visual
    assert missing_glyphs(logical) == []


def test_persian_digits_and_all_persian_letters_have_glyphs():
    assert missing_glyphs("ارتفاع ۲۷۰۰ میلی‌متر — پ چ ژ گ ک ی ء أ ؤ ئ ة ـ ٪ ٫") == []


def test_exported_pdf_embeds_only_bundled_font_and_draws_shaped_rtl_text(tmp_path):
    room = _room(3000, 2000, first_label="دیوار شمالی", elements=[_window("پنجره")])
    views = export_service.pdf_views(room.svg_plan, room.elevations)
    pdf = render_views_pdf("آشپزخانه خانم احمدی", "مشتری تست", views, "A4", str(tmp_path / "fa.pdf"),
                           notices=["هشدار: موارد تأیید نشده"])
    reader = PdfReader(pdf)
    fonts = _fonts(reader)
    assert fonts and all(re.fullmatch(r"/[A-Z]{6}\+Vazirmatn(-Bold|-Regular)", name) for name in fonts), fonts
    for page in reader.pages:
        descriptor_keys = set()
        for font in page["/Resources"]["/Font"].values():
            font = font.get_object()
            if "/DescendantFonts" in font:
                font = font["/DescendantFonts"][0].get_object()
            descriptor_keys |= set(font["/FontDescriptor"].get_object().keys())
        assert "/FontFile2" in descriptor_keys  # TrueType program embedded (subset)
    text = "".join(page.extract_text() for page in reader.pages)
    assert PRESENTATION_FORMS.search(text)
    assert not ARABIC_BASE_LETTERS.search(text), "unshaped (isolated base) Arabic letters were drawn"
    for expected in ("3000 mm × 2700 mm", "900×1200", "3000 mm", "Scale 1:"):
        assert expected in text


def test_pdf_and_png_output_is_deterministic(tmp_path):
    room = _room(3000, 2000, first_label="دیوار شمالی")
    views = export_service.pdf_views(room.svg_plan, room.elevations)
    first = render_views_pdf("آشپزخانه", None, views, "A4", str(tmp_path / "1.pdf"))
    second = render_views_pdf("آشپزخانه", None, views, "A4", str(tmp_path / "2.pdf"))
    assert hashlib.sha256(Path(first).read_bytes()).digest() == hashlib.sha256(Path(second).read_bytes()).digest()
    png1 = render_views_png("آشپزخانه", views, "A4", str(tmp_path / "1.png"))
    png2 = render_views_png("آشپزخانه", views, "A4", str(tmp_path / "2.png"))
    with Image.open(png1) as a, Image.open(png2) as b:
        # Header text is drawn by Pillow with the bundled font: pixel-identical.
        assert a.crop((0, 0, a.width, 180)).tobytes() == b.crop((0, 0, b.width, 180)).tobytes()
        # Drawing tiles come from rl_renderPM, whose glyph anti-aliasing varies by a few grey
        # levels between runs (also with Helvetica; upstream behaviour). Geometry is identical.
        difference = ImageChops.difference(a.convert("L"), b.convert("L"))
        assert max(level for level, count in enumerate(difference.histogram()) if count) <= 8


def test_png_header_rtl_title_is_right_aligned(tmp_path):
    room = _room(3000, 2000)
    png = render_views_png("آشپزخانه خانم احمدی", [("e", room.elevations["w0"])], "A4", str(tmp_path / "t.png"))
    with Image.open(png) as image:
        title_band = image.crop((0, 55, image.width, 105)).convert("L")
        box = title_band.point(lambda value: 255 if value < 128 else 0).getbbox()
    assert box is not None
    assert box[2] == pytest.approx(image.width - 100, abs=6)  # right margin
    assert box[0] > image.width / 2  # short title stays on the right half


@pytest.fixture
def fontless(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_text, "FONT_DIR", tmp_path / "fonts-missing")
    pdf_text.pil_font.cache_clear()
    yield tmp_path
    pdf_text.pil_font.cache_clear()


def test_missing_bundled_font_fails_pdf_and_png_export(fontless):
    room = _room(3000, 2000)
    views = [("e", room.elevations["w0"])]
    with pytest.raises(FontUnavailableError, match="missing"):
        render_views_pdf("x", None, views, "A4", str(fontless / "x.pdf"))
    with pytest.raises(FontUnavailableError, match="missing"):
        render_views_png("x", views, "A4", str(fontless / "x.png"))
    assert not list(fontless.glob("x.*"))


def test_substituted_font_file_fails_digest_check(tmp_path, monkeypatch):
    fonts = tmp_path / "fonts"
    shutil.copytree(pdf_text.FONT_DIR, fonts)
    (fonts / "Vazirmatn-Regular.ttf").write_bytes((fonts / "Vazirmatn-Bold.ttf").read_bytes())
    monkeypatch.setattr(pdf_text, "FONT_DIR", fonts)
    with pytest.raises(FontUnavailableError, match="SHA-256"):
        pdf_text.register_fonts()


def test_bundled_font_and_license_are_shipped():
    for filename, digest in pdf_text.FONT_FILES.values():
        assert hashlib.sha256((pdf_text.FONT_DIR / filename).read_bytes()).hexdigest() == digest
    assert "SIL Open Font License" in (pdf_text.FONT_DIR / "OFL.txt").read_text(encoding="utf-8")


def test_api_export_with_missing_font_fails_job_without_leaking_paths(client, auth_headers, fontless):
    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "آشپزخانه"}).json()["id"]
    room = client.post(f"/api/v1/projects/{project}/rooms", headers=auth_headers,
                       json={"label": "اتاق", "room_type": "rectangular"}).json()["id"]
    corners = [(0, 0, 3000, 0), (3000, 0, 3000, 2000), (3000, 2000, 0, 2000), (0, 2000, 0, 0)]
    for index, (sx, sy, ex, ey) in enumerate(corners):
        wall = client.post(f"/api/v1/rooms/{room}/walls", headers=auth_headers, json={
            "label": f"دیوار {index}", "length_mm": 3000 if index % 2 == 0 else 2000, "height_mm": 2700,
            "start_x_mm": sx, "start_y_mm": sy, "end_x_mm": ex, "end_y_mm": ey}).json()["id"]
        assert client.post(f"/api/v1/walls/{wall}/approve", headers=auth_headers).status_code == 200
    job = client.post(f"/api/v1/exports/{project}", headers=auth_headers, json={"format": "pdf", "layout": "A4"})
    assert job.status_code == 202
    status = client.get(job.json()["status_url"], headers=auth_headers).json()
    assert status["status"] == "failed"
    assert status["error_message"] == "Drawing rendering failed"
    assert "fonts-missing" not in json.dumps(status)


def test_api_refuses_to_start_without_bundled_font(fontless):
    from fastapi.testclient import TestClient

    from app.main import app

    with pytest.raises(FontUnavailableError), TestClient(app):
        pass
