# CivBro — Civitai Model Browser for Stable Diffusion WebUI

**CivBro** is an extension for **Stable Diffusion WebUI** (Gradio / FastAPI / WebUI Forge Classic) that brings the full Civitai browsing, filtering, and model downloading experience directly into your WebUI interface.

---

## 📸 Preview & Screenshots

### Main Model Search Grid
![CivBro Main Search Grid](screenshots/CivbroMain.png)

### Model Info & Required Components / Dependencies
![CivBro Model Info Dependencies](screenshots/CivbroModelinfodeps.png)

### Model Info & Buzz Requirement Handling
![CivBro Buzz Requirement Handling](screenshots/CivbroModelinfo.png)

---

## 🚀 Easy Installation (No Compilation Needed)

CivBro comes pre-compiled and ready to use out of the box. You do **not** need Node.js, Rust, or build tools installed.

### Option 1: Install via WebUI Interface (Recommended)
1. Open your Stable Diffusion WebUI.
2. Go to the **Extensions** tab.
3. Click on the **Install from URL** sub-tab.
4. Paste the repository URL into **URL for extension's git repository**:
   ```text
   https://github.com/empulse75/CivBro
   ```
5. Click **Install**.
6. Go to the **Installed** tab and click **Apply and restart UI** (or restart your WebUI process).

### Option 2: Install via Git Clone
Clone this repository directly into your WebUI extensions folder:
```bash
cd /path/to/sd-webui/extensions
git clone https://github.com/empulse75/CivBro
```
Restart your WebUI.

---

## ✨ Features

- **Native WebUI Tab Integration:** Renders seamlessly as an embedded tab inside Gradio.
- **Civitai Search Parity:** Search checkpoints, LoRAs, VAEs, ControlNets, Text Encoders, embeddings, and upscalers with base-model filtering (SD 1.5, SDXL, Pony, Flux, etc.).
- **Model Card Cosmetics & Decorations:**
  - Creator **cosmetic gradient frames & glow effects**.
  - Creator **avatar decorations** and **trophy badges**.
  - Custom styled **nameplates** and multi-model family badges.
- **Fast & Unblocked:** Uses batched tRPC `model.getById` enrichment for card extras, bypassing rate limits.
- **One-Click Downloading:** Automatically places downloaded files into the correct model folder (`Stable-diffusion/`, `Lora/`, `VAE/`, `embeddings/`, `ControlNet/`, `text_encoder/`).
- **Disk Sidecars:** Generates `.civitai.info` metadata and preview images next to every downloaded model.

---

## 🛠️ Architecture

- **Backend:** FastAPI service mounted under `/civbro/api`.
- **Rust Core:** High-performance PyO3 module (`civbro_core.so`) for file hashing and directory scanning.
- **Frontend:** Pre-built Svelte 5 & TailwindCSS 4 SPA served directly by WebUI.
