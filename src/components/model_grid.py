import gradio as gr
from html import escape
import urllib.parse
import base64

PLACEHOLDER = 'data:image/svg+xml,' + 'PHN2ZyB3aWR0aD0iNDAwIiBoZWlnaHQ9IjYwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMjUyNjJiIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlmIiBmb250LXNpemU9IjE2IiBmaWxsPSIjNTU1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+Tm8gUHJldmlldzwvdGV4dD48L3N2Zz4='

def proxy_url(raw_url):
    encoded = base64.b64encode(raw_url.encode()).decode()
    return f"/civitai/img_proxy?url={urllib.parse.quote(encoded)}"

ICON_DL = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'
ICON_LIKE = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fd7f38" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>'
ICON_COL = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'
ICON_BZ = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
ICON_CM = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>'
ICON_HEART = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>'
ICON_DL_BTN = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'

CSS = """
<style id="civbro-grid-styles">
.civbro-grid {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 14px !important;
    padding: 14px !important;
}
.civbro-card {
    position: relative !important;
    width: 280px !important;
    border-radius: 4px !important;
    overflow: hidden !important;
    border: 4px solid transparent !important;
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #373a40, #2a2b30) border-box !important;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
    cursor: pointer !important;
    transition: transform 0.4s cubic-bezier(0.175,0.885,0.32,1.275) !important;
    font-size: calc(15px) !important;
    content-visibility: auto !important;
    contain-intrinsic-size: 280px 380px !important;
}
.civbro-card:hover {
    will-change: transform !important;
}
.civbro-card[data-base-model*=\"Illustrious\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #a855f7, #7c3aed) border-box !important;
}
.civbro-card[data-base-model*=\"Pony\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #ff69b4, #ec4899, #ff69b4) border-box !important;
}
.civbro-card[data-base-model*=\"Flux\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #f97316, #ea580c) border-box !important;
}
.civbro-card[data-base-model*=\"SD 1.5\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #3b82f6, #2563eb) border-box !important;
}
.civbro-card[data-base-model*=\"SDXL\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #22c55e, #16a34a) border-box !important;
}
.civbro-card[data-base-model*=\"NoobAI\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #14b8a6, #0d9488) border-box !important;
}
.civbro-card[data-base-model*=\"CogVideoX\"],
.civbro-card[data-base-model*=\"Hunyuan\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #8b5cf6, #7c3aed) border-box !important;
}
.civbro-card[data-base-model*=\"Wan\"],
.civbro-card[data-base-model*=\"SVD\"],
.civbro-card[data-base-model*=\"Video\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #ec4899, #db2777) border-box !important;
}
.civbro-card[data-base-model*=\"Cascade\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #06b6d4, #0891b2) border-box !important;
}
.civbro-card[data-base-model*=\"Aura\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #14b8a6, #0f766e) border-box !important;
}
.civbro-card[data-base-model*=\"Other\"] {
    background:
        linear-gradient(#1a1b1e, #1a1b1e) padding-box,
        linear-gradient(135deg, #6b7280, #4b5563) border-box !important;
}
.civbro-card::before {
    content: "" !important;
    display: block !important;
    padding-bottom: 130% !important;
}
.civbro-card:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 32px rgba(34,139,230,0.35) !important;
    z-index: 50 !important;
    transform: translateY(-4px) !important;
}
.civbro-card[data-base-model*=\"Illustrious\"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(168,85,247,0.5) !important;
}
.civbro-card[data-base-model*=\"Pony\"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(255,105,180,0.5) !important;
}
.civbro-card[data-base-model*=\"Flux\"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(249,115,22,0.5) !important;
}
.civbro-card[data-base-model*=\"SD 1.5\"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(59,130,246,0.5) !important;
}
.civbro-card[data-base-model*=\"SDXL\"]:hover {
    box-shadow: 0 12px 28px rgba(0,0,0,0.7), 0 0 40px rgba(34,197,94,0.5) !important;
}
.civbro-card:hover .civbro-card-media {
    transform: scale(1.08) !important;
}
.civbro-card-media {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    transition: transform 0.5s cubic-bezier(0.165,0.84,0.44,1) !important;
    backface-visibility: hidden !important;
}
video.civbro-card-media {
    background: transparent !important;
}
video.civbro-card-media::-webkit-media-controls {
    display: none !important;
}
video.civbro-card-media::-webkit-media-controls-panel {
    display: none !important;
}
video.civbro-card-media::-webkit-media-controls-play-button {
    display: none !important;
}
.civbro-card-overlay {
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
    background: none !important;
    overflow: visible !important;
    clip-path: none !important;
}
.civbro-card-overlay * {
    overflow: visible !important;
}
.civbro-card-info {
    display: flex !important;
    flex-direction: column !important;
    gap: 5px !important;
    pointer-events: auto !important;
}
.civbro-model-name {
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
.civbro-creator-row {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    margin-bottom: 2px !important;
}
.civbro-creator-name {
    color: #fff !important;
    font-size: 1em !important;
    font-weight: 600 !important;
    text-shadow: 0 1px 3px rgba(0,0,0,1), 0 0 4px rgba(0,0,0,0.8) !important;
}
.civbro-avatar-wrapper {
    width: 2.6em !important;
    height: 2.6em !important;
    position: relative !important;
    flex-shrink: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    overflow: visible !important;
    isolation: isolate !important;
}
.civbro-avatar-img {
    width: 2.47em !important;
    height: 2.47em !important;
    border-radius: 50% !important;
    clip-path: circle(50%) !important;
    z-index: 1 !important;
    position: absolute !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    object-fit: cover !important;
    background-color: transparent !important;
}
.civbro-avatar-decoration {
    width: 130% !important;
    height: 130% !important;
    min-width: 130% !important;
    max-width: 130% !important;
    min-height: 130% !important;
    max-height: 130% !important;
    position: absolute !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    z-index: 5 !important;
    pointer-events: none !important;
    mix-blend-mode: screen !important;
    background: transparent !important;
    border-radius: 50% !important;
}
.civbro-badge-wrap {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    border-radius: 4px !important;
    padding: 1px !important;
    line-height: 0 !important;
}
.civbro-avatar-badge {
    height: 2.3em !important;
    width: auto !important;
    vertical-align: middle !important;
    background: none !important;
    background-color: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    outline: none !important;
}
.civbro-pill-base {
    border-radius: 9999px !important;
    padding: 3px 10px !important;
    font-weight: 800 !important;
    display: inline-flex !important;
    align-items: center !important;
    border: none !important;
    white-space: nowrap !important;
    text-shadow: none !important;
}
.civbro-top-left-pills {
    position: absolute !important;
    top: 8px !important;
    left: 8px !important;
    z-index: 20 !important;
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
    max-width: calc(100% - 48px) !important;
}
.civbro-info-pill {
    font-size: 0.765em !important;
    text-transform: uppercase !important;
    height: 2.2em !important;
    background: rgba(0,0,0,0.4) !important;
    color: #fff !important;
}
.civbro-ea-pill {
    font-size: 0.765em !important;
    text-transform: uppercase !important;
    height: 2.2em !important;
    background: rgb(58,205,132) !important;
    color: #fff !important;
}
.civbro-updated-pill {
    font-size: 0.765em !important;
    text-transform: uppercase !important;
    height: 2.2em !important;
    background: rgb(58,205,132) !important;
    color: #fff !important;
}
.civbro-stats-row {
    display: flex !important;
    align-items: center !important;
    margin-top: 5px !important;
    width: 100% !important;
}
.civbro-stats-container {
    display: flex !important;
    gap: 8px !important;
    align-items: center !important;
    width: 100% !important;
    flex-wrap: wrap !important;
}
.civbro-stats-pill {
    background: rgba(30,31,34,0.4) !important;
    border-radius: 9999px !important;
    padding: 2px 10px !important;
    display: inline-flex !important;
    align-items: center !important;
    height: 1.8em !important;
    color: #fff !important;
    font-size: 0.8em !important;
    font-weight: 800 !important;
    border: none !important;
    white-space: nowrap !important;
    gap: 4px !important;
    flex-shrink: 1 !important;
    overflow: hidden !important;
    text-shadow: none !important;
}
.civbro-stats-item {
    display: flex !important;
    align-items: center !important;
    gap: 3px !important;
}
.civbro-stats-item svg {
    width: 1.0em !important;
    height: 1.0em !important;
    fill: none !important;
    stroke: currentColor !important;
    stroke-width: 2.5px !important;
}
.civbro-liked-pill {
    background: rgba(30,31,34,0.4) !important;
    color: #fff !important;
    flex-shrink: 0 !important;
    font-size: 0.85em !important;
    height: 1.4em !important;
    border-radius: 9999px !important;
    padding: 0 0.6em !important;
    display: inline-flex !important;
    align-items: center !important;
    text-shadow: none !important;
}
.civbro-liked-pill svg {
    color: #fd7f38 !important;
    fill: none !important;
    stroke: #fd7f38 !important;
    stroke-width: 2.5px !important;
    width: 1.1em !important;
    height: 1.1em !important;
}
.civbro-card-dl-btn {
    position: absolute !important;
    top: 8px !important;
    right: 8px !important;
    z-index: 20 !important;
    border: none !important;
    border-radius: 6px !important;
    width: 32px !important;
    height: 32px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    background: rgba(0,0,0,0.4) !important;
}
.civbro-card-dl-btn svg {
    filter: drop-shadow(0 1px 3px rgba(0,0,0,0.8)) !important;
}
.civbro-card-dl-btn:hover svg {
    stroke: #228be6 !important;
}
.civbro-content-decoration {
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    z-index: 25 !important;
    pointer-events: none !important;
}
.civbro-content-decoration img {
    width: 100% !important;
    height: 100% !important;
    object-fit: fill !important;
}
.civbro-loading-skeleton {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 14px !important;
    padding: 14px !important;
}
.civbro-skeleton-card {
    width: 280px !important;
    height: 380px !important;
    background: linear-gradient(90deg, #1a1b1e 25%, #2a2b2e 50%, #1a1b1e 75%) !important;
    background-size: 200% 100% !important;
    animation: civbro-shimmer 1.5s ease-in-out infinite !important;
    border-radius: 4px !important;
    border: 1px solid #373a40 !important;
}
@keyframes civbro-shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
.civbro-progress-bar-animated {
    animation: civbro-progress-pulse 2s ease-in-out infinite !important;
}
@keyframes civbro-progress-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}
.civbro-info-pill.civbro-downloading {
    position: relative !important;
    overflow: hidden !important;
    cursor: pointer !important;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.40), inset 0 -1px 2px rgba(255,255,255,0.06) !important;
}
.civbro-dl-canvas {
    position: absolute !important;
    left: 0 !important;
    top: 0 !important;
    width: 100% !important;
    height: 100% !important;
    z-index: 0 !important;
    pointer-events: none !important;
    border-radius: 9999px !important;
}
.civbro-dl-percent {
    position: relative !important;
    z-index: 1 !important;
    font-size: 0.85em !important;
    font-weight: 800 !important;
    color: #4ade80 !important;
    text-shadow: 0 0 6px rgba(34,197,94,0.5) !important;
}
.civbro-info-pill.civbro-downloading:hover {
    background: rgba(239,68,68,0.50) !important;
    color: transparent !important;
    box-shadow: none !important;
}
.civbro-info-pill.civbro-downloading:hover .civbro-dl-canvas {
    display: none !important;
}
.civbro-info-pill.civbro-downloading:hover::after {
    content: "\u2715" !important;
    position: absolute !important;
    left: 50% !important;
    top: 50% !important;
    transform: translate(-50%, -50%) !important;
    color: #fff !important;
    font-size: 1.4em !important;
    font-weight: 900 !important;
    z-index: 2 !important;
}
.civbro-info-pill.civbro-downloading:hover .civbro-dl-percent {
    display: none !important;
}
#civbro-search-btn {
    background: #228be6 !important;
    color: #fff !important;
    border: none !important;
    font-weight: 600 !important;
}
</style>
"""

