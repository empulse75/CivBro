import httpx
import base64
import sys
from fastapi import Response
from modules import script_callbacks

_client = httpx.AsyncClient(timeout=20.0, follow_redirects=True, verify=False)

async def civitai_image_proxy(url: str):
    if not url:
        return Response(status_code=400)
    try:
        decoded_url = base64.b64decode(url).decode()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://civitai.com/",
        }
        response = await _client.get(decoded_url, headers=headers)
        if response.status_code != 200:
            return Response(status_code=response.status_code)
        content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400",
            },
        )
    except Exception as e:
        print(f"CivBro Proxy error: {e}", file=sys.stderr, flush=True)
        return Response(status_code=500)


def on_app_started(_block, app):
    app.add_api_route("/civitai/img_proxy", civitai_image_proxy, methods=["GET"])

    from src.api.routers.downloads import router as downloads_router

    async def civitai_download_status():
        tasks = downloads_router.get_status()
        return [
            {"model_id": t.model_id, "status": t.status, "progress": t.progress, "queue_position": t.queue_position, "error": t.error_message}
            for t in tasks
        ]

    app.add_api_route("/civitai/download_status", civitai_download_status, methods=["GET"])

    async def civitai_download_cancel(model_id: str):
        downloads_router.cancel_by_model(model_id)
        return {"status": "ok"}

    app.add_api_route("/civitai/download_cancel/{model_id}", civitai_download_cancel, methods=["POST"])


script_callbacks.on_app_started(on_app_started)
