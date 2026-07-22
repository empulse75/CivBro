use regex::Regex;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::LazyLock;

// ---------------------------------------------------------------------------
// CDN / image URL helpers
// ---------------------------------------------------------------------------
static CDN_URL: &str = "https://image.civitai.com";
static CIVITAI_IMG_BUCKET: &str = "xG1nkqKTMzGDvpLrqFT7WA";

fn cosmetic_img_url(raw: &str) -> String {
    if raw.is_empty() {
        return String::new();
    }
    if raw.starts_with("http") {
        return raw.to_string();
    }
    format!("{}/{}/{}/original=true/deco.png", CDN_URL, CIVITAI_IMG_BUCKET, raw)
}

// ---------------------------------------------------------------------------
// CSS gradient / colour validation
// ---------------------------------------------------------------------------
static GRADIENT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:repeating-)?(?:linear|radial|conic)-gradient\([#%.,()\-\s\w]*\)$")
        .unwrap()
});
static HEX_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^#[0-9a-fA-F]{3,8}$").unwrap());
static VAE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(^|[_\-.])vae([_\-.]|$)").unwrap()
});
static TE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)text.?encoder|(^|[_\-.])te([_\-.]|$)|(^|[_\-.])txt([_\-.]|$)|t5xxl|clip[_\-]?[lg]")
        .unwrap()
});
static WIDTH_SEG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"/width=\d+[^/]*/").unwrap());

fn sanitize_css_frame(value: &str) -> String {
    let v = value.trim().trim_end_matches(';').trim();
    if v.is_empty() || v.to_lowercase().contains("url(") || v.contains('<') || v.contains('@') {
        return String::new();
    }
    if GRADIENT_RE.is_match(v) {
        v.to_string()
    } else {
        String::new()
    }
}

fn hex_ok(c: &str) -> bool {
    HEX_RE.is_match(c.trim())
}

// ---------------------------------------------------------------------------
// Cosmetic extraction
// ---------------------------------------------------------------------------
pub fn extract_cosmetic(raw: &Value) -> Option<Value> {
    if let Some(cos) = raw.get("cosmetic").and_then(|v| v.as_object()) {
        let data = cos.get("data").and_then(|v| v.as_object()).unwrap_or(cos);
        let css = sanitize_css_frame(data.get("cssFrame").and_then(|v| v.as_str()).unwrap_or(""));
        if !css.is_empty() {
            return Some(json!({"cssFrame": css, "glow": data.get("glow").and_then(|v| v.as_bool()).unwrap_or(false)}));
        }
    }

    let user = raw
        .get("creator")
        .and_then(|v| v.as_object())
        .or_else(|| raw.get("user").and_then(|v| v.as_object()))
        .map(|u| u.clone())
        .unwrap_or_default();
    let cosmetics: Vec<&Value> = user
        .get("cosmetics")
        .and_then(|v| v.as_array())
        .or_else(|| raw.get("cosmetics").and_then(|v| v.as_array()))
        .map(|a| a.iter().collect())
        .unwrap_or_default();

    for c in cosmetics {
        let c_item = match c.get("cosmetic").and_then(|v| v.as_object()) {
            Some(obj) => obj,
            None => match c.as_object() {
                Some(obj) => obj,
                None => continue,
            },
        };
        if c_item.get("type").and_then(|v| v.as_str()) == Some("ContentDecoration") {
            let data = c_item
                .get("data")
                .and_then(|v| v.as_object())
                .unwrap_or(c_item);
            let css = sanitize_css_frame(
                data.get("cssFrame").and_then(|v| v.as_str()).unwrap_or(""),
            );
            if !css.is_empty() {
                return Some(json!({
                    "cssFrame": css,
                    "glow": data.get("glow").and_then(|v| v.as_bool()).unwrap_or(false),
                }));
            }
        }
    }
    None
}

