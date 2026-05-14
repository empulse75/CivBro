import gradio as gr
from src.api.routers.downloads import router

def create_queue_tab():
    with gr.Column():
        gr.Markdown("### Active Downloads")
        status_output = gr.JSON(label="Download Status")
        refresh_btn = gr.Button("Refresh Status")

        def update_status():
            tasks = router.get_status()
            return [vars(t) for t in tasks]

        refresh_btn.click(fn=update_status, outputs=status_output)

    return status_output, refresh_btn
