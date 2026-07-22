from __future__ import annotations

from .client import RUST_AVAILABLE


def subdir_for_type(t: str, name: str = "", model_type: str = "") -> str:
    if RUST_AVAILABLE:
        import civbro_core
        return civbro_core.file_subdir(t, name, model_type)
    return _py_subdir_for_type(t, name, model_type)


def optimize_image_url(url: str, width: int = 450, image_type: str = "image") -> str:
    if RUST_AVAILABLE:
        import civbro_core
        return civbro_core.optimize_cdn_url(url, width, image_type)
    return _py_optimize_image_url(url, width, image_type)


# ---- Pure-Python fallbacks (only used when Rust .so is not available) ----
import re
from .config import CDN_URL, DIR_MAP


def _py_subdir_for_type(t: str, name: str = "", model_type: str = "") -> str:
    s = (t or "").lower()
    if "vae" in s:
        return "VAE"
    if "encoder" in s or s == "te":
        return "text_encoder"
    if "lora" in s or "locon" in s or "dora" in s:
        return "Lora"
    if "embed" in s or "textualinversion" in s:
        return "embeddings"
    if "controlnet" in s:
        return "ControlNet"
    if "upscal" in s or "esrgan" in s:
        return "ESRGAN"
    n = (name or "").lower()
    if re.search(r"(^|[_\-.])vae([_\-.]|$)", n):
        return "VAE"
    if re.search(r"text.?encoder|(^|[_\-.])te([_\-.]|$)|(^|[_\-.])txt([_\-.]|$)|t5xxl|clip[_\-]?[lg]", n):
        return "text_encoder"
    mt = (model_type or "").lower()
    return DIR_MAP.get(mt, "Stable-diffusion")


def _py_optimize_image_url(url: str, width: int = 450, image_type: str = "image") -> str:
    if not url or CDN_URL not in url:
        return url
    if image_type == "video":
        vt = f"transcode=true,width={width or 450},optimized=true"
        if "/original=true/" in url:
            return url.replace("/original=true/", f"/{vt}/")
        m = re.search(r"/width=\d+[^/]*/", url)
        if m:
            return url[: m.start()] + f"/{vt}/" + url[m.end() :]
        return url
    url = url.replace("/original=true/", "/")
    if "/width=" not in url:
        return url.replace(CDN_URL, f"{CDN_URL}/width={width},format=webp")
    return url
