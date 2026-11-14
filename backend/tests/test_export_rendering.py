import io
from pathlib import Path
import pytest
from PIL import Image
from pypdf import PdfReader
from app.services.export_service import generate_project_pdf, generate_project_png, PNG_SIZES

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><path d="M20 20 L380 20 L380 140 L200 140 L200 280 L20 280 Z" fill="none" stroke="black" stroke-width="4"/><text x="25" y="60">3200 mm</text></svg>'


@pytest.mark.parametrize('layout,width_mm,height_mm',[('A4',210,297),('A3',297,420)])
def test_real_svg_vector_pdf_and_300dpi_png(tmp_path,layout,width_mm,height_mm):
    pdf=generate_project_pdf('Fixture Kitchen',None,SVG,{'a':SVG},[],layout,str(tmp_path/'drawing.pdf'))
    reader=PdfReader(pdf)
    assert len(reader.pages)==2
    for page in reader.pages:
        assert float(page.mediabox.width)==pytest.approx(width_mm*72/25.4,abs=.01)
        assert float(page.mediabox.height)==pytest.approx(height_mm*72/25.4,abs=.01)
        assert '3200' in page.extract_text()
        # The L-shaped source path must exist as vector operators, not an image/placeholder.
        assert b'380 140 l' in page.get_contents().get_data()
    png=generate_project_png('Fixture Kitchen',[],SVG,{},layout,str(tmp_path/'drawing.png'))
    with Image.open(png) as image:
        assert image.size==PNG_SIZES[layout]
        assert image.info['dpi'][0]==pytest.approx(300,abs=.1)
        assert image.getbbox() is not None
        # Interior geometry contains dark pixels well below header text.
        assert image.crop((100,300,image.width-100,image.height-100)).convert('L').getextrema()[0] < 100
    assert not list(tmp_path.glob('*.partial'))
