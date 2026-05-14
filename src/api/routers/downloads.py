from typing import List
from src.models.downloads import DownloadTask
from src.utils.downloader import worker

class DownloadsRouter:
    def queue(self, model_id: str, version_id: str) -> DownloadTask:
        return worker.start_download(model_id, version_id)

    def get_status(self) -> List[DownloadTask]:
        return worker.get_status()

    def cancel_by_model(self, model_id: str):
        worker.cancel_by_model(model_id)

router = DownloadsRouter()
