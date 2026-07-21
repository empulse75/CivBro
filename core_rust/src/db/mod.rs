use rusqlite::{params, Connection, Result as SqlResult};
use serde_json::{json, Value};
use std::sync::Mutex;

pub struct Database {
    conn: Mutex<Connection>,
}

impl Database {
    pub fn new(path: &str) -> SqlResult<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL; PRAGMA cache_size=-20000;")?;
        Ok(Database {
            conn: Mutex::new(conn),
        })
    }

    pub fn initialize(&self) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();

        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY,
                civitai_id INTEGER UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                model_type TEXT NOT NULL DEFAULT '',
                base_model TEXT NOT NULL DEFAULT '',
                nsfw INTEGER NOT NULL DEFAULT 0,
                allow_no_credit INTEGER NOT NULL DEFAULT 1,
                allow_derivatives INTEGER NOT NULL DEFAULT 1,
                allow_commercial_use INTEGER NOT NULL DEFAULT 1,
                creator_name TEXT NOT NULL DEFAULT '',
                creator_image TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                images TEXT NOT NULL DEFAULT '[]',
                model_versions TEXT NOT NULL DEFAULT '[]',
                raw_stats TEXT NOT NULL DEFAULT '{}',
                raw_data TEXT NOT NULL DEFAULT '{}',
                local_path TEXT NOT NULL DEFAULT '',
                local_hash TEXT NOT NULL DEFAULT '',
                local_hash_type TEXT NOT NULL DEFAULT '',
                local_scan_time INTEGER NOT NULL DEFAULT 0,
                cached_at INTEGER NOT NULL DEFAULT (unixepoch()),
                updated_at INTEGER NOT NULL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS download_queue (
                id TEXT PRIMARY KEY,
                model_id INTEGER,
                version_id INTEGER,
                file_id INTEGER,
                file_name TEXT NOT NULL DEFAULT '',
                download_url TEXT NOT NULL DEFAULT '',
                download_path TEXT NOT NULL DEFAULT '',
                model_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                bytes_total INTEGER NOT NULL DEFAULT 0,
                bytes_downloaded INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                updated_at INTEGER NOT NULL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL DEFAULT (unixepoch())
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS models_fts USING fts5(
                name,
                description,
                tags,
                creator_name,
                content='models',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS models_ai AFTER INSERT ON models BEGIN
                INSERT INTO models_fts(rowid, name, description, tags, creator_name)
                VALUES (new.id, new.name, new.description, new.tags, new.creator_name);
            END;

            CREATE TRIGGER IF NOT EXISTS models_ad AFTER DELETE ON models BEGIN
                INSERT INTO models_fts(models_fts, rowid, name, description, tags, creator_name)
                VALUES ('delete', old.id, old.name, old.description, old.tags, old.creator_name);
            END;

            CREATE TRIGGER IF NOT EXISTS models_au AFTER UPDATE ON models BEGIN
                INSERT INTO models_fts(models_fts, rowid, name, description, tags, creator_name)
                VALUES ('delete', old.id, old.name, old.description, old.tags, old.creator_name);
                INSERT INTO models_fts(rowid, name, description, tags, creator_name)
                VALUES (new.id, new.name, new.description, new.tags, new.creator_name);
            END;

            CREATE INDEX IF NOT EXISTS idx_models_local_path ON models(local_path);
            CREATE INDEX IF NOT EXISTS idx_models_model_type ON models(model_type);
            CREATE INDEX IF NOT EXISTS idx_models_base_model ON models(base_model);
            CREATE INDEX IF NOT EXISTS idx_models_updated_at ON models(updated_at);
            CREATE INDEX IF NOT EXISTS idx_download_queue_status ON download_queue(status);
            ",
        )?;

        Ok(())
    }

    pub fn upsert_model(&self, data: &str) -> SqlResult<bool> {
        let value: Value =
            serde_json::from_str(data).unwrap_or_else(|_| json!({}));

        let civitai_id = value["id"].as_i64().unwrap_or(0);
        if civitai_id == 0 {
            return Ok(false);
        }

        let name = value["name"].as_str().unwrap_or("").to_string();
        let description = value["description"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let model_type = value["modelType"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let base_model = value["baseModel"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let nsfw = if value["nsfw"].as_bool().unwrap_or(false) {
            1
        } else {
            0
        };
        let creator_name = value["creator"]["username"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let creator_image = value["creator"]["image"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let tags = serde_json::to_string(&value["tags"]).unwrap_or_else(|_| "[]".to_string());
        let images = serde_json::to_string(&value["images"]).unwrap_or_else(|_| "[]".to_string());
        let model_versions = serde_json::to_string(&value["modelVersions"])
            .unwrap_or_else(|_| "[]".to_string());
        let raw_stats = serde_json::to_string(&value["stats"]).unwrap_or_else(|_| "{}".to_string());
        let raw_data = data.to_string();

        let conn = self.conn.lock().unwrap();

        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM models WHERE civitai_id = ?1",
            params![civitai_id],
            |row| row.get(0),
        )?;

        if count > 0 {
            conn.execute(
                "UPDATE models SET
                    name = ?2, description = ?3, model_type = ?4, base_model = ?5,
                    nsfw = ?6, creator_name = ?7, creator_image = ?8,
                    tags = ?9, images = ?10, model_versions = ?11,
                    raw_stats = ?12, raw_data = ?13, updated_at = unixepoch()
                 WHERE civitai_id = ?1",
                params![
                    civitai_id,
                    name,
                    description,
                    model_type,
                    base_model,
                    nsfw,
                    creator_name,
                    creator_image,
                    tags,
                    images,
                    model_versions,
                    raw_stats,
                    raw_data,
                ],
            )?;
        } else {
            conn.execute(
                "INSERT INTO models (
                    civitai_id, name, description, model_type, base_model,
                    nsfw, creator_name, creator_image, tags, images,
                    model_versions, raw_stats, raw_data
                ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
                params![
                    civitai_id,
                    name,
                    description,
                    model_type,
                    base_model,
                    nsfw,
                    creator_name,
                    creator_image,
                    tags,
                    images,
                    model_versions,
                    raw_stats,
                    raw_data,
                ],
            )?;
        }

        Ok(true)
    }

    pub fn search(
        &self,
        query: &str,
        model_type: Option<&str>,
        base_model: Option<&str>,
        limit: i64,
    ) -> SqlResult<Vec<Value>> {
        let conn = self.conn.lock().unwrap();

        let mut results: Vec<Value> = Vec::new();
        let limit = limit.min(100).max(1);

        if query.is_empty() && model_type.is_none() && base_model.is_none() {
            let mut stmt = conn.prepare(
                "SELECT raw_data FROM models ORDER BY updated_at DESC LIMIT ?1",
            )?;
            let rows = stmt.query_map(params![limit], |row| {
                let raw: String = row.get(0)?;
                Ok(raw)
            })?;

            for row in rows {
                if let Ok(raw) = row {
                    if let Ok(val) = serde_json::from_str::<Value>(&raw) {
                        results.push(val);
                    }
                }
            }
            return Ok(results);
        }

        if !query.is_empty() && model_type.is_some() {
            let mut stmt = conn.prepare(
                "SELECT m.raw_data FROM models m
                 JOIN models_fts fts ON m.id = fts.rowid
                 WHERE models_fts MATCH ?1 AND m.model_type = ?2
                 ORDER BY rank LIMIT ?3",
            )?;
            let ft_query = query
                .split_whitespace()
                .map(|w| format!("{}*", w))
                .collect::<Vec<_>>()
                .join(" ");
            let rows = stmt.query_map(
                params![ft_query, model_type.unwrap_or(""), limit],
                |row| {
                    let raw: String = row.get(0)?;
                    Ok(raw)
                },
            )?;

            for row in rows {
                if let Ok(raw) = row {
                    if let Ok(val) = serde_json::from_str::<Value>(&raw) {
                        results.push(val);
                    }
                }
            }
            return Ok(results);
        }

        if !query.is_empty() {
            let mut stmt = conn.prepare(
                "SELECT m.raw_data FROM models m
                 JOIN models_fts fts ON m.id = fts.rowid
                 WHERE models_fts MATCH ?1
                 ORDER BY rank LIMIT ?2",
            )?;
            let ft_query = query
                .split_whitespace()
                .map(|w| format!("{}*", w))
                .collect::<Vec<_>>()
                .join(" ");
            let rows = stmt.query_map(params![ft_query, limit], |row| {
                let raw: String = row.get(0)?;
                Ok(raw)
            })?;

            for row in rows {
                if let Ok(raw) = row {
                    if let Ok(val) = serde_json::from_str::<Value>(&raw) {
                        results.push(val);
                    }
                }
            }
            return Ok(results);
        }

        let mut sql = "SELECT raw_data FROM models WHERE 1=1".to_string();
        let mut param_values: Vec<Box<dyn rusqlite::types::ToSql>> = Vec::new();

        if let Some(mt) = model_type {
            sql.push_str(" AND model_type = ?");
            param_values.push(Box::new(mt.to_string()));
        }

        if let Some(bm) = base_model {
            sql.push_str(" AND base_model = ?");
            param_values.push(Box::new(bm.to_string()));
        }

        sql.push_str(&format!(
            " ORDER BY updated_at DESC LIMIT {}",
            limit
        ));

        let mut stmt = conn.prepare(&sql)?;
        let param_refs: Vec<&dyn rusqlite::types::ToSql> =
            param_values.iter().map(|p| p.as_ref()).collect();

        let rows = stmt.query_map(param_refs.as_slice(), |row| {
            let raw: String = row.get(0)?;
            Ok(raw)
        })?;

        for row in rows {
            if let Ok(raw) = row {
                if let Ok(val) = serde_json::from_str::<Value>(&raw) {
                    results.push(val);
                }
            }
        }

        Ok(results)
    }

    pub fn get_model(&self, id: i64) -> SqlResult<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let result: SqlResult<String> = conn.query_row(
            "SELECT raw_data FROM models WHERE civitai_id = ?1",
            params![id],
            |row| row.get(0),
        );

        match result {
            Ok(data) => Ok(Some(data)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e),
        }
    }

    pub fn set_local_path(
        &self,
        model_id: i64,
        path: &str,
        hash_val: &str,
        hash_type: &str,
    ) -> SqlResult<bool> {
        let conn = self.conn.lock().unwrap();
        let affected = conn.execute(
            "UPDATE models SET local_path = ?2, local_hash = ?3, local_hash_type = ?4, local_scan_time = unixepoch() WHERE civitai_id = ?1",
            params![model_id, path, hash_val, hash_type],
        )?;
        Ok(affected > 0)
    }

    pub fn get_local_models(&self) -> SqlResult<Vec<Value>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT raw_data, local_path, local_hash, local_hash_type, local_scan_time
             FROM models WHERE local_path != ''
             ORDER BY updated_at DESC",
        )?;

        let rows = stmt.query_map([], |row| {
            let raw: String = row.get(0)?;
            let path: String = row.get(1)?;
            let hash_val: String = row.get(2)?;
            let hash_type: String = row.get(3)?;
            let scan_time: i64 = row.get(4)?;
            Ok((raw, path, hash_val, hash_type, scan_time))
        })?;

        let mut results = Vec::new();
        for row in rows {
            if let Ok((raw, path, hash_val, hash_type, scan_time)) = row {
                if let Ok(mut val) = serde_json::from_str::<Value>(&raw) {
                    val["localPath"] = json!(path);
                    val["localHash"] = json!(hash_val);
                    val["localHashType"] = json!(hash_type);
                    val["localScanTime"] = json!(scan_time);
                    results.push(val);
                }
            }
        }

        Ok(results)
    }

    pub fn add_download(&self, data: &str) -> SqlResult<bool> {
        let value: Value =
            serde_json::from_str(data).unwrap_or_else(|_| json!({}));

        let id = value["id"].as_str().unwrap_or("").to_string();
        if id.is_empty() {
            return Ok(false);
        }

        let model_id = value["modelId"].as_i64();
        let version_id = value["versionId"].as_i64();
        let file_id = value["fileId"].as_i64();
        let file_name = value["fileName"].as_str().unwrap_or("").to_string();
        let download_url = value["url"].as_str().unwrap_or("").to_string();
        let download_path = value["downloadPath"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let model_type = value["modelType"]
            .as_str()
            .unwrap_or("")
            .to_string();

        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO download_queue (
                id, model_id, version_id, file_id, file_name,
                download_url, download_path, model_type, status
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'pending')",
            params![
                id,
                model_id,
                version_id,
                file_id,
                file_name,
                download_url,
                download_path,
                model_type,
            ],
        )?;

        Ok(true)
    }

    pub fn get_pending_downloads(&self) -> SqlResult<Vec<Value>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, model_id, version_id, file_id, file_name, download_url,
                    download_path, model_type, status, progress, bytes_total,
                    bytes_downloaded, error_message, created_at, updated_at
             FROM download_queue
             WHERE status IN ('pending', 'downloading', 'paused')
             ORDER BY created_at ASC",
        )?;

        let rows = stmt.query_map([], |row| {
            Ok(json!({
                "id": row.get::<_, String>(0)?,
                "modelId": row.get::<_, Option<i64>>(1)?,
                "versionId": row.get::<_, Option<i64>>(2)?,
                "fileId": row.get::<_, Option<i64>>(3)?,
                "fileName": row.get::<_, String>(4)?,
                "downloadUrl": row.get::<_, String>(5)?,
                "downloadPath": row.get::<_, String>(6)?,
                "modelType": row.get::<_, String>(7)?,
                "status": row.get::<_, String>(8)?,
                "progress": row.get::<_, i64>(9)?,
                "bytesTotal": row.get::<_, i64>(10)?,
                "bytesDownloaded": row.get::<_, i64>(11)?,
                "errorMessage": row.get::<_, Option<String>>(12)?,
                "createdAt": row.get::<_, i64>(13)?,
                "updatedAt": row.get::<_, i64>(14)?,
            }))
        })?;

        let mut results = Vec::new();
        for row in rows {
            if let Ok(val) = row {
                results.push(val);
            }
        }

        Ok(results)
    }

    pub fn update_download_status(&self, id: &str, status: &str) -> SqlResult<bool> {
        let conn = self.conn.lock().unwrap();
        let affected = conn.execute(
            "UPDATE download_queue SET status = ?2, updated_at = unixepoch() WHERE id = ?1",
            params![id, status],
        )?;
        Ok(affected > 0)
    }

    pub fn get_setting(&self, key: &str) -> SqlResult<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let result: SqlResult<String> = conn.query_row(
            "SELECT value FROM settings WHERE key = ?1",
            params![key],
            |row| row.get(0),
        );

        match result {
            Ok(value) => Ok(Some(value)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e),
        }
    }

    pub fn set_setting(&self, key: &str, value: &str) -> SqlResult<bool> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO settings (key, value, updated_at)
             VALUES (?1, ?2, unixepoch())
             ON CONFLICT(key) DO UPDATE SET value = ?2, updated_at = unixepoch()",
            params![key, value],
        )?;
        Ok(true)
    }

    pub fn clear_cache(&self) -> SqlResult<bool> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM models", [])?;
        conn.execute(
            "DELETE FROM models_fts",
            [],
        )?;
        Ok(true)
    }
}
