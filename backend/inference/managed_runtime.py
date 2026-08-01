from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import shutil
import socket
import stat
import subprocess
import tarfile
import threading
import time
import zipfile
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Callable, Literal
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from backend.inference.catalog import (
    ModelCatalogEntry,
    RuntimeAsset,
    current_platform_key,
    load_model_catalog,
)
from backend.inference.llama_cpp import LlamaCppProvider

RuntimePhase = Literal[
    "idle",
    "downloading_runtime",
    "installing_runtime",
    "downloading_model",
    "paused",
    "starting",
    "ready",
    "cancelled",
    "error",
]

_CHUNK_SIZE = 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 5_000
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_MAX_DOWNLOAD_REDIRECTS = 3
_DOWNLOAD_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_INITIAL_DOWNLOAD_HOSTS = frozenset({"github.com", "huggingface.co"})
_GITHUB_DELIVERY_HOSTS = frozenset(
    {
        "github.com",
        "release-assets.githubusercontent.com",
    }
)
_HUGGING_FACE_DELIVERY_HOSTS = frozenset(
    {
        "huggingface.co",
        "cdn-lfs.huggingface.co",
    }
)
_HUGGING_FACE_DELIVERY_SUFFIXES = (".cdn.hf.co", ".xethub.hf.co")
_RUNTIME_MARKER_NAME = ".catalog-sha256"
_RUNTIME_SOURCE_PREFIX = ".catalog-source"
_PRIVATE_CHILD_ENVIRONMENT_NAMES = frozenset(
    {
        "ALL_PROXY",
        "CAREEROS_DESKTOP_SESSION_TOKEN",
        "CAREEROS_MCP_TOKEN",
        "CAREEROS_SECRET_FILE",
        "DATABASE_URL",
        "DYLD_FALLBACK_FRAMEWORK_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "GIT_ASKPASS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "NO_PROXY",
        "PIP_INDEX_URL",
        "PIP_TRUSTED_HOST",
        "SECRET_KEY",
        "SSH_AUTH_SOCK",
        "UV_INDEX_URL",
    }
)
_PRIVATE_CHILD_ENVIRONMENT_PREFIXES = ("GGML_", "LLAMA_")
_PRIVATE_CHILD_ENVIRONMENT_SUFFIXES = (
    "_ACCESS_KEY",
    "_ACCESS_KEY_ID",
    "_API_KEY",
    "_COOKIE",
    "_CREDENTIALS",
    "_JWT",
    "_PASSWORD",
    "_PRIVATE_KEY",
    "_SECRET",
    "_TOKEN",
)


class InstallCancelled(RuntimeError):
    pass


class InstallPaused(RuntimeError):
    pass


class UnsafeArchiveError(ValueError):
    pass


class RuntimeBlockedByWindowsPolicy(RuntimeError):
    pass


class RuntimeStartCancelled(InstallCancelled):
    pass


class ManagedAssetIntegrityError(RuntimeError):
    pass


def _managed_runtime_environment(api_key: str) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in _PRIVATE_CHILD_ENVIRONMENT_NAMES
        and not name.upper().startswith(_PRIVATE_CHILD_ENVIRONMENT_PREFIXES)
        and not name.upper().endswith(_PRIVATE_CHILD_ENVIRONMENT_SUFFIXES)
    }
    environment["LLAMA_API_KEY"] = api_key
    return environment


@dataclass(frozen=True, slots=True)
class ManagedRuntimeSnapshot:
    phase: RuntimePhase
    model_key: str | None
    bytes_downloaded: int
    bytes_total: int
    runtime_installed: bool
    model_installed: bool
    ready: bool
    endpoint: str | None
    error_code: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or ".." in candidate.parts
        or any(":" in part for part in candidate.parts)
    ):
        raise UnsafeArchiveError("archive contains an unsafe member path")
    return candidate


def _destination_path(root: Path, member: PurePosixPath) -> Path:
    root_resolved = root.resolve(strict=False)
    target = root.joinpath(*member.parts).resolve(strict=False)
    if target != root_resolved and root_resolved not in target.parents:
        raise UnsafeArchiveError("archive member escapes the installation directory")
    return target


def _registered_member_path(name: str, seen: set[str]) -> PurePosixPath:
    member = _safe_member_path(name)
    identity = member.as_posix().casefold()
    if identity in seen:
        raise UnsafeArchiveError("archive contains duplicate member paths")
    seen.add(identity)
    return member


def _copy_bounded(
    source: IO[bytes],
    output: IO[bytes],
    *,
    copied: int,
    expected_member_bytes: int,
    max_uncompressed_bytes: int,
    cancelled: threading.Event | None = None,
) -> int:
    member_bytes = 0
    while True:
        if cancelled is not None and cancelled.is_set():
            raise InstallCancelled("model installation cancelled")
        chunk = source.read(_CHUNK_SIZE)
        if not chunk:
            break
        member_bytes += len(chunk)
        if member_bytes > expected_member_bytes:
            raise UnsafeArchiveError("archive member exceeds its declared size")
        if copied + member_bytes > max_uncompressed_bytes:
            raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
        output.write(chunk)
    if member_bytes != expected_member_bytes:
        raise UnsafeArchiveError("archive member size does not match its metadata")
    return copied + member_bytes