def fmt(n):
    if not n: return "0"
    if n >= 1000000: return f"{n/1000000:.1f}M"
    if n >= 1000: return f"{n/1000:.0f}K"
    return str(n)

def build_avatar_html(creator_image, author_name, creator_cosmetics=None):
    if not author_name:
        return ''
    safe_name = urllib.parse.quote(author_name)
    fallback = f'https://api.dicebear.com/7.x/initials/svg?seed={safe_name}&backgroundColor=1a1b1e&textColor=ffffff'

    avatar_main = f'<img class="civbro-avatar-img" src="{fallback}" loading="lazy" />'
    if creator_image:
        if not creator_image.startswith('http'):
            cdn = proxy_url(f'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{creator_image}/original=true/avatar.png')
        else:
            cdn = proxy_url(creator_image)
        avatar_main = f'<img class="civbro-avatar-img" src="{cdn}" loading="lazy" onerror="this.onerror=null;this.src=\'{fallback}\'" />'

    deco_html = ''
    if creator_cosmetics:
        for c in creator_cosmetics:
            if isinstance(c, dict):
                cos = c.get('cosmetic') or c
                if isinstance(cos, dict) and cos.get('type') == 'ProfileDecoration':
                    data = cos.get('data') or {}
                    url = data.get('url', '')
                    if url:
                        if not url.startswith('http'):
                            url = proxy_url(f'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{url}/original=true/deco.png')
                        else:
                            url = proxy_url(url)
                        deco_html = f'<img class="civbro-avatar-decoration" src="{url}" loading="lazy" onerror="this.style.opacity=0" />'
                        break

    return f'<div class="civbro-avatar-wrapper">{avatar_main}{deco_html}</div>'

