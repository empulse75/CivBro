from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Model:
    id: str
    name: str
    type: str
    stats: Dict[str, Any] = field(default_factory=dict)
    images: List[Dict[str, Any]] = field(default_factory=list)
    baseModel: Optional[str] = None
    downloadUrl: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    createdAt: Optional[str] = None
    publishedAt: Optional[str] = None
    nsfwLevel: int = 0
    nsfw: bool = False
    creatorImage: Optional[str] = None
    availability: str = "Public"
    cosmetic: Optional[Any] = None
    creatorCosmetics: List[Dict[str, Any]] = field(default_factory=list)
    badges: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class LocalModel:
    filename: str
    path: str
    type: str
    size_mb: float
    hash: Optional[str] = None
    preview_path: Optional[str] = None
    model_id: Optional[str] = None
    version_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FilterSettings:
    sort: str = "Highest Rated"
    period: str = "All Time"
    types: List[str] = field(default_factory=lambda: ["Checkpoint"])
    baseModels: List[str] = field(default_factory=list)
    nsfw: bool = False
    query: str = ""
    searchType: str = "Model name"
    page: int = 1
    limit: int = 42
    cursor: Optional[str] = None
    status: List[str] = field(default_factory=list)
    checkpointType: str = "All"
    fileFormat: List[str] = field(default_factory=list)
    hideInstalled: bool = False
