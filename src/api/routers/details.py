from typing import Optional
from src.models.entities import Model
from src.api.routers.models import router as models_router

class DetailsRouter:
    def get_details(self, model_id: str) -> Optional[Model]:
        return models_router.get_by_id(model_id)

router = DetailsRouter()