def build_content_deco_html(cosmetic_data):
    if not cosmetic_data:
        return ''
    data = cosmetic_data.get('data') or {}
    if not isinstance(data, dict):
        return ''
    url = data.get('url', '')
    if not url:
        return ''
    if not url.startswith('http'):
        url = proxy_url(f'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{url}/original=true/texture.png')
    else:
        url = proxy_url(url)
    return f'<div class="civbro-content-decoration"><img src="{url}" loading="lazy" onerror="this.style.opacity=0" /></div>'

def get_short_base(b):
    if not b: return ""
    b_lower = b.lower()
    if "sdxl" in b_lower: return "SDXL"
    if "pony" in b_lower: return "Pony"
    if "illustrious" in b_lower: return "Illustrious"
    if "1.5" in b_lower: return "SD 1.5"
    if "2.1" in b_lower: return "SD 2.1"
    if "flux" in b_lower: return "Flux.1"
    if "noob" in b_lower: return "NoobAI"
    return b

def render_card(m, installed_ids=None):
    images = m.get('images', [{}])
    n = m.get('name', 'Unknown')
    s = m.get('stats', {})
    dl = s.get('downloadCount', 0)
    lk = s.get('likes', 0)
    coll = s.get('collectionCount', 0)
    cm = s.get('comments', 0)
    bz = s.get('buzz', 0)
    au = m.get('author', 'Unknown')
    mt = m.get('type', 'Checkpoint')
    bm = m.get('baseModel', '')
    aid = m.get('id', '')
    ea = m.get('availability', '') == 'EarlyAccess'
    ci = m.get('creatorImage', '') or ''
    cosmetic = m.get('cosmetic')
    creator_cosmetics = m.get('creatorCosmetics', []) or []
    created_at = m.get('createdAt', '')
    published_at = m.get('publishedAt', '') or created_at

    preview_img = ''
    preview_video = ''
    for img in images:
        url = img.get('url', '')
        ext = url.rsplit('.', 1)[-1].split('?')[0].lower() if '.' in url else ''
        if ext in ('mp4', 'webm', 'mov'):
            if not preview_video: preview_video = url
        elif ext in ('webp', 'jpg', 'jpeg', 'png', 'gif'):
            if not preview_img: preview_img = url
            break

    if preview_video:
        img_src = preview_img or PLACEHOLDER
        media_html = f'<video class="civbro-card-media" src="{proxy_url(preview_video)}" loop muted autoplay playsinline disablePictureInPicture disableRemotePlayback poster="{proxy_url(img_src) if preview_img else img_src}"></video>'
    elif preview_img:
        media_html = f'<img class="civbro-card-media" src="{proxy_url(preview_img)}" alt="{escape(n)}" loading="lazy" onerror="this.src=\'{PLACEHOLDER}\'" />'
    else:
        media_html = f'<img class="civbro-card-media" src="{PLACEHOLDER}" alt="{n}" />'

    avatar_html = build_avatar_html(ci, au, creator_cosmetics)

    badge_html = ''
    if creator_cosmetics:
        for c in creator_cosmetics:
            if isinstance(c, dict):
                cos = c.get('cosmetic') or c
                if isinstance(cos, dict) and cos.get('type') == 'Badge':
                    data = cos.get('data') or {}
                    url = data.get('url', '')
                    if url:
                        if not url.startswith('http'):
                            url = proxy_url(f'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{url}/original=true/badge.png')
                        else:
                            url = proxy_url(url)
                        badge_html = f'<span class="civbro-badge-wrap"><img class="civbro-avatar-badge" src="{url}" loading="lazy" onerror="this.style.display=\'none\'" /></span>'
                        break

    content_deco_html = build_content_deco_html(cosmetic)
    if not content_deco_html and creator_cosmetics:
        for c in creator_cosmetics:
            if isinstance(c, dict):
                cos = c.get('cosmetic') or c
                if isinstance(cos, dict) and cos.get('type') == 'ContentDecoration':
                    content_deco_html = build_content_deco_html(cos)
                    if content_deco_html:
                        break

    short_bm = get_short_base(bm)
    info_label = f'{escape(short_bm)} | {escape(mt)}' if short_bm else escape(mt)
    tl_pills = f'<span class="civbro-pill-base civbro-info-pill">{info_label}</span>'
    if ea:
        tl_pills += f'<span class="civbro-pill-base civbro-ea-pill">Early Access</span>'
    elif published_at:
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            pub_dt = datetime.strptime(published_at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            delta = (now - pub_dt).total_seconds()
            if delta < 172800:
                if created_at:
                    create_dt = datetime.strptime(created_at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    if (now - create_dt).total_seconds() > 172800:
                        tl_pills += f'<span class="civbro-pill-base civbro-updated-pill">Updated</span>'
                else:
                    tl_pills += f'<span class="civbro-pill-base civbro-updated-pill">Updated</span>'
        except:
            pass

    popup_js = f"var e=document.querySelector('#civbro_popup_trigger textarea');if(e){{e.value='{aid}';e.dispatchEvent(new Event('input',{{bubbles:true}}));setTimeout(function(){{e.dispatchEvent(new Event('change',{{bubbles:true}}))}},50)}}"
    dl_js = f"event.stopPropagation();var e=document.querySelector('#civbro_download_trigger textarea');if(e){{e.value='{aid}';e.dispatchEvent(new Event('change',{{bubbles:true}}))}}"
    is_installed = installed_ids and aid in installed_ids
    dl_btn_html = '' if is_installed else f'<div class="civbro-card-dl-btn" onclick="{dl_js}" title="Download Model">{ICON_DL_BTN}</div>'

    return f'''<div class="civbro-card" data-base-model="{bm}" data-model-id="{aid}" onclick="{popup_js}">
      {content_deco_html}
      {dl_btn_html}
      <div class="civbro-top-left-pills">{tl_pills}</div>
      {media_html}
      <div class="civbro-card-overlay">
        <div class="civbro-card-info">
          <div class="civbro-creator-row">
            {avatar_html}
            <span class="civbro-creator-name">{escape(au)}</span>
            {badge_html}
          </div>
          <div class="civbro-model-name" title="{escape(n)}">{escape(n)}</div>
          <div class="civbro-stats-row">
            <div class="civbro-stats-container">
              <div class="civbro-stats-pill">
                <div class="civbro-stats-item">{ICON_DL} {fmt(dl)}</div>
                <div class="civbro-stats-item">{ICON_COL} {fmt(coll)}</div>
                <div class="civbro-stats-item">{ICON_CM} {fmt(cm)}</div>
                <div class="civbro-stats-item">{ICON_BZ} {fmt(bz)}</div>
              </div>
              <div class="civbro-liked-pill">{ICON_LIKE} {fmt(lk)}</div>
            </div>
          </div>
        </div>
      </div>
    </div>'''

def create_model_grid(models, installed_ids=None):
    return CSS + f'<div class="civbro-grid">{"".join(render_card(vars(m), installed_ids) for m in models)}</div>'
