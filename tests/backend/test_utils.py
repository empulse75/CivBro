"""Tests for utils.py: subdir_for_type, optimize_image_url."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _mock_rust_core(monkeypatch):
    """Set RUST_AVAILABLE=True and inject a mock civbro_core module."""
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", True)
    mock_core = MagicMock()
    monkeypatch.setitem(sys.modules, "civbro_core", mock_core)
    return mock_core


def test_subdir_for_type_returns_correct_dir(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)

    # Map each expected call to its return value
    def _file_subdir(file_type, name, model_type):
        mapping = {
            ("VAE", "", ""): "VAE",
            ("Text Encoder", "", ""): "text_encoder",
            ("te", "", ""): "text_encoder",
            ("LORA", "", ""): "Lora",
            ("LoCon", "", ""): "Lora",
            ("DoRA", "", ""): "Lora",
            ("TextualInversion", "", ""): "embeddings",
            ("Embedding", "", ""): "embeddings",
            ("ControlNet", "", ""): "ControlNet",
            ("Upscaler", "", ""): "ESRGAN",
            ("ESRGAN", "", ""): "ESRGAN",
            ("Model", "my_vae_fp16.safetensors", ""): "VAE",
            ("Model", "some_vae.safetensors", ""): "VAE",
            ("Model", "t5xxl_encoder.safetensors", ""): "text_encoder",
            ("Model", "clip_l.safetensors", ""): "text_encoder",
            ("Model", "plain.safetensors", "Checkpoint"): "Stable-diffusion",
            ("Model", "plain.safetensors", "lora"): "Lora",
            ("", "", "vae"): "VAE",
        }
        return mapping.get((file_type, name, model_type), "")

    mock_core.file_subdir.side_effect = _file_subdir

    from civbro_backend.rust_facade import subdir_for_type

    assert subdir_for_type("VAE", "", "") == "VAE"
    assert subdir_for_type("Text Encoder", "", "") == "text_encoder"
    assert subdir_for_type("te", "", "") == "text_encoder"
    assert subdir_for_type("LORA", "", "") == "Lora"
    assert subdir_for_type("LoCon", "", "") == "Lora"
    assert subdir_for_type("DoRA", "", "") == "Lora"
    assert subdir_for_type("TextualInversion", "", "") == "embeddings"
    assert subdir_for_type("Embedding", "", "") == "embeddings"
    assert subdir_for_type("ControlNet", "", "") == "ControlNet"
    assert subdir_for_type("Upscaler", "", "") == "ESRGAN"
    assert subdir_for_type("ESRGAN", "", "") == "ESRGAN"
    # From filename
    assert subdir_for_type("Model", "my_vae_fp16.safetensors", "") == "VAE"
    assert subdir_for_type("Model", "some_vae.safetensors", "") == "VAE"
    assert subdir_for_type("Model", "t5xxl_encoder.safetensors", "") == "text_encoder"
    assert subdir_for_type("Model", "clip_l.safetensors", "") == "text_encoder"
    # From model_type fallback
    assert subdir_for_type("Model", "plain.safetensors", "Checkpoint") == "Stable-diffusion"
    assert subdir_for_type("Model", "plain.safetensors", "lora") == "Lora"
    assert subdir_for_type("", "", "vae") == "VAE"


def test_optimize_image_url_passthrough_without_rust(monkeypatch):
    """Without Rust core, optimize_image_url returns the URL unchanged (passthrough)."""
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", False)

    from civbro_backend.rust_facade import optimize_image_url

    cdn = "https://image.civitai.com"
    img = f"{cdn}/xG1nkqKTMzGDvpLrqFT7WA/abc/original=true/1.png"
    result = optimize_image_url(img, 450, "image")
    assert result == img  # passthrough: URL returned unchanged

    # Video: also passthrough
    assert optimize_image_url(img, 450, "video") == img

    # Non-CDN URL: passthrough
    other = "https://example.com/x.png"
    assert optimize_image_url(other, 450, "image") == other

    # Empty URL
    assert optimize_image_url("", 450, "image") == ""


def test_optimize_image_url_rewrites_with_rust(monkeypatch):
    """With Rust core, optimize_image_url delegates to civbro_core.optimize_cdn_url."""
    mock_core = _mock_rust_core(monkeypatch)
    mock_core.optimize_cdn_url.return_value = "https://image.civitai.com/width=450,format=webp/x.png"

    from civbro_backend.rust_facade import optimize_image_url

    result = optimize_image_url("https://image.civitai.com/x/original=true/1.png", 450, "image")
    assert "width=450" in result
    assert "original=true" not in result
