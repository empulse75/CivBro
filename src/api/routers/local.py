from typing import List
import os
from src.models.entities import LocalModel
from src.utils.scanner import scanner

class LocalRouter:
    def get_local_models(self) -> List[LocalModel]:
        return scanner.scan_models()

    def delete_model(self, path: str) -> bool:
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except:
            pass
        return False

router = LocalRouter()