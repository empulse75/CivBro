import gradio as gr
import os
import json
import re
import struct
import subprocess
import threading
import time
import urllib.parse
import requests
from html import escape

LOCAL_PLACEHOLDER = 'data:image/svg+xml,' + 'PHN2ZyB3aWR0aD0iNDAwIiBoZWlnaHQ9IjYwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMjUyNjJiIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlmIiBmb250LXNpemU9IjE0IiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+TG9jYWwgTW9kZWw8L3RleHQ+PC9zdmc+'

ICON_DELETE = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>'
ICON_FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
ICON_CIVITAI = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
ICON_COPY = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
ICON_DOWNLOAD = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'

from src.api.routers.local import router as local_router
from src.api.routers.downloads import router as downloads_router

VERSION_RX = re.compile(r'\b[vV]\d+[\d.]*\b|\b\d+\.\d+\.?\d*\b|\bXL\b', re.IGNORECASE)
PAREN_RX = re.compile(r'\([^)]*\)')
BRACKET_RX = re.compile(r'\[[^\]]*\]')

_fetch_lock = threading.Lock()
_fetch_running = False
_fetch_done = 0
_fetch_total = 0
_fetch_current = ""

def _get_headers():
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

def _trpc_search(query):
    try:
        trpc_params = {"limit": 10, "browsingLevel": 255}
        trpc_params["query"] = query
        trpc_input = json.dumps({"json": trpc_params}, separators=(',', ':'))
        trpc_url = f"https://civitai.com/api/trpc/model.getAll?input={urllib.parse.quote(trpc_input)}"
        resp = requests.get(trpc_url, headers=_get_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("data", {}).get("json", {}).get("items", [])
    except Exception:
        return []

def _lookup_by_hash(sha256_hash):
    try:
        if not sha256_hash or len(sha256_hash) < 40:
            return None
        resp = requests.get(
            f"https://civitai.com/api/v1/model-versions/by-hash/{sha256_hash}",
            headers=_get_headers(),
            timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        model_id = data.get("modelId")
        if not model_id:
            return None
        resp2 = requests.get(
            f"https://civitai.com/api/v1/models/{model_id}",
            headers=_get_headers(),
            timeout=10
        )
        if resp2.status_code == 200:
            return resp2.json()
        return None
    except Exception:
        return None

def _fetch_full_model(model_id):
    try:
        resp = requests.get(
            f"https://civitai.com/api/v1/models/{model_id}",
            headers=_get_headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def _find_model(local_model):
    item = None
    if local_model.hash:
        item = _lookup_by_hash(local_model.hash)

    if not item:
        name = os.path.splitext(local_model.filename)[0]
        queries = _make_queries(name)
        best = None
        best_score = 0
        seen = set()
        for query in queries:
            if not query or query in seen:
                continue
            seen.add(query)
            for candidate in _trpc_search(query):
                score = _score_match(candidate.get("name", ""), name)
                if score > best_score:
                    best_score = score
                    best = candidate
            if best_score >= 80:
                break
        if best_score >= 25:
            item = best

    if not item:
        return None

    mid = str(item.get("id", ""))
    if not mid:
        return None
    return _fetch_full_model(mid)

def _make_queries(name):
    queries = [name]
    stripped = BRACKET_RX.sub('', PAREN_RX.sub('', name))
    stripped = VERSION_RX.sub('', stripped)
    stripped = re.sub(r'\s+', ' ', stripped).strip()
    if stripped and stripped != name and len(stripped) >= 3:
        queries.append(stripped)
    words = [w for w in name.split() if len(w) > 2 and not VERSION_RX.fullmatch(w)]
    if len(words) >= 2:
        queries.append(' '.join(words[:5]))
    return list(dict.fromkeys(queries))

def _score_match(item_name, local_name):
    il = item_name.lower()
    ll = local_name.lower()
    if il == ll:
        return 1000
    lw = set(ll.split())
    iw = set(il.split())
    overlap = lw & iw
    if not overlap:
        return 0
    score = len(overlap) * 20
    score += len(overlap) / max(len(lw), 1) * 30
    for w in overlap:
        if w in il:
            score += 2
    return int(score)

def _get_accessible_version(item):
    versions = item.get("modelVersions", [])
    accessible = []
    for v in versions:
        if v.get("availability") == "EarlyAccess":
            continue
        if v.get("requiresBuzz"):
            continue
        accessible.append(v)
    if not accessible:
        accessible = versions
    accessible.sort(key=lambda v: v.get("createdAt", ""), reverse=True)
    return accessible[0] if accessible else None

def _download_preview(version, dest_model_path):
    for img in version.get("images", []):
        if img.get("type") == "image" or not img.get("type"):
            url = img.get("url", "")
            if not url:
                continue
            if not url.startswith("http"):
                url = f"https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{url}/width=450/{url}.jpeg"
            try:
                resp = requests.get(url, timeout=30, headers=_get_headers())
                resp.raise_for_status()
                preview_path = os.path.splitext(dest_model_path)[0] + ".preview.png"
                with open(preview_path, 'wb') as f:
                    f.write(resp.content)
                return True
            except Exception:
                continue
    return False

def _save_model_json(item, version, dest_model_path):
    try:
        json_path = os.path.splitext(dest_model_path)[0] + ".json"
        info = {
            "id": str(item.get("id", "")),
            "name": item.get("name", ""),
            "type": item.get("type", ""),
            "baseModel": version.get("baseModel", ""),
            "author": (item.get("creator") or {}).get("username", ""),
            "downloadUrl": version.get("downloadUrl", ""),
            "versionId": str(version.get("id", "")),
        }
        with open(json_path, 'w') as f:
            json.dump(info, f, indent=2)
    except Exception:
        pass

def _fetch_previews():
    global _fetch_running, _fetch_done, _fetch_total, _fetch_current
    try:
        models = local_router.get_local_models()
        missing = [m for m in models if not m.preview_path]

        with _fetch_lock:
            _fetch_total = len(missing)
            _fetch_done = 0

        for m in missing:
            with _fetch_lock:
                _fetch_current = os.path.splitext(m.filename)[0]

            item = _find_model(m)
            if item:
                version = _get_accessible_version(item)
                if version:
                    _download_preview(version, m.path)
                    _save_model_json(item, version, m.path)
                time.sleep(0.6)

            with _fetch_lock:
                _fetch_done += 1
    except Exception:
        pass
    finally:
        with _fetch_lock:
            _fetch_running = False
            _fetch_current = ""

def _start_fetch():
    global _fetch_running, _fetch_done, _fetch_total, _fetch_current
    with _fetch_lock:
        if _fetch_running:
            return
        _fetch_running = True
        _fetch_done = 0
        _fetch_total = 0
        _fetch_current = ""
    threading.Thread(target=_fetch_previews, daemon=True).start()

CSS = """
<style id="civbro-local-styles">
.civbro-local-grid {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 14px !important;
    padding: 14px !important;
}
.civbro-local-card {
    position: relative !important;
    width: 280px !important;
    border-radius: 4px !important;
    overflow: hidden !important;
    border: 4px solid transparent !important;
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #373a40, #2a2b30) border-box !important;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
    transition: box-shadow 0.4s cubic-bezier(0.175,0.885,0.32,1.275), transform 0.4s cubic-bezier(0.175,0.885,0.32,1.275) !important;
}
.civbro-local-card::before {
    content: "" !important;
    display: block !important;
    padding-bottom: 130% !important;
}
.civbro-local-card[data-base-model*="Illustrious"] {
    background: linear-gradient(#1a1b1e, #1a1b1e) padding-box, linear-gradient(135deg, #a855f7, #7c3aed) border-box !important;
}
.civbro-local-card[data-base-model*="Pony"] {
    background: linear-gradient(#1a1b1e, #1a1b1e) padding-box, linear-gradient(135deg, #ff69b4, #ec4899, #ff69b4) border-box !important;
}
.civbro-local-card[data-base-model*="Flux"] {
    background: linear-gradient(#1a1b1e, #1a1b1e) padding-box, linear-gradient(135deg, #f97316, #ea580c) border-box !important;
}
.civbro-local-card[data-base-model*="SD 1.5"] {
    background: linear-gradient(#1a1b1e, #1a1b1e) padding-box, linear-gradient(135deg, #3b82f6, #2563eb) border-box !important;
}
.civbro-local-card[data-base-model*="SDXL"] {
    background: linear-gradient(#1a1b1e, #1a1b1e) padding-box, linear-gradient(135deg, #22c55e, #16a34a) border-box !important;
}
.civbro-local-card:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 32px rgba(34,139,230,0.35) !important;
    z-index: 50 !important;
    transform: translateY(-4px) !important;
}
.civbro-local-card[data-base-model*="Illustrious"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(168,85,247,0.5) !important;
}
.civbro-local-card[data-base-model*="Pony"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(255,105,180,0.5) !important;
}
.civbro-local-card[data-base-model*="Flux"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(249,115,22,0.5) !important;
}
.civbro-local-card[data-base-model*="SD 1.5"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(59,130,246,0.5) !important;
}
.civbro-local-card[data-base-model*="SDXL"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(34,197,94,0.5) !important;
}
.civbro-local-card:hover .civbro-local-card-media {
    transform: scale(1.08) !important;
}
.civbro-local-card-media {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    transition: transform 0.5s cubic-bezier(0.165,0.84,0.44,1) !important;
}
.civbro-local-card-overlay {
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-end !important;
    z-index: 10 !important;
    padding: 12px !important;
    pointer-events: none !important;
}
.civbro-local-card-info {
    display: flex !important;
    flex-direction: column !important;
    gap: 5px !important;
    pointer-events: auto !important;
}
.civbro-local-card-name {
    color: #fff !important;
    font-size: 1.2em !important;
    font-weight: 800 !important;
    line-height: 1.2 !important;
    text-shadow: 0 1px 3px rgba(0,0,0,1), 0 0 4px rgba(0,0,0,0.8) !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
}
.civbro-local-card-meta {
    color: #aaa !important;
    font-size: 11px !important;
    display: flex !important;
    gap: 8px !important;
    align-items: center !important;
}
.civbro-local-card-size {
    color: #888 !important;
}
.civbro-local-progress-wrap {
    margin-top: 2px !important;
}
.civbro-local-progress {
    height: 4px !important;
    border-radius: 2px !important;
    background: rgba(55,58,64,0.6) !important;
    overflow: hidden !important;
    margin-bottom: 3px !important;
}
.civbro-local-progress-bar {
    height: 100% !important;
    background: #228be6 !important;
    border-radius: 2px !important;
    transition: width 0.3s ease !important;
}
.civbro-local-progress-bar.active {
    animation: civbro-progress-pulse 2s ease-in-out infinite !important;
}
@keyframes civbro-progress-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}
.civbro-local-status {
    font-size: 10px !important;
    color: #228be6 !important;
}
.civbro-local-actions {
    position: absolute !important;
    top: 8px !important;
    right: 8px !important;
    display: flex !important;
    flex-direction: row !important;
    gap: 4px !important;
    z-index: 20 !important;
}
.civbro-local-actions-left {
    position: absolute !important;
    top: 8px !important;
    left: 8px !important;
    display: flex !important;
    flex-direction: row !important;
    gap: 4px !important;
    z-index: 20 !important;
}
.civbro-local-action-btn {
    background: rgba(0,0,0,0.4) !important;
    border: none !important;
    border-radius: 6px !important;
    width: 32px !important;
    height: 32px !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: background 0.2s ease !important;
}
.civbro-local-action-btn:hover {
    background: rgba(34,139,230,0.5) !important;
}
.civbro-local-action-btn.delete:hover {
    background: rgba(239,68,68,0.6) !important;
}
.civbro-local-action-btn.copy:active {
    background: rgba(34,197,94,0.5) !important;
}
.civbro-local-empty {
    padding: 40px !important;
    color: #aaa !important;
    text-align: center !important;
    font-size: 15px !important;
    width: 100% !important;
}
.civbro-local-fetch-status {
    color: #228be6 !important;
    font-size: 12px !important;
    margin-top: 6px !important;
    text-align: center !important;
}
</style>
"""

def create_local_tab():
    with gr.Column():
        gr.HTML(CSS)

        local_grid = gr.HTML(value="Loading...")
        local_delete_trigger = gr.Textbox(elem_id="civbro_local_delete", visible=False)
        local_action_trigger = gr.Textbox(elem_id="civbro_local_action", visible=False)
        local_refresh_trigger = gr.Textbox(elem_id="civbro_local_refresh", visible=False)

        def handle_delete(path):
            if path:
                local_router.delete_model(path)
            return scan()

        def handle_action(data_str):
            if not data_str:
                return scan()
            try:
                data = json.loads(data_str)
                action = data.get('action', '')
                path = data.get('path', '')
                if action == 'open_folder' and path:
                    folder = os.path.dirname(path) if os.path.isfile(path) else path
                    if os.path.isdir(folder):
                        try:
                            subprocess.Popen(['xdg-open', folder])
                        except Exception:
                            pass
            except (json.JSONDecodeError, ValueError):
                pass
            return scan()

        local_delete_trigger.change(fn=handle_delete, inputs=local_delete_trigger, outputs=local_grid)
        local_delete_trigger.input(fn=handle_delete, inputs=local_delete_trigger, outputs=local_grid)
        local_action_trigger.change(fn=handle_action, inputs=local_action_trigger, outputs=local_grid)
        local_action_trigger.input(fn=handle_action, inputs=local_action_trigger, outputs=local_grid)
        local_refresh_trigger.change(fn=lambda x: scan(), inputs=local_refresh_trigger, outputs=local_grid)
        local_refresh_trigger.input(fn=lambda x: scan(), inputs=local_refresh_trigger, outputs=local_grid)

        def render_local_card(filename, full_path, file_type, size_mb, preview_path=None, model_id=None, base_model="", progress=None, status=None):
            name = os.path.splitext(filename)[0]

            if preview_path and os.path.exists(preview_path):
                quoted_path = urllib.parse.quote(preview_path, safe='')
                img_src = f"/file={quoted_path}"
            else:
                img_src = LOCAL_PLACEHOLDER

            progress_html = ""
            if progress is not None:
                progress_html = f"""
                <div class="civbro-local-progress-wrap">
                    <div class="civbro-local-progress"><div class="civbro-local-progress-bar active" style="width:{min(100, max(0, progress))}%"></div></div>
                </div>"""

            status_html = ""
            if status:
                status_html = f'<div class="civbro-local-status">{escape(status)}</div>'

            left_buttons = ""
            if model_id:
                left_buttons += f'''<button class="civbro-local-action-btn" onclick="event.stopPropagation();window.open('https://civitai.com/models/{model_id}','_blank')" title="View on CivitAI">{ICON_CIVITAI}</button>'''

            escaped_path = escape(full_path).replace("'", "\\'")
            copy_js = f"event.stopPropagation();navigator.clipboard.writeText('{escaped_path}').then(function(){{var b=event.target.closest('.civbro-local-action-btn');b.style.background='rgba(34,197,94,0.4)';b.style.borderColor='#22c55e';setTimeout(function(){{b.style.background='';b.style.borderColor=''}},800)}})"
            open_js = f"event.stopPropagation();var e=document.querySelector('#civbro_local_action textarea');if(e){{e.value=JSON.stringify({{action:'open_folder','path':'{escaped_path}'}});e.dispatchEvent(new Event('input',{{bubbles:true}}));setTimeout(function(){{e.dispatchEvent(new Event('change',{{bubbles:true}}))}},50)}}"
            delete_js = f"event.stopPropagation();if(!confirm('Delete {escape(name)}?'))return;var e=document.querySelector('#civbro_local_delete textarea');if(e){{e.value='{escaped_path}';e.dispatchEvent(new Event('input',{{bubbles:true}}));setTimeout(function(){{e.dispatchEvent(new Event('change',{{bubbles:true}}))}},50)}}"

            return f'''<div class="civbro-local-card" data-base-model="{escape(base_model or '')}">
                <img class="civbro-local-card-media" src="{img_src}" alt="{escape(name)}" loading="lazy" onerror="this.src='{LOCAL_PLACEHOLDER}'" />
                <div class="civbro-local-card-overlay">
                    <div class="civbro-local-card-info">
                        <div class="civbro-local-card-name" title="{escape(name)}">{escape(name)}</div>
                        <div class="civbro-local-card-meta">
                            <span>{escape(file_type)}</span>
                            <span class="civbro-local-card-size">{size_mb:.1f} MB</span>
                        </div>
                        {progress_html}
                        {status_html}
                    </div>
                </div>
                <div class="civbro-local-actions-left">
                    {left_buttons}
                </div>
                <div class="civbro-local-actions">
                    <button class="civbro-local-action-btn copy" onclick="{copy_js}" title="Copy Path">{ICON_COPY}</button>
                    <button class="civbro-local-action-btn" onclick="{open_js}" title="Open Folder">{ICON_FOLDER}</button>
                    <button class="civbro-local-action-btn delete" onclick="{delete_js}" title="Delete Model">{ICON_DELETE}</button>
                </div>
            </div>'''

        def scan():
            cards = []

            try:
                tasks = downloads_router.get_status()
            except:
                tasks = []

            models = local_router.get_local_models()
            has_missing = any(not m.preview_path for m in models)
            if has_missing:
                _start_fetch()

            for task in tasks:
                if task.status not in ("downloading", "queued"):
                    continue
                cards.append(render_local_card(
                    filename=(task.model_id or "downloading") + ".safetensors",
                    full_path=task.destination or "",
                    file_type="Downloading",
                    size_mb=0,
                    progress=task.progress,
                    status=task.status,
                ))

            for m in models:
                base_model = ""
                json_path = os.path.splitext(m.path)[0] + ".json"
                if os.path.exists(json_path):
                    try:
                        with open(json_path) as f:
                            jdata = json.load(f)
                        base_model = jdata.get("baseModel", "") or ""
                    except:
                        pass
                cards.append(render_local_card(
                    filename=m.filename,
                    file_type=m.type,
                    size_mb=m.size_mb,
                    full_path=m.path,
                    preview_path=m.preview_path,
                    model_id=m.model_id,
                    base_model=base_model,
                ))

            if not cards:
                html = '<div class="civbro-local-grid"><div class="civbro-local-empty">No local models found.<br>Downloads will appear here.</div></div>'
            else:
                html = f'<div class="civbro-local-grid">{"".join(cards)}</div>'

            with _fetch_lock:
                running = _fetch_running
                done = _fetch_done
                total = _fetch_total
                current = _fetch_current

            if running and total > 0:
                html += f'<div class="civbro-local-fetch-status"><span style="display:inline-flex;align-items:center;gap:6px;">{ICON_DOWNLOAD} Fetching previews: {done}/{total} — {escape(current)}</span></div>'

            return html

        scan_result = scan()
        local_grid.value = scan_result

    return local_grid
