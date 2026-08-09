use serde_json::{json, Value};

use super::models::parse_model_rich;
use super::optimize_image_url;

// ---------------------------------------------------------------------------
// File / image mapping
// ---------------------------------------------------------------------------
fn map_api_file(f: &Value) -> Value {
    let meta = f.get("metadata");
    let meta_str = |key: &str| {
        meta.and_then(|m| m.get(key))
            .and_then(|v| v.as_str())
            .unwrap_or("")
    };
    json!({
        "id": f.get("id"),
        "name": f.get("name"),
        "sizeKB": f.get("sizeKB").filter(|v| v.is_number()).cloned().unwrap_or(json!(0)),
        "type": f.get("type").and_then(|v| v.as_str()).unwrap_or(""),
        "primary": f.get("primary").and_then(|v| v.as_bool()).unwrap_or(false),
        "format": meta_str("format"),
        "fp": meta_str("fp"),
        "sizeType": meta_str("size"),
        "hashes": f.get("hashes").cloned().unwrap_or(json!({})),
        "downloadUrl": f.get("downloadUrl").and_then(|v| v.as_str()).unwrap_or(""),
        "scannedAt": f.get("scannedAt"),
        "pickleScanResult": f.get("pickleScanResult"),
        "virusScanResult": f.get("virusScanResult"),
    })
}

fn map_files(data: &Value) -> Vec<Value> {
    data.get("files")
        .and_then(|v| v.as_array())
        .map(|fs| fs.iter().map(map_api_file).collect())
        .unwrap_or_default()
}

fn map_image_array(imgs: &[Value], width: u32) -> Vec<Value> {
    imgs.iter()
        .map(|img| {
            let mut img = img.clone();
            if let Some(url) = img.get("url").and_then(|v| v.as_str()).map(String::from) {
                let img_type = img
                    .get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("image");
                img["url"] = json!(optimize_image_url(&url, width, img_type));
            }
            img
        })
        .collect()
}

fn ea_ends_at(v: &Value) -> Value {
    v.get("earlyAccessEndsAt")
        .filter(|x| !x.is_null())
        .cloned()
        .unwrap_or_else(|| {
            v.get("earlyAccessConfig")
                .and_then(|c| c.get("timeframe"))
                .cloned()
                .unwrap_or(Value::Null)
        })
}

fn map_version_summary(mv: &Value) -> Value {
    let images = mv
        .get("images")
        .and_then(|v| v.as_array())
        .map(|a| map_image_array(a, 450))
        .unwrap_or_default();
    json!({
        "id": mv.get("id"),
        "name": mv.get("name"),
        "baseModel": mv.get("baseModel"),
        "trainedWords": mv.get("trainedWords").cloned().unwrap_or(json!([])),
        "images": images,
        "downloadUrl": mv.get("downloadUrl").and_then(|v| v.as_str()).unwrap_or(""),
        "files": map_files(mv),
        "createdAt": mv.get("createdAt"),
        "availability": mv.get("availability").and_then(|v| v.as_str()).unwrap_or("Public"),
        "buzzCost": mv.get("buzz"),
        "stats": mv.get("stats").cloned().unwrap_or(json!({})),
        "description": mv.get("description").and_then(|v| v.as_str()).unwrap_or(""),
        "earlyAccessEndsAt": ea_ends_at(mv),
    })
}

// ---------------------------------------------------------------------------
// Version list builder
// ---------------------------------------------------------------------------
pub fn build_version_list(model_json: &str) -> Result<String, String> {
    let data: Value =
        serde_json::from_str(model_json).map_err(|e| format!("JSON parse: {}", e))?;
    let versions: Vec<Value> = data
        .get("modelVersions")
        .and_then(|v| v.as_array())
        .map(|mvs| mvs.iter().map(map_version_summary).collect())
        .unwrap_or_default();
    serde_json::to_string(&json!({"modelId": data.get("id"), "versions": versions}))
        .map_err(|e| format!("JSON serialize: {}", e))
}

// ---------------------------------------------------------------------------
// ISO timestamp utilities
// ---------------------------------------------------------------------------
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

