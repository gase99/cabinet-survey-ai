"""Render deterministic engine SVGs, never substitute simulated room rectangles."""
import io
import os
from pathlib import Path
import uuid
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A3, A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF, renderPM
from svglib.svglib import svg2rlg

PAGE_SIZES = {'A4': A4, 'A3': A3}
PNG_SIZES = {'A4': (2480, 3508), 'A3': (3508, 4961)}


def output_file(extension, output_path):
    if output_path:
        return output_path
    root = Path(os.environ.get('EXPORT_STORAGE_DIR', './var/data/exports'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return str(root / f'{uuid.uuid4().hex}.{extension}')


def pdf_views(plan_svg, elevations):
    """Backward-compatible view list: one plan page plus one page per elevation."""
    return ([('Top-down plan', plan_svg)] if plan_svg else []) + [
        (f'Wall elevation {wall_id}', svg) for wall_id, svg in elevations.items()]


def render_views_pdf(project_title, customer_name, views, layout='A4', output_path=None):
    """Render one vector PDF page per (title, svg) view, in the given order."""
    path = output_file('pdf', output_path)
    width, height = PAGE_SIZES[layout]
    temporary = path + '.partial'
    try:
        pdf = canvas.Canvas(temporary, pagesize=(width,height), invariant=1)
        for index,(title,svg) in enumerate(views):
            pdf.setFont('Helvetica-Bold',14)
            pdf.drawString(15*mm,height-20*mm,project_title[:100])
            pdf.setFont('Helvetica',9)
            pdf.drawString(15*mm,height-27*mm,f'{title} | Customer: {customer_name or "-"}')
            pdf.drawString(15*mm,height-33*mm,'Dimensions in mm. Fitted view, not a fixed fabrication scale. Verify on site.')
            drawing = svg2rlg(io.BytesIO(svg.encode('utf-8')))
            if drawing is None or drawing.width <= 0 or drawing.height <= 0:
                raise ValueError('Invalid drawing SVG')
            available_w,available_h = width-30*mm,height-65*mm
            factor = min(available_w/drawing.width, available_h/drawing.height)
            pdf.saveState()
            pdf.translate(15*mm+(available_w-drawing.width*factor)/2,
                          20*mm+(available_h-drawing.height*factor)/2)
            pdf.scale(factor,factor)
            renderPDF.draw(drawing,pdf,0,0)
            pdf.restoreState()
            pdf.setFont('Helvetica',8)
            pdf.drawString(15*mm,10*mm,f'{layout} | Page {index+1}/{len(views)} | Print at 100% to preserve page layout')
            pdf.showPage()
        pdf.save()
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return path


def generate_project_pdf(project_title, customer_name, plan_svg, elevations,
                         dimension_annotations, layout='A4', output_path=None):
    return render_views_pdf(project_title, customer_name,
                            pdf_views(plan_svg if plan_svg else '', elevations or {}),
                            layout=layout, output_path=output_path)


def render_views_png(project_title, views, layout='A4', output_path=None):
    path = output_file('png', output_path)
    width,height = PNG_SIZES[layout]
    image = Image.new('RGB',(width,height),'white')
    draw = ImageDraw.Draw(image)
    draw.text((100,60),project_title,fill='black',font_size=32)
    draw.text((100,110),'Dimensions in mm | fitted view, not fixed scale',fill='black',font_size=24)
    # PNG is a single sheet; PDF retains a separate vector page for each view.
    columns = 1 if len(views)<=2 else 2
    rows = max(1,(len(views)+columns-1)//columns)
    cell_w,cell_h = (width-200)//columns,(height-300)//rows
    for index,(title,svg) in enumerate(views):
        drawing = svg2rlg(io.BytesIO(svg.encode('utf-8')))
        if drawing is None:
            raise ValueError('Invalid drawing SVG')
        factor = min((cell_w-40)/drawing.width,(cell_h-40)/drawing.height)
        drawing.scale(factor,factor)
        drawing.width *= factor
        drawing.height *= factor
        png = renderPM.drawToString(drawing,fmt='PNG',backend='_renderPM')
        tile = Image.open(io.BytesIO(png)).convert('RGB')
        image.paste(tile,(100+(index%columns)*cell_w,180+(index//columns)*cell_h))
    temporary = path + '.partial'
    try:
        image.save(temporary,format='PNG',dpi=(300,300))
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return path


def generate_project_png(project_title, dimension_annotations, plan_svg,
                         elevations=None, layout='A4', output_path=None):
    return render_views_png(project_title, pdf_views(plan_svg if plan_svg else '', elevations or {}),
                            layout=layout, output_path=output_path)
