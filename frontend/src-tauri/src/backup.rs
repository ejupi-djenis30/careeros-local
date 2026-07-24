use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use sha2::{Digest, Sha256};
use tauri::ipc::{InvokeBody, Request};
use tauri::WebviewWindow;
use tauri_plugin_dialog::DialogExt;

const MAX_BACKUP_BYTES: usize = 512 * 1024 * 1024;
const BUFFER_BYTES: usize = 128 * 1024;
const SIDECAR_ATTEMPTS: usize = 16;
const FILENAME_HEADER: &str = "X-CareerOS-Filename";
const TITLE_HEADER: &str = "X-CareerOS-Dialog-Title";
const DIGEST_HEADER: &str = "X-Content-SHA256";
static BACKUP_SAVE_LOCK: Mutex<()> = Mutex::new(());

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct VerifiedBackupSave {
    saved: bool,
    sha256: String,
    byte_size: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackupSaveError {
    code: &'static str,
    message: &'static str,
}

impl BackupSaveError {
    const fn new(code: &'static str, message: &'static str) -> Self {
        Self { code, message }
    }

    const fn invalid_request() -> Self {
        Self::new("backup_save_invalid", "The backup save request is invalid.")
    }

    const fn destination_denied() -> Self {
        Self::new(
            "backup_destination_denied",
            "Choose the backup destination again.",
        )
    }

    const fn checksum_mismatch() -> Self {
        Self::new(
            "backup_checksum_mismatch",
            "The backup checksum does not match its bytes.",
        )
    }

    const fn io_failure() -> Self {
        Self::new(
            "backup_save_failed",
            "CareerOS could not save and verify the backup.",
        )
    }

    const fn rollback_failure() -> Self {
        Self::new(
            "backup_rollback_failed",
            "CareerOS preserved the previous backup in a recovery file, but could not restore its original name.",
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct FileFingerprint {
    bytes: u64,
    sha256: [u8; 32],
}

struct Sidecar {
    part: PathBuf,
    rollback: PathBuf,
    file: Option<File>,
}

fn decode_text_header(request: &Request<'_>, name: &str) -> Result<String, BackupSaveError> {
    let encoded = request
        .headers()
        .get(name)
        .and_then(|value| value.to_str().ok())
        .ok_or_else(BackupSaveError::invalid_request)?;
    let bytes = STANDARD
        .decode(encoded)
        .map_err(|_| BackupSaveError::invalid_request())?;
    String::from_utf8(bytes).map_err(|_| BackupSaveError::invalid_request())
}

fn decode_filename(request: &Request<'_>) -> Result<String, BackupSaveError> {
    validate_filename(decode_text_header(request, FILENAME_HEADER)?)
}

fn validate_filename(value: String) -> Result<String, BackupSaveError> {
    let path = Path::new(&value);
    if value.is_empty()
        || value.len() > 180
        || value.trim() != value
        || value.contains('/')
        || value.contains('\\')
        || value.chars().any(char::is_control)
        || path.components().count() != 1
        || path.file_name().and_then(|name| name.to_str()) != Some(value.as_str())
        || !path
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("zip"))
    {
        return Err(BackupSaveError::invalid_request());
    }
    Ok(value)
}

fn validate_title(value: String) -> Result<String, BackupSaveError> {
    if value.is_empty()
        || value.len() > 120
        || value.trim() != value
        || value.chars().any(char::is_control)
    {
        return Err(BackupSaveError::invalid_request());
    }
    Ok(value)
}

fn decode_digest(request: &Request<'_>) -> Result<([u8; 32], String), BackupSaveError> {
    let value = request
        .headers()
        .get(DIGEST_HEADER)
        .and_then(|header| header.to_str().ok())
        .map(str::trim)
        .filter(|value| value.len() == 64)
        .ok_or_else(BackupSaveError::invalid_request)?;
    let mut digest = [0_u8; 32];
    for (index, chunk) in value.as_bytes().chunks_exact(2).enumerate() {
        let pair = std::str::from_utf8(chunk).map_err(|_| BackupSaveError::invalid_request())?;
        digest[index] =
            u8::from_str_radix(pair, 16).map_err(|_| BackupSaveError::invalid_request())?;
    }
    Ok((digest, value.to_ascii_lowercase()))
}

fn payload<'a>(request: &'a Request<'a>) -> Result<&'a [u8], BackupSaveError> {
    let InvokeBody::Raw(bytes) = request.body() else {
        return Err(BackupSaveError::invalid_request());
    };
    if bytes.is_empty() || bytes.len() > MAX_BACKUP_BYTES {
        return Err(BackupSaveError::invalid_request());
    }
    Ok(bytes)
}

fn digest_bytes(bytes: &[u8]) -> [u8; 32] {
    Sha256::digest(bytes).into()
}

fn fingerprint(path: &Path) -> io::Result<FileFingerprint> {
    reject_special_file(path)?;
    let mut file = File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; BUFFER_BYTES];
    let mut bytes = 0_u64;
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes = bytes
            .checked_add(count as u64)
            .ok_or_else(|| io::Error::other("file length overflow"))?;
        digest.update(&buffer[..count]);
    }
    Ok(FileFingerprint {
        bytes,
        sha256: digest.finalize().into(),
    })
}

fn reject_special_file(path: &Path) -> io::Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file() || is_reparse_point(&metadata) {
        return Err(io::Error::other("backup destination is not a regular file"));
    }
    Ok(())
}