fn extract_nameplate(data: &Value) -> Option<Value> {
    let obj = data.as_object()?;
    if let Some(grad) = obj.get("gradient").and_then(|v| v.as_object()) {
        if hex_ok(grad.get("from").and_then(|v| v.as_str()).unwrap_or(""))
            && hex_ok(grad.get("to").and_then(|v| v.as_str()).unwrap_or(""))
        {
            let deg = grad
                .get("deg")
                .and_then(|v| v.as_f64())
                .map(|d| d as i64)
                .unwrap_or(90);
            return Some(json!({
                "gradient": format!(
                    "linear-gradient({}deg, {}, {})",
                    deg,
                    grad["from"].as_str().unwrap().trim(),
                    grad["to"].as_str().unwrap().trim()
                )
            }));
        }
    }
    if let Some(color) = obj.get("color").and_then(|v| v.as_str()) {
        if hex_ok(color) {
            return Some(json!({"color": color.trim()}));
        }
    }
    None
}

pub fn extract_creator_cosmetics(item: &Value) -> Value {
    let user = item
        .get("creator")
        .and_then(|v| v.as_object())
        .or_else(|| item.get("user").and_then(|v| v.as_object()))
        .map(|u| u.clone())
        .unwrap_or_default();

    let mut deco = cosmetic_img_url(
        user.get("avatarDeco")
            .or_else(|| user.get("profileDecoration"))
            .and_then(|v| v.as_str())
            .unwrap_or(""),
    );
    let mut badge = cosmetic_img_url(user.get("badge").and_then(|v| v.as_str()).unwrap_or(""));
    let mut nameplate: Option<Value> = user
        .get("nameplate")
        .and_then(|v| v.as_object())
        .and_then(|np| extract_nameplate(&json!(np)));

    let cosmetics: Vec<&Value> = user
        .get("cosmetics")
        .and_then(|v| v.as_array())
        .or_else(|| item.get("cosmetics").and_then(|v| v.as_array()))
        .map(|a| a.iter().collect())
        .unwrap_or_default();

    for c in &cosmetics {
        let c_item = match c.get("cosmetic").and_then(|v| v.as_object()) {
            Some(obj) => obj,
            None => match c.as_object() {
                Some(obj) => obj,
                None => continue,
            },
        };
        let ctype = c_item.get("type").and_then(|v| v.as_str()).unwrap_or("");
        let data = c_item
            .get("data")
            .and_then(|v| v.as_object())
            .unwrap_or(c_item);
        let url = data.get("url").and_then(|v| v.as_str()).unwrap_or("");
        match ctype {
            "ProfileDecoration" if deco.is_empty() => deco = cosmetic_img_url(url),
            "Badge" if badge.is_empty() => badge = cosmetic_img_url(url),
            "NamePlate" if nameplate.is_none() => {
                nameplate = extract_nameplate(&Value::Object(data.clone()));
            }
            _ => {}
        }
    }

    json!({
        "avatarDeco": if deco.is_empty() { Value::Null } else { json!(deco) },
        "badge": if badge.is_empty() { Value::Null } else { json!(badge) },
        "nameplate": nameplate.unwrap_or(Value::Null),
    })
}

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
fn dir_map() -> HashMap<String, String> {
    HashMap::from([
        ("checkpoint".into(), "Stable-diffusion".into()),
        ("lora".into(), "Lora".into()),
        ("locon".into(), "Lora".into()),
        ("textualinversion".into(), "embeddings".into()),
        ("hypernetwork".into(), "hypernetworks".into()),
        ("vae".into(), "VAE".into()),
        ("controlnet".into(), "ControlNet".into()),
        ("upscaler".into(), "ESRGAN".into()),
    ])
}

pub fn subdir_for_type(file_type: &str, name: &str, model_type: &str) -> String {
    let s = file_type.to_lowercase();
    if s.contains("vae") { return "VAE".into(); }
    if s.contains("encoder") || s == "te" { return "text_encoder".into(); }
    if s.contains("lora") || s.contains("locon") || s.contains("dora") {
        return "Lora".into();
    }
    if s.contains("embed") || s.contains("textualinversion") {
        return "embeddings".into();
    }
    if s.contains("controlnet") { return "ControlNet".into(); }
    if s.contains("upscal") || s.contains("esrgan") { return "ESRGAN".into(); }

    let n = name.to_lowercase();
    if VAE_RE.is_match(&n) { return "VAE".into(); }
    if TE_RE.is_match(&n) { return "text_encoder".into(); }

    let mt = model_type.to_lowercase();
    dir_map().get(&mt).cloned().unwrap_or_else(|| "Stable-diffusion".into())
}

