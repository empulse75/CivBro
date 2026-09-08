use pyo3::prelude::*;
use std::path::Path;

mod db;
mod hash;
mod license;
mod parse;
mod scanner;

use db::Database as CivBroDb;

// ---------------------------------------------------------------------------
// Macro to reduce repeated PyDatabase null-guard boilerplate for bool methods.
// ---------------------------------------------------------------------------
macro_rules! with_db_bool {
    ($self:expr, $method:ident ($($arg:expr),*)) => {{
        if let Some(ref db) = $self.inner {
            db.$method($($arg),*).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())
            })
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Database not available",
            ))
        }
    }};
}

// ---------------------------------------------------------------------------
// PyDatabase — thin PyO3 wrapper around db::Database
// ---------------------------------------------------------------------------
#[pyclass(name = "Database")]
struct PyDatabase {
    inner: Option<CivBroDb>,
}

#[pymethods]
impl PyDatabase {
    #[new]
    #[pyo3(signature = (path = None))]
    fn new(path: Option<&str>) -> PyResult<Self> {
        let db_path = path
            .map(|p| p.to_string())
            .or_else(|| std::env::var("CIVBRO_DB_PATH").ok())
            .unwrap_or_else(|| {
                let dir = std::env::current_dir()
                    .unwrap_or_else(|_| Path::new(".").to_path_buf());
                dir.join("civbro.db").to_string_lossy().to_string()
            });

        match CivBroDb::new(&db_path) {
            Ok(db) => {
                db.initialize().map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
                        "Failed to initialize database: {}",
                        e
                    ))
                })?;
                Ok(PyDatabase { inner: Some(db) })
            }
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
                "Failed to open database: {}",
                e
            ))),
        }
    }

    fn upsert_model(&self, data: &str) -> PyResult<bool> {
        with_db_bool!(self, upsert_model(data))
    }

    #[pyo3(signature = (query, model_type = None, base_model = None, limit = None))]
    fn search(
        &self,
        query: &str,
        model_type: Option<&str>,
        base_model: Option<&str>,
        limit: Option<i64>,
    ) -> PyResult<String> {
        if let Some(ref db) = self.inner {
            let results = db
                .search(query, model_type, base_model, limit.unwrap_or(20))
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            serde_json::to_string(&results)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Database not available",
            ))
        }
    }

    fn get_model(&self, id: i64) -> PyResult<Option<String>> {
        if let Some(ref db) = self.inner {
            match db.get_model(id) {
                Ok(Some(data)) => Ok(Some(data)),
                Ok(None) => Ok(None),
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    e.to_string(),
                )),
            }
        } else {
            Ok(None)
        }
    }

    fn set_local_path(
        &self,
        model_id: i64,
        path: &str,
        hash_val: &str,
        hash_type: &str,
    ) -> PyResult<bool> {
        with_db_bool!(self, set_local_path(model_id, path, hash_val, hash_type))
    }

    fn get_local_models(&self) -> PyResult<String> {
        if let Some(ref db) = self.inner {
            let results = db
                .get_local_models()
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            serde_json::to_string(&results)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Database not available",
            ))
        }
    }

    fn add_download(&self, data: &str) -> PyResult<bool> {
        with_db_bool!(self, add_download(data))
    }

    fn get_pending_downloads(&self) -> PyResult<String> {
        if let Some(ref db) = self.inner {
            let results = db
                .get_pending_downloads()
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            serde_json::to_string(&results)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Database not available",
            ))
        }
    }

    fn update_download_status(&self, id: &str, status: &str) -> PyResult<bool> {
        with_db_bool!(self, update_download_status(id, status))
    }

    fn get_setting(&self, key: &str) -> PyResult<Option<String>> {
        if let Some(ref db) = self.inner {
            match db.get_setting(key) {
                Ok(val) => Ok(val),
                Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    e.to_string(),
                )),
            }
        } else {
            Ok(None)
        }
    }

    fn set_setting(&self, key: &str, value: &str) -> PyResult<bool> {
        with_db_bool!(self, set_setting(key, value))
    }

    fn ingest_license(&self, key: &str) -> PyResult<String> {
        match license::validate_license_key(key) {
            Ok(()) => {
                if let Some(ref db) = self.inner {
                    db.set_setting("license_key", key)
                        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
                    db.set_setting(
                        "license_ingested_at",
                        &std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_secs()
                            .to_string(),
                    )
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
                }
                Ok("ok".into())
            }
            Err(e) => Ok(format!("invalid:{}", e)),
        }
    }

    fn is_license_active(&self) -> PyResult<bool> {
        if let Some(ref db) = self.inner {
            match db.get_setting("license_key") {
                Ok(Some(key)) if !key.is_empty() => {
                    Ok(license::validate_license_key(&key).is_ok())
                }
                _ => Ok(false),
            }
        } else {
            Ok(false)
        }
    }

    fn clear_cache(&self) -> PyResult<bool> {
        with_db_bool!(self, clear_cache())
    }
}

