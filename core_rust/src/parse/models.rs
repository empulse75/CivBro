use serde_json::{json, Value};

use super::cosmetics::{extract_cosmetic, extract_creator_cosmetics};
use super::optimize_image_url;

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
    let mvs: Vec<&Value> = raw
        .get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().collect())
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
                    let img_type = img.get("type").and_then(|v| v.as_str()).unwrap_or("image");
                    img["url"] = json!(optimize_image_url(&url, width, img_type));
                }
                images.push(img);
            }
        }
    }
    images
}

// ---------------------------------------------------------------------------
// Model version parsing
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

// ---------------------------------------------------------------------------
// Model parsing (slim / rich / trpc)
// ---------------------------------------------------------------------------
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
                let cand_type = cand
                    .get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("image");
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

    let poster_val = if poster.is_empty() {
        raw.get("poster")
            .and_then(|v| v.as_str())
            .map(|p| json!(optimize_image_url(p, 300, "image")))
            .unwrap_or(Value::Null)
    } else {
        json!(poster)
    };

    let creator_cosmetics = extract_creator_cosmetics(raw);

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
        "poster": poster_val,
        "cosmetic": extract_cosmetic(raw),
        "avatarDeco": creator_cosmetics["avatarDeco"].clone(),
        "badge": creator_cosmetics["badge"].clone(),
        "nameplate": creator_cosmetics["nameplate"].clone(),
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
// Batch parser
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
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use crate::parse::subdir_for_type;
    use serde_json::json;

    #[test]
    fn subdir_routes_file_types_to_correct_dirs() {
        assert_eq!(subdir_for_type("VAE", "", ""), "VAE");
        assert_eq!(subdir_for_type("Text Encoder", "", ""), "text_encoder");
        assert_eq!(subdir_for_type("LORA", "", ""), "Lora");
        assert_eq!(subdir_for_type("dora", "", ""), "Lora");
        assert_eq!(subdir_for_type("ControlNet", "", ""), "ControlNet");
        assert_eq!(subdir_for_type("Model", "my_vae.safetensors", ""), "VAE");
        assert_eq!(
            subdir_for_type("Model", "t5xxl_fp16.safetensors", ""),
            "text_encoder"
        );
        assert_eq!(
            subdir_for_type("Model", "plain.safetensors", "Checkpoint"),
            "Stable-diffusion"
        );
        assert_eq!(
            subdir_for_type("Model", "plain.safetensors", "Upscaler"),
            "ESRGAN"
        );
        assert_eq!(subdir_for_type("Model", "plain.pt", "AestheticGradient"), "aesthetic_embeddings");
        assert_eq!(subdir_for_type("Model", "plain.pt", "Hypernetwork"), "hypernetworks");
        assert_eq!(subdir_for_type("Model", "plain.safetensors", "MotionModule"), "AnimateDiff");
        assert_eq!(subdir_for_type("Archive", "poses.zip", "Poses"), "Poses");
        assert_eq!(subdir_for_type("Config", "subjects.txt", "Wildcards"), "wildcards");
        assert_eq!(subdir_for_type("Archive", "tool.zip", "Other"), "Other");
    }

    #[test]
    fn subdir_for_type_with_locon_and_dora() {
        assert_eq!(subdir_for_type("LoCon", "", ""), "Lora");
        assert_eq!(subdir_for_type("DoRA", "", ""), "Lora");
        assert_eq!(
            subdir_for_type("", "my_locn_v1.safetensors", "Checkpoint"),
            "Stable-diffusion"
        );
    }

    #[test]
    fn optimize_url_rewrites_images_and_videos() {
        let base =
            "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc/original=true/1.png";
        let img = optimize_image_url(base, 450, "image");
        assert!(img.contains("/width=450,format=webp/"));
        assert!(!img.contains("original=true"));

        let vid = optimize_image_url(base, 450, "video");
        assert!(vid.contains("transcode=true"));

        let other = "https://example.com/x.png";
        assert_eq!(optimize_image_url(other, 450, "image"), other);
    }

    #[test]
    fn slim_parser_extracts_cosmetics_once() {
        let raw = json!({
            "id": 7,
            "name": "test",
            "type": "LORA",
            "creator": {
                "username": "tester",
                "image": "",
                "cosmetics": [
                    {"cosmetic": {"type": "Badge", "data": {"url": "badge1"}}}
                ]
            },
            "modelVersions": [{"id": 1, "images": [{"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/a/original=true/i.png", "type": "image"}]}],
        });
        let slim = parse_model_slim(&raw);
        assert_eq!(slim["id"], 7);
        assert!(slim["badge"].as_str().unwrap().contains("badge1"));
        assert!(slim["images"][0]["url"]
            .as_str()
            .unwrap()
            .contains("width=300"));
        assert_eq!(slim["stats"]["downloadCount"], 0);
    }

    #[test]
    fn parse_models_batch_trpc_style() {
        let items = json!([{
            "id": 1, "name": "m1", "type": "Checkpoint", "modelType": "Checkpoint",
            "creator": {"username": "u","image":""},
            "modelVersions": [{"id": 1, "images": [{"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7wa/a/original=true/i.png", "type": "image"}]}],
            "stats": {}, "tags": []
        }]);
        let result = parse_models_batch(&items.to_string(), "trpc").unwrap();
        let parsed: Vec<Value> = serde_json::from_str(&result).unwrap();
        assert_eq!(parsed.len(), 1);
        assert!(parsed[0]["images"][0]["url"]
            .as_str()
            .unwrap()
            .contains("width=450"));
    }
}
