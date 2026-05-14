import gradio as gr
from src.tabs.browser_tab import create_browser_tab
from src.tabs.local_tab import create_local_tab
from src.components.model_details_popup import create_model_popup
from src.api.routers.downloads import router as downloads_router

def create_ui():
    with gr.Blocks(analytics_enabled=False) as interface:
        popup_trigger = gr.Textbox(elem_id="civbro_popup_trigger", visible=False)
        download_trigger = gr.Textbox(elem_id="civbro_download_trigger", visible=False)

        popup, load_details, image_gallery, model_name, model_stats, download_btn = create_model_popup()

        popup_trigger.change(fn=load_details, inputs=popup_trigger, outputs=[popup, image_gallery, model_name, model_stats, download_btn])
        popup_trigger.input(fn=load_details, inputs=popup_trigger, outputs=[popup, image_gallery, model_name, model_stats, download_btn])

        def trigger_download(model_id):
            import sys
            if not model_id:
                return ""
            existing = downloads_router.get_status()
            for t in existing:
                if t.model_id == model_id and t.status in ('queued', 'downloading'):
                    print(f"CivBro: Download already active for model {model_id}", file=sys.stderr, flush=True)
                    return ""
            print(f"CivBro: Download triggered for model {model_id}", file=sys.stderr, flush=True)
            try:
                task = downloads_router.queue(model_id, "latest")
                print(f"CivBro: Download task created: {task.id} status={task.status}", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"CivBro: Download error: {e}", file=sys.stderr, flush=True)
            return ""

        download_trigger.change(fn=trigger_download, inputs=download_trigger, outputs=download_trigger)
        download_trigger.input(fn=trigger_download, inputs=download_trigger, outputs=download_trigger)

        with gr.Tabs():
            with gr.Tab("Browser"):
                create_browser_tab()

            with gr.Tab("Local Management"):
                create_local_tab()

    return interface

if __name__ == "__main__":
    demo = create_ui()
    demo.launch()
