# CivBro Extension

A Stable Diffusion WebUI extension providing a complete 1-to-1 clone of the Civitai.com browsing experience directly within your local WebUI.

## Features

- **Visual Parity**: 100% matched CSS and visual layout to Civitai.com's model grid and popups.
- **Model Browser**: Browse, search, and filter models using tRPC for instant hydration.
- **Download Integration**: Single-click downloads directly to your WebUI directories.
- **Local Management**: View and manage your currently installed models.
- **Standalone**: No manual dependency installations required.

## Installation

The extension pulls its own dependencies upon first launch of the WebUI.

1. Clone into `extensions/CivBro`
2. Restart the WebUI.

## Development & Testing

- **Backend**: Python (tRPC)
- **Frontend**: Gradio Blocks with custom HTML/CSS
- **Testing**: Playwright visual regression tests

```bash
# Run tests
npm test
```