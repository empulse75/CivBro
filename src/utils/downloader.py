import os
import json
import time
import threading
import requests
from typing import Dict, List, Optional
from src.models.downloads import DownloadTask
from src.api.routers.models import router as models_router

WEBUI_MODELS_DIR = os.environ.get("WEBUI_MODELS_DIR", "/home/gonzo/webui/sd-webui-forge-classic/models/Stable-diffusion")

def _get_headers() -> Dict[str, str]:
    config_path = os.path.join(os.path.expanduser("~/.config/civbro"), "config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
            api_key = config.get("civitai_api_key", "")
            if api_key:
                return {"Authorization": f"Bearer {api_key}"}
    except:
        pass
    return {}

def _download_preview_image(model, dest_model_path: str):
    images = model.images
    if not images:
        return
    for img in images:
        url = img.get('url', '')
        if not url or not url.startswith('http'):
            continue
        preview_ext = '.preview.png'
        if '.mp4' in url.lower():
            continue
        base_no_ext = os.path.splitext(dest_model_path)[0]
        preview_path = base_no_ext + preview_ext
        try:
            resp = requests.get(url, stream=True, timeout=30, headers=_get_headers())
            resp.raise_for_status()
            with open(preview_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return
        except Exception:
            continue

def _save_model_info(dest_model_path: str, model):
    base_no_ext = os.path.splitext(dest_model_path)[0]
    json_path = base_no_ext + '.json'
    try:
        info = {
            'id': model.id,
            'name': model.name,
            'type': model.type,
            'baseModel': model.baseModel,
            'author': model.author,
            'downloaded_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        with open(json_path, 'w') as f:
            json.dump(info, f, indent=2)
    except Exception:
        pass

class DownloadWorker:
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self._queue: List[str] = []
        self._current_task_id: Optional[str] = None
        self.lock = threading.Lock()
        self._cleanup_counter = 0

    def _update_queue_positions(self):
        for i, tid in enumerate(self._queue, 1):
            if tid in self.tasks:
                self.tasks[tid].queue_position = i

    def _cleanup_stale(self):
        self._cleanup_counter += 1
        if self._cleanup_counter % 10 != 0:
            return
        stale = [tid for tid, t in self.tasks.items() if t.status in ("completed", "cancelled", "error")]
        for tid in stale:
            del self.tasks[tid]

    def start_download(self, model_id: str, version_id: str) -> DownloadTask:
        model = models_router.get_by_id(model_id)
        if not model:
            task = DownloadTask(id=f"{model_id}_error", model_id=model_id, version_id=version_id, status="error", error_message="Model not found in cache")
            return task

        dl_url = model.downloadUrl
        if not dl_url:
            v1_base = "https://civitai.com/api/v1"
            try:
                headers = _get_headers()
                resp = requests.get(f"{v1_base}/models/{model_id}", headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                versions = data.get("modelVersions", [])
                if versions:
                    v0 = versions[0]
                    dl_url = v0.get("downloadUrl")
                    if not dl_url:
                        files = v0.get("files", [])
                        if files:
                            dl_url = files[0].get("downloadUrl")
                if not dl_url:
                    task = DownloadTask(id=f"{model_id}_error", model_id=model_id, version_id=version_id, status="error", error_message="No download URL found")
                    return task
            except Exception as e:
                task = DownloadTask(id=f"{model_id}_error", model_id=model_id, version_id=version_id, status="error", error_message=str(e))
                return task

        task_id = f"{model_id}_{version_id}_{int(time.time())}"
        task = DownloadTask(id=task_id, model_id=model_id, version_id=version_id)
        task.status = "queued"
        task.destination = os.path.join(WEBUI_MODELS_DIR, f"{model.name}.safetensors")
        task._dl_url = dl_url
        task._model = model

        with self.lock:
            self.tasks[task_id] = task
            self._queue.append(task_id)
            self._update_queue_positions()
            self._cleanup_stale()

        self._start_next()
        return task

    def _start_next(self):
        while True:
            dl_url = None
            dest = None
            model = None
            task_id = None

            with self.lock:
                if self._current_task_id is not None:
                    return
                if not self._queue:
                    return
                task_id = self._queue.pop(0)
                task = self.tasks.get(task_id)
                if not task or task.status == "cancelled":
                    continue
                task.status = "downloading"
                task.queue_position = 0
                self._current_task_id = task_id
                self._update_queue_positions()
                dl_url = task._dl_url
                dest = task.destination
                model = task._model

            threading.Thread(
                target=self._run_download,
                args=(task_id, dl_url, dest, model),
                daemon=True
            ).start()
            return

    def _run_download(self, task_id: str, url: str, dest: str, model):
        try:
            self._download(task_id, url, dest, model)
        except Exception as e:
            task = self.tasks.get(task_id)
            if task:
                task.status = "error"
                task.error_message = str(e)
        finally:
            self._on_complete(task_id)

    def _on_complete(self, task_id: str):
        with self.lock:
            if self._current_task_id == task_id:
                self._current_task_id = None
        self._start_next()

    def _download(self, task_id: str, url: str, dest: str, model):
        task = self.tasks[task_id]
        task.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        resp = requests.get(url, stream=True, timeout=30, headers=_get_headers())
        resp.raise_for_status()
        total = int(resp.headers.get('content-length', 0))
        downloaded = 0
        with open(dest, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if task.status == "cancelled":
                    f.close()
                    if os.path.exists(dest):
                        os.remove(dest)
                    return
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    task.progress = min(100.0, (downloaded / total) * 100.0)
        if task.status == "cancelled":
            if os.path.exists(dest):
                os.remove(dest)
            return
        task.progress = 100.0
        task.status = "completed"
        task.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        _save_model_info(dest, model)
        _download_preview_image(model, dest)

    def cancel_download(self, task_id: str):
        with self.lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                if task.status == "queued":
                    task.status = "cancelled"
                    if task_id in self._queue:
                        self._queue.remove(task_id)
                    self._update_queue_positions()
                else:
                    task.status = "cancelled"

    def cancel_by_model(self, model_id: str):
        with self.lock:
            for t in list(self.tasks.values()):
                if t.model_id == model_id and t.status in ("downloading", "queued"):
                    self.cancel_download(t.id)

    def get_status(self) -> List[DownloadTask]:
        with self.lock:
            return list(self.tasks.values())

worker = DownloadWorker()