/// Parse the leading 'YYYY-MM-DDTHH:MM:SS' of an ISO-8601 UTC timestamp.
pub fn iso_to_epoch(s: &str) -> Option<i64> {
    let n = |r: &str| r.parse::<i64>().ok();
    if s.len() < 19 {
        return None;
    }
    let (date, time) = s.split_at(10);
    let mut dp = date.split('-');
    let (y, m, d) = (
        dp.next().and_then(n)?,
        dp.next().and_then(n)?,
        dp.next().and_then(n)?,
    );
    let mut tp = time[1..].split(':');
    let hh = tp.next().and_then(n)?;
    let mm = tp.next().and_then(n)?;
    let ss_raw = tp.next()?;
    let ss_clean = ss_raw.split('.').next().unwrap_or(ss_raw);
    let ss = n(&ss_clean.replace(['Z', 'z', '+'], ""))?;
    Some(days_from_civil(y, m, d) * 86400 + hh * 3600 + mm * 60 + ss)
}

fn effective_availability(data: &Value) -> String {
    let availability = data
        .get("availability")
        .and_then(|v| v.as_str())
        .unwrap_or("Public");
    if availability != "Public" {
        return availability.to_string();
    }
    let ea_ends = data
        .get("earlyAccessEndsAt")
        .and_then(|v| v.as_str());
    match ea_ends.and_then(iso_to_epoch) {
        Some(t) if t > now_epoch() => "EarlyAccess".to_string(),
        _ => "Public".to_string(),
    }
}

