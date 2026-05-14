import gradio as gr

def get_base_models():
    return [
        "Anima", "AuraFlow", "Chroma", "CogVideoX",
        "Flux.1 D", "Flux.1 Krea", "Flux.1 Kontext", "Flux.1 S",
        "Flux.2 D", "HiDream",
        "Hunyuan 1", "Hunyuan Video",
        "Illustrious", "Imagen4", "Kolors",
        "LTXV", "Lumina",
        "Mochi", "Nano Banana", "NoobAI",
        "ODOR", "OpenAI", "PixArt E", "PixArt a",
        "Playground v2", "Pony", "Pony V7", "Qwen",
        "SD 1.4", "SD 1.5", "SD 1.5 Hyper", "SD 1.5 LCM",
        "SD 2.0", "SD 2.0 768", "SD 2.1", "SD 2.1 768", "SD 2.1 Unclip",
        "SD 3", "SD 3.5", "SDXL 0.9", "SDXL 1.0",
        "SDXL Hyper", "SDXL Lightning",
        "SVD", "SVD XT", "Stable Cascade", "Wan",
        "Other",
    ]

def get_content_types():
    return [
        "Checkpoint", "Embedding", "Hypernetwork", "Aesthetic Gradient",
        "LoRA", "LyCORIS", "DoRA", "Controlnet", "Upscaler",
        "Motion", "VAE", "Poses", "Wildcards", "Workflows", "Detection", "Other",
    ]

def get_model_statuses():
    return ["Early Access", "On-site Generation", "Made On-site", "Featured"]

def get_checkpoint_types():
    return ["All", "Trained", "Merge"]

def get_file_formats():
    return ["SafeTensor", "PickleTensor", "GGUF", "Diffusers", "Core ML", "ONNX"]

def get_search_types():
    return ["Model name", "User name", "Tag"]

def get_time_periods():
    return ["Day", "Week", "Month", "Year", "All Time"]

DEFAULT_FILTERS = {
    "search": "",
    "search_type": "Model name",
    "period": "All Time",
    "model_status": [],
    "content_type": ["Checkpoint"],
    "checkpoint_type": "All",
    "file_format": [],
    "base_models": [],
    "modifiers": [],
    "sort_type": "Most Downloaded",
    "nsfw": "SFW",
    "hide_installed": False,
}

def create_sidebar(initial_key_status='<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:#555;color:#fff;font-size:12px;font-weight:600;">No Key</span>',
                   saved=None):
    f = dict(DEFAULT_FILTERS)
    if saved:
        for k, v in saved.items():
            if k in f and v is not None:
                f[k] = v

    with gr.Column(elem_id="civbro-sidebar"):
        search = gr.Textbox(label="", placeholder="Search models...", show_label=False, container=False, value=f["search"])
        with gr.Row():
            search_btn = gr.Button("Search", variant="primary", elem_id="civbro-search-btn")

        gr.HTML('<div class="civbro-section-divider"><span>Search type</span></div>')
        search_type = gr.Radio(label='', choices=get_search_types(), value=f["search_type"], elem_id="searchType")

        gr.HTML('<div class="civbro-section-divider"><span>Time period</span></div>')
        period = gr.Radio(label='', choices=get_time_periods(), value=f["period"], elem_id="timePeriod")

        gr.HTML('<div class="civbro-section-divider"><span>Model status</span></div>')
        model_status = gr.CheckboxGroup(label='', choices=get_model_statuses(), value=f["model_status"], elem_id="modelStatus")

        gr.HTML('<div class="civbro-section-divider"><span>Model types</span></div>')
        content_type = gr.CheckboxGroup(label='', choices=get_content_types(), value=f["content_type"], elem_id="contentType")

        gr.HTML('<div class="civbro-section-divider"><span>Checkpoint type</span></div>')
        checkpoint_type = gr.Radio(label='', choices=get_checkpoint_types(), value=f["checkpoint_type"], elem_id="checkpointType")

        gr.HTML('<div class="civbro-section-divider"><span>File format</span></div>')
        file_format = gr.CheckboxGroup(label='', choices=get_file_formats(), value=f["file_format"], elem_id="fileFormat")

        gr.HTML('<div class="civbro-section-divider"><span>Base model</span></div>')
        base_models = gr.CheckboxGroup(label='', choices=get_base_models(), value=f["base_models"], elem_id="baseFilter")

        gr.HTML('<div class="civbro-section-divider"><span>Modifiers</span></div>')
        modifiers = gr.CheckboxGroup(label='', choices=["Hidden"], value=f["modifiers"], elem_id="modifiers")

        gr.HTML('<div class="civbro-section-divider"><span>Sort</span></div>')
        sort_type = gr.Radio(label='', choices=[
            "Most Downloaded", "Highest Rated", "Newest", "Oldest",
            "Most Liked", "Most Buzz", "Most Discussed", "Most Collected", "Most Images",
        ], value=f["sort_type"], elem_id="sortType")

        gr.HTML('<div class="civbro-section-divider"><span>Options</span></div>')
        nsfw = gr.Radio(label='', choices=["SFW", "NSFW"], value=f["nsfw"], elem_id="nsfwToggle")
        hide_installed = gr.Checkbox(label="Hide Installed", value=f["hide_installed"])

        gr.HTML('<div class="civbro-section-divider"><span>API Key</span></div>')
        with gr.Row(elem_classes="civbro-api-row"):
            api_key = gr.Textbox(label="", placeholder="Enter Civitai API key...", show_label=False, container=False, type="password")
            key_status = gr.HTML(value=initial_key_status, visible=True)

        clear_all_btn = gr.Button("Clear all filters", variant="secondary", elem_id="civbro-clear-all-btn")

    return {
        "search": search, "search_btn": search_btn,
        "search_type": search_type,
        "period": period,
        "model_status": model_status,
        "content_type": content_type,
        "checkpoint_type": checkpoint_type,
        "file_format": file_format,
        "base_models": base_models,
        "modifiers": modifiers,
        "sort_type": sort_type,
        "nsfw": nsfw, "hide_installed": hide_installed,
        "api_key": api_key, "key_status": key_status,
        "clear_all_btn": clear_all_btn,
    }
