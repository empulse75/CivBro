use serde_json::{json, Value};

use super::cosmetics::{extract_cosmetic, extract_creator_cosmetics};
use super::optimize_image_url;

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
        let arr: Vec<Value> = serde_json::from_str(data_str)
            .map_err(|e| format!("JSON parse: {}", e))?;
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
        let count = meta
            .and_then(|m| m.get("items").and_then(|v| v.as_i64()))
            .unwrap_or(1);

        let mut items: Vec<Value> = Vec::new();
        for model_i in 0..count as usize {
            let base = 3 + model_i * stride;
            let mut obj = serde_json::Map::new();
            for (key, vi) in tpl.iter() {
                if let Some(vi) = vi.as_i64() {
                    let idx = if model_i == 0 {
                        vi as usize
                    } else {
                        base + vi as usize
                    };
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
    for key in &["avatarDeco", "badge", "profileBackground", "nameplate"] {
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
                let obj = v.as_object();
                let requires = obj
                    .and_then(|o| o.get("requiresBuzz"))
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let licensing = obj
                    .and_then(|o| o.get("licensingFeeType"))
                    .and_then(|v| v.as_str())
                    .map(|s| s == "PerImageBuzz")
                    .unwrap_or(false);
                requires || licensing
            })
        })
        .unwrap_or(false);
    if has_buzz {
        extras.insert("hasBuzz".into(), json!(true));
    }

    extras.insert(
        "name".into(),
        item.get("name").cloned().unwrap_or(json!("")),
    );
    extras.insert(
        "modelType".into(),
        item.get("modelType")
            .or(item.get("type"))
            .cloned()
            .unwrap_or(json!("")),
    );
    extras.insert(
        "nsfw".into(),
        json!(item
            .get("nsfw")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)),
    );
    extras.insert(
        "stats".into(),
        item.get("stats").cloned().unwrap_or(json!({})),
    );

    let creator = ["creator", "user"]
        .iter()
        .filter_map(|key| item.get(*key).and_then(|v| v.as_object()))
        .find(|creator| {
            creator
                .get("username")
                .and_then(|v| v.as_str())
                .is_some_and(|username| !username.is_empty())
        })
        .map(|c| {
            json!({
                "username": c.get("username").and_then(|v| v.as_str()).unwrap_or(""),
                "image": c.get("image").and_then(|v| v.as_str())
                    .or_else(|| c.get("profilePicture").and_then(|v| v.as_str()))
                    .unwrap_or(""),
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

    if let Some(first_img) = imgs.first().and_then(|v| v.as_object()) {
        let img_url = first_img
            .get("url")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let img_type = first_img
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("image");
        let mut im = Value::Object(first_img.clone());
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
    if extras
        .get("hasBuzz")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
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
        "profileBackground": extras.get("profileBackground"),
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
                        "sizeKB": c.get("sizeKB").filter(|v| v.is_number()).cloned().unwrap_or(json!(0)),
                        "required": c.get("isRequired").and_then(|v| v.as_bool()).unwrap_or(true),
                        "downloadUrl": format!("https://civitai.com/api/download/models/{}", vid),
                    }))
                })
                .collect()
        })
        .unwrap_or_default();
    serde_json::to_string(&deps).map_err(|e| format!("JSON serialize: {}", e))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn trpc_items_handles_dict_form() {
        let resp = json!({
            "result": {"data": {"json": {"items": [{"id": 1}], "nextCursor": null}}}
        });
        let out = parse_trpc_items(&resp.to_string()).unwrap();
        let items: Vec<Value> = serde_json::from_str(&out).unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["id"], 1);
    }

    #[test]
    fn extras_merge_respects_null_and_existing_fields() {
        let slim = json!({"id": 1, "publishedAt": "2024-01-01"});
        let extras = json!({"availability": "EarlyAccess", "publishedAt": "2025-01-01", "createdAt": "2024-06-01", "hasBuzz": true});
        let merged =
            apply_extras_to_slim(&slim.to_string(), &extras.to_string()).unwrap();
        let val: Value = serde_json::from_str(&merged).unwrap();
        assert_eq!(val["availability"], "EarlyAccess");
        assert_eq!(
            val["publishedAt"],
            "2024-01-01",
            "existing value must win"
        );
        assert_eq!(
            val["createdAt"],
            "2024-06-01",
            "missing value filled from extras"
        );
        assert_eq!(val["hasBuzz"], true);
    }

    #[test]
    fn build_trpc_extras_includes_buzz_flag() {
        let item = json!({
            "id": 1, "name": "buzz-model",
            "modelType": "Checkpoint", "creator": {"username": "u","image":""},
            "modelVersions": [{"id": 1, "requiresBuzz": true}]
        });
        let result = build_trpc_extras(&item.to_string()).unwrap();
        let extras: Value = serde_json::from_str(&result).unwrap();
        assert_eq!(extras["hasBuzz"], true);
    }

    #[test]
    fn build_trpc_extras_uses_user_when_creator_is_missing() {
        let item = json!({
            "id": 22922,
            "name": "Lyriel",
            "modelType": "Checkpoint",
            "creator": null,
            "user": {"username": "civitai", "image": null, "profilePicture": "avatar.webp"},
            "modelVersions": []
        });
        let result = build_trpc_extras(&item.to_string()).unwrap();
        let extras: Value = serde_json::from_str(&result).unwrap();
        assert_eq!(extras["creator"]["username"], "civitai");
        assert_eq!(extras["creator"]["image"], "avatar.webp");
    }

}
