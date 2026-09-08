use sha2::{Digest, Sha256};

pub fn for_each_chunk(path: &str, mut visit: impl FnMut(&[u8])) -> Result<(), String> {
    use std::fs::File;
    use std::io::Read;

    let mut file = File::open(path).map_err(|e| format!("File open error: {}", e))?;
    let mut buffer = vec![0u8; 1024 * 1024];
    loop {
        let n = file
            .read(&mut buffer)
            .map_err(|e| format!("Read error: {}", e))?;
        if n == 0 {
            break;
        }
        visit(&buffer[..n]);
    }
    Ok(())
}

pub fn compute_file_hash(path: &str, algorithm: &str) -> Result<String, String> {
    match algorithm {
        "sha256" => {
            let mut hasher = Sha256::new();
            for_each_chunk(path, |chunk| hasher.update(chunk))?;
            Ok(hex::encode(hasher.finalize()))
        }
        "blake3" => {
            let mut hasher = blake3::Hasher::new();
            for_each_chunk(path, |chunk| {
                hasher.update(chunk);
            })?;
            Ok(hasher.finalize().to_hex().to_string())
        }
        other => Err(format!("Unsupported algorithm: {}", other)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn compute_sha256_of_known_content() {
        let mut tmp = tempfile::NamedTempFile::new().unwrap();
        tmp.write_all(b"hello world").unwrap();
        let path = tmp.path().to_string_lossy().to_string();

        let hash = compute_file_hash(&path, "sha256").unwrap();
        assert_eq!(
            hash,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        );
    }

    #[test]
    fn unsupported_algorithm_returns_error() {
        let hash = compute_file_hash("/dev/null", "md5");
        assert!(hash.is_err());
        assert!(hash
            .unwrap_err()
            .contains("Unsupported algorithm"));
    }
}
