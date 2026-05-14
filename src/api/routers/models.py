import requests
import json
import os
import threading
import time
import urllib.parse
from typing import List, Optional, Dict
from src.models.entities import Model, FilterSettings

class ModelsRouter:
    BASE = "https://civitai.com/api/v1"
    TRPC = "https://civitai.com/api/trpc"
    _cache: Dict[str, Model] = {}
    _trpc_cache: Dict[str, tuple] = {}
    _lock = threading.Lock()
    TRPC_CACHE_TTL = 300
    _last_request_time = 0
    _min_request_gap = 2.0

    TYPE_MAP = {
        "Checkpoint": "Checkpoint",
        "Embedding": "TextualInversion",
        "Hypernetwork": "Hypernetwork",
        "Aesthetic Gradient": "AestheticGradient",
        "LoRA": "LORA",
        "LyCORIS": "LoCon",
        "DoRA": "DoRA",
        "Controlnet": "Controlnet",
        "Upscaler": "Upscaler",
        "Motion": "MotionModule",
        "VAE": "VAE",
        "Poses": "Poses",
        "Wildcards": "Wildcards",
        "Workflows": "Workflows",
        "Detection": "Other",
        "Other": "Other",
    }

    def __init__(self):
        self._scroll_cursor = None
        self._scroll_models = []
        self._scroll_exhausted = False

    def _get_headers(self) -> Dict[str, str]:
        config_path = os.path.join(os.path.expanduser("~/.config/civbro"), "config.json")
        try:
            with open(config_path) as f:
                config = json.load(f)
                api_key = config.get("civitai_api_key", "")
                if api_key:
                    return {"Authorization": f"Bearer {api_key}"}
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {}

    def _map_trpc_item(self, item: dict) -> Model:
        ver = item.get("version") or item.get("modelVersions", [{}])[0]
        rank = item.get("rank", {})
        creator = item.get("user") or item.get("creator") or {}
        creator_image = creator.get("image", "")
        profile_picture = creator.get("profilePicture") or {}
        if isinstance(profile_picture, dict) and profile_picture.get("url"):
            creator_image = profile_picture.get("url") or creator_image

        images = []
        for img in item.get("images", []):
            url = img.get("url") or img.get("imageUrl", "")
            if url:
                # tRPC returns bare UUIDs, build full Civitai image URL
                if not url.startswith("http"):
                    img_type = img.get("type", "image")
                    if img_type == "video":
                        url = f"https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{url}/width=450/{url}.mp4"
                    else:
                        url = f"https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{url}/width=450/{url}.jpeg"
                images.append({"url": url})

        return Model(
            id=str(item.get("id", "")),
            name=item.get("name", "Unknown"),
            type=item.get("type", "Checkpoint"),
            stats={
                "downloadCount": rank.get("downloadCountAllTime") or rank.get("downloadCount", 0),
                "rating": 0.0,
                "likes": rank.get("thumbsUpCountAllTime") or rank.get("thumbsUpCount", 0),
                "comments": rank.get("commentCountAllTime") or rank.get("commentCount", 0),
                "buzz": rank.get("tippedAmountCountAllTime") or rank.get("tippedAmountCount", 0),
                "collectionCount": rank.get("collectedCountAllTime") or rank.get("collectedCount", 0),
            },
            images=images if images else [{"url": ""}],
            baseModel=ver.get("baseModel", ""),
            downloadUrl=item.get("downloadUrl") or ver.get("downloadUrl"),
            author=creator.get("username", "Unknown"),
            tags=item.get("tags", []) or [],
            createdAt=item.get("createdAt"),
            publishedAt=ver.get("publishedAt"),
            description=ver.get("name", ""),
            nsfwLevel=item.get("nsfwLevel", 0),
            nsfw=item.get("nsfw", False),
            creatorImage=creator_image,
            availability=ver.get("availability", "Public"),
            cosmetic=item.get("cosmetic"),
            creatorCosmetics=creator.get("cosmetics", []),
        )

    def _map_api_response(self, item: dict) -> Model:
        versions = item.get("modelVersions", [])
        v0 = versions[0] if versions else {}

        images = []
        for v in versions:
            for img in v.get("images", []):
                url = img.get("url") or img.get("imageUrl", "")
                if url:
                    images.append({"url": url})

        creator = item.get("creator") or item.get("user") or {}
        creator_image = creator.get("image", "")
        profile_picture = creator.get("profilePicture") or {}
        if isinstance(profile_picture, dict) and profile_picture.get("url"):
            creator_image = profile_picture.get("url") or creator_image

        return Model(
            id=str(item.get("id", "")),
            name=item.get("name", "Unknown"),
            type=item.get("type", "Checkpoint"),
            stats={
                "downloadCount": item.get("stats", {}).get("downloadCount", 0),
                "rating": item.get("stats", {}).get("rating", 0.0),
                "likes": item.get("stats", {}).get("thumbsUpCount", 0),
                "comments": item.get("stats", {}).get("commentCount", 0),
                "buzz": item.get("stats", {}).get("tippedAmountCount", 0),
                "collectionCount": item.get("stats", {}).get("favoriteCount", 0),
            },
            images=images if images else [{"url": ""}],
            baseModel=v0.get("baseModel", ""),
            downloadUrl=v0.get("downloadUrl"),
            author=creator.get("username", "Unknown"),
            tags=item.get("tags", []) or [],
            createdAt=item.get("createdAt"),
            publishedAt=v0.get("publishedAt"),
            description=v0.get("name", ""),
            nsfwLevel=item.get("nsfwLevel", 0),
            nsfw=item.get("nsfw", False),
            creatorImage=creator_image,
            availability=v0.get("availability", "Public"),
            cosmetic=item.get("cosmetic"),
            creatorCosmetics=creator.get("cosmetics", []),
        )

    def _fetch_trpc(self, filters: FilterSettings, trpc_base: str):
        trpc_params = {"limit": filters.limit, "browsingLevel": 255 if filters.nsfw else 1}
        if filters.cursor:
            trpc_params["cursor"] = filters.cursor
        if filters.nsfw:
            trpc_params["browsingLevel"] = 255
        if filters.query:
            if filters.searchType == "User name":
                trpc_params["username"] = filters.query
            elif filters.searchType == "Tag":
                trpc_params["tag"] = filters.query
            else:
                trpc_params["query"] = filters.query
        if filters.sort:
            trpc_params["sort"] = filters.sort
        if filters.period and filters.period != "All Time":
            trpc_params["period"] = filters.period.replace(" ", "")
        if filters.types:
            t_types = [self.TYPE_MAP.get(t, t) for t in filters.types]
            trpc_params["types"] = t_types
        if filters.baseModels:
            trpc_params["baseModels"] = filters.baseModels
        if filters.checkpointType and filters.checkpointType != "All":
            trpc_params["checkpointType"] = filters.checkpointType
        if filters.fileFormat:
            trpc_params["fileFormats"] = [f for f in filters.fileFormat if f != "All"]

        trpc_input = json.dumps({"json": trpc_params}, separators=(',', ':'))
        trpc_url = f"{trpc_base}/model.getAll?input={urllib.parse.quote(trpc_input)}"
        resp = requests.get(trpc_url, headers=self._get_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {}).get("data", {}).get("json", {})
        items = result.get("items", [])
        return items, result.get("nextCursor")

    def get_all(self, filters: FilterSettings):
        with self._lock:
            # Dynamic base URL for NSFW
            base_url = "https://civitai.red" if filters.nsfw else "https://civitai.com"
            v1_base = f"{base_url}/api/v1"
            trpc_base = f"{base_url}/api/trpc"
            # Rate limit
            now = time.time()
            gap = now - self._last_request_time
            if gap < self._min_request_gap:
                time.sleep(self._min_request_gap - gap)
            self._last_request_time = time.time()

            cache_key = str(vars(filters))
            # Check tRPC cache
            if cache_key in self._trpc_cache:
                models, ts = self._trpc_cache[cache_key]
                if time.time() - ts < self.TRPC_CACHE_TTL:
                    return models, None

            # Try tRPC first
            try:
                items, next_cursor = self._fetch_trpc(filters, trpc_base)
                if items:
                    models = []
                    for item in items:
                        model = self._map_trpc_item(item)
                        self._cache[model.id] = model
                        models.append(model)
                    self._trpc_cache[cache_key] = (models, time.time())
                    return models, next_cursor
            except Exception as e:
                pass  # fall through to v1

            # v1 REST fallback
            try:
                params = {
                    "limit": 42,
                    "sort": filters.sort or "Most Downloaded",
                }
                if filters.query:
                    if filters.searchType == "User name":
                        params["username"] = filters.query
                    elif filters.searchType == "Tag":
                        params["tag"] = filters.query
                    else:
                        params["query"] = filters.query
                if filters.period and filters.period != "All Time":
                    params["period"] = filters.period
                if filters.types:
                    params["types"] = [self.TYPE_MAP.get(t, t) for t in filters.types]
                if filters.baseModels:
                    params["baseModel"] = ",".join(filters.baseModels)
                if filters.nsfw:
                    params["nsfw"] = "true"
                if filters.checkpointType and filters.checkpointType != "All":
                    params["checkpointType"] = filters.checkpointType
                if filters.fileFormat:
                    ff_list = [f for f in filters.fileFormat if f != "All"]
                    if ff_list:
                        params["fileFormat"] = ",".join(ff_list)

                resp = requests.get(f"{v1_base}/models", params=params, headers=self._get_headers(), timeout=15)
                resp.raise_for_status()
                data = resp.json()

                items = data.get("items", [])
                models = []
                for item in items:
                    model = self._map_api_response(item)
                    self._cache[model.id] = model
                    models.append(model)

                self._trpc_cache[cache_key] = (models, time.time())
                return models, None

            except requests.RequestException as e:
                print(f"Civitai API error: {e}")
                return [], None
            except Exception as e:
                print(f"Civitai API error: {e}")
                return [], None

    def get_by_id(self, model_id: str) -> Optional[Model]:
        return self._cache.get(model_id)

    def list(self, filters: FilterSettings):
        return self.get_all(filters)

router = ModelsRouter()
