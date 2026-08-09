use regex::Regex;
use serde_json::{json, Value};
use std::sync::LazyLock;

use super::{CDN_URL, CIVITAI_IMG_BUCKET};

// ---------------------------------------------------------------------------
// CSS gradient / colour validation
// ---------------------------------------------------------------------------
static GRADIENT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:repeating-)?(?:linear|radial|conic)-gradient\([#%.,()\-\s\w]*\)$").unwrap()
});
static HEX_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^#[0-9a-fA-F]{3,8}$").unwrap());

fn cosmetic_img_url(raw: &str) -> String {
    if raw.is_empty() {
        return String::new();
    }
    if raw.starts_with("http") {
        return raw.to_string();
    }
    format!(
        "{}/{}/{}/original=true/deco.png",
        CDN_URL, CIVITAI_IMG_BUCKET, raw
    )
}

fn profile_background_url(raw: &str, media_type: &str) -> String {
    if raw.is_empty() || raw.starts_with("http") {
        return raw.to_string();
    }
    if media_type == "video" {
        format!(
            "{}/{}/{}/transcode=true,width=450,optimized=true/{}.webm",
            CDN_URL, CIVITAI_IMG_BUCKET, raw, raw
        )
    } else {
        format!(
            "{}/{}/{}/width=450,optimized=true/{}.jpeg",
            CDN_URL, CIVITAI_IMG_BUCKET, raw, raw
        )
    }
}

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
fn presentation_user(item: &Value) -> serde_json::Map<String, Value> {
    let creator = item.get("creator").and_then(|v| v.as_object());
    let user = item.get("user").and_then(|v| v.as_object());
    let mut presentation = user.cloned().unwrap_or_default();
    if let Some(creator) = creator {
        for (key, value) in creator {
            if key == "cosmetics" && value.as_array().is_some_and(|items| items.is_empty()) {
                continue;
            }
            presentation.insert(key.clone(), value.clone());
        }
    }
    presentation
}

pub fn extract_cosmetic(raw: &Value) -> Option<Value> {
    if let Some(cos) = raw.get("cosmetic").and_then(|v| v.as_object()) {
        let data = cos.get("data").and_then(|v| v.as_object()).unwrap_or(cos);
        let css = sanitize_css_frame(data.get("cssFrame").and_then(|v| v.as_str()).unwrap_or(""));
        if !css.is_empty() {
            return Some(json!({"cssFrame": css, "glow": data.get("glow").and_then(|v| v.as_bool()).unwrap_or(false)}));
        }
    }

    let user = presentation_user(raw);
    let cosmetics: Vec<&Value> = user
        .get("cosmetics")
        .and_then(|v| v.as_array())
        .or_else(|| raw.get("cosmetics").and_then(|v| v.as_array()))
        .map(|a| a.iter().collect())
        .unwrap_or_default();

    let mut cosmetics = cosmetics;
    cosmetics.sort_by_key(|c| if c.get("data").map_or(false, |v| !v.is_null()) { 0 } else { 1 });
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
                let texture = data.get("texture").and_then(|v| v.as_object());
                let texture_url = texture
                    .and_then(|v| v.get("url"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .trim_start_matches("url('")
                    .trim_end_matches("')");
                return Some(json!({
                    "cssFrame": css,
                    "glow": data.get("glow").and_then(|v| v.as_bool()).unwrap_or(false),
                    "type": data.get("type"),
                    "color": data.get("color"),
                    "brightness": data.get("brightness"),
                    "textureUrl": texture_url,
                    "textureWidth": texture.and_then(|v| v.get("size")).and_then(|v| v.get("width")),
                    "textureHeight": texture.and_then(|v| v.get("size")).and_then(|v| v.get("height")),
                }));
            }
        }
    }
    None
}