def _validated_initial_download_url(url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("download URL is malformed") from exc
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme.casefold() != "https"
        or host not in _INITIAL_DOWNLOAD_HOSTS
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("download requires an approved HTTPS catalog origin")
    return url, host


def _validated_redirect_url(current_url: str, location: str, *, origin_host: str) -> str:
    candidate = urljoin(current_url, location)
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("download redirect URL is malformed") from exc
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme.casefold() != "https"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("download redirect leaves the approved HTTPS delivery network")
    if origin_host == "github.com":
        approved = host in _GITHUB_DELIVERY_HOSTS
    else:
        approved = host in _HUGGING_FACE_DELIVERY_HOSTS or host.endswith(
            _HUGGING_FACE_DELIVERY_SUFFIXES
        )
    if not approved:
        raise ValueError("download redirect leaves the approved HTTPS delivery network")
    return candidate


def safe_extract_archive(
    archive_path: Path,
    destination: Path,
    archive_type: Literal["zip", "tar.gz"],
    *,
    max_members: int = _MAX_ARCHIVE_MEMBERS,
    max_uncompressed_bytes: int = _MAX_ARCHIVE_BYTES,
    cancelled: threading.Event | None = None,
) -> None:
    """Extract regular files only, with traversal and decompression-bomb limits."""
    destination.mkdir(parents=True, exist_ok=False)
    try:
        copied = 0
        seen: set[str] = set()
        if cancelled is not None and cancelled.is_set():
            raise InstallCancelled("model installation cancelled")
        if archive_type == "zip":
            with zipfile.ZipFile(archive_path) as archive:
                zip_members = archive.infolist()
                if len(zip_members) > max_members:
                    raise UnsafeArchiveError("archive contains too many members")
                if any(item.file_size < 0 for item in zip_members):
                    raise UnsafeArchiveError("archive contains an invalid member size")
                if sum(item.file_size for item in zip_members) > max_uncompressed_bytes:
                    raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
                for zip_item in zip_members:
                    if cancelled is not None and cancelled.is_set():
                        raise InstallCancelled("model installation cancelled")
                    mode = zip_item.external_attr >> 16
                    file_type = stat.S_IFMT(mode)
                    if stat.S_ISLNK(mode) or (
                        file_type and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)
                    ):
                        raise UnsafeArchiveError("archive links and special files are forbidden")
                    member = _registered_member_path(zip_item.filename, seen)
                    target = _destination_path(destination, member)
                    if zip_item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(zip_item) as source, target.open("wb") as output:
                        copied = _copy_bounded(
                            source,
                            output,
                            copied=copied,
                            expected_member_bytes=zip_item.file_size,
                            max_uncompressed_bytes=max_uncompressed_bytes,
                            cancelled=cancelled,
                        )
                    if mode & stat.S_IXUSR:
                        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        else:
            with tarfile.open(archive_path, "r:gz") as archive:
                tar_members = archive.getmembers()
                if len(tar_members) > max_members:
                    raise UnsafeArchiveError("archive contains too many members")
                if any(item.size < 0 for item in tar_members):
                    raise UnsafeArchiveError("archive contains an invalid member size")
                regular_size = sum(item.size for item in tar_members if item.isfile())
                if regular_size > max_uncompressed_bytes:
                    raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
                for tar_item in tar_members:
                    if cancelled is not None and cancelled.is_set():
                        raise InstallCancelled("model installation cancelled")
                    if not (tar_item.isfile() or tar_item.isdir()):
                        raise UnsafeArchiveError("archive links and special files are forbidden")
                    member = _registered_member_path(tar_item.name, seen)
                    target = _destination_path(destination, member)
                    if tar_item.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    tar_source = archive.extractfile(tar_item)
                    if tar_source is None:
                        raise UnsafeArchiveError("archive member cannot be read")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar_source, target.open("wb") as output:
                        copied = _copy_bounded(
                            tar_source,
                            output,
                            copied=copied,
                            expected_member_bytes=tar_item.size,
                            max_uncompressed_bytes=max_uncompressed_bytes,
                            cancelled=cancelled,
                        )
                    target.chmod(tar_item.mode & 0o777)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def download_verified(
    *,
    url: str,
    destination: Path,
    expected_sha256: str,
    expected_size: int,
    cancelled: threading.Event,
    paused: threading.Event | None = None,
    progress: Callable[[int], None],
    client_factory: Callable[[], httpx.Client] | None = None,
) -> None:
    """Resume an asset download and atomically publish it after hash verification."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.parent / f".{destination.name}.part"
    if partial.is_symlink():
        partial.unlink()
    elif partial.exists() and not partial.is_file():
        raise ValueError("download partial path is not a regular file")
    digest = hashlib.sha256()
    received = 0
    current_url, origin_host = _validated_initial_download_url(url)
    factory = client_factory or (
        lambda: httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(connect=15, read=30, write=30, pool=5),
            trust_env=False,
        )
    )
    try:
        if partial.is_file():
            received = partial.stat().st_size
            if received > expected_size:
                partial.unlink()
                received = 0
            else:
                with partial.open("rb") as existing:
                    for chunk in iter(lambda: existing.read(_CHUNK_SIZE), b""):
                        digest.update(chunk)
                progress(received)
        if paused is not None and paused.is_set():
            raise InstallPaused("model installation paused")
        if cancelled.is_set():
            raise InstallCancelled("model installation cancelled")
        if received == expected_size:
            if digest.hexdigest() != expected_sha256.casefold():
                raise ValueError("download SHA-256 does not match the signed catalog")
            os.replace(partial, destination)
            return

        request_headers = {"Range": f"bytes={received}-"} if received else None
        with factory() as client:
            redirects = 0
            while True:
                stream = (
                    client.stream("GET", current_url, headers=request_headers)
                    if request_headers
                    else client.stream("GET", current_url)
                )
                with stream as response:
                    status_code = int(getattr(response, "status_code", 200))
                    if status_code in _DOWNLOAD_REDIRECT_STATUSES:
                        redirects += 1
                        if redirects > _MAX_DOWNLOAD_REDIRECTS:
                            raise ValueError("download exceeded its redirect limit")
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("download redirect is missing its destination")
                        current_url = _validated_redirect_url(
                            current_url,
                            location,
                            origin_host=origin_host,
                        )
                        continue
                    response.raise_for_status()
                    if received and status_code != 206:
                        received = 0
                        digest = hashlib.sha256()
                        progress(0)
                    advertised = response.headers.get("content-length")
                    expected_response_size = expected_size - received
                    if advertised is not None:
                        if not advertised.isascii() or not advertised.isdecimal():
                            raise ValueError("download size header is malformed")
                        if int(advertised) != expected_response_size:
                            raise ValueError("download size does not match the signed catalog")
                    mode = "ab" if received else "wb"
                    with partial.open(mode) as output:
                        for chunk in response.iter_bytes(_CHUNK_SIZE):
                            if paused is not None and paused.is_set():
                                raise InstallPaused("model installation paused")
                            if cancelled.is_set():
                                raise InstallCancelled("model installation cancelled")
                            if not chunk:
                                continue
                            received += len(chunk)
                            if received > expected_size:
                                raise ValueError("download exceeds the signed catalog size")
                            output.write(chunk)
                            digest.update(chunk)
                            progress(received)
                        output.flush()
                        os.fsync(output.fileno())
                    break
        if received != expected_size:
            raise ValueError("download is incomplete")
        if digest.hexdigest() != expected_sha256.casefold():
            raise ValueError("download SHA-256 does not match the signed catalog")
        os.replace(partial, destination)
    except InstallPaused:
        raise
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _is_link_like(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _unlink_link_like(path: Path) -> None:
    if path.is_junction() and not path.is_symlink():
        path.rmdir()
    else:
        path.unlink(missing_ok=True)


def _runtime_source_name(archive_type: Literal["zip", "tar.gz"]) -> str:
    return f"{_RUNTIME_SOURCE_PREFIX}.{archive_type}"


def _hash_archive_member(source: IO[bytes], *, expected_size: int) -> str:
    digest = hashlib.sha256()
    received = 0
    while chunk := source.read(_CHUNK_SIZE):
        received += len(chunk)
        if received > expected_size:
            raise UnsafeArchiveError("archive member exceeds its declared size")
        digest.update(chunk)
    if received != expected_size:
        raise UnsafeArchiveError("archive member size does not match its metadata")
    return digest.hexdigest()


def _relative_to_package(
    member: PurePosixPath,
    package_parts: tuple[str, ...],
) -> PurePosixPath | None:
    if member.parts[: len(package_parts)] != package_parts:
        return None
    relative_parts = member.parts[len(package_parts) :]
    if not relative_parts:
        return None
    return PurePosixPath(*relative_parts)


def _runtime_archive_manifest(
    archive_path: Path,
    runtime: RuntimeAsset,
) -> dict[str, tuple[int, str]]:
    """Derive the installed file inventory from the checksum-pinned source archive."""

    seen: set[str] = set()
    if runtime.archive_type == "zip":
        with zipfile.ZipFile(archive_path) as archive:
            zip_members = archive.infolist()
            if len(zip_members) > _MAX_ARCHIVE_MEMBERS:
                raise UnsafeArchiveError("archive contains too many members")
            if any(item.file_size < 0 for item in zip_members):
                raise UnsafeArchiveError("archive contains an invalid member size")
            if sum(item.file_size for item in zip_members) > _MAX_ARCHIVE_BYTES:
                raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
            checked: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for zip_item in zip_members:
                mode = zip_item.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if stat.S_ISLNK(mode) or (
                    file_type and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)
                ):
                    raise UnsafeArchiveError("archive links and special files are forbidden")
                checked.append((zip_item, _registered_member_path(zip_item.filename, seen)))
            executable_members = [
                member
                for zip_item, member in checked
                if not zip_item.is_dir() and member.name == runtime.executable
            ]
            if len(executable_members) != 1:
                raise UnsafeArchiveError("runtime archive does not contain one expected executable")
            package_parts = executable_members[0].parts[:-1]
            manifest: dict[str, tuple[int, str]] = {}
            for zip_item, member in checked:
                if zip_item.is_dir():
                    continue
                relative = _relative_to_package(member, package_parts)
                if relative is None:
                    continue
                identity = relative.as_posix()
                if len(relative.parts) == 1 and identity in {
                    _RUNTIME_MARKER_NAME,
                    _runtime_source_name(runtime.archive_type),
                }:
                    raise UnsafeArchiveError("runtime archive uses a reserved metadata path")
                with archive.open(zip_item) as zip_source:
                    manifest[identity] = (
                        zip_item.file_size,
                        _hash_archive_member(
                            zip_source,
                            expected_size=zip_item.file_size,
                        ),
                    )
        if runtime.executable not in manifest:
            raise UnsafeArchiveError("runtime executable is outside the packaged runtime root")
        return manifest
    else:
        with tarfile.open(archive_path, "r:gz") as archive:
            tar_members = archive.getmembers()
            if len(tar_members) > _MAX_ARCHIVE_MEMBERS:
                raise UnsafeArchiveError("archive contains too many members")
            if any(item.size < 0 for item in tar_members):
                raise UnsafeArchiveError("archive contains an invalid member size")
            if sum(item.size for item in tar_members if item.isfile()) > _MAX_ARCHIVE_BYTES:
                raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
            checked_tar: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
            for tar_item in tar_members:
                if not (tar_item.isfile() or tar_item.isdir()):
                    raise UnsafeArchiveError("archive links and special files are forbidden")
                checked_tar.append((tar_item, _registered_member_path(tar_item.name, seen)))
            executable_members = [
                member
                for tar_item, member in checked_tar
                if tar_item.isfile() and member.name == runtime.executable
            ]
            if len(executable_members) != 1:
                raise UnsafeArchiveError("runtime archive does not contain one expected executable")
            package_parts = executable_members[0].parts[:-1]
            manifest = {}
            for tar_item, member in checked_tar:
                if not tar_item.isfile():
                    continue
                relative = _relative_to_package(member, package_parts)
                if relative is None:
                    continue
                identity = relative.as_posix()
                if len(relative.parts) == 1 and identity in {
                    _RUNTIME_MARKER_NAME,
                    _runtime_source_name(runtime.archive_type),
                }:
                    raise UnsafeArchiveError("runtime archive uses a reserved metadata path")
                tar_source = archive.extractfile(tar_item)
                if tar_source is None:
                    raise UnsafeArchiveError("archive member cannot be read")
                with tar_source:
                    manifest[identity] = (
                        tar_item.size,
                        _hash_archive_member(
                            tar_source,
                            expected_size=tar_item.size,
                        ),
                    )
    if runtime.executable not in manifest:
        raise UnsafeArchiveError("runtime executable is outside the packaged runtime root")
    return manifest


def _archive_declared_uncompressed_size(
    archive_path: Path,
    archive_type: Literal["zip", "tar.gz"],
) -> int:
    if archive_type == "zip":
        with zipfile.ZipFile(archive_path) as archive:
            zip_members = archive.infolist()
            if len(zip_members) > _MAX_ARCHIVE_MEMBERS:
                raise UnsafeArchiveError("archive contains too many members")
            if any(item.file_size < 0 for item in zip_members):
                raise UnsafeArchiveError("archive contains an invalid member size")
            declared = sum(item.file_size for item in zip_members)
    else:
        with tarfile.open(archive_path, "r:gz") as archive:
            tar_members = archive.getmembers()
            if len(tar_members) > _MAX_ARCHIVE_MEMBERS:
                raise UnsafeArchiveError("archive contains too many members")
            if any(item.size < 0 for item in tar_members):
                raise UnsafeArchiveError("archive contains an invalid member size")
            declared = sum(item.size for item in tar_members if item.isfile())
    if declared > _MAX_ARCHIVE_BYTES:
        raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
    return declared


class ManagedRuntime:
    """Own the llama.cpp runtime required by analysis inside the per-user data directory."""

    def __init__(
        self,
        data_dir: Path,
        *,
        download: Callable[..., None] = download_verified,
    ) -> None:
        self.data_dir = data_dir.resolve(strict=False)
        self.runtime_root = self.data_dir / "models" / "runtime"
        self.model_root = self.data_dir / "models" / "weights"
        self.staging_root = self.data_dir / "staging" / "local-model"
        self.download = download
        self._lock = threading.RLock()
        self._cancelled = threading.Event()
        self._paused = threading.Event()
        self._worker_started = threading.Event()
        self._worker_done = threading.Event()
        self._worker_done.set()
        self._task: asyncio.Task[None] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._api_key: str | None = None
        self._endpoint: str | None = None
        self._model_key: str | None = None
        self._phase: RuntimePhase = "idle"
        self._downloaded = 0
        self._total = 0
        self._error_code: str | None = None
        self._replace_from: str | None = None
        self._restart_times: deque[float] = deque(maxlen=4)
        self._runtime_verification_cache: tuple[object, ...] | None = None

    def _paths(self, model: ModelCatalogEntry, runtime: RuntimeAsset) -> tuple[Path, Path, Path]:
        catalog = load_model_catalog()
        runtime_dir = self.runtime_root / catalog.runtime.version / current_platform_key()
        executable = runtime_dir / runtime.executable
        model_path = self.model_root / model.filename
        return runtime_dir, executable, model_path

    def _ensure_owned_directory(self, directory: Path) -> None:
        try:
            relative = directory.relative_to(self.data_dir)
        except ValueError as exc:
            raise RuntimeError("managed directory escapes application data") from exc
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if _is_link_like(self.data_dir) or not self.data_dir.is_dir():
            raise RuntimeError("managed data path is not a trusted directory")
        current = self.data_dir
        for part in relative.parts:
            current /= part
            if current.exists() or _is_link_like(current):
                if _is_link_like(current) or not current.is_dir():
                    raise RuntimeError("managed path is not a trusted directory")
            else:
                current.mkdir()
        resolved = directory.resolve(strict=True)
        if resolved != self.data_dir and self.data_dir not in resolved.parents:
            raise RuntimeError("managed directory escapes application data")

    def _runtime_tree_stamp(self, runtime_dir: Path) -> tuple[tuple[object, ...], ...]:
        root_stat = runtime_dir.lstat()
        entries: list[tuple[object, ...]] = [
            (
                ".",
                root_stat.st_mode,
                root_stat.st_size,
                root_stat.st_mtime_ns,
                root_stat.st_ctime_ns,
            )
        ]
        for current, directory_names, file_names in os.walk(runtime_dir, followlinks=False):
            directory_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            current_path = Path(current)
            for name in [*directory_names, *file_names]:
                path = current_path / name
                item_stat = path.lstat()
                entries.append(
                    (
                        path.relative_to(runtime_dir).as_posix(),
                        item_stat.st_mode,
                        item_stat.st_size,
                        item_stat.st_mtime_ns,
                        item_stat.st_ctime_ns,
                    )
                )
            directory_names[:] = [
                name for name in directory_names if not _is_link_like(current_path / name)
            ]
        return tuple(entries)

    def _verified_regular_file(
        self,
        path: Path,
        *,
        root: Path,
        expected_size: int,
        expected_sha256: str,
        cancelled: threading.Event | None = None,
    ) -> None:
        if cancelled is not None and cancelled.is_set():
            raise RuntimeStartCancelled("managed runtime startup was cancelled")
        if _is_link_like(path) or not path.is_file():
            raise ValueError("managed asset is not a regular file")
        if _is_link_like(root) or not root.is_dir():
            raise ValueError("managed asset root is not a trusted directory")
        resolved_root = root.resolve(strict=True)
        if resolved_root != self.data_dir and self.data_dir not in resolved_root.parents:
            raise ValueError("managed asset root escapes application data")
        resolved_path = path.resolve(strict=True)
        if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
            raise ValueError("managed asset escapes its installation directory")
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise ValueError("managed asset size does not match the signed catalog")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size != expected_size
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
            ):
                raise ValueError("managed asset changed before verification")
            for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                if cancelled is not None and cancelled.is_set():
                    raise RuntimeStartCancelled("managed runtime startup was cancelled")
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        current = path.stat()
        if (
            after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or _is_link_like(path)
            or current.st_dev != opened.st_dev
            or current.st_ino != opened.st_ino
            or current.st_size != opened.st_size
            or current.st_mtime_ns != opened.st_mtime_ns
            or digest.hexdigest() != expected_sha256.casefold()
        ):
            raise ValueError("managed asset SHA-256 verification failed")

    def _runtime_is_verified(
        self,
        runtime_dir: Path,
        executable: Path,
        runtime: RuntimeAsset,
        *,
        force: bool = False,
    ) -> bool:
        marker = runtime_dir / _RUNTIME_MARKER_NAME
        source_archive = runtime_dir / _runtime_source_name(runtime.archive_type)
        try:
            if _is_link_like(runtime_dir) or not runtime_dir.is_dir():
                raise ValueError("managed runtime directory is not trusted")
            resolved_runtime = runtime_dir.resolve(strict=True)
            if resolved_runtime != self.data_dir and self.data_dir not in resolved_runtime.parents:
                raise ValueError("managed runtime directory escapes application data")
            stamp = self._runtime_tree_stamp(runtime_dir)
            cache_key: tuple[object, ...] = (
                str(resolved_runtime),
                runtime.sha256,
                runtime.archive_type,
                runtime.executable,
                stamp,
            )
            with self._lock:
                if not force and self._runtime_verification_cache == cache_key:
                    return True
            if (
                _is_link_like(marker)
                or _is_link_like(source_archive)
                or marker.read_bytes() != runtime.sha256.encode("ascii")
            ):
                raise ValueError("managed runtime catalog marker is invalid")
            self._verified_regular_file(
                source_archive,
                root=runtime_dir,
                expected_size=runtime.size_bytes,
                expected_sha256=runtime.sha256,
            )
            expected_files = _runtime_archive_manifest(source_archive, runtime)
            actual_files: dict[str, Path] = {}
            for current, directory_names, file_names in os.walk(runtime_dir, followlinks=False):
                directory_names.sort(key=str.casefold)
                file_names.sort(key=str.casefold)
                current_path = Path(current)
                for name in directory_names:
                    directory = current_path / name
                    if _is_link_like(directory) or not directory.is_dir():
                        raise ValueError("managed runtime contains a linked directory")
                    resolved = directory.resolve(strict=True)
                    if resolved != resolved_runtime and resolved_runtime not in resolved.parents:
                        raise ValueError("managed runtime directory escapes application data")
                for name in file_names:
                    path = current_path / name
                    relative = path.relative_to(runtime_dir).as_posix()
                    if relative in {
                        _RUNTIME_MARKER_NAME,
                        _runtime_source_name(runtime.archive_type),
                    }:
                        continue
                    if _is_link_like(path) or not path.is_file():
                        raise ValueError("managed runtime contains a special file")
                    actual_files[relative] = path
                directory_names[:] = [
                    name for name in directory_names if not _is_link_like(current_path / name)
                ]
            if actual_files.keys() != expected_files.keys():
                raise ValueError("managed runtime file inventory does not match its source archive")
            for relative, (expected_size, expected_sha256) in expected_files.items():
                self._verified_regular_file(
                    actual_files[relative],
                    root=runtime_dir,
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                )
            if actual_files.get(runtime.executable) != executable:
                raise ValueError("managed runtime executable path is invalid")
            verified_stamp = self._runtime_tree_stamp(runtime_dir)
            if verified_stamp != stamp:
                raise ValueError("managed runtime changed during integrity verification")
            cache_key = (
                str(resolved_runtime),
                runtime.sha256,
                runtime.archive_type,
                runtime.executable,
                verified_stamp,
            )
            with self._lock:
                self._runtime_verification_cache = cache_key
            return True
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile):
            with self._lock:
                self._runtime_verification_cache = None
            return False

    def _verify_launch_assets(
        self,
        *,
        runtime_dir: Path,
        executable: Path,
        runtime: RuntimeAsset,
        model_path: Path,
        model: ModelCatalogEntry,
        cancelled: threading.Event | None,
    ) -> None:
        if cancelled is not None and cancelled.is_set():
            raise RuntimeStartCancelled("managed runtime startup was cancelled")
        if not self._runtime_is_verified(runtime_dir, executable, runtime, force=True):
            raise ManagedAssetIntegrityError("managed runtime integrity verification failed")
        try:
            self._verified_regular_file(
                model_path,
                root=self.model_root,
                expected_size=model.size_bytes,
                expected_sha256=model.sha256,
                cancelled=cancelled,
            )
        except RuntimeStartCancelled:
            raise
        except (OSError, ValueError) as exc:
            raise ManagedAssetIntegrityError("managed model integrity verification failed") from exc

    def snapshot(self) -> ManagedRuntimeSnapshot:
        catalog = load_model_catalog()
        with self._lock:
            model_key = self._model_key or (catalog.models[0].key if catalog.models else None)
            if model_key is None:
                runtime_installed = model_installed = False
            else:
                model = catalog.model(model_key)
                runtime = catalog.runtime.assets[current_platform_key()]
                _, executable, model_path = self._paths(model, runtime)
                runtime_installed = self._runtime_is_verified(
                    executable.parent,
                    executable,
                    runtime,
                )
                try:
                    model_installed = (
                        not _is_link_like(model_path)
                        and model_path.is_file()
                        and model_path.stat().st_size == model.size_bytes
                        and model_path.resolve(strict=True).is_relative_to(self.data_dir)
                    )
                except OSError:
                    model_installed = False
            ready = (
                self._process is not None
                and self._process.poll() is None
                and self._phase == "ready"
            )
            return ManagedRuntimeSnapshot(
                phase=self._phase,
                model_key=model_key,
                bytes_downloaded=self._downloaded,
                bytes_total=self._total,
                runtime_installed=runtime_installed,
                model_installed=model_installed,
                ready=ready,
                endpoint=self._endpoint if ready else None,
                error_code=self._error_code,
            )

    async def install(self, model_key: str, *, replace: bool = False) -> ManagedRuntimeSnapshot:
        with self._lock:
            if not self._worker_done.is_set() or (self._task is not None and not self._task.done()):
                raise RuntimeError("a local model installation is already running")
            if self._phase == "paused" and self._model_key == model_key:
                raise RuntimeError("resume the paused model installation")
            catalog = load_model_catalog()
            model = catalog.model(model_key)
            runtime = catalog.runtime.assets[current_platform_key()]
            self._cancelled.clear()
            self._paused.clear()
            self._replace_from = (
                self._model_key
                if replace and self._model_key is not None and self._model_key != model_key
                else None
            )
            self._model_key = model_key
            self._error_code = None
            self._phase = "downloading_runtime"
            self._downloaded = 0
            self._total = runtime.size_bytes + model.size_bytes
            self._worker_started.clear()
            self._worker_done.clear()
            self._task = asyncio.create_task(asyncio.to_thread(self._run_install_worker, model_key))
        await asyncio.sleep(0)
        return self.snapshot()

    async def wait_for_install(self) -> ManagedRuntimeSnapshot:
        task = self._task
        caller_cancelled = False
        if task is not None:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                current = asyncio.current_task()
                caller_cancelled = current is not None and current.cancelling() > 0

        if not self._worker_done.is_set():
            worker_wait = asyncio.create_task(asyncio.to_thread(self._worker_done.wait))
            while not worker_wait.done():
                try:
                    await asyncio.shield(worker_wait)
                except asyncio.CancelledError:
                    caller_cancelled = True
            await worker_wait
        if caller_cancelled:
            raise asyncio.CancelledError
        return self.snapshot()

    def cancel_install(self) -> ManagedRuntimeSnapshot:
        with self._lock:
            self._cancelled.set()
            self._paused.clear()
            if self._phase in {
                "downloading_runtime",
                "installing_runtime",
                "downloading_model",
                "starting",
                "paused",
            }:
                self._phase = "cancelled"
        return self.snapshot()

    def discard_partial_downloads(self) -> None:
        """Delete resumable fragments only after the installer worker has stopped."""
        for root in (self.staging_root, self.model_root):
            resolved = root.resolve(strict=False)
            if resolved == self.data_dir or not resolved.is_relative_to(self.data_dir):
                raise RuntimeError("managed download path escapes the application data directory")
            if not root.is_dir():
                continue
            for partial in root.glob(".*.part"):
                partial.unlink(missing_ok=True)

    def pause_install(self) -> ManagedRuntimeSnapshot:
        with self._lock:
            if self._phase not in {"downloading_runtime", "downloading_model"}:
                raise RuntimeError("only an active download can be paused")
            self._paused.set()
            self._phase = "paused"
        return self.snapshot()

    async def resume_install(self) -> ManagedRuntimeSnapshot:
        with self._lock:
            if self._phase != "paused" or self._model_key is None:
                raise RuntimeError("no paused model installation is available")
            previous = self._task
            model_key = self._model_key
        if previous is not None:
            await self.wait_for_install()
        with self._lock:
            self._cancelled.clear()
            self._paused.clear()
            self._error_code = None
            self._phase = "downloading_runtime"
            self._worker_started.clear()
            self._worker_done.clear()
            self._task = asyncio.create_task(asyncio.to_thread(self._run_install_worker, model_key))
        await asyncio.sleep(0)
        return self.snapshot()

    def _progress(self, base: int) -> Callable[[int], None]:
        def update(received: int) -> None:
            with self._lock:
                self._downloaded = base + received

        return update

    def _install_sync(self, model_key: str) -> None:
        catalog = load_model_catalog()
        model = catalog.model(model_key)
        runtime = catalog.runtime.assets[current_platform_key()]
        runtime_dir, executable, model_path = self._paths(model, runtime)
        self._ensure_owned_directory(self.staging_root)
        self._ensure_owned_directory(self.model_root)
        self._ensure_owned_directory(runtime_dir.parent)
        with self._lock:
            self._total = runtime.size_bytes + model.size_bytes
            self._downloaded = 0
        try:
            runtime_verified = self._runtime_is_verified(runtime_dir, executable, runtime)
            model_verified = False
            if model_path.exists() or _is_link_like(model_path):
                try:
                    self._verified_regular_file(
                        model_path,
                        root=self.model_root,
                        expected_size=model.size_bytes,
                        expected_sha256=model.sha256,
                    )
                    model_verified = True
                except (OSError, ValueError):
                    if _is_link_like(model_path) or model_path.is_file():
                        if _is_link_like(model_path):
                            _unlink_link_like(model_path)
                        else:
                            model_path.unlink(missing_ok=True)
                    elif model_path.is_dir():
                        shutil.rmtree(model_path)

            archive = self.staging_root / (
                f"llama-{catalog.runtime.version}.{runtime.archive_type}"
            )
            archive_verified = False
            if not runtime_verified and (archive.exists() or _is_link_like(archive)):
                try:
                    self._verified_regular_file(
                        archive,
                        root=self.staging_root,
                        expected_size=runtime.size_bytes,
                        expected_sha256=runtime.sha256,
                    )
                    archive_verified = True
                except (OSError, ValueError):
                    if _is_link_like(archive) or archive.is_file():
                        if _is_link_like(archive):
                            _unlink_link_like(archive)
                        else:
                            archive.unlink(missing_ok=True)
                    elif archive.is_dir():
                        shutil.rmtree(archive)
            elif runtime_verified and (archive.exists() or _is_link_like(archive)):
                if _is_link_like(archive) or archive.is_file():
                    if _is_link_like(archive):
                        _unlink_link_like(archive)
                    else:
                        archive.unlink(missing_ok=True)
                elif archive.is_dir():
                    shutil.rmtree(archive)

            model_partial = model_path.parent / f".{model_path.name}.part"
            resumable_model_bytes = 0
            if not model_verified and not _is_link_like(model_partial) and model_partial.is_file():
                partial_size = model_partial.stat().st_size
                if partial_size <= model.size_bytes:
                    resumable_model_bytes = partial_size
            download_bytes = 0
            if not runtime_verified and not archive_verified:
                download_bytes += runtime.size_bytes
            if not model_verified:
                download_bytes += model.size_bytes - resumable_model_bytes
            if download_bytes:
                download_bytes += 256 * 1024 * 1024
            if download_bytes and shutil.disk_usage(self.data_dir).free < download_bytes:
                with self._lock:
                    self._phase = "error"
                    self._error_code = "insufficient_disk_space"
                return

            if not runtime_verified:
                with self._lock:
                    self._phase = "downloading_runtime"
                if not archive_verified:
                    self.download(
                        url=runtime.url,
                        destination=archive,
                        expected_sha256=runtime.sha256,
                        expected_size=runtime.size_bytes,
                        cancelled=self._cancelled,
                        paused=self._paused,
                        progress=self._progress(0),
                    )
                else:
                    with self._lock:
                        self._downloaded = runtime.size_bytes
                extraction_bytes = _archive_declared_uncompressed_size(
                    archive,
                    runtime.archive_type,
                )
                remaining_model_bytes = (
                    0 if model_verified else model.size_bytes - resumable_model_bytes
                )
                required_free = extraction_bytes + remaining_model_bytes + (256 * 1024 * 1024)
                if shutil.disk_usage(self.data_dir).free < required_free:
                    with self._lock:
                        self._phase = "error"
                        self._error_code = "insufficient_disk_space"
                    return
                with self._lock:
                    self._phase = "installing_runtime"
                extracted = self.staging_root / f"runtime-{uuid4().hex}"
                try:
                    safe_extract_archive(
                        archive,
                        extracted,
                        runtime.archive_type,
                        cancelled=self._cancelled,
                    )
                    candidates = [
                        path
                        for path in extracted.rglob(runtime.executable)
                        if path.is_file() and not _is_link_like(path)
                    ]
                    if len(candidates) != 1:
                        raise ValueError("runtime archive does not contain one expected executable")
                    packaged_root = candidates[0].parent
                    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
                    if _is_link_like(runtime_dir) or runtime_dir.is_file():
                        if _is_link_like(runtime_dir):
                            _unlink_link_like(runtime_dir)
                        else:
                            runtime_dir.unlink(missing_ok=True)
                    elif runtime_dir.exists():
                        shutil.rmtree(runtime_dir)
                    with self._lock:
                        self._runtime_verification_cache = None
                    os.replace(packaged_root, runtime_dir)
                    os.replace(
                        archive,
                        runtime_dir / _runtime_source_name(runtime.archive_type),
                    )
                    marker = runtime_dir / _RUNTIME_MARKER_NAME
                    marker_temporary = runtime_dir / f".{_RUNTIME_MARKER_NAME}.{uuid4().hex}.tmp"
                    with marker_temporary.open("w", encoding="ascii", newline="") as output:
                        output.write(runtime.sha256)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(marker_temporary, marker)
                    if not self._runtime_is_verified(
                        runtime_dir,
                        executable,
                        runtime,
                        force=True,
                    ):
                        raise ValueError("installed runtime failed integrity verification")
                finally:
                    shutil.rmtree(extracted, ignore_errors=True)
            else:
                with self._lock:
                    self._downloaded = runtime.size_bytes
            if not model_verified:
                with self._lock:
                    self._phase = "downloading_model"
                self.download(
                    url=model.url,
                    destination=model_path,
                    expected_sha256=model.sha256,
                    expected_size=model.size_bytes,
                    cancelled=self._cancelled,
                    paused=self._paused,
                    progress=self._progress(runtime.size_bytes),
                )
            else:
                with self._lock:
                    self._downloaded = self._total
            if self._paused.is_set():
                raise InstallPaused("model installation paused")
            if self._cancelled.is_set():
                raise InstallCancelled("model installation cancelled")
            self.start(model_key, cancelled=self._cancelled)
            replace_from = self._replace_from
            if replace_from and replace_from != model_key:
                previous = catalog.model(replace_from)
                (self.model_root / previous.filename).unlink(missing_ok=True)
            self._replace_from = None
        except InstallPaused:
            with self._lock:
                self._phase = "paused"
                self._error_code = None
        except InstallCancelled:
            with self._lock:
                self._phase = "cancelled"
                self._error_code = None
                self._replace_from = None
        except Exception as exc:
            with self._lock:
                self._phase = "error"
                self._error_code = (
                    "runtime_blocked_by_windows_policy"
                    if isinstance(exc, RuntimeBlockedByWindowsPolicy)
                    else "managed_asset_integrity_failed"
                    if isinstance(exc, ManagedAssetIntegrityError)
                    else type(exc).__name__.lower()
                )
                self._replace_from = None

    def _run_install_worker(self, model_key: str) -> None:
        self._worker_started.set()
        try:
            self._install_sync(model_key)
        finally:
            self._worker_done.set()

    def start(
        self,
        model_key: str | None = None,
        *,
        cancelled: threading.Event | None = None,
    ) -> ManagedRuntimeSnapshot:
        catalog = load_model_catalog()
        selected = model_key or self._model_key or catalog.models[0].key
        model = catalog.model(selected)
        runtime = catalog.runtime.assets[current_platform_key()]
        runtime_dir, executable, model_path = self._paths(model, runtime)
        self._verify_launch_assets(
            runtime_dir=runtime_dir,
            executable=executable,
            runtime=runtime,
            model_path=model_path,
            model=model,
            cancelled=cancelled,
        )
        if cancelled is not None and cancelled.is_set():
            raise RuntimeStartCancelled("managed runtime startup was cancelled")
        self.stop()
        if cancelled is not None and cancelled.is_set():
            raise RuntimeStartCancelled("managed runtime startup was cancelled")
        port = _available_loopback_port()
        api_key = secrets.token_urlsafe(48)
        endpoint = f"http://127.0.0.1:{port}"
        command = [
            str(executable),
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--alias",
            model.key,
            "--ctx-size",
            str(model.recommended_context_tokens),
            "--parallel",
            "1",
        ]
        runtime_environment = _managed_runtime_environment(api_key)
        creationflags = (
            subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            if os.name == "nt"
            else 0
        )
        with self._lock:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeStartCancelled("managed runtime startup was cancelled")
            self._phase = "starting"
            self._model_key = selected
            self._api_key = api_key
            self._endpoint = endpoint
            try:
                self._process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    cwd=runtime_dir,
                    close_fds=True,
                    env=runtime_environment,
                )
            except OSError as exc:
                self._api_key = None
                self._endpoint = None
                self._process = None
                self._phase = "error"
                self._error_code = "runtime_start_failed"
                if os.name == "nt" and getattr(exc, "winerror", None) in {577, 1260}:
                    self._error_code = "runtime_blocked_by_windows_policy"
                    raise RuntimeBlockedByWindowsPolicy(
                        "Windows application-control policy blocked the managed runtime"
                    ) from exc
                raise
            except Exception:
                self._api_key = None
                self._endpoint = None
                self._process = None
                self._phase = "error"
                self._error_code = "runtime_start_failed"
                raise
        if not self._wait_until_healthy(timeout_seconds=45, cancelled=cancelled):
            exit_code = self._process.poll() if self._process is not None else None
            self.stop()
            if cancelled is not None and cancelled.is_set():
                with self._lock:
                    self._phase = "idle"
                    self._error_code = None
                raise RuntimeStartCancelled("managed runtime startup was cancelled")
            with self._lock:
                self._phase = "error"
                if os.name == "nt" and exit_code in {-1073740760, 3221226536}:
                    self._error_code = "runtime_blocked_by_windows_policy"
                else:
                    self._error_code = "runtime_start_failed"
            if self._error_code == "runtime_blocked_by_windows_policy":
                raise RuntimeBlockedByWindowsPolicy(
                    "Windows application-control policy blocked the managed runtime"
                )
            raise RuntimeError("managed llama.cpp failed its health check")
        with self._lock:
            self._phase = "ready"
            self._error_code = None
        return self.snapshot()

    def _wait_until_healthy(
        self,
        *,
        timeout_seconds: float,
        cancelled: threading.Event | None = None,
    ) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if cancelled is not None and cancelled.is_set():
                return False
            process = self._process
            if process is None or process.poll() is not None:
                return False
            try:
                with httpx.Client(timeout=1, trust_env=False) as client:
                    response = client.get(f"{self._endpoint}/health")
                if response.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(0.15)
        return False

    def cancel_startup(self, cancelled: threading.Event) -> None:
        """Linearize shutdown against the process-spawn critical section."""

        with self._lock:
            cancelled.set()

    def restart(self) -> ManagedRuntimeSnapshot:
        now = time.monotonic()
        with self._lock:
            while self._restart_times and now - self._restart_times[0] > 300:
                self._restart_times.popleft()
            if len(self._restart_times) >= 3:
                raise RuntimeError("managed runtime restart limit reached")
            self._restart_times.append(now)
        return self.start()

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._api_key = None
            self._endpoint = None
            if self._phase in {"ready", "starting"}:
                self._phase = "idle"
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    if process.poll() is None:
                        raise
                if process.poll() is None:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
        finally:
            if process.poll() is not None:
                with self._lock:
                    if self._process is process:
                        self._process = None

    def erase_installation(self) -> dict[str, int]:
        """Remove only model/runtime paths owned by CareerOS Local."""

        self.cancel_install()
        if not self._worker_done.is_set():
            raise RuntimeError("managed installer worker must stop before erasure")
        self.stop()
        removed_files = 0
        removed_bytes = 0
        for target in (self.runtime_root, self.model_root, self.staging_root):
            try:
                target.relative_to(self.data_dir)
            except ValueError as exc:
                raise RuntimeError(
                    "managed runtime path escapes the application data directory"
                ) from exc
            if _is_link_like(target):
                try:
                    removed_bytes += target.lstat().st_size
                except OSError:
                    pass
                _unlink_link_like(target)
                removed_files += 1
                continue
            resolved = target.resolve(strict=False)
            if resolved == self.data_dir or not resolved.is_relative_to(self.data_dir):
                raise RuntimeError("managed runtime path escapes the application data directory")
            if not target.exists():
                continue
            if target.is_file():
                try:
                    removed_bytes += target.stat().st_size
                except OSError:
                    pass
                target.unlink(missing_ok=True)
                removed_files += 1
                continue
            for item in target.rglob("*"):
                if item.is_file() or item.is_symlink():
                    removed_files += 1
                    try:
                        removed_bytes += item.stat().st_size
                    except OSError:
                        pass
            shutil.rmtree(target)
        for parent in (self.data_dir / "models", self.data_dir / "staging"):
            if (
                parent.exists()
                and not _is_link_like(parent)
                and parent.resolve(strict=True).is_relative_to(self.data_dir)
                and not any(parent.iterdir())
            ):
                parent.rmdir()
        with self._lock:
            self._phase = "idle"
            self._model_key = None
            self._downloaded = 0
            self._total = 0
            self._error_code = None
        return {"model_files": removed_files, "model_bytes": removed_bytes}

    def provider(self) -> LlamaCppProvider:
        snapshot = self.snapshot()
        if not snapshot.ready or self._endpoint is None or self._api_key is None:
            raise RuntimeError("managed local model is not ready")
        return LlamaCppProvider(
            endpoint=self._endpoint,
            model=snapshot.model_key or "managed",
            api_key=self._api_key,
            process_id=self._process.pid if self._process is not None else None,
        )


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


_singleton_lock = threading.Lock()
_singleton: ManagedRuntime | None = None


def managed_data_dir() -> Path:
    configured = os.getenv("CAREEROS_DESKTOP_DATA_DIR") or os.getenv("DATA_DIR") or "data"
    return Path(configured).expanduser().resolve(strict=False)


def get_managed_runtime() -> ManagedRuntime:
    global _singleton
    with _singleton_lock:
        root = managed_data_dir()
        if _singleton is None or _singleton.data_dir != root:
            if _singleton is not None:
                _singleton.stop()
            _singleton = ManagedRuntime(root)
        return _singleton


def stop_managed_runtime() -> None:
    with _singleton_lock:
        if _singleton is not None:
            _singleton.stop()


def erase_managed_runtime_installation() -> dict[str, int]:
    return get_managed_runtime().erase_installation()


async def quiesce_managed_runtime_installation() -> None:
    """Cancel and join the real installer worker before destructive cleanup."""

    manager = get_managed_runtime()
    manager.cancel_install()
    try:
        await manager.wait_for_install()
    except asyncio.CancelledError:
        raise
    except Exception:
        # A completed install task may retain an exception from setup that ran
        # before its normal error-state handler. Erasure needs only the stronger
        # invariant that the underlying worker has actually stopped.
        if not manager._worker_done.is_set():
            raise
