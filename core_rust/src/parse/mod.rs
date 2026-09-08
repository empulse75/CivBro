// Shared utilities — used across parse sub-modules.

use regex::Regex;
use std::sync::LazyLock;

// ---------------------------------------------------------------------------
// CDN / image URL helpers
// ---------------------------------------------------------------------------
pub static CDN_URL: &str = "https://image.civitai.com";
pub static CIVITAI_IMG_BUCKET: &str = "xG1nkqKTMzGDvpLrqFT7WA";

// ---------------------------------------------------------------------------
// Regex statics
// ---------------------------------------------------------------------------
pub static VAE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(^|[_\-.])vae([_\-.]|$)").unwrap()
});
pub static TE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)text.?encoder|(^|[_\-.])te([_\-.]|$)|(^|[_-])txt([_\-.]|$)|t5xxl|clip[_\-]?[lg]")
        .unwrap()
});
pub static WIDTH_SEG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"/width=\d+[^/]*/").unwrap());

// ---------------------------------------------------------------------------
// CDN URL optimization
// ---------------------------------------------------------------------------
pub fn optimize_image_url(url: &str, width: u32, image_type: &str) -> String {
    if url.is_empty() || !url.contains(CDN_URL) {
        return url.to_string();
    }
    if image_type == "video" {
        let vt = format!("transcode=true,width={},optimized=true", width.max(450));
        if url.contains("/original=true/") {
            return url.replace("/original=true/", &format!("/{}/", vt));
        }
        if let Some(m) = WIDTH_SEG_RE.find(url) {
            let start = m.start();
            let end = m.end();
            return format!("{}/{}/{}", &url[..start], vt, &url[end..]);
        }
        return url.to_string();
    }
    let url = url.replace("/original=true/", "/");
    if !url.contains("/width=") {
        return url.replace(CDN_URL, &format!("{}/width={},format=webp", CDN_URL, width));
    }
    url
}

// ---------------------------------------------------------------------------
// Subdirectory mapping
// ---------------------------------------------------------------------------
use std::collections::HashMap;

static DIR_MAP: LazyLock<HashMap<&'static str, &'static str>> = LazyLock::new(|| {
    HashMap::from([
        ("checkpoint", "Stable-diffusion"),
        ("lora", "Lora"),
        ("locon", "Lora"),
        ("textualinversion", "embeddings"),
        ("hypernetwork", "hypernetworks"),
        ("vae", "VAE"),
        ("controlnet", "ControlNet"),
        ("upscaler", "ESRGAN"),
        ("motionmodule", "AnimateDiff"),
        ("aestheticgradient", "aesthetic_embeddings"),
        ("poses", "Poses"),
        ("wildcards", "wildcards"),
        ("other", "Other"),
        ("textencoder", "text_encoder"),
    ])
});

pub fn subdir_for_type(file_type: &str, name: &str, model_type: &str) -> String {
    let s = file_type.to_lowercase();
    if s.contains("vae") {
        return "VAE".into();
    }
    if s.contains("encoder") || s == "te" {
        return "text_encoder".into();
    }
    if s.contains("lora") || s.contains("locon") || s.contains("dora") {
        return "Lora".into();
    }
    if s.contains("embed") || s.contains("textualinversion") {
        return "embeddings".into();
    }
    if s.contains("controlnet") {
        return "ControlNet".into();
    }
    if s.contains("upscal") || s.contains("esrgan") {
        return "ESRGAN".into();
    }

    let n = name.to_lowercase();
    if VAE_RE.is_match(&n) {
        return "VAE".into();
    }
    if TE_RE.is_match(&n) {
        return "text_encoder".into();
    }

    let mt = model_type.to_lowercase();
    DIR_MAP
        .get(mt.as_str())
        .unwrap_or(&"Stable-diffusion")
        .to_string()
}

// ---------------------------------------------------------------------------
// Re-exports
// ---------------------------------------------------------------------------
pub mod cosmetics;
pub mod models;
pub mod trpc;
pub mod versions;

pub use models::parse_models_batch;
pub use trpc::{
    apply_extras_to_slim, build_trpc_extras, make_slim_from_trpc, parse_dependencies,
    parse_trpc_items,
};
pub use versions::{build_version_detail, build_version_list};
