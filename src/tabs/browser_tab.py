import gradio as gr
import json
import os
from src.components.sidebar import create_sidebar
from src.components.model_grid import create_model_grid, CSS as GRID_CSS

LOADING_SKELETON = GRID_CSS + '<div class="civbro-loading-skeleton">' + ''.join(['<div class="civbro-skeleton-card"></div>' for _ in range(16)]) + '</div>'
from src.api.routers.models import router
from src.api.routers.local import router as local_router
from src.models.entities import FilterSettings

CONFIG_DIR = os.path.expanduser("~/.config/civbro")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
FILTERS_PATH = os.path.join(CONFIG_DIR, "filters.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

def save_api_key(key):
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            try:
                config = json.load(f)
            except: pass
    config["civitai_api_key"] = key
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def load_api_key():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("civitai_api_key", "")
    except:
        return ""

def save_filters(data):
    try:
        existing = {}
        if os.path.exists(FILTERS_PATH):
            with open(FILTERS_PATH) as f:
                existing = json.load(f)
        existing.update(data)
        with open(FILTERS_PATH, "w") as f:
            json.dump(existing, f, indent=2)
    except:
        pass

def load_filters():
    try:
        with open(FILTERS_PATH) as f:
            return json.load(f)
    except:
        return {}

def validate_key(key):
    if not key:
        return '<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:#555;color:#fff;font-size:12px;font-weight:600;">No Key</span>'
    import requests
    try:
        resp = requests.get("https://civitai.com/api/v1/me", headers={"Authorization": f"Bearer {key}"}, timeout=5)
        if resp.status_code == 200:
            return '<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:#22c55e;color:#fff;font-size:12px;font-weight:600;">Key Valid</span>'
    except:
        pass
    return '<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:#ef4444;color:#fff;font-size:12px;font-weight:600;">Key Invalid</span>'

def save_current_filters(search, search_type, content_type, period, sort_type, base_models, model_status, checkpoint_type, file_format, page, nsfw, hide_installed, api_key, modifiers):
    save_filters({
        "search": search or "",
        "search_type": search_type if isinstance(search_type, str) else "Model name",
        "content_type": content_type or ["Checkpoint"],
        "sort_type": sort_type,
        "period": period if isinstance(period, str) else (period[0] if period else "All Time"),
        "base_models": base_models or [],
        "model_status": model_status or [],
        "checkpoint_type": checkpoint_type if isinstance(checkpoint_type, str) else "All",
        "file_format": file_format or [],
        "nsfw": nsfw,
        "modifiers": modifiers or [],
        "hide_installed": hide_installed,
    })
    return ()

def _get_installed_ids():
    try:
        return {m.model_id for m in local_router.get_local_models() if m.model_id}
    except:
        return set()

def do_search(search, search_type, content_type, period, sort_type, base_models, model_status, checkpoint_type, file_format, page, nsfw, hide_installed, api_key, modifiers):
    if api_key:
        save_api_key(api_key)
    installed_ids = _get_installed_ids()
    types = ["Checkpoint"] if not content_type else content_type
    sort = sort_type or "Most Downloaded"
    p = period if isinstance(period, str) else (period[0] if period else "All Time")
    limit = 42
    current_page = int(page) if page else 1
    stype = search_type if isinstance(search_type, str) else "Model name"

    if current_page <= 1:
        router._scroll_cursor = None
        router._scroll_models = []
        router._scroll_exhausted = False

    if router._scroll_exhausted:
        return create_model_grid(router._scroll_models, installed_ids) if router._scroll_models else ''

    if router._scroll_cursor and current_page > 1:
        c = router._scroll_cursor
    else:
        c = None

    if current_page > 1 and not c:
        if router._scroll_models:
            return create_model_grid(router._scroll_models, installed_ids)
        return ''

    nsfw_bool = nsfw == "NSFW" if isinstance(nsfw, str) else bool(nsfw)

    filters = FilterSettings(
        query=search or "", sort=sort, period=p, searchType=stype,
        types=types, baseModels=base_models or [],
        checkpointType=checkpoint_type if isinstance(checkpoint_type, str) else "All",
        fileFormat=file_format if isinstance(file_format, list) else [],
        nsfw=nsfw_bool, page=1, limit=limit, cursor=c
    )
    try:
        models, next_cursor = router.list(filters)
        if next_cursor:
            router._scroll_cursor = next_cursor
        else:
            router._scroll_cursor = None
            if current_page > 1:
                router._scroll_exhausted = True
        if models:
            router._scroll_models.extend(models)
        if current_page <= 1 and router._scroll_cursor:
            filters2 = FilterSettings(
                query=search or "", sort=sort, period=p, searchType=stype,
                types=types, baseModels=base_models or [],
                checkpointType=checkpoint_type if isinstance(checkpoint_type, str) else "All",
                fileFormat=file_format if isinstance(file_format, list) else [],
                nsfw=nsfw_bool, page=1, limit=limit, cursor=router._scroll_cursor
            )
            models2, cursor2 = router.list(filters2)
            if cursor2:
                router._scroll_cursor = cursor2
            else:
                router._scroll_cursor = None
            if models2:
                router._scroll_models.extend(models2)
        if router._scroll_models:
            return create_model_grid(router._scroll_models, installed_ids)
        return ''
    except Exception as e:
        import traceback
        traceback.print_exc()
        return ''

def clear_all_filters():
    save_current_filters("", "Model name", ["Checkpoint"], "All Time", "Most Downloaded", [], [], "All", [], "1", "SFW", False, "", [])
    return ("", "Model name", "All Time", [], ["Checkpoint"], "All", [], [], "Most Downloaded", "1", "SFW", False, [], "")
    #          search  search_type  period  m_status  content_type  chkpt_type  file_fmt  base_mod  sort_type  page  nsfw  hide_inst  modifiers  api_key

def auto_save_key(key):
    save_api_key(key)
    return key

def create_browser_tab():
    initial_key = load_api_key()
    initial_status = validate_key(initial_key)
    saved_filters = load_filters()

    sf_search = saved_filters.get("search", "") or ""
    sf_search_type = saved_filters.get("search_type", "Model name") or "Model name"
    sf_content_type = saved_filters.get("content_type") or ["Checkpoint"]
    sf_period = saved_filters.get("period", "All Time") or "All Time"
    sf_sort = saved_filters.get("sort_type", "Most Downloaded") or "Most Downloaded"
    sf_base = saved_filters.get("base_models") or []
    sf_status = saved_filters.get("model_status") or []
    sf_chkpt = saved_filters.get("checkpoint_type", "All") or "All"
    sf_file = saved_filters.get("file_format") or []
    sf_page = 1
    sf_nsfw = saved_filters.get("nsfw", "SFW") or "SFW"
    sf_hide = saved_filters.get("hide_installed", False)
    sf_mods = saved_filters.get("modifiers") or []

    # Pre-generate initial grid (show skeleton while loading, replace if API returns)
    try:
        initial_grid = do_search(sf_search, sf_search_type, sf_content_type, sf_period, sf_sort, sf_base, sf_status, sf_chkpt, sf_file, sf_page, sf_nsfw, sf_hide, initial_key, sf_mods)
        if not initial_grid or initial_grid == '':
            initial_grid = LOADING_SKELETON
    except Exception as e:
        initial_grid = LOADING_SKELETON

    # Sidebar + Grid layout - sidebar fixed scroll, grid fills rest
    gr.HTML("""
    <style>
    #civbro-sidebar {
        width: 380px !important;
        min-width: 380px !important;
        max-width: 380px !important;
        background: #2b2d33 !important;
        border: 1px solid #373a40 !important;
        border-radius: 8px !important;
        padding: 16px !important;
        overflow-x: hidden !important;
        overflow-y: auto !important;
        max-height: calc(100vh - 120px) !important;
        display: block !important;
    }
    #civbro-grid-wrapper {
        flex: 1 !important;
        min-width: 0 !important;
    }
    /* Force Row to stay side-by-side */
    .gradio-row:has(#civbro-sidebar) {
        flex-wrap: nowrap !important;
        align-items: flex-start !important;
    }
    .civbro-section-header {
        color: #aaa !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        margin: 16px 0 8px 0 !important;
    }
    #civbro-sidebar .form,
    #civbro-sidebar .wrap {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 6px !important;
        padding: 0 !important;
        margin: 0 0 8px 0 !important;
    }
    #civbro-sidebar .form label,
    #civbro-sidebar .wrap label,
    #civbro-sidebar .gradio-radio label {
        position: relative !important;
        display: inline-flex !important;
        align-items: center !important;
        padding: 6px 14px !important;
        border-radius: 20px !important;
        background: #373a40 !important;
        color: #ccc !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        cursor: pointer !important;
        border: 1px solid transparent !important;
        margin: 0 3px 3px 0 !important;
        justify-content: center !important;
    }
    #civbro-sidebar .form label:has(input:checked),
    #civbro-sidebar .wrap label:has(input:checked),
    #civbro-sidebar .gradio-radio label:has(input:checked) {
        background: #228be6 !important;
        color: #fff !important;
        border-color: #228be6 !important;
    }
    #civbro-sidebar input[type="checkbox"],
    #civbro-sidebar input[type="radio"] {
        opacity: 0 !important;
        position: absolute !important;
        left: 4px !important;
        top: 50% !important;
        margin-top: -7px !important;
        width: 14px !important;
        height: 14px !important;
        cursor: pointer !important;
        z-index: 1 !important;
    }
    .civbro-api-row {
        position: relative !important;
    }
    .civbro-api-row .gradio-html {
        position: absolute !important;
        right: 8px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
    }
    #civbro-main-row {
        flex-wrap: nowrap !important;
        align-items: flex-start !important;
    }
    .civbro-section-divider {
        border-bottom: 1px solid #373a40 !important;
        margin: 20px 0 10px 0 !important;
        padding-bottom: 4px !important;
        position: relative !important;
    }
    .civbro-section-divider span {
        font-size: 12px !important;
        font-weight: 800 !important;
        color: #868e96 !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
    }
    .civbro-section-divider::after {
        content: "" !important;
        position: absolute !important;
        bottom: -1px !important;
        left: 0 !important;
        width: 48px !important;
        height: 2px !important;
        background: #228be6 !important;
        box-shadow: 0 0 6px #228be6 !important;
    }
    #civbro-clear-all-btn {
        width: 100% !important;
        margin-top: 20px !important;
        padding: 12px !important;
        background: #373a40 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        cursor: pointer !important;
    }
    #civbro-clear-all-btn:hover {
        background: #4a4d55 !important;
    }
    </style>
    """)

    with gr.Row(elem_id="civbro-main-row"):
        sidebar_components = create_sidebar(initial_key_status=initial_status, saved=saved_filters)
        grid_html = gr.HTML(label="Model Grid", value=initial_grid, elem_id="civbro-grid-wrapper")
        page_trigger = gr.Textbox(elem_id="civbro-page-trigger", visible=False, value="1")
        load_more_btn = gr.Button("", elem_id="civbro-load-more-btn", visible=False)
        persist_dummy = gr.Textbox(visible=False)

    sidebar_components["api_key"].change(fn=auto_save_key, inputs=sidebar_components["api_key"], outputs=sidebar_components["api_key"])
    sidebar_components["api_key"].change(fn=validate_key, inputs=sidebar_components["api_key"], outputs=sidebar_components["key_status"])

    filter_inputs = [
        sidebar_components["search"],
        sidebar_components["search_type"],
        sidebar_components["content_type"],
        sidebar_components["period"],
        sidebar_components["sort_type"],
        sidebar_components["base_models"],
        sidebar_components["model_status"],
        sidebar_components["checkpoint_type"],
        sidebar_components["file_format"],
        page_trigger,
        sidebar_components["nsfw"],
        sidebar_components["hide_installed"],
        sidebar_components["api_key"],
        sidebar_components["modifiers"],
    ]

    for comp in filter_inputs:
        if comp != sidebar_components["api_key"] and comp != page_trigger:
            comp.change(fn=do_search, inputs=filter_inputs, outputs=grid_html)
            comp.change(fn=save_current_filters, inputs=filter_inputs, outputs=persist_dummy)

    page_trigger.change(fn=do_search, inputs=filter_inputs, outputs=grid_html)
    sidebar_components["search_btn"].click(fn=do_search, inputs=filter_inputs, outputs=grid_html)
    load_more_btn.click(fn=do_search, inputs=filter_inputs, outputs=grid_html)

    clear_outputs = [
        sidebar_components["search"],
        sidebar_components["search_type"],
        sidebar_components["period"],
        sidebar_components["model_status"],
        sidebar_components["content_type"],
        sidebar_components["checkpoint_type"],
        sidebar_components["file_format"],
        sidebar_components["base_models"],
        sidebar_components["sort_type"],
        page_trigger,
        sidebar_components["nsfw"],
        sidebar_components["hide_installed"],
        sidebar_components["modifiers"],
        sidebar_components["api_key"],
    ]
    sidebar_components["clear_all_btn"].click(fn=clear_all_filters, inputs=[], outputs=clear_outputs).then(fn=do_search, inputs=filter_inputs, outputs=grid_html)

    return grid_html, filter_inputs, do_search
