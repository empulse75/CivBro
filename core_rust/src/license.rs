use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::Deserialize;

const LICENSE_PREFIX: &str = "CIVBRO-";
const LICENSE_PUBLIC_KEY: [u8; 32] = [
    0x7f, 0xd6, 0x1b, 0x6a, 0x6e, 0x9f, 0x1a, 0x7c, 0x57, 0x66, 0x75, 0x5c, 0x7f, 0xdc, 0x83, 0xb3,
    0x6a, 0x46, 0x30, 0x02, 0xed, 0xc6, 0x5f, 0x26, 0xf3, 0x4e, 0x5a, 0xa1, 0xc2, 0xe6, 0xd5, 0x0f,
];

#[derive(Deserialize)]
struct LicensePayload {
    license_id: String,
    issued_at: u64,
}

pub fn validate_license_key(key: &str) -> Result<(), String> {
    let encoded = key
        .trim()
        .strip_prefix(LICENSE_PREFIX)
        .ok_or_else(|| "License key must start with CIVBRO-".to_string())?;
    let (payload_encoded, signature_encoded) = encoded
        .split_once('.')
        .ok_or_else(|| "License key has an invalid format".to_string())?;

    let payload = URL_SAFE_NO_PAD
        .decode(payload_encoded)
        .map_err(|_| "License payload is not valid base64url".to_string())?;
    let signature_bytes = URL_SAFE_NO_PAD
        .decode(signature_encoded)
        .map_err(|_| "License signature is not valid base64url".to_string())?;
    let signature = Signature::from_slice(&signature_bytes)
        .map_err(|_| "License signature has an invalid length".to_string())?;
    let verifying_key = VerifyingKey::from_bytes(&LICENSE_PUBLIC_KEY)
        .map_err(|_| "License verifier is invalid".to_string())?;

    verifying_key
        .verify(&payload, &signature)
        .map_err(|_| "Invalid license signature".to_string())?;

    let claims: LicensePayload =
        serde_json::from_slice(&payload).map_err(|_| "License payload is invalid".to_string())?;
    if claims.license_id.trim().is_empty() || claims.issued_at == 0 {
        return Err("License payload is incomplete".into());
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const VALID_KEY: &str = concat!(
        "CIVBRO-eyJpc3N1ZWRfYXQiOjE3ODU3NTg0MDAsImxpY2Vuc2VfaWQiOiJ0ZXN0LWZpeHR1cmUifQ.",
        "E0ZCyZJTbKl9WFIiUJ1Rhm544GmNfyGnX7h7wwbl3iTnW_63ou_P7kUmkch2rpNqZp_jENgdzFzFjpqej1xcDg"
    );

    #[test]
    fn valid_license_key_is_accepted() {
        assert!(validate_license_key(VALID_KEY).is_ok());
    }

    #[test]
    fn surrounding_whitespace_is_accepted() {
        assert!(validate_license_key(&format!("  {VALID_KEY}  ")).is_ok());
    }

    #[test]
    fn empty_key_is_rejected() {
        assert!(validate_license_key("").is_err());
    }

    #[test]
    fn missing_prefix_is_rejected() {
        assert!(validate_license_key(VALID_KEY.trim_start_matches(LICENSE_PREFIX)).is_err());
    }

    #[test]
    fn malformed_key_is_rejected() {
        assert!(validate_license_key("CIVBRO-not-a-signed-license").is_err());
    }

    #[test]
    fn modified_payload_is_rejected() {
        let forged = VALID_KEY.replacen("eyJ", "fyJ", 1);
        assert!(validate_license_key(&forged).is_err());
    }

    #[test]
    fn modified_signature_is_rejected() {
        let mut forged = VALID_KEY.to_string();
        forged.pop();
        forged.push('A');
        assert!(validate_license_key(&forged).is_err());
    }

    #[test]
    fn old_symmetric_checksum_format_is_rejected() {
        let forged = "CIVBRO-FORGED123456-PAYLOAD12345-OFFLINE12345-123456789012";
        assert!(validate_license_key(forged).is_err());
    }
}
