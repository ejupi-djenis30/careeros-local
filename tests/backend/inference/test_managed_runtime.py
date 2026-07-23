import hashlib
import io
import tarfile
import threading
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.inference.managed_runtime import (
    InstallCancelled,
    InstallPaused,
    ManagedRuntime,
    UnsafeArchiveError,
    download_verified,
    safe_extract_archive,
)


class _StreamResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.headers = {"content-length": str(len(content))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, _chunk_size: int):
        yield self.content


class _StreamClient:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def stream(self, method: str, url: str) -> _StreamResponse:
        assert method == "GET"
        assert url.startswith("https://")
        return _StreamResponse(self.content)


class _RangeResponse(_StreamResponse):
    def __init__(self, chunks: list[bytes], *, status_code: int) -> None:
        super().__init__(b"".join(chunks))
        self.chunks = chunks
        self.status_code = status_code

    def iter_bytes(self, _chunk_size: int):
        yield from self.chunks


class _RangeClient(_StreamClient):
    def __init__(self, chunks: list[bytes], *, status_code: int) -> None:
        super().__init__(b"".join(chunks))
        self.chunks = chunks
        self.status_code = status_code
        self.headers: dict[str, str] | None = None

    def stream(
        self, method: str, url: str, headers: dict[str, str] | None = None
    ) -> _RangeResponse:
        assert method == "GET"
        assert url.startswith("https://")
        self.headers = headers
        return _RangeResponse(self.chunks, status_code=self.status_code)


def test_zip_extraction_rejects_path_traversal() -> None:
    with TemporaryDirectory(prefix="careeros-zip-") as directory:
        root = Path(directory)
        archive = root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../escape.exe", b"bad")

        with pytest.raises(UnsafeArchiveError):
            safe_extract_archive(archive, root / "output", "zip")
        assert not (root / "escape.exe").exists()
        assert not (root / "output").exists()


def test_tar_extraction_rejects_links() -> None:
    with TemporaryDirectory(prefix="careeros-tar-") as directory:
        root = Path(directory)
        archive = root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            link = tarfile.TarInfo("runtime/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            output.addfile(link)

        with pytest.raises(UnsafeArchiveError):
            safe_extract_archive(archive, root / "output", "tar.gz")


def test_safe_archive_extracts_regular_runtime_file() -> None:
    with TemporaryDirectory(prefix="careeros-runtime-") as directory:
        root = Path(directory)
        archive = root / "runtime.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("bundle/llama-server.exe", b"runtime")

        destination = root / "output"
        safe_extract_archive(archive, destination, "zip")

        assert (destination / "bundle" / "llama-server.exe").read_bytes() == b"runtime"


def test_verified_download_is_atomic_and_cancellable() -> None:
    with TemporaryDirectory(prefix="careeros-download-") as directory:
        root = Path(directory)
        content = b"verified-model"
        destination = root / "model.gguf"
        cancelled = threading.Event()
        cancelled.set()

        with pytest.raises(InstallCancelled):
            download_verified(
                url="https://huggingface.co/model.gguf",
                destination=destination,
                expected_sha256="0" * 64,
                expected_size=len(content),
                cancelled=cancelled,
                progress=lambda _received: None,
                client_factory=lambda: _StreamClient(content),
            )

        assert not destination.exists()
        assert not list(root.glob("*.part"))


def test_verified_download_preserves_and_resumes_a_paused_partial() -> None:
    with TemporaryDirectory(prefix="careeros-resume-") as directory:
        root = Path(directory)
        first = b"verified-"
        second = b"model"
        content = first + second
        destination = root / "model.gguf"
        cancelled = threading.Event()
        paused = threading.Event()

        def pause_after_first(received: int) -> None:
            if received == len(first):
                paused.set()

        with pytest.raises(InstallPaused):
            download_verified(
                url="https://huggingface.co/model.gguf",
                destination=destination,
                expected_sha256=hashlib.sha256(content).hexdigest(),
                expected_size=len(content),
                cancelled=cancelled,
                paused=paused,
                progress=pause_after_first,
                client_factory=lambda: _RangeClient([first, second], status_code=200),
            )

        partial = root / ".model.gguf.part"
        assert partial.read_bytes() == first
        paused.clear()
        resumed = _RangeClient([second], status_code=206)
        download_verified(
            url="https://huggingface.co/model.gguf",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_size=len(content),
            cancelled=cancelled,
            paused=paused,
            progress=lambda _received: None,
            client_factory=lambda: resumed,
        )

        assert resumed.headers == {"Range": f"bytes={len(first)}-"}
        assert destination.read_bytes() == content
        assert not partial.exists()


def test_discard_partial_downloads_preserves_verified_assets() -> None:
    with TemporaryDirectory(prefix="careeros-cancel-") as directory:
        manager = ManagedRuntime(Path(directory))
        partials = [
            manager.staging_root / ".runtime.zip.part",
            manager.model_root / ".model.gguf.part",
        ]
        verified = manager.model_root / "model.gguf"
        for path in [*partials, verified]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"asset")

        manager.discard_partial_downloads()

        assert all(not path.exists() for path in partials)
        assert verified.read_bytes() == b"asset"


def test_archive_size_limit_is_enforced() -> None:
    with TemporaryDirectory(prefix="careeros-limit-") as directory:
        root = Path(directory)
        archive = root / "large.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            value = b"12345"
            item = tarfile.TarInfo("runtime/file")
            item.size = len(value)
            output.addfile(item, io.BytesIO(value))

        with pytest.raises(UnsafeArchiveError, match="size limit"):
            safe_extract_archive(
                archive,
                root / "output",
                "tar.gz",
                max_uncompressed_bytes=4,
            )
