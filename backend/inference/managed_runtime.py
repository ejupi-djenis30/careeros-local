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
from typing import Callable, Literal
from uuid import uuid4

import httpx

from backend.inference.catalog import (
    ModelCatalogEntry,
    RuntimeAsset,
    current_platform_key,
    load_model_catalog,
    verify_file_sha256,
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


class InstallCancelled(RuntimeError):
    pass


class InstallPaused(RuntimeError):
    pass


class UnsafeArchiveError(ValueError):
    pass


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


def safe_extract_archive(
    archive_path: Path,
    destination: Path,
    archive_type: Literal["zip", "tar.gz"],
    *,
    max_members: int = _MAX_ARCHIVE_MEMBERS,
    max_uncompressed_bytes: int = _MAX_ARCHIVE_BYTES,
) -> None:
    """Extract regular files only, with traversal and decompression-bomb limits."""
    destination.mkdir(parents=True, exist_ok=False)
    try:
        if archive_type == "zip":
            with zipfile.ZipFile(archive_path) as archive:
                zip_members = archive.infolist()
                if len(zip_members) > max_members:
                    raise UnsafeArchiveError("archive contains too many members")
                if sum(item.file_size for item in zip_members) > max_uncompressed_bytes:
                    raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
                for zip_item in zip_members:
                    mode = zip_item.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise UnsafeArchiveError("archive links are forbidden")
                    target = _destination_path(
                        destination, _safe_member_path(zip_item.filename)
                    )
                    if zip_item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(zip_item) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, _CHUNK_SIZE)
                    if mode & stat.S_IXUSR:
                        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        else:
            with tarfile.open(archive_path, "r:gz") as archive:
                tar_members = archive.getmembers()
                if len(tar_members) > max_members:
                    raise UnsafeArchiveError("archive contains too many members")
                regular_size = sum(item.size for item in tar_members if item.isfile())
                if regular_size > max_uncompressed_bytes:
                    raise UnsafeArchiveError("archive exceeds its uncompressed size limit")
                for tar_item in tar_members:
                    if not (tar_item.isfile() or tar_item.isdir()):
                        raise UnsafeArchiveError("archive links and special files are forbidden")
                    target = _destination_path(
                        destination, _safe_member_path(tar_item.name)
                    )
                    if tar_item.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    tar_source = archive.extractfile(tar_item)
                    if tar_source is None:
                        raise UnsafeArchiveError("archive member cannot be read")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar_source, target.open("wb") as output:
                        shutil.copyfileobj(tar_source, output, _CHUNK_SIZE)
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
    digest = hashlib.sha256()
    received = 0
    factory = client_factory or (
        lambda: httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(300, connect=15),
            trust_env=True,
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
            stream = (
                client.stream("GET", url, headers=request_headers)
                if request_headers
                else client.stream("GET", url)
            )
            with stream as response:
                response.raise_for_status()
                status_code = int(getattr(response, "status_code", 200))
                if received and status_code != 206:
                    received = 0
                    digest = hashlib.sha256()
                    progress(0)
                advertised = response.headers.get("content-length")
                expected_response_size = expected_size - received
                if advertised and int(advertised) != expected_response_size:
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


class ManagedRuntime:
    """Own the optional llama.cpp runtime and model inside the per-user data directory."""

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

    def _paths(
        self, model: ModelCatalogEntry, runtime: RuntimeAsset
    ) -> tuple[Path, Path, Path]:
        catalog = load_model_catalog()
        runtime_dir = self.runtime_root / catalog.runtime.version / current_platform_key()
        executable = runtime_dir / runtime.executable
        model_path = self.model_root / model.filename
        return runtime_dir, executable, model_path

    @staticmethod
    def _runtime_is_verified(runtime_dir: Path, executable: Path, expected: str) -> bool:
        marker = runtime_dir / ".catalog-sha256"
        try:
            return executable.is_file() and marker.read_text(encoding="ascii").strip() == expected
        except OSError:
            return False

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
                    executable.parent, executable, runtime.sha256
                )
                model_installed = model_path.is_file()
            ready = self._process is not None and self._process.poll() is None and self._phase == "ready"
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

    async def install(
        self, model_key: str, *, replace: bool = False
    ) -> ManagedRuntimeSnapshot:
        with self._lock:
            if self._task is not None and not self._task.done():
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
            self._task = asyncio.create_task(asyncio.to_thread(self._install_sync, model_key))
        await asyncio.sleep(0)
        return self.snapshot()

    async def wait_for_install(self) -> ManagedRuntimeSnapshot:
        task = self._task
        if task is not None:
            await task
        return self.snapshot()

    def cancel_install(self) -> ManagedRuntimeSnapshot:
        self._cancelled.set()
        self._paused.clear()
        with self._lock:
            if self._phase in {"downloading_runtime", "downloading_model", "paused"}:
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
        if previous is not None and not previous.done():
            await previous
        with self._lock:
            self._cancelled.clear()
            self._paused.clear()
            self._error_code = None
            self._phase = "downloading_runtime"
            self._task = asyncio.create_task(asyncio.to_thread(self._install_sync, model_key))
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
        self.staging_root.mkdir(parents=True, exist_ok=True)
        required_free = model.size_bytes + (runtime.size_bytes * 2) + (256 * 1024 * 1024)
        if shutil.disk_usage(self.data_dir).free < required_free:
            with self._lock:
                self._phase = "error"
                self._error_code = "insufficient_disk_space"
            return
        with self._lock:
            self._total = runtime.size_bytes + model.size_bytes
            self._downloaded = 0
        try:
            if not self._runtime_is_verified(runtime_dir, executable, runtime.sha256):
                with self._lock:
                    self._phase = "downloading_runtime"
                archive = self.staging_root / f"llama-{catalog.runtime.version}.{runtime.archive_type}"
                self.download(
                    url=runtime.url,
                    destination=archive,
                    expected_sha256=runtime.sha256,
                    expected_size=runtime.size_bytes,
                    cancelled=self._cancelled,
                    paused=self._paused,
                    progress=self._progress(0),
                )
                with self._lock:
                    self._phase = "installing_runtime"
                extracted = self.staging_root / f"runtime-{uuid4().hex}"
                safe_extract_archive(archive, extracted, runtime.archive_type)
                candidates = list(extracted.rglob(runtime.executable))
                if len(candidates) != 1:
                    raise ValueError("runtime archive does not contain one expected executable")
                packaged_root = candidates[0].parent
                runtime_dir.parent.mkdir(parents=True, exist_ok=True)
                if runtime_dir.exists():
                    shutil.rmtree(runtime_dir)
                os.replace(packaged_root, runtime_dir)
                (runtime_dir / ".catalog-sha256").write_text(
                    runtime.sha256, encoding="ascii"
                )
                shutil.rmtree(extracted, ignore_errors=True)
                archive.unlink(missing_ok=True)
            else:
                with self._lock:
                    self._downloaded = runtime.size_bytes
            if model_path.is_file():
                try:
                    verify_file_sha256(model_path, model.sha256)
                except (OSError, ValueError):
                    model_path.unlink(missing_ok=True)
            if not model_path.is_file():
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
            self.start(model_key)
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
                self._error_code = type(exc).__name__.lower()
                self._replace_from = None

    def start(self, model_key: str | None = None) -> ManagedRuntimeSnapshot:
        catalog = load_model_catalog()
        selected = model_key or self._model_key or catalog.models[0].key
        model = catalog.model(selected)
        runtime = catalog.runtime.assets[current_platform_key()]
        _, executable, model_path = self._paths(model, runtime)
        if not executable.is_file() or not model_path.is_file():
            raise FileNotFoundError("managed runtime and model must be installed before startup")
        self.stop()
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
            "--api-key",
            api_key,
            "--alias",
            model.key,
            "--ctx-size",
            str(model.recommended_context_tokens),
            "--parallel",
            "1",
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with self._lock:
            self._phase = "starting"
            self._model_key = selected
            self._api_key = api_key
            self._endpoint = endpoint
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        if not self._wait_until_healthy(timeout_seconds=45):
            self.stop()
            with self._lock:
                self._phase = "error"
                self._error_code = "runtime_start_failed"
            raise RuntimeError("managed llama.cpp failed its health check")
        with self._lock:
            self._phase = "ready"
            self._error_code = None
        return self.snapshot()

    def _wait_until_healthy(self, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
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
            self._process = None
            self._api_key = None
            self._endpoint = None
            if self._phase in {"ready", "starting"}:
                self._phase = "idle"
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def erase_installation(self) -> dict[str, int]:
        """Remove only model/runtime paths owned by CareerOS Local."""

        self.cancel_install()
        self.stop()
        removed_files = 0
        removed_bytes = 0
        for target in (self.runtime_root, self.model_root, self.staging_root):
            resolved = target.resolve(strict=False)
            if resolved == self.data_dir or not resolved.is_relative_to(self.data_dir):
                raise RuntimeError("managed runtime path escapes the application data directory")
            if not target.exists() and not target.is_symlink():
                continue
            if target.is_symlink() or target.is_file():
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
            if parent.exists() and not any(parent.iterdir()):
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
