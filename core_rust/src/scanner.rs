use serde_json::json;

pub fn scan_model_dir(dir_path: &str, extensions: &[String]) -> Result<String, String> {
    use std::time::UNIX_EPOCH;
    use walkdir::WalkDir;

    let mut results: Vec<serde_json::Value> = Vec::new();

    for entry in WalkDir::new(dir_path)
        .follow_links(false)
        .max_depth(4)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        if !entry.file_type().is_file() {
            continue;
        }

        let path = entry.path();
        if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            if extensions.iter().any(|e| {
                let pat = e.trim_start_matches('.');
                ext.eq_ignore_ascii_case(pat)
            }) {
                let name = path
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string();
                let meta = entry.metadata().ok();
                let size = meta.as_ref().map(|m| m.len()).unwrap_or(0);
                let modified = meta
                    .and_then(|m| m.modified().ok())
                    .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                    .map(|d| d.as_secs());

                results.push(json!({
                    "path": path.to_string_lossy().to_string(),
                    "name": name,
                    "size": size,
                    "modified": modified,
                }));
            }
        }
    }

    serde_json::to_string(&results).map_err(|e| format!("JSON serialize: {}", e))
}

pub fn clean_orphan_parts(root_dir: &str) -> Result<u32, String> {
    use std::fs;
    use walkdir::WalkDir;

    let mut count = 0u32;
    for entry in WalkDir::new(root_dir)
        .follow_links(false)
        .max_depth(4)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        if !entry.file_type().is_file() {
            continue;
        }
        let path = entry.path();
        if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            if ext.eq_ignore_ascii_case("part") {
                if fs::remove_file(path).is_ok() {
                    count += 1;
                }
            }
        }
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;


    #[test]
    fn scan_model_dir_finds_safetensors() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("test.safetensors");
        fs::write(&p, b"fake model").unwrap();

        let result = scan_model_dir(
            dir.path().to_str().unwrap(),
            &["safetensors".into(), "ckpt".into()],
        )
        .unwrap();
        let items: Vec<serde_json::Value> = serde_json::from_str(&result).unwrap();
        assert_eq!(items.len(), 1);
        assert!(items[0]["name"].as_str().unwrap().contains("test"));
    }

    #[test]
    fn clean_orphan_parts_deletes_part_files() {
        let dir = tempfile::tempdir().unwrap();
        let part_path = dir.path().join("download.part");
        let good_path = dir.path().join("model.safetensors");
        fs::write(&part_path, b"partial").unwrap();
        fs::write(&good_path, b"complete").unwrap();

        let count = clean_orphan_parts(dir.path().to_str().unwrap()).unwrap();
        assert_eq!(count, 1);
        assert!(!part_path.exists());
        assert!(good_path.exists());
    }

    #[test]
    fn clean_orphan_parts_empty_dir() {
        let dir = tempfile::tempdir().unwrap();
        let count = clean_orphan_parts(dir.path().to_str().unwrap()).unwrap();
        assert_eq!(count, 0);
    }
}
