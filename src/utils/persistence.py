import json
import os
from src.models.entities import FilterSettings

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")

_SETTINGS_KEYS = ("sort", "period", "types", "baseModels", "nsfw", "query", "page")

def save_settings(settings: FilterSettings):
    data = {k: getattr(settings, k) for k in _SETTINGS_KEYS}
    data.setdefault("types", ["Checkpoint"])
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

def load_settings() -> FilterSettings:
    if not os.path.exists(CONFIG_PATH):
        return FilterSettings()
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            return FilterSettings(**{k: data[k] for k in _SETTINGS_KEYS if k in data})
    except Exception:
        return FilterSettings()
