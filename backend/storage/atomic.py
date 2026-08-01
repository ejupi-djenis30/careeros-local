import errno
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

from backend.core.config import settings


class StorageWriteError(RuntimeError):
    """A local durable write failed before it could be committed atomically."""


_STORAGE_ERRNOS = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_STALE_ATOMIC_WRITE_SCAN_LIMIT = 100_000


def _path_for_containment(path: str) -> str:
    """Normalize Win32 extended-path aliases before a containment comparison."""

    normalized = os.path.normpath(path)
    if os.name == "nt":
        if normalized.startswith("\\\\?\\UNC\\"):
            normalized = "\\\\" + normalized[8:]
        elif normalized.startswith("\\\\?\\"):
            normalized = normalized[4:]
    return os.path.normcase(normalized)


def _is_link_like(path: Path, metadata: os.stat_result | None = None) -> bool:
    details = metadata or path.lstat()
    file_attributes = int(getattr(details, "st_file_attributes", 0))
    return stat.S_ISLNK(details.st_mode) or bool(file_attributes & 0x400)


def read_stable_bounded_file(
    path: str | Path,
    *,
    maximum_size: int,
    expected_size: int | None = None,
    require_single_link: bool = True,
) -> bytes:
    """Read one descriptor-stable regular file within an explicit byte bound.

    Recovery metadata uses ``require_single_link=True`` so an attacker or a
    corrupt filesystem namespace cannot make one journal entry alias another
    file. Atomic content publication disables only that link-count constraint
    while identical writers may briefly share the same inode.
    """

    if (
        isinstance(maximum_size, bool)
        or not isinstance(maximum_size, int)
        or maximum_size < 0
        or (
            expected_size is not None
            and (
                isinstance(expected_size, bool)
                or not isinstance(expected_size, int)
                or expected_size < 0
                or expected_size > maximum_size
            )
        )
    ):
        raise ValueError("Stable file read bounds are invalid")

    source = Path(path)
    before = source.lstat()

    def metadata_is_valid(metadata: os.stat_result) -> bool:
        return (
            stat.S_ISREG(metadata.st_mode)
            and not _is_link_like(source, metadata)
            and (not require_single_link or int(getattr(metadata, "st_nlink", 1)) == 1)
            and 0 <= metadata.st_size <= maximum_size
            and (expected_size is None or metadata.st_size == expected_size)
        )

    if not metadata_is_valid(before):
        raise ValueError("Stored file is not one bounded regular file")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if os.name != "nt":
        # Opening a FIFO for reading blocks before fstat can reject it. A
        # non-blocking open is harmless for ordinary files and keeps hostile
        # special files from pinning the request worker indefinitely.
        flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(source, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not metadata_is_valid(opened)
            or not os.path.samestat(before, opened)
            or opened.st_size != before.st_size
            or (
                require_single_link
                and os.name != "nt"
                and (
                    opened.st_mtime_ns != before.st_mtime_ns
                    or opened.st_ctime_ns != before.st_ctime_ns
                )
            )
        ):
            raise ValueError("Stored file changed while it was being opened")

        chunks: list[bytes] = []
        remaining = opened.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(data) != opened.st_size
            or not metadata_is_valid(after)
            or not os.path.samestat(opened, after)
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or after.st_ctime_ns != opened.st_ctime_ns
        ):
            raise ValueError("Stored file changed while it was being read")
        return data
    finally:
        os.close(descriptor)


def _read_regular_file_exact(path: Path, expected_size: int) -> bytes:
    """Read exact content while permitting a publisher's transient second link."""

    return read_stable_bounded_file(
        path,
        maximum_size=expected_size,
        expected_size=expected_size,
        require_single_link=False,
    )


