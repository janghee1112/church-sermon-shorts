from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


RenderStatus = Literal["queued", "preparing", "rendering", "completed", "failed", "cancelled"]


class RenderResponse(BaseModel):
    id: int
    project_id: str
    draft_id: int
    version: int
    status: RenderStatus
    progress: int
    current_step: str
    error_code: Optional[str]
    error_message: Optional[str]
    output_file_name: Optional[str]
    output_file_size: Optional[int]
    output_duration_sec: Optional[float]
    output_width: Optional[int]
    output_height: Optional[int]
    preview_url: Optional[str]
    download_url: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    updated_at: datetime

