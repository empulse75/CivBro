from __future__ import annotations

import os
from pathlib import Path

CIVITAI_REST_API = "https://civitai.com/api/v1"
CIVITAI_TRPC_API = "https://civitai.com/api/trpc"
CIVITAI_RED_API = "https://civitai.red/api/v1"
CDN_URL = "https://image.civitai.com"

EXTENSION_DIR = Path(__file__).parent.parent.parent.resolve()
DB_PATH = EXTENSION_DIR / "civbro.db"

# The extension directory as the WebUI sees it, which is what locates the
# models tree. EXTENSION_DIR is resolved, so on the common setup where the repo
# is symlinked into extensions/ it points back at the checkout instead of into
# the WebUI — keep the unresolved path too.
_EXTENSION_DIR_UNRESOLVED = Path(__file__).parent.parent.parent


def _host_paths():
    try:
        from modules import paths_internal
        return paths_internal
    except ImportError:
        try:
            from modules import paths
            return paths
        except ImportError:
            return None


def _resolve_models_root() -> str:
    """Locate the WebUI's models directory.

    Order: explicit override, then the running WebUI's own path config, then the
    extensions/<name>/../../models layout. Hardcoding an absolute path here
    breaks every install but the developer's.
    """
    override = os.environ.get("SD_WEBUI_MODELS_DIR")
    if override:
        return override

    # Authoritative when we are imported inside the WebUI process; it accounts
    # for --models-dir and fork-specific layouts.
    models_path = getattr(_host_paths(), "models_path", None)
    if models_path:
        return str(Path(models_path).resolve())

    for base in (_EXTENSION_DIR_UNRESOLVED, EXTENSION_DIR):
        candidate = base.parent.parent / "models"
        if candidate.is_dir():
            return str(candidate)

    # Last resort: keep the extension importable so the health endpoint can
    # report the problem instead of crashing at import time.
    return str(_EXTENSION_DIR_UNRESOLVED.parent.parent / "models")


MODELS_ROOT = _resolve_models_root()


def get_model_dir(dir_name: str, models_root: str | None = None) -> str:
    """Honor host category directories, including paths not yet created.

    An explicit different root or environment override isolates standalone
    callers. Passing the active MODELS_ROOT retains the host's category mapping.
    """
    root = Path(models_root or MODELS_ROOT).resolve()
    if os.environ.get("SD_WEBUI_MODELS_DIR") or root != Path(MODELS_ROOT).resolve():
        return str(root / dir_name)
    option = {
        "Stable-diffusion": "ckpt_dir", "Lora": "lora_dir",
        "embeddings": "embeddings_dir", "hypernetworks": "hypernetwork_dir",
        "VAE": "vae_dir", "ControlNet": "controlnet_dir",
        "text_encoder": "te_dir",
    }.get(dir_name)
    if option:
        try:
            from modules import shared
        except ImportError:
            shared = None
        # A1111/Forge expose cmd_opts; SD.Next stores resolved category paths in opts.
        for options in (getattr(shared, "cmd_opts", None), getattr(shared, "opts", None)):
            custom = getattr(options, option, None)
            if isinstance(custom, (str, os.PathLike)) and custom:
                return str(Path(custom).resolve())
    if dir_name == "embeddings":
        data_path = getattr(_host_paths(), "data_path", None)
        if data_path:
            return str(Path(data_path).resolve() / "embeddings")
    return str(root / dir_name)


def get_allowed_model_roots(models_root: str | None = None) -> list[Path]:
    """Use the same resolved directories for download jails and local scans."""
    roots = [Path(models_root or MODELS_ROOT).resolve()]
    for category in sorted(set(DIR_MAP.values())):
        resolved = Path(get_model_dir(category, models_root)).resolve()
        # Avoid scanning every category twice when it is already below a root.
        if not any(resolved.is_relative_to(root) for root in roots):
            roots.append(resolved)
    return roots


DEFAULT_CIVITAI_NSFW = "None"
DEFAULT_LIMIT = 20
DEFAULT_QUERY = ""

LARGE_THRESHOLD_KB = 2 * 1024 * 1024
MAX_LARGE_CONCURRENT = 1
MAX_SMALL_CONCURRENT = 4

THROTTLE_DURATION = 8.0

WARMUP_INTERVAL = 45.0

SEARCH_CACHE_TTL = 604800.0
SEARCH_CACHE_MAX = 1024

COSMETIC_CACHE_TTL = 3600.0
COSMETIC_CACHE_MAX = 256
EXTRAS_ID_TTL = 3600.0
# One entry per model ever browsed; the WebUI process is long-lived, so this
# must be bounded or the cache grows for the lifetime of the session.
EXTRAS_ID_CACHE_MAX = 8192
TRPC_EXTRAS_MAX_PAGES = 20

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
    "motionmodule": "AnimateDiff",
    "aestheticgradient": "aesthetic_embeddings",
    "poses": "Poses",
    "wildcards": "wildcards",
    "other": "Other",
    "textencoder": "text_encoder",
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
    "AestheticGradient": "aesthetic_embeddings",
    "Poses": "Poses",
    "Wildcards": "wildcards",
    "Other": "Other",
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
    "aesthetic_embeddings": "AestheticGradient",
    "Poses": "Poses",
    "wildcards": "Wildcards",
    "Other": "Other",
}

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}

EXCLUDED_TAG_IDS = [5161, 5162, 5188, 5249, 130818, 130820, 133182, 130401, 110980]

# Settings keys clients are allowed to write. Anything else is dropped.
ALLOWED_SETTING_KEYS = frozenset({
    "showNsfw",
    "defaultModelTypes",
    "defaultBaseModels",
    "defaultModelType",
    "defaultBaseModel",
    "defaultSort",
    "defaultPeriod",
    "nsfwBlur",
    "civitaiRedApiKey",
    "useCivitaiRed",
    "unlockedBuzzModelIds",
    "eaOnly",
    "updatedOnly",
    "fastSearch",
    "onlyInstalled",
})

# Writable but never readable through the API (write-only secrets).
SENSITIVE_SETTING_KEYS = frozenset({"civitaiRedApiKey"})