def is_storage_exhaustion(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, OSError) and current.errno in _STORAGE_ERRNOS:
            return True
        message = str(current).casefold()
        if any(
            marker in message
            for marker in ("database or disk is full", "disk is full", "no space left")
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def data_root(*, create: bool = True) -> Path:
    root = Path(settings.DATA_DIR).expanduser().resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_data_path(relative_path: str | Path, *, create_root: bool = True) -> Path:
    raw_path = relative_path.as_posix() if isinstance(relative_path, Path) else relative_path
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Stored paths must be non-empty relative paths")
    if "\x00" in raw_path:
        raise ValueError("Stored paths cannot contain null bytes")
    if "\\" in raw_path:
        raise ValueError("Stored paths must use portable forward-slash separators")
    if raw_path.startswith("/") or _WINDOWS_DRIVE_PATH.match(raw_path):
        raise ValueError("Stored paths must be relative to the local data directory")

    parts = raw_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Stored paths must be normalized and cannot contain traversal")

    root = data_root(create=create_root)
    root_real = os.path.realpath(os.fspath(root))
    current = Path(root_real)
    for part in parts:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if _is_link_like(current, metadata):
            raise ValueError(
                "Stored path escapes the local data directory or contains a symbolic link "
                "or reparse point"
            )
    try:
        resolved = os.path.realpath(os.path.join(root_real, *parts))
    except OSError as exc:
        raise ValueError("Stored path escapes the local data directory") from exc
    comparison_root = _path_for_containment(root_real)
    comparison_resolved = _path_for_containment(resolved)
    try:
        common = os.path.commonpath((comparison_root, comparison_resolved))
    except ValueError as exc:
        raise ValueError("Stored path escapes the local data directory") from exc
    if common != comparison_root:
        raise ValueError("Stored path escapes the local data directory")
    return Path(resolved)


def fsync_directory(directory: Path) -> None:
    """Durably publish directory-entry changes where the OS exposes that primitive.

    POSIX requires an explicit directory fsync after rename/unlink. Windows does
    not support opening directories through ``os.open``; file handles are flushed
    before ``os.replace`` and recovery journals cover interrupted publication.
    """

    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_replace(source: str | Path, destination: str | Path) -> None:
    """Atomically replace and request write-through publication on Windows."""

    if os.name != "nt":
        os.replace(source, destination)
        return
    import ctypes

    move_file_replace_existing = 0x1
    move_file_write_through = 0x8
    kernel32 = getattr(ctypes, "windll").kernel32
    kernel32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel32.MoveFileExW.restype = ctypes.c_int
    if not kernel32.MoveFileExW(
        os.fspath(source),
        os.fspath(destination),
        move_file_replace_existing | move_file_write_through,
    ):
        raise getattr(ctypes, "WinError")()


def durable_mkdir(directory: Path) -> None:
    """Create a directory chain and durably publish every new directory entry."""

    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for target in reversed(missing):
        target.mkdir(exist_ok=True)
        fsync_directory(target.parent)


def durable_unlink(path: Path) -> bool:
    """Remove one file and durably publish the missing directory entry."""

    try:
        path.unlink()
    except FileNotFoundError:
        return False
    fsync_directory(path.parent)
    return True


def _best_effort_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        durable_unlink(path)
    except OSError:
        pass


def _stale_atomic_write_candidates(
    root: Path,
    remaining_scan_entries: list[int] | None = None,
) -> list[Path]:
    """Enumerate cleanup candidates without traversing link-like directories.

    ``Path.rglob`` follows Windows directory junctions.  A stale-write sweep must
    never walk through a reparse point because the matching file could then live
    outside the private data root.
    """

    candidates: list[Path] = []
    pending = [root]
    remaining = (
        remaining_scan_entries
        if remaining_scan_entries is not None
        else [_STALE_ATOMIC_WRITE_SCAN_LIMIT]
    )
    while pending:
        directory = pending.pop()
        try:
            before = directory.lstat()
        except FileNotFoundError:
            continue
        if _is_link_like(directory, before) or not stat.S_ISDIR(before.st_mode):
            continue

        discovered_directories: list[Path] = []
        discovered_candidates: list[Path] = []
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    remaining[0] -= 1
                    if remaining[0] < 0:
                        raise StorageWriteError(
                            "Interrupted private file cleanup exceeded its scan limit"
                        )
                    path = Path(entry.path)
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if _is_link_like(path, metadata):
                        # A symbolic-link entry can safely be unlinked without
                        # following its target. A junction/reparse directory is
                        # neither traversed nor removed by this file-only sweep.
                        if entry.name.startswith(".write-") and stat.S_ISLNK(metadata.st_mode):
                            discovered_candidates.append(path)
                        continue
                    if stat.S_ISDIR(metadata.st_mode):
                        discovered_directories.append(path)
                    elif entry.name.startswith(".write-") and stat.S_ISREG(metadata.st_mode):
                        discovered_candidates.append(path)
        except FileNotFoundError:
            continue

        # Refuse results from a directory that was exchanged while it was being
        # enumerated.  The component chain is checked again immediately before
        # every unlink below.
        try:
            after = directory.lstat()
        except FileNotFoundError:
            continue
        if (
            _is_link_like(directory, after)
            or not stat.S_ISDIR(after.st_mode)
            or not os.path.samestat(before, after)
        ):
            continue
        pending.extend(discovered_directories)
        candidates.extend(discovered_candidates)
    return candidates


def _cleanup_candidate_is_safe(root: Path, path: Path) -> bool:
    """Revalidate a candidate and its lexical parent chain before unlinking."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return False

    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        return False
    if _is_link_like(root, root_metadata) or not stat.S_ISDIR(root_metadata.st_mode):
        return False

    current = root
    for component in relative.parts[:-1]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return False
        if _is_link_like(current, metadata) or not stat.S_ISDIR(metadata.st_mode):
            return False

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)


def cleanup_stale_atomic_writes() -> int:
    """Remove crash-left write temporaries before the single worker starts serving."""

    removed = 0
    remaining_scan_entries = [_STALE_ATOMIC_WRITE_SCAN_LIMIT]
    candidates: list[tuple[Path, Path]] = []
    for namespace in ("assets", "resumes"):
        root = resolve_data_path(namespace)
        if not root.exists():
            continue
        try:
            candidates.extend(
                (root, path)
                for path in _stale_atomic_write_candidates(root, remaining_scan_entries)
            )
        except OSError as exc:
            raise StorageWriteError(
                "Interrupted private file cleanup failed; verify the local data directory."
            ) from exc
    for root, path in candidates:
        if not _cleanup_candidate_is_safe(root, path):
            continue
        try:
            if durable_unlink(path):
                removed += 1
        except OSError as exc:
            raise StorageWriteError(
                "Interrupted private file cleanup failed; verify the local data directory."
            ) from exc
    return removed


def atomic_write(relative_path: str | Path, data: bytes) -> tuple[Path, bool]:
    temporary_name: str | None = None
    try:
        destination = resolve_data_path(relative_path)
        durable_mkdir(destination.parent)
        if destination.exists():
            try:
                existing = _read_regular_file_exact(destination, len(data))
            except ValueError as exc:
                raise ValueError(
                    "Existing stored file does not match the requested content"
                ) from exc
            if existing != data:
                raise ValueError("Existing stored file does not match the requested content")
            return destination, False

        handle, temporary_name = tempfile.mkstemp(
            prefix=f".write-{destination.name}-",
            dir=destination.parent,
        )
        with os.fdopen(handle, "wb") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            # Publish without replacement. Content-addressed callers may race;
            # replacing here makes ownership ambiguous and can let a losing DB
            # transaction delete the winner's durable bytes during cleanup.
            os.link(temporary_name, destination)
        except FileExistsError:
            try:
                existing = _read_regular_file_exact(destination, len(data))
            except ValueError as exc:
                raise ValueError(
                    "Existing stored file does not match the requested content"
                ) from exc
            if existing != data:
                raise ValueError("Existing stored file does not match the requested content")
            durable_unlink(Path(temporary_name))
            temporary_name = None
            return destination, False

        durable_unlink(Path(temporary_name))
        temporary_name = None
        fsync_directory(destination.parent)
        return destination, True
    except OSError as exc:
        _best_effort_unlink(Path(temporary_name) if temporary_name is not None else None)
        raise StorageWriteError(
            "Local storage write failed; verify free disk space and folder access, then retry."
        ) from exc
    except Exception:
        _best_effort_unlink(Path(temporary_name) if temporary_name is not None else None)
        raise


def read_verified(
    relative_path: str | Path,
    expected_sha256: str,
    *,
    expected_size: int,
    maximum_size: int,
) -> bytes:
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or isinstance(maximum_size, bool)
        or not isinstance(maximum_size, int)
        or expected_size <= 0
        or maximum_size <= 0
        or expected_size > maximum_size
        or not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("Stored file metadata is invalid")
    source = resolve_data_path(relative_path, create_root=False)
    data = read_stable_bounded_file(
        source,
        maximum_size=maximum_size,
        expected_size=expected_size,
    )
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise ValueError("Stored file failed its integrity check")
    return data
