# CivBro — Civitai Model Browser for Stable Diffusion WebUI

**CivBro** is an extension for **Stable Diffusion WebUI** (Gradio / FastAPI / WebUI Forge Classic) that brings the full Civitai browsing, filtering, and model downloading experience directly into your WebUI interface.

---

## Installation

The frontend is prebuilt: Node.js is not needed on the user's machine.
`install.py` uses the **WebUI's active Python interpreter** to install CivBro's
missing Python dependencies without upgrading its Gradio, FastAPI or PyTorch
framework. Native wheels are selected by OS, CPU architecture and Python ABI,
checked against release SHA-256 checksums, and installed privately in the extension.

### Compatibility and prerequisites

- **Host:** an A1111-compatible extension API (`modules.script_callbacks`),
  Gradio and FastAPI. This includes the integration contract used by AUTOMATIC1111,
  Forge/Forge Neo, reForge and SD.Next; fork-specific versions can still differ.
  ComfyUI and arbitrary standalone WebUIs do not implement this extension API.
- **Python:** GIL-enabled CPython 3.10 or newer. Free-threaded Python and PyPy
  are not supported by the native wheel ABI.
- **Release wheels:** Linux (glibc), Windows and macOS, on x86-64 and ARM64.
  The release workflow runs native smoke checks on each platform before publishing.
  This checks the native core, not every possible WebUI/platform combination.
- **Network:** the installer needs HTTPS access to GitHub releases and the configured
  Python package index when dependencies are missing. Existing verified installations
  do not re-download their native core.
- **Source builds:** if no compatible wheel exists, or the checkout's Rust sources
  differ from the release, the installer builds locally. It installs an isolated
  Maturin build tool and, when absent, bootstraps a minimal user-local Rust toolchain
  from the official checksum-verified installer. System C/C++ compilers and SDKs
  require OS administration and are not silently installed:
  - Debian/Ubuntu: `sudo apt-get install build-essential`
  - Fedora: `sudo dnf install gcc`
  - Arch: `sudo pacman -S base-devel`
  - macOS: `xcode-select --install`
  - Windows: Visual Studio C++ Build Tools with MSVC and the Windows SDK.

A failed dependency or build check stops CivBro installation with an error;
it does not claim readiness or replace the native core with a slower Python fallback.
The host's `--skip-install` option is respected.

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

## Features

- **Native WebUI Tab Integration:** Renders seamlessly as an embedded tab inside Gradio.
- **Civitai Search Parity:** Search checkpoints, LoRAs, VAEs, ControlNets, Text Encoders, embeddings, and upscalers with base-model filtering (SD 1.5, SDXL, Pony, Flux, etc.). Filters change without triggering search — explicit Search button required.
- **Model Card Cosmetics & Decorations:**
  - Creator **cosmetic gradient frames & glow effects** matching Civitai's 8px radius / 6px visual border.
  - Creator **avatar decorations** and **trophy badges**.
  - Custom styled **nameplates** and multi-model family badges with short codes (IL, XL, Pony, F1, etc.).
- **Reactive Browse Filters:** "Early Access", "Updated Last 48h", NSFW, and "Only Installed" filter retained search results immediately, including models enriched asynchronously by tRPC.
- **NSFW Control:** Toggle hides NSFW-flagged models completely from the grid (not just blur).
- **Smart Buzz-Aware Downloads:** Lock icon on unpurchased buzz models (opens civitai.com); tracks purchased models across sessions.
- **Generation-Only Detection:** Popup warns when a model has no downloadable checkpoint files.
- **Fast & Unblocked:** Uses batched tRPC `model.getById` enrichment for card extras, bypassing rate limits.
- **One-Click Downloading:** Automatically places downloaded files into the correct model folder (`Stable-diffusion/`, `Lora/`, `VAE/`, `embeddings/`, `ControlNet/`, `text_encoder/`).
- **Disk Sidecars:** Generates `.civitai.info` metadata and preview images next to every downloaded model.
- **Popup Animations:** Scale+fade entrance, backdrop fade-in, skeleton loading, version-switch transitions.

---

## Architecture

- **Backend:** Modular FastAPI app (17 Python modules) mounted under `/civbro/api`. HTTP I/O only — all CPU-bound work (parsing, hashing, CSS validation, URL rewriting) lives in Rust.
- **Rust Core:** Portable PyO3 `abi3` package — model parsing, Ed25519 signature verification, bundled SQLite FTS5, SHA-256/BLAKE3 hashing and directory scanning. Optimized release builds use thin LTO and runtime CPU feature detection, not machine-specific `target-cpu=native` instructions.
- **Frontend:** Svelte 5 & TailwindCSS 4 SPA with reactive state, 6-state DownloadButton component, shared Svelte actions, and CSS animations.

The backend honors host model directory overrides, including embeddings outside
the main models tree. `SD_WEBUI_MODELS_DIR` provides an explicit isolated root;
`CIVBRO_DB_PATH` overrides the extension-local database. The embedded UI preserves
reverse-proxy subpaths, and its routes reuse the host's Gradio login policy.

## Updates and recovery

Update through the WebUI extension manager and restart the WebUI. The installer
reuses a verified native package when its source fingerprint matches; otherwise it
stages and checks a replacement before activating it. Back up `civbro.db` before
changing versions. To roll back, restore a known-good extension checkout and its
matching database backup, then restart so the installer verifies its native core.

Only extension distribution files are tracked. Local tests, caches, virtual
environments, screenshots, editor settings and machine state are ignored.
`.github/` is retained to build, verify and publish platform wheels with integrity
metadata. Third-party notices accompany both the frontend and native package.

---

## License

CivBro is **source-visible, not open source**. See [LICENSE](LICENSE) for the full terms.

| | |
|---|---|
| **You may** | Install and run CivBro on machines you own or control, for personal or internal use (including internal commercial use); build it locally from this unmodified source; keep backups; read and study the code. |
| **You may not** | Modify, patch, or create derivative works; redistribute, mirror, or republish it in source or compiled form; bundle it into another product; offer it to third parties as a hosted service; publish a modified fork. |

Third-party components (Svelte, TailwindCSS, DOMPurify, the Rust crates, and the
Python packages installed at runtime) remain under their own licences — see
Section 5 of [LICENSE](LICENSE).

Requests for rights beyond this licence — modification, redistribution, or
integration into another project — need prior written permission; open an issue
on this repository to ask.

Copyright (c) 2026 empulse75. All rights reserved.
