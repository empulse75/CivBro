"""
CivBro Agent API — RESTful interface for AI agents to search, inspect, and download models.

Endpoints:
  GET  /api/search?query=<term>&baseModel=<model>&sort=<sort>&nsfw=<bool>&page=1&limit=20
  GET  /api/model/<id>
  POST /api/download  {"modelId": <int>, "versionId": <int>, "fileName": "<string>"}

Run: uvicorn src.api.agent_api:app --host 127.0.0.1 --port 8000
"""

from typing import Optional, List
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.api.routers.models import router as models_router
from src.api.routers.downloads import router as downloads_router
from src.models.entities import FilterSettings

app = FastAPI(title="CivBro Agent API", version="1.0.0")


class DownloadRequest(BaseModel):
    modelId: int
    versionId: Optional[int] = None
    fileName: Optional[str] = None


class DownloadResponse(BaseModel):
    status: str
    localPath: Optional[str] = None
    message: Optional[str] = None


@app.get("/api/search")
def search_models(
    query: str = Query("", description="Search term"),
    baseModel: str = Query("", description="Filter by base model"),
    sort: str = Query("Highest Rated", description="Sort order"),
    nsfw: bool = Query(False, description="Include NSFW models"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        types = ["Checkpoint"]
        filters = FilterSettings(query=query, sort=sort, types=types, nsfw=nsfw, page=page)
        models = models_router.list(filters)
        return {
            "status": "ok",
            "count": len(models),
            "page": page,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "type": m.type,
                    "author": m.author,
                    "baseModel": m.baseModel,
                    "rating": m.stats.get("rating", 0),
                    "downloads": m.stats.get("downloadCount", 0),
                    "likes": m.stats.get("likes", 0),
                    "previewImage": m.images[0].get("url") if m.images else None,
                    "downloadUrl": m.downloadUrl,
                }
                for m in models[:limit]
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/{model_id}")
def get_model(model_id: str):
    model = models_router.get_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found in cache. Trigger a search first.")
    return {
        "status": "ok",
        "model": {
            "id": model.id,
            "name": model.name,
            "type": model.type,
            "author": model.author,
            "baseModel": model.baseModel,
            "stats": model.stats,
            "images": model.images,
            "downloadUrl": model.downloadUrl,
            "tags": model.tags,
            "createdAt": model.createdAt,
        },
    }


@app.post("/api/download", response_model=DownloadResponse)
def download_model(req: DownloadRequest):
    try:
        task = downloads_router.queue(str(req.modelId), str(req.versionId) if req.versionId else "latest")
        return DownloadResponse(status="queued", localPath=task.destination, message="Download queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "CivBro Agent API", "version": "1.0.0"}