// ---------------------------------------------------------------------------
// Tag / base-model extraction
// ---------------------------------------------------------------------------
fn parse_tags(raw: &Value) -> Vec<String> {
    match raw.get("tags").and_then(|v| v.as_array()) {
        Some(arr) => {
            if let Some(first) = arr.first() {
                if first.is_object() {
                    arr.iter()
                        .filter_map(|t| t.get("name").and_then(|v| v.as_str()).map(String::from))
                        .collect()
                } else {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                }
            } else {
                vec![]
            }
        }
        None => vec![],
    }
}

fn parse_base_models(raw: &Value) -> Vec<String> {
    let mvs = raw
        .get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().collect::<Vec<_>>())
        .unwrap_or_default();
    let base_model = mvs
        .first()
        .and_then(|mv| mv.get("baseModel").and_then(|v| v.as_str()))
        .unwrap_or_else(|| raw.get("baseModel").and_then(|v| v.as_str()).unwrap_or(""));

    if let Some(raw_base_models) = raw.get("baseModels").and_then(|v| v.as_array()) {
        let list: Vec<String> = raw_base_models
            .iter()
            .filter_map(|b| b.as_str().map(String::from))
            .filter(|s| !s.is_empty())
            .collect();
        if !list.is_empty() {
            return list;
        }
    }
    if !base_model.is_empty() {
        vec![base_model.to_string()]
    } else {
        vec![]
    }
}

fn parse_creator(raw: &Value) -> Value {
    let creator = raw.get("creator").and_then(|v| v.as_object());
    json!({
        "username": creator.and_then(|c| c.get("username").and_then(|v| v.as_str())).unwrap_or(""),
        "image": creator.and_then(|c| c.get("image").and_then(|v| v.as_str())).unwrap_or(""),
    })
}

// ---------------------------------------------------------------------------
// Image list extraction
// ---------------------------------------------------------------------------
fn parse_images_for_versions(model_versions: &[&Value], width: u32) -> Vec<Value> {
    let mut images: Vec<Value> = Vec::new();
    for mv in model_versions {
        if let Some(imgs) = mv.get("images").and_then(|v| v.as_array()) {
            for img in imgs {
                let mut img = img.clone();
                if let Some(url) = img
                    .get("url")
                    .and_then(|v| v.as_str())
                    .map(|u| u.to_string())
                {
                    let img_type = img
                        .get("type")
                        .and_then(|v| v.as_str())
                        .unwrap_or("image");
                    img["url"] = json!(optimize_image_url(&url, width, img_type));
                }
                images.push(img);
            }
        }
    }
    images
}