fn now_epoch() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// Version detail builder
// ---------------------------------------------------------------------------
pub fn build_version_detail(rest_json: &str, trpc_json: &str) -> Result<String, String> {
    let data: Value =
        serde_json::from_str(rest_json).map_err(|e| format!("JSON parse: {}", e))?;
    let trpc: Value =
        serde_json::from_str(trpc_json).map_err(|e| format!("JSON parse: {}", e))?;

    let model_obj = data
        .get("model")
        .filter(|m| m.is_object())
        .cloned()
        .unwrap_or(json!({}));
    let creator = model_obj
        .get("creator")
        .filter(|c| c.is_object())
        .cloned()
        .unwrap_or(json!({}));
    let images = data
        .get("images")
        .and_then(|v| v.as_array())
        .map(|a| map_image_array(a, 450))
        .unwrap_or_default();
    let deps: Value =
        serde_json::from_str(&crate::parse::trpc::parse_dependencies(trpc_json)?)
            .map_err(|e| format!("JSON parse: {}", e))?;
    let buzz = data
        .get("buzz")
        .or_else(|| data.get("buzzCost"))
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let trpc_or_model = |key: &str| {
        trpc.get(key)
            .filter(|v| !v.is_null())
            .cloned()
            .unwrap_or_else(|| model_obj.get(key).cloned().unwrap_or(Value::Null))
    };

    let detail = json!({
        "id": data.get("id"),
        "modelId": data.get("modelId"),
        "name": data.get("name"),
        "baseModel": data.get("baseModel"),
        "trainedWords": data.get("trainedWords").cloned().unwrap_or(json!([])),
        "images": images,
        "downloadUrl": data.get("downloadUrl").and_then(|v| v.as_str()).unwrap_or(""),
        "dependencies": deps,
        "air": trpc.get("air").and_then(|v| v.as_str()).unwrap_or(""),
        "clipSkip": trpc.get("clipSkip"),
        "epochs": trpc.get("epochs"),
        "steps": trpc.get("steps"),
        "tensorType": trpc_or_model("tensorType"),
        "modelSize": trpc_or_model("modelSize"),
        "availability": effective_availability(&data),
        "earlyAccessEndsAt": ea_ends_at(&data),
        "buzzCost": buzz,
        "allowCommercialUse": model_obj.get("allowCommercialUse"),
        "allowDerivatives": model_obj.get("allowDerivatives"),
        "allowNoCredit": model_obj.get("allowNoCredit"),
        "allowDifferentLicense": model_obj.get("allowDifferentLicense"),
        "baseModels": model_obj.get("baseModels").cloned().unwrap_or(json!([])),
        "creator": {
            "username": creator.get("username").and_then(|v| v.as_str()).unwrap_or(""),
            "image": creator.get("image").and_then(|v| v.as_str()).unwrap_or(""),
            "createdAt": creator.get("createdAt"),
        },
        "updatedAt": data.get("updatedAt"),
        "files": map_files(&data),
        "createdAt": data.get("createdAt"),
        "stats": data.get("stats").cloned().unwrap_or(json!({})),
        "description": data.get("description").and_then(|v| v.as_str()).unwrap_or(""),
        "model": parse_model_rich(&model_obj),
    });
    serde_json::to_string(&detail).map_err(|e| format!("JSON serialize: {}", e))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn api_file_preserves_fractional_size_kb() {
        let mapped = map_api_file(&json!({
            "id": 1,
            "name": "model.safetensors",
            "sizeKB": 1023.75,
            "type": "Model"
        }));
        assert_eq!(mapped["sizeKB"], 1023.75);
    }

    #[test]
    fn iso_to_epoch_converts_utc_timestamps() {
        let past = iso_to_epoch("2020-01-01T00:00:00Z").unwrap();
        let future = iso_to_epoch("2030-01-01T00:00:00Z").unwrap();
        assert!(future > past);
        assert_eq!(
            iso_to_epoch("2024-06-01T12:00:00Z"),
            iso_to_epoch("2024-06-01T12:00:00.123Z")
        );
        assert_eq!(iso_to_epoch("short"), None);
        assert_eq!(iso_to_epoch(""), None);
    }

    #[test]
    fn version_list_maps_files_and_images() {
        let raw = json!({
            "id": 42,
            "modelVersions": [{
                "id": 100,
                "name": "v1",
                "baseModel": "Pony",
                "images": [{"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/a/original=true/p.png", "type": "image"}],
                "files": [{"id": 7, "name": "m.safetensors", "sizeKB": 1024, "type": "Model", "primary": true, "metadata": {"format": "SafeTensor", "fp": "fp16"}, "downloadUrl": "https://civitai.com/api/download/models/100"}],
                "availability": "Public",
                "buzz": 500,
                "stats": {"downloadCount": 99},
            }]
        });
        let out = build_version_list(&raw.to_string()).unwrap();
        let result: Value = serde_json::from_str(&out).unwrap();
        assert_eq!(result["modelId"], 42);
        let v = &result["versions"][0];
        assert_eq!(v["id"], 100);
        assert!(v["images"][0]["url"]
            .as_str()
            .unwrap()
            .contains("width=450"));
        assert_eq!(v["files"][0]["format"], "SafeTensor");
        assert_eq!(v["files"][0]["fp"], "fp16");
        assert_eq!(v["buzzCost"], 500);
        assert_eq!(v["stats"]["downloadCount"], 99);
    }

    #[test]
    fn version_detail_merges_rest_and_trpc() {
        let rest = json!({
            "id": 200, "modelId": 42, "name": "v2", "baseModel": "SDXL 1.0",
            "downloadUrl": "https://civitai.com/api/download/models/200",
            "availability": "EarlyAccess",
            "earlyAccessEndsAt": "2030-01-01T00:00:00Z",
            "images": [{"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/x/original=true/i.png", "type": "image"}],
            "files": [{"id": 8, "name": "m.safetensors", "sizeKB": 2048, "type": "Model", "metadata": {"format": "SafeTensor"}}],
            "model": {"id": 42, "allowCommercialUse": true, "allowNoCredit": false}
        });
        let trpc = json!({ "air": "Pony+SDXL", "clipSkip": 2, "epochs": 50, "steps": 5000, "tensorType": "fp16", "modelSize": "large", "linkedComponents": [] });
        let out =
            build_version_detail(&rest.to_string(), &trpc.to_string()).unwrap();
        let result: Value = serde_json::from_str(&out).unwrap();
        assert_eq!(result["id"], 200);
        assert_eq!(result["air"], "Pony+SDXL");
        assert_eq!(result["clipSkip"], 2);
        assert_eq!(result["availability"], "EarlyAccess");
        assert!(result["earlyAccessEndsAt"]
            .as_str()
            .unwrap()
            .contains("2030"));
        assert_eq!(result["allowCommercialUse"], true);
        assert_eq!(result["model"]["id"], 42);
        assert_eq!(result["files"][0]["format"], "SafeTensor");
    }
}
