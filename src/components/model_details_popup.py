import gradio as gr
from src.api.routers.details import router

def create_model_popup():
    gr.HTML("""
    <style>
    #model-popup {
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        z-index: 9999 !important;
        background: #2c2e33 !important;
        max-width: 90vw !important;
        max-height: 85vh !important;
        overflow-y: auto !important;
        border-radius: 12px !important;
        padding: 24px !important;
        box-shadow: 0 0 40px rgba(0,0,0,0.8), 0 0 0 2000px rgba(0,0,0,0.6) !important;
        min-width: 600px !important;
    }
    #model-popup-close {
        position: absolute !important;
        top: 12px !important;
        right: 16px !important;
        font-size: 24px !important;
        color: #aaa !important;
        cursor: pointer !important;
        border: none !important;
        background: none !important;
        z-index: 10000 !important;
    }
    #model-popup-close:hover { color: #fff !important; }
    .civbro-lightbox {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        background: rgba(0,0,0,0.95) !important;
        z-index: 10001 !important;
        display: none !important;
        align-items: center !important;
        justify-content: center !important;
        flex-direction: column !important;
    }
    .civbro-lightbox.active { display: flex !important; }
    .civbro-lightbox img {
        max-width: 90vw !important;
        max-height: 80vh !important;
        object-fit: contain !important;
    }
    .civbro-lightbox-close {
        position: absolute !important;
        top: 20px !important;
        right: 30px !important;
        font-size: 32px !important;
        color: #fff !important;
        cursor: pointer !important;
        border: none !important;
        background: none !important;
    }
    .civbro-lightbox-meta {
        color: #aaa !important;
        margin-top: 12px !important;
        font-size: 13px !important;
    }
    </style>
    """)

    with gr.Column(visible=False, elem_id="model-popup") as popup:
        gr.HTML('<button id="model-popup-close" onclick="document.querySelector(\'#model-popup\').classList.add(\'hide\');document.querySelector(\'#model-popup\').style.display=\'none\'">&times;</button>')

        with gr.Row():
            with gr.Column(scale=1):
                image_gallery = gr.Gallery(label="Images", elem_id="popup-gallery")
            with gr.Column(scale=2):
                model_name = gr.Markdown()
                model_stats = gr.Markdown()
                download_btn = gr.Button("Download Model")

        close_btn = gr.Button("Close")

    def load_details(model_id: str):
        if not model_id:
            return [gr.update(visible=False), [], "", "", gr.update()]

        details = router.get_details(model_id)
        if not details:
            return [gr.update(visible=False), [], "", "", gr.update()]

        images = [img.get("url") for img in details.images if img.get("url")]
        s = details.stats
        stats_md = (
            f"**Base Model**: {details.baseModel}\n\n"
            f"**Downloads**: {s.get('downloadCount', 0):,}\n"
            f"**Likes**: {s.get('likes', 0):,}\n"
            f"**Collections**: {s.get('collectionCount', 0):,}\n"
            f"**Comments**: {s.get('comments', 0):,}\n"
            f"**Buzz**: {s.get('buzz', 0):,}\n"
            f"**Rating**: {s.get('rating', 0.0):.1f}\n\n"
            f"**Author**: {details.author}\n"
            f"**NSFW Level**: {details.nsfwLevel}"
        )

        return [
            gr.update(visible=True),
            images,
            f"# {details.name}",
            stats_md,
            gr.update(interactive=True)
        ]

    def close_popup():
        return gr.update(visible=False)

    close_btn.click(fn=close_popup, outputs=popup)

    return popup, load_details, image_gallery, model_name, model_stats, download_btn
