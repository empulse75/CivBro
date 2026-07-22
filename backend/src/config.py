from __future__ import annotations

import os
from pathlib import Path

CIVITAI_REST_API = "https://civitai.com/api/v1"
CIVITAI_TRPC_API = "https://civitai.com/api/trpc"
CIVITAI_RED_API = "https://civitai.red/api/v1"
CDN_URL = "https://image.civitai.com"

MODELS_ROOT = os.environ.get("SD_WEBUI_MODELS_DIR") or "/home/gonzo/webui/sd-webui-forge-classic/models"

EXTENSION_DIR = Path(__file__).parent.parent.resolve()
CACHE_DIR = EXTENSION_DIR / "cache"

DEFAULT_CIVITAI_NSFW = "None"
DEFAULT_LIMIT = 20
DEFAULT_QUERY = ""

LARGE_THRESHOLD_KB = 2 * 1024 * 1024
MAX_LARGE_CONCURRENT = 1
MAX_SMALL_CONCURRENT = 4

THROTTLE_SPEED_MULTIPLIER = 0.20
THROTTLE_DURATION = 8.0

WARMUP_INTERVAL = 45.0

SEARCH_CACHE_TTL = 604800.0
SEARCH_CACHE_MAX = 1024

COSMETIC_CACHE_TTL = 3600.0
EXTRAS_ID_TTL = 3600.0

CIVITAI_IMG_BUCKET = "xG1nkqKTMzGDvpLrqFT7WA"

DIR_MAP: dict[str, str] = {
    "checkpoint": "Stable-diffusion",
    "lora": "Lora",
    "locon": "Lora",
    "textualinversion": "embeddings",
    "hypernetwork": "hypernetworks",
    "vae": "VAE",
    "controlnet": "ControlNet",
    "upscaler": "ESRGAN",
}

FRONTEND_DIR_MAP: dict[str, str] = {
    "Checkpoint": "Stable-diffusion",
    "LORA": "Lora",
    "LoCon": "Lora",
    "DoRA": "Lora",
    "LoRA": "Lora",
    "TextualInversion": "embeddings",
    "Hypernetwork": "hypernetworks",
    "VAE": "VAE",
    "Controlnet": "ControlNet",
    "Upscaler": "ESRGAN",
    "MotionModule": "AnimateDiff",
    "Poses": "Poses",
    "Wildcards": "wildcards",
    "text_encoder": "text_encoder",
}

TYPE_BY_DIR: dict[str, str] = {
    "Stable-diffusion": "Checkpoint",
    "Lora": "LORA",
    "embeddings": "TextualInversion",
    "VAE": "VAE",
    "text_encoder": "TextEncoder",
    "ControlNet": "Controlnet",
    "ESRGAN": "Upscaler",
    "hypernetworks": "Hypernetwork",
    "AnimateDiff": "MotionModule",
}

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}

EXCLUDED_TAG_IDS = [5161, 5162, 5188, 5249, 130818, 130820, 133182, 130401, 110980]