fn extract_nameplate(data: &Value) -> Option<Value> {
    let obj = data.as_object()?;
    if let Some(grad) = obj.get("gradient").and_then(|v| v.as_object()) {
        let from = grad.get("from").and_then(|v| v.as_str()).unwrap_or("");
        let to = grad.get("to").and_then(|v| v.as_str()).unwrap_or("");
        if hex_ok(from) && hex_ok(to) {
            let deg = grad
                .get("deg")
                .and_then(|v| v.as_f64())
                .map(|d| d as i64)
                .unwrap_or(90);
            return Some(json!({
                "gradient": format!(
                    "linear-gradient({}deg, {}, {})",
                    deg,
                    from.trim(),
                    to.trim()
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
    let user = presentation_user(item);

    let mut deco = cosmetic_img_url(
        user.get("avatarDeco")
            .or_else(|| user.get("profileDecoration"))
            .and_then(|v| v.as_str())
            .unwrap_or(""),
    );
    let mut badge = cosmetic_img_url(user.get("badge").and_then(|v| v.as_str()).unwrap_or(""));
    let direct_bg = user.get("profileBackground").and_then(|v| v.as_object());
    let mut profile_background_type = direct_bg
        .and_then(|v| v.get("type"))
        .and_then(|v| v.as_str())
        .unwrap_or("image")
        .to_string();
    let mut profile_background = profile_background_url(
        direct_bg
            .and_then(|v| v.get("url"))
            .and_then(|v| v.as_str())
            .unwrap_or(""),
        &profile_background_type,
    );
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
            "ProfileBackground" if profile_background.is_empty() => {
                profile_background_type = data
                    .get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("image")
                    .to_string();
                profile_background = profile_background_url(url, &profile_background_type)
            }
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
        "profileBackground": if profile_background.is_empty() {
            Value::Null
        } else {
            json!({"url": profile_background, "type": profile_background_type})
        },
        "nameplate": nameplate.unwrap_or(Value::Null),
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn sanitize_css_frame_blocks_injection() {
        assert!(
            sanitize_css_frame("linear-gradient(90deg, #fff, #000)")
                .starts_with("linear-gradient")
        );
        assert_eq!(sanitize_css_frame("url(https://evil.com/x)"), "");
        assert_eq!(sanitize_css_frame("red"), "");
        assert_eq!(
            sanitize_css_frame("linear-gradient(90deg,#fff,#000); background: url(x)"),
            ""
        );
    }

    #[test]
    fn nameplate_color_fallback() {
        let data = json!({"color": "#ff00ff"});
        let np = extract_nameplate(&data);
        assert!(np.is_some());
        assert_eq!(np.unwrap()["color"], "#ff00ff");
    }

    #[test]
    fn nameplate_none_for_invalid() {
        assert!(extract_nameplate(&json!({})).is_none());
        assert!(extract_nameplate(&json!({"gradient": {"from": "red"}})).is_none());
    }

    #[test]
    fn creator_cosmetics_with_only_nameplate() {
        let item = json!({
            "creator": {
                "username": "u",
                "nameplate": {"color": "#abcdef"}
            }
        });
        let result = extract_creator_cosmetics(&item);
        assert!(result["nameplate"]["color"]
            .as_str()
            .unwrap()
            .contains("#abcdef"));
        assert!(result["avatarDeco"].is_null());
        assert!(result["badge"].is_null());
    }

    #[test]
    fn creator_cosmetics_extract_profile_background() {
        let item = json!({
            "user": {
                "cosmetics": [{
                    "cosmetic": {
                        "type": "ProfileBackground",
                        "data": {"url": "66137185-3c2b-4422-b0d8-a49c2e1ebb51", "type": "image"}
                    }
                }]
            }
        });

        let result = extract_creator_cosmetics(&item);
        assert!(result["profileBackground"]["url"]
            .as_str()
            .unwrap()
            .contains("66137185-3c2b-4422-b0d8-a49c2e1ebb51"));
        assert_eq!(result["profileBackground"]["type"], "image");
    }

    #[test]
    fn creator_cosmetics_preserve_video_profile_background() {
        let item = json!({
            "user": {
                "cosmetics": [{
                    "cosmetic": {
                        "type": "ProfileBackground",
                        "data": {"url": "774d12b3-b264-4712-8484-ddbecf0bb14a", "type": "video"}
                    }
                }]
            }
        });

        let result = extract_creator_cosmetics(&item);
        assert_eq!(result["profileBackground"]["type"], "video");
        assert!(result["profileBackground"]["url"]
            .as_str()
            .unwrap()
            .ends_with(".webm"));
    }

    #[test]
    fn creator_cosmetics_uses_rich_user_when_creator_is_slim() {
        let item = json!({
            "creator": {"username": "creator", "image": "avatar.jpg", "badge": "badge-id", "cosmetics": []},
            "user": {
                "cosmetics": [{
                    "data": {"equipped": true},
                    "cosmetic": {
                        "type": "ProfileBackground",
                        "data": {"url": "774d12b3-b264-4712-8484-ddbecf0bb14a", "type": "video"}
                    }
                }]
            }
        });

        let result = extract_creator_cosmetics(&item);
        assert_eq!(result["profileBackground"]["type"], "video");
        assert!(result["profileBackground"]["url"].as_str().unwrap().ends_with(".webm"));
    }

    #[test]
    fn holiday_lights_content_decoration_keeps_texture() {
        let item = json!({
            "user": {
                "cosmetics": [{
                    "cosmetic": {
                        "type": "ContentDecoration",
                        "data": {
                            "type": "holiday-lights",
                            "color": "green",
                            "brightness": 0.5,
                            "cssFrame": "linear-gradient(90deg, #34502B 4%, #7B9971 47%, #34502B 95%)",
                            "texture": {
                                "url": "url('https://image.civitai.com/texture.png')",
                                "size": {"width": 14, "height": 14}
                            }
                        }
                    }
                }]
            }
        });

        let result = extract_cosmetic(&item).unwrap();
        assert_eq!(result["type"], "holiday-lights");
        assert_eq!(result["color"], "green");
        assert_eq!(result["brightness"], 0.5);
        assert_eq!(result["textureUrl"], "https://image.civitai.com/texture.png");
        assert_eq!(result["textureWidth"], 14);
        assert_eq!(result["textureHeight"], 14);
    }
}
