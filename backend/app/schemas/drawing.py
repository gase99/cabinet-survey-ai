from pydantic import BaseModel
from typing import List

class DrawingResponse(BaseModel):
    project_id: str
    room_id: str
    plan_svg: str
    elevations: dict[str, str]
    area_mm2: int
    perimeter_mm: int
    errors: list
    warnings: list
    dimension_annotations: list
    metadata: dict

class ExportRequest(BaseModel):
    format: str = "pdf"  # pdf | png
    layout: str = "A4"  # A3 | A4
    include_elevations: bool = True
    include_plan: bool = True

class ExportOut(BaseModel):
    id: str
    project_id: str
    format: str
    layout: str
    status: str
    file_path: str | None = None
    error_message: str | None = None
    model_config = {"from_attributes": True}
