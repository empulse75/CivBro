use pyo3::prelude::*;
use std::path::Path;

mod db;

use db::Database as CivBroDb;

#[pyclass(name = "Database")]
struct PyDatabase {
    inner: Option<CivBroDb>,
}

#[pymethods]
impl PyDatabase {
    #[new]
    fn new() -> PyResult<Self> {
        let db_path = std::env::var("CIVBRO_DB_PATH").unwrap_or_else(|_| {
            let dir = std::env::current_dir()
                .unwrap_or_else(|_| Path::new(".").to_path_buf());
            dir.join("civbro.db").to_string_lossy().to_string()
        });

        match CivBroDb::new(&db_path) {
            Ok(db) => {
                if let Err(e) = db.initialize() {
                    eprintln!("[CivBro] DB init warning: {}", e);
                }
                Ok(PyDatabase { inner: Some(db) })
            }
            Err(e) => {
                eprintln!("[CivBro] Failed to open database: {}", e);
                Ok(PyDatabase { inner: None })
            }
        }
    }

    fn upsert_model(&self, data: &str) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            Ok(db.upsert_model(data).unwrap_or(false))
        } else {
            Ok(false)
        }
    }

    #[pyo3(signature = (query, model_type=None, base_model=None, limit=None))]
    fn search(&self, query: &str, model_type: Option<&str>, base_model: Option<&str>, limit: Option<i64>) -> PyResult<String> {
        if let Some(ref db) = self.inner {
            let results = db
                .search(query, model_type, base_model, limit.unwrap_or(20))
                .unwrap_or_default();
            let json = serde_json::to_string(&results)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            Ok(json)
        } else {
            Ok("[]".to_string())
        }
    }

    fn get_model(&self, id: i64) -> PyResult<Option<String>> {
        if let Some(ref db) = self.inner {
            match db.get_model(id) {
                Ok(Some(data)) => Ok(Some(data)),
                Ok(None) => Ok(None),
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())),
            }
        } else {
            Ok(None)
        }
    }

    fn set_local_path(&self, model_id: i64, path: &str, hash_val: &str, hash_type: &str) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            Ok(db.set_local_path(model_id, path, hash_val, hash_type).unwrap_or(false))
        } else {
            Ok(false)
        }
    }

    fn get_local_models(&self) -> PyResult<String> {
        if let Some(ref db) = self.inner {
            let results = db.get_local_models().unwrap_or_default();
            let json = serde_json::to_string(&results)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            Ok(json)
        } else {
            Ok("[]".to_string())
        }
    }

    fn add_download(&self, data: &str) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            Ok(db.add_download(data).unwrap_or(false))
        } else {
            Ok(false)
        }
    }

    fn get_pending_downloads(&self) -> PyResult<String> {
        if let Some(ref db) = self.inner {
            let results = db.get_pending_downloads().unwrap_or_default();
            let json = serde_json::to_string(&results)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            Ok(json)
        } else {
            Ok("[]".to_string())
        }
    }

    fn update_download_status(&self, id: &str, status: &str) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            Ok(db.update_download_status(id, status).unwrap_or(false))
        } else {
            Ok(false)
        }
    }

    fn get_setting(&self, key: &str) -> PyResult<Option<String>> {
        if let Some(ref db) = self.inner {
            match db.get_setting(key) {
                Ok(val) => Ok(val),
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())),
            }
        } else {
            Ok(None)
        }
    }

    fn set_setting(&self, key: &str, value: &str) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            Ok(db.set_setting(key, value).unwrap_or(false))
        } else {
            Ok(false)
        }
    }

    fn clear_cache(&self) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            Ok(db.clear_cache().unwrap_or(false))
        } else {
            Ok(false)
        }
    }
}

#[pyfunction]
fn compute_file_hash(py: Python<'_>, path: &str, algorithm: &str) -> PyResult<String> {
    use sha2::{Digest, Sha256};
    use std::fs::File;
    use std::io::Read;

    // Release the GIL for the whole hash so a multi-GB checkpoint doesn't block
    // the Python event loop (the caller offloads this to a worker thread).
    py.allow_threads(|| -> PyResult<String> {
        let mut file = File::open(path)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyFileNotFoundError, _>(e.to_string()))?;
        // 1 MB heap buffer — far fewer read syscalls than the old 64 KB buffer.
        let mut buffer = vec![0u8; 1024 * 1024];

        if algorithm == "sha256" {
            let mut hasher = Sha256::new();
            loop {
                let n = file
                    .read(&mut buffer)
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;
                if n == 0 {
                    break;
                }
                hasher.update(&buffer[..n]);
            }
            Ok(hex::encode(hasher.finalize()))
        } else if algorithm == "blake3" {
            let mut hasher = blake3::Hasher::new();
            loop {
                let n = file
                    .read(&mut buffer)
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;
                if n == 0 {
                    break;
                }
                hasher.update(&buffer[..n]);
            }
            Ok(hasher.finalize().to_hex().to_string())
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Unsupported algorithm: {}", algorithm),
            ))
        }
    })
}

#[pyfunction]
fn parse_json_fast(json_str: &str) -> PyResult<String> {
    let value: serde_json::Value = serde_json::from_str(json_str)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let compact = serde_json::to_string(&value)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    Ok(compact)
}

#[pyfunction]
fn scan_model_dir(py: Python<'_>, dir_path: &str, extensions: Vec<String>) -> PyResult<String> {
    use std::time::UNIX_EPOCH;
    use walkdir::WalkDir;

    // Directory walking + stat is I/O bound; release the GIL so the Python event
    // loop stays responsive while this runs in a worker thread.
    py.allow_threads(|| -> PyResult<String> {
        let mut results: Vec<serde_json::Value> = Vec::new();

        for entry in WalkDir::new(dir_path).max_depth(4).into_iter().filter_map(|e| e.ok()) {
            if !entry.file_type().is_file() {
                continue;
            }

            let path = entry.path();
            if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                if extensions.iter().any(|e| e.eq_ignore_ascii_case(ext)) {
                    let name = path
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    let (size, modified) = match entry.metadata() {
                        Ok(m) => {
                            let s = m.len();
                            let mod_time = m
                                .modified()
                                .ok()
                                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                                .map(|d| d.as_secs());
                            (s, mod_time)
                        }
                        Err(_) => (0, None),
                    };

                    results.push(serde_json::json!({
                        "path": path.to_string_lossy().to_string(),
                        "name": name,
                        "size": size,
                        "modified": modified,
                    }));
                }
            }
        }

        let json = serde_json::to_string(&results)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok(json)
    })
}

#[pyfunction]
fn clean_orphan_parts(py: Python<'_>, root_dir: &str) -> PyResult<u32> {
    use walkdir::WalkDir;
    use std::fs;

    py.allow_threads(|| -> PyResult<u32> {
        let mut count = 0u32;
        for entry in WalkDir::new(root_dir).into_iter().filter_map(|e| e.ok()) {
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
    })
}

#[pymodule]
fn civbro_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyDatabase>()?;
    m.add_function(wrap_pyfunction!(compute_file_hash, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json_fast, m)?)?;
    m.add_function(wrap_pyfunction!(scan_model_dir, m)?)?;
    m.add_function(wrap_pyfunction!(clean_orphan_parts, m)?)?;
    Ok(())
}