// ---------------------------------------------------------------------------
// PyO3 freestanding functions
// ---------------------------------------------------------------------------

#[pyfunction]
fn parse_models(json_items: &str, style: &str) -> PyResult<String> {
    parse::parse_models_batch(json_items, style)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn parse_trpc_response(response_json: &str) -> PyResult<String> {
    parse::parse_trpc_items(response_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn build_extras(item_json: &str) -> PyResult<String> {
    parse::build_trpc_extras(item_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn merge_extras_into_slim(slim_json: &str, extras_json: &str) -> PyResult<String> {
    parse::apply_extras_to_slim(slim_json, extras_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn build_slim_from_extras(extras_json: &str, model_id: i64) -> PyResult<String> {
    parse::make_slim_from_trpc(extras_json, model_id)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn optimize_cdn_url(url: &str, width: u32, image_type: &str) -> PyResult<String> {
    Ok(parse::optimize_image_url(url, width, image_type))
}

#[pyfunction]
fn file_subdir(file_type: &str, name: &str, model_type: &str) -> PyResult<String> {
    Ok(parse::subdir_for_type(file_type, name, model_type))
}

#[pyfunction]
fn parse_deps(trpc_json: &str) -> PyResult<String> {
    parse::parse_dependencies(trpc_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn build_version_list(model_json: &str) -> PyResult<String> {
    parse::build_version_list(model_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn build_version_detail(rest_json: &str, trpc_json: &str) -> PyResult<String> {
    parse::build_version_detail(rest_json, trpc_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pyfunction]
fn compute_file_hash(py: Python<'_>, path: &str, algorithm: &str) -> PyResult<String> {
    py.allow_threads(|| -> PyResult<String> {
        hash::compute_file_hash(path, algorithm)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
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
    py.allow_threads(|| -> PyResult<String> {
        scanner::scan_model_dir(dir_path, &extensions)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
    })
}

#[pyfunction]
fn clean_orphan_parts(py: Python<'_>, root_dir: &str) -> PyResult<u32> {
    py.allow_threads(|| -> PyResult<u32> {
        scanner::clean_orphan_parts(root_dir)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
    })
}

#[pyfunction]
fn validate_license_key(key: &str) -> PyResult<String> {
    match license::validate_license_key(key) {
        Ok(()) => Ok("valid".into()),
        Err(e) => Ok(format!("invalid:{}", e)),
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------
#[pymodule]
fn civbro_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyDatabase>()?;
    m.add_function(wrap_pyfunction!(compute_file_hash, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json_fast, m)?)?;
    m.add_function(wrap_pyfunction!(scan_model_dir, m)?)?;
    m.add_function(wrap_pyfunction!(clean_orphan_parts, m)?)?;
    m.add_function(wrap_pyfunction!(parse_models, m)?)?;
    m.add_function(wrap_pyfunction!(parse_trpc_response, m)?)?;
    m.add_function(wrap_pyfunction!(build_extras, m)?)?;
    m.add_function(wrap_pyfunction!(merge_extras_into_slim, m)?)?;
    m.add_function(wrap_pyfunction!(build_slim_from_extras, m)?)?;
    m.add_function(wrap_pyfunction!(optimize_cdn_url, m)?)?;
    m.add_function(wrap_pyfunction!(file_subdir, m)?)?;
    m.add_function(wrap_pyfunction!(parse_deps, m)?)?;
    m.add_function(wrap_pyfunction!(build_version_list, m)?)?;
    m.add_function(wrap_pyfunction!(build_version_detail, m)?)?;
    m.add_function(wrap_pyfunction!(validate_license_key, m)?)?;
    Ok(())
}
