import os
import json
import struct
from typing import List
from src.models.entities import LocalModel

WEBUI_BASE = os.environ.get("WEBUI_DIR", "/home/gonzo/webui/sd-webui-forge-classic")
MODEL_DIRS = {
    "Stable-diffusion": "Checkpoint",
    "Lora": "Lora",
    "VAE": "VAE",
    "embeddings": "Embedding",
}
MODEL_EXTENSIONS = ('.safetensors', '.ckpt', '.pt')

def _read_safetensors_meta(filepath):
    try:
        with open(filepath, 'rb') as f:
            header_len = struct.unpack('<Q', f.read(8))[0]
            header = json.loads(f.read(min(header_len, 1024 * 1024)))
        return header.get('__metadata__', {})
    except Exception:
        return {}

def _extract_hash(meta):
    return (
        meta.get('ss_new_sd_model_hash') or
        meta.get('ss_model_hash') or
        meta.get('sshs_model_hash') or
        None
    )

class Scanner:
    def scan_models(self) -> List[LocalModel]:
        results = []
        for subdir, model_type in MODEL_DIRS.items():
            path = os.path.join(WEBUI_BASE, "models", subdir)
            if not os.path.isdir(path):
                continue
            try:
                for entry in os.scandir(path):
                    if entry.is_file() and entry.name.endswith(MODEL_EXTENSIONS):
                        size_mb = round(entry.stat().st_size / (1024 * 1024), 1)
                        base_no_ext = os.path.splitext(entry.path)[0]

                        preview_path = None
                        for ext in ('.preview.png', '.preview.jpg', '.preview.jpeg', '.preview.webp', '.png'):
                            candidate = base_no_ext + ext
                            if os.path.exists(candidate):
                                preview_path = candidate
                                break

                        model_id = None
                        version_id = None
                        json_path = base_no_ext + '.json'
                        if os.path.exists(json_path):
                            try:
                                with open(json_path) as f:
                                    data = json.load(f)
                                if isinstance(data, dict):
                                    model_id = str(data.get('id', '')) or None
                                    version_id = str(data.get('versionId', '')) or None
                            except (json.JSONDecodeError, IOError):
                                pass

                        metadata_hash = None
                        if entry.name.endswith('.safetensors'):
                            meta = _read_safetensors_meta(entry.path)
                            metadata_hash = _extract_hash(meta)

                        results.append(LocalModel(
                            filename=entry.name,
                            path=entry.path,
                            type=model_type,
                            size_mb=size_mb,
                            hash=metadata_hash,
                            preview_path=preview_path,
                            model_id=model_id,
                            version_id=version_id,
                        ))
            except PermissionError:
                continue
        return results

scanner = Scanner()
