from dataclasses import dataclass, field
from typing import Optional

@dataclass
class DownloadTask:
    id: str
    model_id: str
    version_id: str
    status: str = "queued"
    progress: float = 0.0
    queue_position: int = 0
    destination: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    _dl_url: Optional[str] = field(default=None, repr=False)
    _model: Optional[object] = field(default=None, repr=False)
