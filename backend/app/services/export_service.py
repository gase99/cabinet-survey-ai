"""Render deterministic engine SVGs, never substitute simulated room rectangles."""
import io
import os
import uuid
import xml.etree.ElementTree as ET  # parses only engine-generated, XML-escaped SVG
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.graphics import renderPDF, renderPM
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.pagesizes import A3, A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from app.services.pdf_text import FONT_NAME, FONT_NAME_BOLD, is_rtl, pil_font, register_fonts, shape

PAGE_SIZES = {"A4": A4, "A3": A3}
PNG_SIZES = {"A4": (2480, 3508), "A3": (3508, 4961)}


def output_file(extension, output_path):
    if output_path:
        return output_path
    root = Path(os.environ.get("EXPORT_STORAGE_DIR", "./var/data/exports"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return str(root / f"{uuid.uuid4().hex}.{extension}")


def pdf_views(plan_svg, elevations):
    """Backward-compatible view list: one plan page plus one page per elevation."""
    return ([("Top-down plan", plan_svg)] if plan_svg else []) + [
        (f"Wall elevation {wall_id}", svg) for wall_id, svg in elevations.items()
    ]


# Standard drawing scales (1:N). The largest drawing size that fits the page is chosen.
STANDARD_SCALES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500)
SCALE_BAR_LENGTHS_MM = (10, 20, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 50000)
MARGIN = 15 * mm
FOOTER_SPACE = 20 * mm
HEADER_SPACE = 45 * mm


def normalized_svg(svg: str) -> tuple[str, float, float, bool]:
    """Make 1 SVG user unit = 1 drawing unit; return (svg, width, height, millimetre_units).

    Engine SVGs use a viewBox in model millimetres with a nominal pixel width/height whose
    aspect ratio may differ from the viewBox. svglib scales x and y independently (it
    ignores preserveAspectRatio), which distorted elevations. Setting width/height to the
    viewBox size keeps the drawing undistorted and makes the print scale exact. An SVG
    without a viewBox has no known unit, so it can only be fitted (never "to scale")."""
    root = ET.fromstring(svg)
    raw_box = (root.get("viewBox") or "").replace(",", " ").split()
    if raw_box:
        box = [float(value) for value in raw_box]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            raise ValueError("Drawing SVG viewBox must have a positive size")
        width, height, millimetres = box[2], box[3], True
    else:
        width = float((root.get("width") or "0").removesuffix("px"))
        height = float((root.get("height") or "0").removesuffix("px"))
        if width <= 0 or height <= 0:
            raise ValueError("Drawing SVG must have a viewBox or a positive width and height")
        millimetres = False
    root.set("width", repr(width))
    root.set("height", repr(height))
    return ET.tostring(root, encoding="unicode"), width, height, millimetres


@dataclass(frozen=True)
class PageScale:
    denominator: int | None  # None = did not fit at any standard scale (fitted, NOT TO SCALE)
    factor: float  # PDF points per model millimetre
    origin_x: float
    origin_y: float
    width: float
    height: float

    @property
    def label(self) -> str:
        return f"Scale 1:{self.denominator}" if self.denominator else "NOT TO SCALE (fitted to page)"


def choose_scale(
    model_w_mm: float,
    model_h_mm: float,
    page_w: float,
    page_h: float,
    notice_lines: int = 0,
    to_scale: bool = True,
) -> PageScale:
    """Largest standard scale whose drawing fits the free page area, else fitted/not to scale."""
    available_w = page_w - 2 * MARGIN
    available_h = page_h - HEADER_SPACE - 6 * mm * notice_lines - FOOTER_SPACE - 12 * mm
    denominator: int | None = next(
        (n for n in STANDARD_SCALES if model_w_mm * mm / n <= available_w and model_h_mm * mm / n <= available_h),
        None,
    ) if to_scale else None
    factor = mm / denominator if denominator else min(available_w / model_w_mm, available_h / model_h_mm)
    width, height = model_w_mm * factor, model_h_mm * factor
    origin_x = MARGIN + (available_w - width) / 2
    origin_y = FOOTER_SPACE + 12 * mm + (available_h - height) / 2
    return PageScale(denominator, factor, origin_x, origin_y, width, height)


def scale_bar_length_mm(denominator: int, max_paper_mm: float = 50) -> int:
    fitting = [length for length in SCALE_BAR_LENGTHS_MM if length / denominator <= max_paper_mm]
    return fitting[-1] if fitting else SCALE_BAR_LENGTHS_MM[0]


def _shape_drawing_text(node) -> None:
    """Use the bundled font for every SVG label and shape Persian/Arabic text."""
    if isinstance(node, Drawing):  # avoid ReportLab's Times-Roman default graphics state
        node.initialFontName = FONT_NAME  # type: ignore[attr-defined]  # declared in Drawing._attrMap
    if isinstance(node, String):
        node.fontName = FONT_NAME
        node.text = shape(node.text)
    for child in getattr(node, "contents", []) or []:
        _shape_drawing_text(child)


def _draw_text(pdf, text: str, y: float, page_w: float, font: str = FONT_NAME, size: float = 9) -> None:
    """Draw one header line; RTL text is right-aligned, LTR text left-aligned."""
    pdf.setFont(font, size)
    visual = shape(text)
    if is_rtl(text):
        pdf.drawRightString(page_w - MARGIN, y, visual)
    else:
        pdf.drawString(MARGIN, y, visual)


def _draw_scale_bar(pdf, page: PageScale) -> None:
    if not page.denominator:
        return
    length_mm = scale_bar_length_mm(page.denominator)
    length_pt = length_mm * page.factor
    x, y = MARGIN, FOOTER_SPACE
    pdf.setLineWidth(0.6)
    pdf.line(x, y, x + length_pt, y)
    for tick in (x, x + length_pt / 2, x + length_pt):
        pdf.line(tick, y - 1.2 * mm, tick, y + 1.2 * mm)
    pdf.setFont(FONT_NAME, 7)
    pdf.drawString(x, y + 2 * mm, f"0    {length_mm} mm    (1:{page.denominator}, {length_mm / page.denominator:g} mm on paper)")


def render_views_pdf(
    project_title,
    customer_name,
    views,
    layout="A4",
    output_path=None,
    notices: list[str] | None = None,
):
    """Render one vector PDF page per (title, svg) view at a stated standard scale."""
    register_fonts()
    path = output_file("pdf", output_path)
    width, height = PAGE_SIZES[layout]
    temporary = path + ".partial"
    notice_lines = [line[:140] for line in (notices or []) if line][:4]
    try:
        # Stubs mistype initialFontName; it names the page's initial font (default Helvetica).
        pdf = canvas.Canvas(
            temporary, pagesize=(width, height), invariant=1, initialFontName=FONT_NAME  # type: ignore[arg-type]
        )
        for index, (title, svg) in enumerate(views):
            normalized, model_w, model_h, millimetres = normalized_svg(svg)
            drawing = svg2rlg(io.BytesIO(normalized.encode("utf-8")))
            if drawing is None or drawing.width <= 0 or drawing.height <= 0:
                raise ValueError("Invalid drawing SVG")
            _shape_drawing_text(drawing)
            page = choose_scale(model_w, model_h, width, height, len(notice_lines), millimetres)
            pdf.setFillColorRGB(0, 0, 0)
            _draw_text(pdf, project_title[:100], height - 20 * mm, width, FONT_NAME_BOLD, 14)
            _draw_text(pdf, f"{title} | Customer: {customer_name or '-'}", height - 27 * mm, width)
            pdf.setFont(FONT_NAME_BOLD, 9)
            pdf.drawString(
                MARGIN,
                height - 33 * mm,
                f"{page.label} on {layout} — print at 100% / actual size. Dimensions in mm."
                if page.denominator
                else f"{page.label} — do not measure from this page. Dimensions in mm.",
            )
            pdf.setFont(FONT_NAME, 8)
            pdf.drawString(MARGIN, height - 38 * mm, "Verify all dimensions on site before fabrication.")
            if notice_lines:
                pdf.setFillColorRGB(0.75, 0.1, 0.1)
                for line_idx, line in enumerate(notice_lines):
                    _draw_text(pdf, line, height - (44 + 6 * line_idx) * mm, width, FONT_NAME_BOLD, 8.5)
                pdf.setFillColorRGB(0, 0, 0)
            pdf.saveState()
            pdf.translate(page.origin_x, page.origin_y)
            pdf.scale(page.factor, page.factor)
            renderPDF.draw(drawing, pdf, 0, 0)
            pdf.restoreState()
            pdf.setFillColorRGB(0, 0, 0)
            pdf.setStrokeColorRGB(0, 0, 0)
            _draw_scale_bar(pdf, page)
            pdf.setFont(FONT_NAME, 8)
            pdf.drawString(
                MARGIN,
                10 * mm,
                f"{layout} | Page {index + 1}/{len(views)} | {page.label} | Print at 100% (no fit-to-page)",
            )
            pdf.showPage()
        pdf.save()
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def generate_project_pdf(
    project_title,
    customer_name,
    plan_svg,
    elevations,
    dimension_annotations,
    layout="A4",
    output_path=None,
    notices: list[str] | None = None,
):
    return render_views_pdf(
        project_title,
        customer_name,
        pdf_views(plan_svg if plan_svg else "", elevations or {}),
        layout=layout,
        output_path=output_path,
        notices=notices,
    )


def render_views_png(
    project_title,
    views,
    layout="A4",
    output_path=None,
    notices: list[str] | None = None,
):
    register_fonts()
    path = output_file("png", output_path)
    width, height = PNG_SIZES[layout]
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def line(y: int, text: str, size: int, fill, bold: bool = False) -> None:
        font = pil_font(size, bold)
        visual = shape(text)
        x = width - 100 - int(draw.textlength(visual, font=font)) if is_rtl(text) else 100
        draw.text((x, y), visual, fill=fill, font=font)

    line(60, project_title, 32, "black", bold=True)
    line(110, "Dimensions in mm | fitted overview sheet, NOT TO SCALE (use the PDF for scaled prints)", 24, "black")
    notice_lines = [text[:140] for text in (notices or []) if text][:4]
    top_offset = 180
    if notice_lines:
        for line_idx, text in enumerate(notice_lines):
            line(150 + line_idx * 32, text, 22, (180, 20, 20), bold=True)
        top_offset = 160 + len(notice_lines) * 32
    # PNG is a single sheet; PDF retains a separate vector page for each view.
    columns = 1 if len(views) <= 2 else 2
    rows = max(1, (len(views) + columns - 1) // columns)
    cell_w, cell_h = (width - 200) // columns, (height - top_offset - 120) // rows
    for index, (title, svg) in enumerate(views):
        drawing = svg2rlg(io.BytesIO(normalized_svg(svg)[0].encode("utf-8")))
        if drawing is None:
            raise ValueError("Invalid drawing SVG")
        _shape_drawing_text(drawing)
        factor = min((cell_w - 40) / drawing.width, (cell_h - 40) / drawing.height)
        drawing.scale(factor, factor)
        drawing.width *= factor
        drawing.height *= factor
        png = renderPM.drawToString(drawing, fmt="PNG", backend="_renderPM")
        png_bytes = png if isinstance(png, bytes) else png.encode("latin1")
        tile = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        image.paste(
            tile,
            (100 + (index % columns) * cell_w, top_offset + (index // columns) * cell_h),
        )
    temporary = path + ".partial"
    try:
        image.save(temporary, format="PNG", dpi=(300, 300))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def generate_project_png(
    project_title,
    dimension_annotations,
    plan_svg,
    elevations=None,
    layout="A4",
    output_path=None,
    notices: list[str] | None = None,
):
    return render_views_png(
        project_title,
        pdf_views(plan_svg if plan_svg else "", elevations or {}),
        layout=layout,
        output_path=output_path,
        notices=notices,
    )