#[cfg(windows)]
fn is_reparse_point(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn is_reparse_point(metadata: &fs::Metadata) -> bool {
    metadata.file_type().is_symlink()
}

fn sidecar_name(suffix: &str) -> OsString {
    let mut name = OsString::from(".careeros-");
    name.push(format!("{:032x}", rand::random::<u128>()));
    name.push(suffix);
    name
}

fn create_sidecar(parent: &Path) -> io::Result<Sidecar> {
    for _ in 0..SIDECAR_ATTEMPTS {
        let part = parent.join(sidecar_name(".part"));
        let rollback = parent.join(sidecar_name(".rollback"));
        if fs::symlink_metadata(&rollback).is_ok() {
            continue;
        }
        match OpenOptions::new().write(true).create_new(true).open(&part) {
            Ok(file) => {
                return Ok(Sidecar {
                    part,
                    rollback,
                    file: Some(file),
                })
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::AlreadyExists,
        "could not reserve a unique backup sidecar",
    ))
}

#[cfg(unix)]
fn sync_parent(parent: &Path) -> io::Result<()> {
    File::open(parent)?.sync_all()
}

#[cfg(not(unix))]
fn sync_parent(_parent: &Path) -> io::Result<()> {
    Ok(())
}

fn remove_file_if_present(path: &Path) -> io::Result<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

fn rollback(
    destination: &Path,
    parent: &Path,
    part: &Path,
    rollback: &Path,
    original: Option<FileFingerprint>,
    promoted: bool,
) -> Result<(), BackupSaveError> {
    let _ = remove_file_if_present(part);
    if promoted && remove_file_if_present(destination).is_err() {
        return Err(BackupSaveError::rollback_failure());
    }
    if let Some(expected) = original {
        if fingerprint(rollback).ok() != Some(expected) {
            return Err(BackupSaveError::rollback_failure());
        }
        if fs::symlink_metadata(destination).is_ok()
            || fs::rename(rollback, destination).is_err()
            || sync_parent(parent).is_err()
            || fingerprint(destination).ok() != Some(expected)
        {
            return Err(BackupSaveError::rollback_failure());
        }
    } else {
        let _ = remove_file_if_present(rollback);
    }
    Ok(())
}

fn save_verified_backup_bytes<F>(
    destination: &Path,
    bytes: &[u8],
    expected_sha256: [u8; 32],
    after_promote: F,
) -> Result<(), BackupSaveError>
where
    F: FnOnce(&Path) -> io::Result<()>,
{
    if digest_bytes(bytes) != expected_sha256 {
        return Err(BackupSaveError::checksum_mismatch());
    }

    let parent = destination
        .parent()
        .and_then(|path| path.canonicalize().ok())
        .filter(|path| path.is_dir())
        .ok_or_else(BackupSaveError::destination_denied)?;
    let filename = destination
        .file_name()
        .ok_or_else(BackupSaveError::destination_denied)?;
    let destination = parent.join(filename);
    let original = match fs::symlink_metadata(&destination) {
        Ok(_) => {
            Some(fingerprint(&destination).map_err(|_| BackupSaveError::destination_denied())?)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => None,
        Err(_) => return Err(BackupSaveError::destination_denied()),
    };
    let mut sidecar = create_sidecar(&parent).map_err(|_| BackupSaveError::io_failure())?;
    let mut original_moved = false;
    let mut promoted = false;

    let operation = (|| -> Result<(), BackupSaveError> {
        let mut part_file = sidecar
            .file
            .take()
            .ok_or_else(BackupSaveError::io_failure)?;
        let write_result = part_file
            .write_all(bytes)
            .and_then(|()| part_file.sync_all());
        drop(part_file);
        write_result.map_err(|_| BackupSaveError::io_failure())?;
        if fingerprint(&sidecar.part).ok()
            != Some(FileFingerprint {
                bytes: bytes.len() as u64,
                sha256: expected_sha256,
            })
        {
            return Err(BackupSaveError::io_failure());
        }

        if let Some(expected_original) = original {
            if fs::symlink_metadata(&sidecar.rollback).is_ok() {
                return Err(BackupSaveError::io_failure());
            }
            fs::rename(&destination, &sidecar.rollback)
                .map_err(|_| BackupSaveError::io_failure())?;
            original_moved = true;
            sync_parent(&parent).map_err(|_| BackupSaveError::io_failure())?;
            if fingerprint(&sidecar.rollback).ok() != Some(expected_original) {
                return Err(BackupSaveError::io_failure());
            }
        }

        if fs::symlink_metadata(&destination).is_ok() {
            return Err(BackupSaveError::io_failure());
        }
        fs::rename(&sidecar.part, &destination).map_err(|_| BackupSaveError::io_failure())?;
        promoted = true;
        sync_parent(&parent).map_err(|_| BackupSaveError::io_failure())?;
        after_promote(&destination).map_err(|_| BackupSaveError::io_failure())?;
        if fingerprint(&destination).ok()
            != Some(FileFingerprint {
                bytes: bytes.len() as u64,
                sha256: expected_sha256,
            })
        {
            return Err(BackupSaveError::io_failure());
        }
        if original.is_some() {
            remove_file_if_present(&sidecar.rollback).map_err(|_| BackupSaveError::io_failure())?;
            let _ = sync_parent(&parent);
        }
        Ok(())
    })();

    match operation {
        Ok(()) => Ok(()),
        Err(error) => {
            rollback(
                &destination,
                &parent,
                &sidecar.part,
                &sidecar.rollback,
                original.filter(|_| original_moved),
                promoted,
            )?;
            Err(error)
        }
    }
}

#[tauri::command(async)]
pub fn desktop_save_verified_backup(
    window: WebviewWindow,
    request: Request<'_>,
) -> Result<Option<VerifiedBackupSave>, BackupSaveError> {
    let filename = decode_filename(&request)?;
    let title = validate_title(decode_text_header(&request, TITLE_HEADER)?)?;
    let (expected_sha256, sha256) = decode_digest(&request)?;
    let bytes = payload(&request)?;
    if digest_bytes(bytes) != expected_sha256 {
        return Err(BackupSaveError::checksum_mismatch());
    }
    let _guard = BACKUP_SAVE_LOCK
        .lock()
        .map_err(|_| BackupSaveError::io_failure())?;
    let Some(destination) = window
        .dialog()
        .file()
        .set_title(title)
        .set_file_name(filename)
        .add_filter("CareerOS Local backup", &["zip"])
        .blocking_save_file()
        .and_then(|path| path.into_path().ok())
    else {
        return Ok(None);
    };
    save_verified_backup_bytes(&destination, bytes, expected_sha256, |_| Ok(()))?;
    Ok(Some(VerifiedBackupSave {
        saved: true,
        sha256,
        byte_size: bytes.len(),
    }))
}

#[cfg(test)]
mod tests {
    use super::{digest_bytes, save_verified_backup_bytes, validate_filename, validate_title};
    use std::fs::{self, OpenOptions};
    use std::io::Write;
    use std::path::{Path, PathBuf};

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "careeros-backup-test-{:032x}",
                rand::random::<u128>()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }

        fn sidecars(&self) -> Vec<PathBuf> {
            fs::read_dir(&self.0)
                .unwrap()
                .filter_map(Result::ok)
                .map(|entry| entry.path())
                .filter(|path| {
                    path.file_name()
                        .and_then(|name| name.to_str())
                        .is_some_and(|name| name.starts_with(".careeros-"))
                })
                .collect()
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn accepts_only_a_bounded_zip_filename_for_the_native_dialog() {
        assert_eq!(
            validate_filename("careeros-backup.zip".to_string()).unwrap(),
            "careeros-backup.zip"
        );
        for unsafe_name in [
            "../backup.zip",
            "nested/backup.zip",
            r"nested\backup.zip",
            "backup.txt",
            ".zip",
            " backup.zip",
            "backup.zip\n",
        ] {
            assert_eq!(
                validate_filename(unsafe_name.to_string()).unwrap_err().code,
                "backup_save_invalid"
            );
        }
        assert_eq!(
            validate_filename(format!("{}.zip", "a".repeat(177)))
                .unwrap_err()
                .code,
            "backup_save_invalid"
        );
    }

    #[test]
    fn accepts_only_a_bounded_single_line_native_dialog_title() {
        assert_eq!(
            validate_title("Save CareerOS Local backup".to_string()).unwrap(),
            "Save CareerOS Local backup"
        );
        for unsafe_title in ["", " title", "title ", "line\nbreak"] {
            assert_eq!(
                validate_title(unsafe_title.to_string()).unwrap_err().code,
                "backup_save_invalid"
            );
        }
        assert_eq!(
            validate_title("a".repeat(121)).unwrap_err().code,
            "backup_save_invalid"
        );
    }

    #[test]
    fn creates_and_replaces_a_verified_backup_without_sidecars() {
        let directory = TestDirectory::new();
        let destination = directory.path().join("backup.zip");
        let first = b"first portable archive";
        let second = b"second portable archive";

        save_verified_backup_bytes(&destination, first, digest_bytes(first), |_| Ok(())).unwrap();
        assert_eq!(fs::read(&destination).unwrap(), first);
        save_verified_backup_bytes(&destination, second, digest_bytes(second), |_| Ok(())).unwrap();

        assert_eq!(fs::read(&destination).unwrap(), second);
        assert!(directory.sidecars().is_empty());
    }

    #[test]
    fn rejects_a_checksum_mismatch_before_touching_the_destination() {
        let directory = TestDirectory::new();
        let destination = directory.path().join("backup.zip");
        fs::write(&destination, b"existing backup").unwrap();

        let error = save_verified_backup_bytes(
            &destination,
            b"new backup",
            digest_bytes(b"different bytes"),
            |_| Ok(()),
        )
        .unwrap_err();

        assert_eq!(error.code, "backup_checksum_mismatch");
        assert_eq!(fs::read(&destination).unwrap(), b"existing backup");
        assert!(directory.sidecars().is_empty());
    }

    #[test]
    fn restores_the_previous_backup_after_a_post_rename_fault() {
        let directory = TestDirectory::new();
        let destination = directory.path().join("backup.zip");
        fs::write(&destination, b"existing backup").unwrap();
        let replacement = b"verified replacement";

        let error = save_verified_backup_bytes(
            &destination,
            replacement,
            digest_bytes(replacement),
            |path| {
                let mut file = OpenOptions::new().write(true).truncate(true).open(path)?;
                file.write_all(b"fault")?;
                file.sync_all()
            },
        )
        .unwrap_err();

        assert_eq!(error.code, "backup_save_failed");
        assert_eq!(fs::read(&destination).unwrap(), b"existing backup");
        assert!(directory.sidecars().is_empty());
    }

    #[test]
    fn refuses_non_regular_destinations() {
        let directory = TestDirectory::new();
        let destination = directory.path().join("backup.zip");
        fs::create_dir(&destination).unwrap();
        let archive = b"verified backup";

        let error =
            save_verified_backup_bytes(&destination, archive, digest_bytes(archive), |_| Ok(()))
                .unwrap_err();

        assert_eq!(error.code, "backup_destination_denied");
        assert!(destination.is_dir());
        assert!(directory.sidecars().is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn refuses_a_symlink_destination() {
        use std::os::unix::fs::symlink;

        let directory = TestDirectory::new();
        let target = directory.path().join("target.zip");
        let destination = directory.path().join("backup.zip");
        fs::write(&target, b"target").unwrap();
        symlink(&target, &destination).unwrap();
        let archive = b"verified backup";

        let error =
            save_verified_backup_bytes(&destination, archive, digest_bytes(archive), |_| Ok(()))
                .unwrap_err();

        assert_eq!(error.code, "backup_destination_denied");
        assert_eq!(fs::read(&target).unwrap(), b"target");
        assert!(directory.sidecars().is_empty());
    }

    #[cfg(windows)]
    #[test]
    fn refuses_a_reparse_point_destination_when_symlinks_are_available() {
        use std::os::windows::fs::symlink_file;

        let directory = TestDirectory::new();
        let target = directory.path().join("target.zip");
        let destination = directory.path().join("backup.zip");
        fs::write(&target, b"target").unwrap();
        if symlink_file(&target, &destination).is_err() {
            return;
        }
        let archive = b"verified backup";

        let error =
            save_verified_backup_bytes(&destination, archive, digest_bytes(archive), |_| Ok(()))
                .unwrap_err();

        assert_eq!(error.code, "backup_destination_denied");
        assert_eq!(fs::read(&target).unwrap(), b"target");
        assert!(directory.sidecars().is_empty());
    }
}