// ---------------------------------------------------------------------------
// Model parsing (slim / rich / trpc)
// ---------------------------------------------------------------------------
fn parse_model_versions(raw: &Value) -> Vec<Value> {
    raw.get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|mvs| {
            mvs.iter()
                .map(|mv| {
                    let version_images = parse_images_for_versions(&[mv], 450);
                    json!({
                        "id": mv.get("id"),
                        "name": mv.get("name"),
                        "baseModel": mv.get("baseModel"),
                        "trainedWords": mv.get("trainedWords").cloned().unwrap_or(json!([])),
                        "images": version_images,
                        "downloadUrl": mv.get("downloadUrl").and_then(|v| v.as_str()).unwrap_or(""),
                        "files": mv.get("files").cloned().unwrap_or(json!([])),
                        "createdAt": mv.get("createdAt"),
                        "stats": mv.get("stats").cloned().unwrap_or(json!({})),
                    })
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

fn build_stats(raw: &Value, slim: bool) -> Value {
    let stats = raw.get("stats").and_then(|v| v.as_object());
    if slim {
        json!({
            "downloadCount": stats.and_then(|s| s.get("downloadCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "rating": stats.and_then(|s| s.get("rating").and_then(|v| v.as_f64())).unwrap_or(0.0),
            "thumbsUpCount": stats.and_then(|s| s.get("thumbsUpCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "favoriteCount": stats.and_then(|s| s.get("favoriteCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "commentCount": stats.and_then(|s| s.get("commentCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "tippedAmountCount": stats.and_then(|s| s.get("tippedAmountCount").and_then(|v| v.as_i64())).unwrap_or(0),
        })
    } else {
        json!({
            "downloadCount": stats.and_then(|s| s.get("downloadCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "favoriteCount": stats.and_then(|s| s.get("favoriteCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "commentCount": stats.and_then(|s| s.get("commentCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "ratingCount": stats.and_then(|s| s.get("ratingCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "rating": stats.and_then(|s| s.get("rating").and_then(|v| v.as_f64())).unwrap_or(0.0),
            "thumbsUpCount": stats.and_then(|s| s.get("thumbsUpCount").and_then(|v| v.as_i64())).unwrap_or(0),
            "thumbsDownCount": stats.and_then(|s| s.get("thumbsDownCount").and_then(|v| v.as_i64())).unwrap_or(0),
        })
    }
}

pub fn parse_model_slim(raw: &Value) -> Value {
    let mvs: Vec<&Value> = raw
        .get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().collect())
        .unwrap_or_default();
    let imgs: Vec<&Value> = mvs
        .first()
        .and_then(|mv| mv.get("images").and_then(|v| v.as_array()))
        .or_else(|| raw.get("images").and_then(|v| v.as_array()))
        .map(|a| a.iter().collect())
        .unwrap_or_default();

    let mut images = vec![];
    let mut poster = String::new();
    if let Some(first_img) = imgs.first() {
        let mut im = (*first_img).clone();
        let img_url = first_img
            .get("url")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let img_type = first_img
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("image");
        im["url"] = json!(optimize_image_url(img_url, 300, img_type));
        images.push(im);

        if img_type == "video" {
            for cand in &imgs {
                let cand_type = cand.get("type").and_then(|v| v.as_str()).unwrap_or("image");
                if cand_type != "video" {
                    if let Some(url) = cand.get("url").and_then(|v| v.as_str()) {
                        poster = optimize_image_url(url, 300, "image");
                    }
                    break;
                }
            }
        }
    }

    let mut tags = parse_tags(raw);
    tags.truncate(8);
    let base_models = parse_base_models(raw);
    let base_model = base_models.first().cloned().unwrap_or_default();
    let creator = raw.get("creator").and_then(|v| v.as_object());

    let mut ea_deadline: Option<String> = raw
        .get("earlyAccessDeadline")
        .or_else(|| raw.get("earlyAccessEndsAt"))
        .and_then(|v| v.as_str())
        .map(String::from);
    if ea_deadline.is_none() {
        if let Some(ea_cfg) = raw.get("earlyAccessConfig").and_then(|v| v.as_object()) {
            ea_deadline = ea_cfg
                .get("timeframe")
                .or_else(|| ea_cfg.get("deadline"))
                .and_then(|v| v.as_str())
                .map(String::from);
        }
    }

    let mv0 = mvs.first();
    let published_at = raw
        .get("publishedAt")
        .or_else(|| mv0.and_then(|mv| mv.get("publishedAt")))
        .and_then(|v| v.as_str());
    let created_at = raw
        .get("createdAt")
        .or_else(|| mv0.and_then(|mv| mv.get("createdAt")))
        .and_then(|v| v.as_str());

    json!({
        "id": raw.get("id"),
        "name": raw.get("name"),
        "modelType": raw.get("modelType").or(raw.get("type")),
        "type": raw.get("type").or(raw.get("modelType")),
        "nsfw": raw.get("nsfw").and_then(|v| v.as_bool()).unwrap_or(false),
        "baseModel": base_model,
        "baseModels": base_models,
        "tags": tags,
        "availability": raw.get("availability").and_then(|v| v.as_str()).unwrap_or("Public"),
        "earlyAccessDeadline": ea_deadline,
        "publishedAt": published_at,
        "createdAt": created_at,
        "images": images,
        "poster": if poster.is_empty() { Value::Null } else { json!(poster) },
        "cosmetic": extract_cosmetic(raw),
        "avatarDeco": extract_creator_cosmetics(raw)["avatarDeco"].clone(),
        "badge": extract_creator_cosmetics(raw)["badge"].clone(),
        "nameplate": extract_creator_cosmetics(raw)["nameplate"].clone(),
        "stats": build_stats(raw, true),
        "creator": {
            "username": creator.and_then(|c| c.get("username").and_then(|v| v.as_str())).unwrap_or(""),
            "image": creator.and_then(|c| c.get("image").and_then(|v| v.as_str())).unwrap_or(""),
        },
    })
}

pub fn parse_model_rich(raw: &Value) -> Value {
    let images = parse_images_for_versions(
        &raw.get("modelVersions")
            .and_then(|v| v.as_array())
            .map(|a| a.iter().collect::<Vec<_>>())
            .unwrap_or_default(),
        450,
    );
    let tags = parse_tags(raw);
    let model_versions = parse_model_versions(raw);
    let deco_cos = extract_creator_cosmetics(raw);
    let base_models = parse_base_models(raw);
    let base_model = base_models.first().cloned().unwrap_or_default();

    json!({
        "id": raw.get("id"),
        "name": raw.get("name"),
        "description": raw.get("description").and_then(|v| v.as_str()).unwrap_or(""),
        "modelType": raw.get("modelType").or(raw.get("type")),
        "baseModel": base_model,
        "baseModels": base_models,
        "nsfw": raw.get("nsfw").and_then(|v| v.as_bool()).unwrap_or(false),
        "tags": tags,
        "images": images,
        "modelVersions": model_versions,
        "cosmetic": extract_cosmetic(raw),
        "avatarDeco": deco_cos["avatarDeco"].clone(),
        "badge": deco_cos["badge"].clone(),
        "nameplate": deco_cos["nameplate"].clone(),
        "stats": build_stats(raw, false),
        "creator": parse_creator(raw),
        "createdAt": raw.get("createdAt"),
        "updatedAt": raw.get("updatedAt"),
        "lastVersionAt": raw.get("lastVersionAt"),
    })
}

pub fn parse_model_trpc(raw: &Value) -> Value {
    let mut parsed = parse_model_rich(raw);
    parsed["mode"] = raw.get("mode").cloned().unwrap_or(Value::Null);
    parsed
}

// ---------------------------------------------------------------------------
// Batch parser: takes JSON array of raw items, returns JSON array of parsed models
// ---------------------------------------------------------------------------
pub fn parse_models_batch(json_items: &str, style: &str) -> Result<String, String> {
    let items: Vec<Value> =
        serde_json::from_str(json_items).map_err(|e| format!("JSON parse error: {}", e))?;
    let parsed: Vec<Value> = items
        .iter()
        .map(|item| match style {
            "slim" => parse_model_slim(item),
            "trpc" => parse_model_trpc(item),
            _ => parse_model_rich(item),
        })
        .collect();
    serde_json::to_string(&parsed).map_err(|e| format!("JSON serialize error: {}", e))
}

// ---------------------------------------------------------------------------
// SuperJSON / tRPC item parsing
// ---------------------------------------------------------------------------
fn resolve_cosmetic_field(obj: &mut Value, arr: &[Value]) {
    let cos = match obj.get_mut("cosmetic") {
        Some(cos) => cos,
        None => return,
    };
    if !cos.is_object() {
        return;
    }
    let data_idx = match cos.get("data").and_then(|v| v.as_i64()) {
        Some(idx) if idx >= 0 && (idx as usize) < arr.len() => idx as usize,
        _ => return,
    };
    let data_tpl = match arr.get(data_idx).and_then(|v| v.as_object()) {
        Some(tpl) => tpl,
        None => return,
    };
    if !data_tpl.values().all(|v| v.is_i64()) {
        return;
    }
    let resolved: serde_json::Map<String, Value> = data_tpl
        .iter()
        .filter_map(|(k, vi)| {
            vi.as_i64()
                .filter(|&idx| idx >= 0 && (idx as usize) < arr.len())
                .map(|idx| (k.clone(), arr[idx as usize].clone()))
        })
        .collect();
    cos["data"] = Value::Object(resolved);
}

fn resolve_value(val: &Value, arr: &[Value], depth: u32) -> Value {
    if depth > 5 {
        return val.clone();
    }
    if let Some(idx) = val.as_i64() {
        if idx >= 0 && (idx as usize) < arr.len() {
            return resolve_value(&arr[idx as usize], arr, depth + 1);
        }
    }
    if let Some(list) = val.as_array() {
        return Value::Array(
            list.iter()
                .map(|v| resolve_value(v, arr, depth + 1))
                .collect(),
        );
    }
    if let Some(obj) = val.as_object() {
        let vs: Vec<&Value> = obj.values().collect();
        if !vs.is_empty() && vs.iter().all(|v| v.is_i64()) {
            let resolved: serde_json::Map<String, Value> = obj
                .iter()
                .filter_map(|(k, vi)| {
                    vi.as_i64()
                        .filter(|&idx| idx >= 0 && (idx as usize) < arr.len())
                        .map(|idx| (k.clone(), arr[idx as usize].clone()))
                })
                .collect();
            return Value::Object(resolved);
        }
    }
    val.clone()
}

fn resolve_user_field(obj: &mut Value, arr: &[Value]) {
    let user_raw = match obj.get("user") {
        Some(u) if u.is_object() => u.clone(),
        _ => return,
    };
    obj["user"] = resolve_value(&user_raw, arr, 0);
}

pub fn parse_trpc_items(response_json: &str) -> Result<String, String> {
    let resp: Value =
        serde_json::from_str(response_json).map_err(|e| format!("JSON parse: {}", e))?;
    let data = match resp.get("result").and_then(|r| r.get("data")) {
        Some(d) => d,
        None => return Ok("[]".into()),
    };

    if data.is_object() {
        let items = data
            .get("json")
            .and_then(|j| j.get("items"))
            .cloned()
            .unwrap_or(json!([]));
        return serde_json::to_string(&items).map_err(|e| format!("JSON serialize: {}", e));
    }

    if let Some(data_str) = data.as_str() {
        let arr: Vec<Value> =
            serde_json::from_str(data_str).map_err(|e| format!("JSON parse: {}", e))?;
        if arr.len() < 3 {
            return Ok("[]".into());
        }
        let meta = arr[0].as_object();
        let tpl = arr[2].as_object().ok_or("Invalid tRPC template")?;
        let stride = tpl
            .values()
            .filter_map(|v| v.as_i64())
            .max()
            .unwrap_or(0) as usize
            + 1;
        let count = meta.and_then(|m| m.get("items").and_then(|v| v.as_i64())).unwrap_or(1);

        let mut items: Vec<Value> = Vec::new();
        for model_i in 0..count as usize {
            let base = 3 + model_i * stride;
            let mut obj = serde_json::Map::new();
            for (key, vi) in tpl.iter() {
                if let Some(vi) = vi.as_i64() {
                    let idx = if model_i == 0 { vi as usize } else { base + vi as usize };
                    if idx < arr.len() {
                        obj.insert(key.clone(), arr[idx].clone());
                    }
                }
            }
            if obj.contains_key("id") {
                let mut obj_val = Value::Object(obj);
                resolve_user_field(&mut obj_val, &arr);
                resolve_cosmetic_field(&mut obj_val, &arr);
                items.push(obj_val);
            }
        }
        return serde_json::to_string(&items).map_err(|e| format!("JSON serialize: {}", e));
    }

    Ok("[]".into())
}

// ---------------------------------------------------------------------------
// tRPC extras builder
// ---------------------------------------------------------------------------
pub fn build_trpc_extras(item_json: &str) -> Result<String, String> {
    let item: Value =
        serde_json::from_str(item_json).map_err(|e| format!("JSON parse: {}", e))?;

    let mut extras = serde_json::Map::new();

    if let Some(cos) = extract_cosmetic(&item) {
        extras.insert("cosmetic".into(), cos);
    }

    if let Some(base_models) = item.get("baseModels").and_then(|v| v.as_array()) {
        let bm: Vec<String> = base_models
            .iter()
            .filter_map(|b| b.as_str().map(String::from))
            .filter(|s| !s.is_empty())
            .collect();
        if !bm.is_empty() {
            extras.insert("baseModels".into(), json!(bm));
        }
    }

    let deco = extract_creator_cosmetics(&item);
    for key in &["avatarDeco", "badge", "nameplate"] {
        if !deco[*key].is_null() {
            extras.insert(key.to_string(), deco[*key].clone());
        }
    }

    for field in &[
        "availability",
        "earlyAccessDeadline",
        "publishedAt",
        "createdAt",
        "mode",
    ] {
        if let Some(val) = item.get(field) {
            if !val.is_null() {
                extras.insert(field.to_string(), val.clone());
            }
        }
    }

    let has_buzz = item
        .get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|mvs| {
            mvs.iter().any(|v| {
                v.as_object()
                    .and_then(|o| o.get("requiresBuzz"))
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false);
    if has_buzz {
        extras.insert("hasBuzz".into(), json!(true));
    }

    extras.insert("name".into(), item.get("name").cloned().unwrap_or(json!("")));
    extras.insert(
        "modelType".into(),
        item.get("modelType")
            .or(item.get("type"))
            .cloned()
            .unwrap_or(json!("")),
    );
    extras.insert(
        "nsfw".into(),
        json!(item.get("nsfw").and_then(|v| v.as_bool()).unwrap_or(false)),
    );
    extras.insert("stats".into(), item.get("stats").cloned().unwrap_or(json!({})));

    let creator = item
        .get("creator")
        .and_then(|v| v.as_object())
        .map(|c| {
            json!({
                "username": c.get("username").and_then(|v| v.as_str()).unwrap_or(""),
                "image": c.get("image").and_then(|v| v.as_str()).unwrap_or(""),
            })
        })
        .unwrap_or(json!({"username": "", "image": ""}));
    extras.insert("creator".into(), creator);

    let mvs: Vec<&Value> = item
        .get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().collect())
        .unwrap_or_default();
    let imgs = mvs
        .first()
        .and_then(|mv| mv.get("images").and_then(|v| v.as_array()))
        .or_else(|| item.get("images").and_then(|v| v.as_array()))
        .map(|a| a.iter().collect::<Vec<_>>())
        .unwrap_or_default();

    if let Some(first_img) = imgs.first() {
        let mut im = (*first_img).clone();
        let img_url = first_img
            .get("url")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let img_type = first_img
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("image");
        im["url"] = json!(optimize_image_url(img_url, 300, img_type));
        extras.insert("images".into(), json!([im]));
    }

    serde_json::to_string(&Value::Object(extras))
        .map_err(|e| format!("JSON serialize: {}", e))
}

// ---------------------------------------------------------------------------
// Apply extras to slim model
// ---------------------------------------------------------------------------
pub fn apply_extras_to_slim(slim_json: &str, extras_json: &str) -> Result<String, String> {
    let mut slim: Value =
        serde_json::from_str(slim_json).map_err(|e| format!("JSON parse: {}", e))?;
    let extras: Value =
        serde_json::from_str(extras_json).map_err(|e| format!("JSON parse: {}", e))?;

    for field in &["availability", "earlyAccessDeadline"] {
        if let Some(val) = extras.get(field) {
            if !val.is_null() {
                slim[field] = val.clone();
            }
        }
    }
    for field in &["publishedAt", "createdAt"] {
        if slim.get(field).map_or(true, |v| v.is_null()) {
            if let Some(val) = extras.get(field) {
                if !val.is_null() {
                    slim[field] = val.clone();
                }
            }
        }
    }
    if extras.get("hasBuzz").and_then(|v| v.as_bool()).unwrap_or(false) {
        slim["hasBuzz"] = json!(true);
    }

    serde_json::to_string(&slim).map_err(|e| format!("JSON serialize: {}", e))
}

// ---------------------------------------------------------------------------
// Build slim model from tRPC extras
// ---------------------------------------------------------------------------
pub fn make_slim_from_trpc(extras_json: &str, model_id: i64) -> Result<String, String> {
    let extras: Value =
        serde_json::from_str(extras_json).map_err(|e| format!("JSON parse: {}", e))?;
    let result = json!({
        "id": model_id,
        "name": extras.get("name").and_then(|v| v.as_str()).unwrap_or(""),
        "modelType": extras.get("modelType").and_then(|v| v.as_str()).unwrap_or("Checkpoint"),
        "type": extras.get("modelType").and_then(|v| v.as_str()).unwrap_or("Checkpoint"),
        "nsfw": extras.get("nsfw").and_then(|v| v.as_bool()).unwrap_or(false),
        "baseModel": "",
        "tags": [],
        "images": extras.get("images").cloned().unwrap_or(json!([])),
        "poster": extras.get("poster").cloned().unwrap_or(Value::Null),
        "cosmetic": extras.get("cosmetic"),
        "availability": extras.get("availability").and_then(|v| v.as_str()).unwrap_or("EarlyAccess"),
        "earlyAccessDeadline": extras.get("earlyAccessDeadline"),
        "publishedAt": extras.get("publishedAt"),
        "createdAt": extras.get("createdAt"),
        "hasBuzz": extras.get("hasBuzz").and_then(|v| v.as_bool()).unwrap_or(false),
        "stats": extras.get("stats").cloned().unwrap_or(json!({})),
        "creator": extras.get("creator").cloned().unwrap_or(json!({"username": "", "image": ""})),
        "baseModels": extras.get("baseModels").cloned().unwrap_or(json!([])),
        "avatarDeco": extras.get("avatarDeco"),
        "badge": extras.get("badge"),
        "nameplate": extras.get("nameplate"),
        "_fromTrpcExtras": true,
    });
    serde_json::to_string(&result).map_err(|e| format!("JSON serialize: {}", e))
}

// ---------------------------------------------------------------------------
// Dependency parsing
// ---------------------------------------------------------------------------
pub fn parse_dependencies(trpc_json: &str) -> Result<String, String> {
    let trpc: Value =
        serde_json::from_str(trpc_json).map_err(|e| format!("JSON parse: {}", e))?;
    let deps: Vec<Value> = trpc
        .get("linkedComponents")
        .and_then(|v| v.as_array())
        .map(|comps| {
            comps
                .iter()
                .filter_map(|c| {
                    let vid = c.get("versionId")?.as_i64()?;
                    Some(json!({
                        "type": c.get("componentType").or(c.get("fileType")).and_then(|v| v.as_str()).unwrap_or(""),
                        "modelId": c.get("modelId"),
                        "modelName": c.get("modelName"),
                        "versionId": vid,
                        "versionName": c.get("versionName"),
                        "fileId": c.get("fileId"),
                        "name": c.get("fileName").or(c.get("modelName")).and_then(|v| v.as_str()).unwrap_or(""),
                        "sizeKB": c.get("sizeKB").and_then(|v| v.as_i64()).unwrap_or(0),
                        "required": c.get("isRequired").and_then(|v| v.as_bool()).unwrap_or(true),
                        "downloadUrl": format!("https://civitai.com/api/download/models/{}", vid),
                    }))
                })
                .collect()
        })
        .unwrap_or_default();
    serde_json::to_string(&deps).map_err(|e| format!("JSON serialize: {}", e))
}
