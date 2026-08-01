import asyncio
import hashlib
import io
import os
import tarfile
import threading
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import backend.inference.managed_runtime as managed_runtime_module
from backend.inference.catalog import ModelCatalogEntry, RuntimeAsset
from backend.inference.managed_runtime import (
    InstallCancelled,
    InstallPaused,
    ManagedAssetIntegrityError,
    ManagedRuntime,
    RuntimeStartCancelled,
    UnsafeArchiveError,
    download_verified,
    quiesce_managed_runtime_installation,
    safe_extract_archive,
)


def _installed_runtime(directory: str) -> tuple[ManagedRuntime, str]:
    manager = ManagedRuntime(Path(directory))
    catalog = managed_runtime_module.load_model_catalog()
    model = catalog.models[0]
    runtime = catalog.runtime.assets[managed_runtime_module.current_platform_key()]
    _, executable, model_path = manager._paths(model, runtime)
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"verified test runtime")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"verified test model")
    return manager, model.key


class _StreamResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {"content-length": str(len(content))}

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


class _ScriptedClient:
    def __init__(self, responses: list[_StreamResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def stream(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> _StreamResponse:
        assert method == "GET"
        self.calls.append((url, headers))
        return self.responses.pop(0)


def _runtime_asset_from_archive(archive: Path, *, executable: str) -> RuntimeAsset:
    archive_bytes = archive.read_bytes()
    return RuntimeAsset(
        archive_type="zip",
        url="https://github.com/ggml-org/llama.cpp/releases/download/b1/runtime.zip",
        sha256=hashlib.sha256(archive_bytes).hexdigest(),
        size_bytes=len(archive_bytes),
        executable=executable,
    )


def _write_verified_runtime(
    runtime_dir: Path,
    runtime: RuntimeAsset,
    archive: Path,
) -> tuple[Path, Path]:
    executable = runtime_dir / runtime.executable
    companion = runtime_dir / "runtime.dll"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"verified executable")
    companion.write_bytes(b"verified companion")
    (runtime_dir / managed_runtime_module._RUNTIME_MARKER_NAME).write_text(
        runtime.sha256,
        encoding="ascii",
    )
    (runtime_dir / managed_runtime_module._runtime_source_name(runtime.archive_type)).write_bytes(
        archive.read_bytes()
    )
    return executable, companion


def _small_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ManagedRuntime, RuntimeAsset, ModelCatalogEntry, Path, Path, Path]:
    fixture_archive = tmp_path / "runtime-fixture.zip"
    with zipfile.ZipFile(fixture_archive, "w") as output:
        output.writestr("bundle/llama-server.exe", b"verified executable")
        output.writestr("bundle/runtime.dll", b"verified companion")
    runtime = _runtime_asset_from_archive(fixture_archive, executable="llama-server.exe")
    model_bytes = b"verified model"
    model = ModelCatalogEntry(
        key="test-model",
        display_name="Test model",
        author="Test",
        license="Apache-2.0",
        parameters="test",
        quantization="test",
        context_tokens=1024,
        recommended_context_tokens=1024,
        size_bytes=len(model_bytes),
        minimum_ram_bytes=1,
        recommended_ram_bytes=1,
        url="https://huggingface.co/test/model/resolve/main/model.gguf",
        sha256=hashlib.sha256(model_bytes).hexdigest(),
        filename="model.gguf",
        capabilities=("structured-output",),
    )
    catalog = SimpleNamespace(
        runtime=SimpleNamespace(
            version="b1",
            assets={"test-platform": runtime},
        ),
        models=(model,),
        model=lambda key: model if key == model.key else None,
    )
    monkeypatch.setattr(managed_runtime_module, "load_model_catalog", lambda: catalog)
    monkeypatch.setattr(managed_runtime_module, "current_platform_key", lambda: "test-platform")
    manager = ManagedRuntime(tmp_path / "data")
    runtime_dir, executable, model_path = manager._paths(model, runtime)
    _write_verified_runtime(runtime_dir, runtime, fixture_archive)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(model_bytes)
    return manager, runtime, model, runtime_dir, executable, model_path


def test_managed_runtime_passes_api_key_only_through_sanitized_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "managed-runtime-secret-that-must-not-enter-argv"
    inherited_secrets = {
        "CAREEROS_DESKTOP_SESSION_TOKEN": "desktop-session-secret",
        "CAREEROS_MCP_TOKEN": "agent-grant-secret",
        "CAREEROS_SECRET_FILE": "C:/private/installation-secret",
        "SECRET_KEY": "vault-signing-secret",
        "DATABASE_URL": "sqlite:///C:/private/careeros.db",
        "GITHUB_TOKEN": "ci-token",
        "AWS_SECRET_ACCESS_KEY": "cloud-secret",
        "HTTPS_PROXY": "https://credential@example.invalid",
        "LLAMA_ARG_API_KEY_FILE": "C:/private/llama-key",
        "LLAMA_ARG_TOOLS": "true",
        "GGML_OPENCL_PLATFORM": "untrusted-platform",
        "LD_PRELOAD": "/tmp/untrusted-library.so",
        "DYLD_INSERT_LIBRARIES": "/tmp/untrusted-library.dylib",
    }
    for name, value in inherited_secrets.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CAREEROS_RUNTIME_TEST_HINT", "preserve-me")
    captured: dict[str, object] = {}
    process = MagicMock()
    process.poll.return_value = None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        captured["close_fds"] = kwargs["close_fds"]
        return process

    with TemporaryDirectory(prefix="careeros-runtime-launch-") as directory:
        manager, model_key = _installed_runtime(directory)
        monkeypatch.setattr(managed_runtime_module.secrets, "token_urlsafe", lambda _size: secret)
        monkeypatch.setattr(managed_runtime_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(manager, "_wait_until_healthy", lambda **_kwargs: True)
        monkeypatch.setattr(manager, "_verify_launch_assets", lambda **_kwargs: None)

        snapshot = manager.start(model_key)

    command = captured["command"]
    environment = captured["environment"]
    assert isinstance(command, list)
    assert isinstance(environment, dict)
    assert snapshot.ready is True
    assert "--api-key" not in command
    assert secret not in command
    assert environment["LLAMA_API_KEY"] == secret
    assert environment["CAREEROS_RUNTIME_TEST_HINT"] == "preserve-me"
    assert inherited_secrets.keys().isdisjoint(environment)
    assert captured["cwd"] == Path(command[0]).parent
    assert captured["close_fds"] is True
    assert os.environ.get("LLAMA_API_KEY") != secret


def test_managed_runtime_launch_failure_never_exposes_api_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "managed-runtime-secret-that-must-stay-redacted"
    captured_command: list[str] = []

    def fail_popen(command, **_kwargs):
        captured_command.extend(command)
        raise OSError("managed runtime launch denied")

    with TemporaryDirectory(prefix="careeros-runtime-failure-") as directory:
        manager, model_key = _installed_runtime(directory)
        monkeypatch.setattr(managed_runtime_module.secrets, "token_urlsafe", lambda _size: secret)
        monkeypatch.setattr(managed_runtime_module.subprocess, "Popen", fail_popen)
        monkeypatch.setattr(manager, "_verify_launch_assets", lambda **_kwargs: None)

        with pytest.raises(OSError, match="managed runtime launch denied") as failure:
            manager.start(model_key)

    assert "--api-key" not in captured_command
    assert secret not in captured_command
    assert secret not in str(failure.value)
    assert secret not in caplog.text


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


@pytest.mark.parametrize(
    ("initial_url", "redirect_url"),
    [
        (
            "https://github.com/ggml-org/llama.cpp/releases/download/b1/runtime.zip",
            "https://release-assets.githubusercontent.com/github-production-release-asset/file?sig=1",
        ),
        (
            "https://huggingface.co/test/model/resolve/main/model.gguf",
            "https://us.aws.cdn.hf.co/repository/file?sig=1",
        ),
    ],
)
def test_verified_download_allows_only_known_provider_delivery_redirects(
    tmp_path: Path,
    initial_url: str,
    redirect_url: str,
) -> None:
    content = b"verified delivery"
    client = _ScriptedClient(
        [
            _StreamResponse(
                b"",
                status_code=302,
                headers={"location": redirect_url},
            ),
            _StreamResponse(content),
        ]
    )
    destination = tmp_path / "asset.bin"

    download_verified(
        url=initial_url,
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_size=len(content),
        cancelled=threading.Event(),
        progress=lambda _received: None,
        client_factory=lambda: client,
    )

    assert destination.read_bytes() == content
    assert [url for url, _headers in client.calls] == [initial_url, redirect_url]


@pytest.mark.parametrize(
    "redirect_url",
    [
        "https://example.invalid/asset.bin",
        "http://release-assets.githubusercontent.com/asset.bin",
        "https://github.com.attacker.invalid/asset.bin",
    ],
)
def test_verified_download_rejects_redirect_expansion_before_a_second_request(
    tmp_path: Path,
    redirect_url: str,
) -> None:
    initial_url = "https://github.com/ggml-org/llama.cpp/releases/download/b1/runtime.zip"
    client = _ScriptedClient(
        [
            _StreamResponse(
                b"",
                status_code=302,
                headers={"location": redirect_url},
            )
        ]
    )
    destination = tmp_path / "asset.bin"

    with pytest.raises(ValueError, match="approved HTTPS delivery network"):
        download_verified(
            url=initial_url,
            destination=destination,
            expected_sha256="0" * 64,
            expected_size=1,
            cancelled=threading.Event(),
            progress=lambda _received: None,
            client_factory=lambda: client,
        )

    assert client.calls == [(initial_url, None)]
    assert not destination.exists()
    assert not (tmp_path / ".asset.bin.part").exists()


def test_verified_download_rejects_more_than_three_redirects(tmp_path: Path) -> None:
    initial_url = "https://huggingface.co/test/model/resolve/main/model.gguf"
    redirects = [
        _StreamResponse(
            b"",
            status_code=302,
            headers={"location": f"https://huggingface.co/test/redirect-{index}"},
        )
        for index in range(4)
    ]
    client = _ScriptedClient(redirects)

    with pytest.raises(ValueError, match="redirect limit"):
        download_verified(
            url=initial_url,
            destination=tmp_path / "asset.bin",
            expected_sha256="0" * 64,
            expected_size=1,
            cancelled=threading.Event(),
            progress=lambda _received: None,
            client_factory=lambda: client,
        )

    assert len(client.calls) == 4


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/ggml-org/runtime.zip",
        "https://example.invalid/runtime.zip",
        "https://github.com:444/ggml-org/runtime.zip",
        "https://huggingface.co/test/model.gguf?unsigned=1",
    ],
)
def test_verified_download_rejects_invalid_initial_origin_without_network(
    tmp_path: Path,
    url: str,
) -> None:
    client_factory = MagicMock(side_effect=AssertionError("network must not be attempted"))

    with pytest.raises(ValueError, match="approved HTTPS catalog origin"):
        download_verified(
            url=url,
            destination=tmp_path / "asset.bin",
            expected_sha256="0" * 64,
            expected_size=1,
            cancelled=threading.Event(),
            progress=lambda _received: None,
            client_factory=client_factory,
        )

    client_factory.assert_not_called()


def test_verified_download_preserves_range_across_approved_redirect(
    tmp_path: Path,
) -> None:
    first = b"verified-"
    second = b"model"
    content = first + second
    destination = tmp_path / "model.gguf"
    (tmp_path / ".model.gguf.part").write_bytes(first)
    redirect_url = "https://us.aws.cdn.hf.co/repository/file?sig=1"
    client = _ScriptedClient(
        [
            _StreamResponse(
                b"",
                status_code=302,
                headers={"location": redirect_url},
            ),
            _RangeResponse([second], status_code=206),
        ]
    )

    download_verified(
        url="https://huggingface.co/test/model/resolve/main/model.gguf",
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_size=len(content),
        cancelled=threading.Event(),
        progress=lambda _received: None,
        client_factory=lambda: client,
    )

    expected_range = {"Range": f"bytes={len(first)}-"}
    assert client.calls == [
        ("https://huggingface.co/test/model/resolve/main/model.gguf", expected_range),
        (redirect_url, expected_range),
    ]
    assert destination.read_bytes() == content


def test_verified_download_default_transport_ignores_proxy_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"verified transport"
    captured: dict[str, object] = {}

    def client_factory(**kwargs):
        captured.update(kwargs)
        return _StreamClient(content)

    monkeypatch.setattr(managed_runtime_module.httpx, "Client", client_factory)

    download_verified(
        url="https://huggingface.co/test/model/resolve/main/model.gguf",
        destination=tmp_path / "asset.bin",
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_size=len(content),
        cancelled=threading.Event(),
        progress=lambda _received: None,
    )

    timeout = captured["timeout"]
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False
    assert timeout.connect == 15
    assert timeout.read == 30
    assert timeout.write == 30
    assert timeout.pool == 5


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


def test_archive_extraction_rejects_casefold_duplicate_paths(tmp_path: Path) -> None:
    archive = tmp_path / "duplicates.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("bundle/runtime.dll", b"first")
        output.writestr("bundle/RUNTIME.dll", b"second")

    with pytest.raises(UnsafeArchiveError, match="duplicate member paths"):
        safe_extract_archive(archive, tmp_path / "output", "zip")

    assert not (tmp_path / "output").exists()


def test_archive_copy_enforces_actual_streaming_limit() -> None:
    with pytest.raises(UnsafeArchiveError, match="uncompressed size limit"):
        managed_runtime_module._copy_bounded(
            io.BytesIO(b"12345"),
            io.BytesIO(),
            copied=0,
            expected_member_bytes=5,
            max_uncompressed_bytes=4,
        )


def test_archive_extraction_cancellation_removes_partial_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("bundle/first.dll", b"first")
        output.writestr("bundle/second.dll", b"second")
    cancelled = threading.Event()
    original_copy = managed_runtime_module._copy_bounded
    copied_members = 0

    def cancel_after_first(*args, **kwargs):
        nonlocal copied_members
        result = original_copy(*args, **kwargs)
        copied_members += 1
        if copied_members == 1:
            cancelled.set()
        return result

    monkeypatch.setattr(managed_runtime_module, "_copy_bounded", cancel_after_first)
    destination = tmp_path / "output"

    with pytest.raises(InstallCancelled):
        safe_extract_archive(
            archive,
            destination,
            "zip",
            cancelled=cancelled,
        )

    assert not destination.exists()


def test_runtime_verification_is_anchored_to_the_signed_source_archive(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("bundle/llama-server.exe", b"verified executable")
        output.writestr("bundle/runtime.dll", b"verified companion")
    runtime = _runtime_asset_from_archive(archive, executable="llama-server.exe")
    manager = ManagedRuntime(tmp_path / "data")
    runtime_dir = manager.runtime_root / "b1" / "test-platform"
    executable, companion = _write_verified_runtime(runtime_dir, runtime, archive)

    assert manager._runtime_is_verified(runtime_dir, executable, runtime, force=True)

    companion.write_bytes(b"modified companion")
    assert not manager._runtime_is_verified(runtime_dir, executable, runtime, force=True)

    companion.write_bytes(b"verified companion")
    source = runtime_dir / managed_runtime_module._runtime_source_name(runtime.archive_type)
    source.write_bytes(source.read_bytes() + b"tampered")
    assert not manager._runtime_is_verified(runtime_dir, executable, runtime, force=True)


def test_runtime_verification_rejects_legacy_marker_without_source_archive(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("bundle/llama-server.exe", b"verified executable")
        output.writestr("bundle/runtime.dll", b"verified companion")
    runtime = _runtime_asset_from_archive(archive, executable="llama-server.exe")
    manager = ManagedRuntime(tmp_path / "data")
    runtime_dir = manager.runtime_root / "b1" / "test-platform"
    executable, _companion = _write_verified_runtime(runtime_dir, runtime, archive)
    (runtime_dir / managed_runtime_module._runtime_source_name(runtime.archive_type)).unlink()

    assert not manager._runtime_is_verified(runtime_dir, executable, runtime, force=True)


@pytest.mark.parametrize("tampered_asset", ["runtime", "model"])
def test_runtime_start_refuses_tampered_assets_before_process_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tampered_asset: str,
) -> None:
    manager, _runtime, model, runtime_dir, _executable, model_path = _small_catalog(
        tmp_path,
        monkeypatch,
    )
    if tampered_asset == "runtime":
        (runtime_dir / "runtime.dll").write_bytes(b"modified companion")
    else:
        model_path.write_bytes(b"modified model!")
    popen = MagicMock(side_effect=AssertionError("process launch must not be attempted"))
    monkeypatch.setattr(managed_runtime_module.subprocess, "Popen", popen)

    with pytest.raises(ManagedAssetIntegrityError, match="integrity"):
        manager.start(model.key)

    popen.assert_not_called()


def test_runtime_start_honors_cancellation_before_process_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = threading.Event()
    cancelled.set()
    popen = MagicMock(side_effect=AssertionError("process launch must not be attempted"))

    with TemporaryDirectory(prefix="careeros-cancelled-launch-") as directory:
        manager, model_key = _installed_runtime(directory)
        monkeypatch.setattr(manager, "_verify_launch_assets", lambda **_kwargs: None)
        monkeypatch.setattr(managed_runtime_module.subprocess, "Popen", popen)

        with pytest.raises(RuntimeStartCancelled):
            manager.start(model_key, cancelled=cancelled)

    popen.assert_not_called()


def test_runtime_stop_retains_live_process_handle_when_termination_fails(
    tmp_path: Path,
) -> None:
    manager = ManagedRuntime(tmp_path)
    process = MagicMock()
    process.poll.return_value = None
    process.terminate.side_effect = OSError("termination denied")
    manager._process = process
    manager._api_key = "private"
    manager._endpoint = "http://127.0.0.1:1234"
    manager._phase = "ready"

    with pytest.raises(OSError, match="termination denied"):
        manager.stop()

    assert manager._process is process
    assert manager._api_key is None
    assert manager._endpoint is None
    assert manager._phase == "idle"


def test_runtime_restart_is_limited_to_three_attempts_per_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ManagedRuntime(tmp_path)
    result = object()
    start = MagicMock(return_value=result)
    monkeypatch.setattr(manager, "start", start)
    monkeypatch.setattr(managed_runtime_module.time, "monotonic", lambda: 10.0)

    assert [manager.restart() for _attempt in range(3)] == [result, result, result]
    with pytest.raises(RuntimeError, match="restart limit"):
        manager.restart()

    assert start.call_count == 3


def test_installed_assets_do_not_require_download_free_space(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _runtime, model, _runtime_dir, _executable, _model_path = _small_catalog(
        tmp_path,
        monkeypatch,
    )
    monkeypatch.setattr(manager, "start", lambda _model_key, **_kwargs: manager.snapshot())
    monkeypatch.setattr(
        managed_runtime_module.shutil,
        "disk_usage",
        MagicMock(side_effect=AssertionError("installed assets need no download preflight")),
    )

    manager._install_sync(model.key)

    assert manager.snapshot().error_code is None


def test_runtime_install_retains_verified_source_and_publishes_valid_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_archive = tmp_path / "runtime-fixture.zip"
    with zipfile.ZipFile(fixture_archive, "w") as output:
        output.writestr("bundle/llama-server.exe", b"verified executable")
        output.writestr("bundle/runtime.dll", b"verified companion")
    runtime = _runtime_asset_from_archive(fixture_archive, executable="llama-server.exe")
    model_bytes = b"verified model"
    model = ModelCatalogEntry(
        key="test-model",
        display_name="Test model",
        author="Test",
        license="Apache-2.0",
        parameters="test",
        quantization="test",
        context_tokens=1024,
        recommended_context_tokens=1024,
        size_bytes=len(model_bytes),
        minimum_ram_bytes=1,
        recommended_ram_bytes=1,
        url="https://huggingface.co/test/model/resolve/main/model.gguf",
        sha256=hashlib.sha256(model_bytes).hexdigest(),
        filename="model.gguf",
        capabilities=("structured-output",),
    )
    catalog = SimpleNamespace(
        runtime=SimpleNamespace(version="b1", assets={"test-platform": runtime}),
        models=(model,),
        model=lambda key: model if key == model.key else None,
    )
    monkeypatch.setattr(managed_runtime_module, "load_model_catalog", lambda: catalog)
    monkeypatch.setattr(managed_runtime_module, "current_platform_key", lambda: "test-platform")

    def download(**kwargs) -> None:
        destination = kwargs["destination"]
        content = fixture_archive.read_bytes() if destination.suffix == ".zip" else model_bytes
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        kwargs["progress"](len(content))

    manager = ManagedRuntime(tmp_path / "data", download=download)
    monkeypatch.setattr(manager, "start", lambda _model_key: manager.snapshot())

    manager._install_sync(model.key)

    runtime_dir, executable, model_path = manager._paths(model, runtime)
    source = runtime_dir / managed_runtime_module._runtime_source_name(runtime.archive_type)
    assert source.read_bytes() == fixture_archive.read_bytes()
    assert model_path.read_bytes() == model_bytes
    assert manager._runtime_is_verified(runtime_dir, executable, runtime, force=True)


def test_runtime_install_preflights_extraction_and_reuses_verified_staging_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_archive = tmp_path / "runtime-fixture.zip"
    with zipfile.ZipFile(fixture_archive, "w") as output:
        output.writestr("bundle/llama-server.exe", b"verified executable")
        output.writestr("bundle/runtime.dll", b"verified companion")
    runtime = _runtime_asset_from_archive(fixture_archive, executable="llama-server.exe")
    model_bytes = b"verified model"
    model = ModelCatalogEntry(
        key="test-model",
        display_name="Test model",
        author="Test",
        license="Apache-2.0",
        parameters="test",
        quantization="test",
        context_tokens=1024,
        recommended_context_tokens=1024,
        size_bytes=len(model_bytes),
        minimum_ram_bytes=1,
        recommended_ram_bytes=1,
        url="https://huggingface.co/test/model/resolve/main/model.gguf",
        sha256=hashlib.sha256(model_bytes).hexdigest(),
        filename="model.gguf",
        capabilities=("structured-output",),
    )
    catalog = SimpleNamespace(
        runtime=SimpleNamespace(version="b1", assets={"test-platform": runtime}),
        models=(model,),
        model=lambda key: model if key == model.key else None,
    )
    monkeypatch.setattr(managed_runtime_module, "load_model_catalog", lambda: catalog)
    monkeypatch.setattr(managed_runtime_module, "current_platform_key", lambda: "test-platform")
    downloads: list[Path] = []

    def download(**kwargs) -> None:
        destination = kwargs["destination"]
        downloads.append(destination)
        content = fixture_archive.read_bytes() if destination.suffix == ".zip" else model_bytes
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        kwargs["progress"](len(content))

    manager = ManagedRuntime(tmp_path / "data", download=download)
    monkeypatch.setattr(manager, "start", lambda _model_key, **_kwargs: manager.snapshot())
    disk_usage = MagicMock(
        side_effect=[
            SimpleNamespace(free=1_000_000_000),
            SimpleNamespace(free=0),
            SimpleNamespace(free=1_000_000_000),
            SimpleNamespace(free=1_000_000_000),
        ]
    )
    monkeypatch.setattr(managed_runtime_module.shutil, "disk_usage", disk_usage)

    manager._install_sync(model.key)
    first = manager.snapshot()
    assert first.phase == "error"
    assert first.error_code == "insufficient_disk_space"
    assert [path.suffix for path in downloads] == [".zip"]

    manager._install_sync(model.key)

    runtime_dir, executable, model_path = manager._paths(model, runtime)
    assert [path.suffix for path in downloads] == [".zip", ".gguf"]
    assert model_path.read_bytes() == model_bytes
    assert manager._runtime_is_verified(runtime_dir, executable, runtime, force=True)
    assert disk_usage.call_count == 4


@pytest.mark.asyncio
async def test_erasure_joins_real_installer_worker_even_if_async_task_was_cancelled(
    tmp_path,
    monkeypatch,
) -> None:
    manager = ManagedRuntime(tmp_path)
    model_key = managed_runtime_module.load_model_catalog().models[0].key
    worker_started = threading.Event()
    allow_worker_exit = threading.Event()
    late_file = manager.model_root / "late-worker-write.bin"

    def blocked_install(_model_key: str) -> None:
        worker_started.set()
        allow_worker_exit.wait(timeout=5)
        late_file.parent.mkdir(parents=True, exist_ok=True)
        late_file.write_bytes(b"worker-finished")

    monkeypatch.setattr(manager, "_install_sync", blocked_install)
    await manager.install(model_key)
    assert await asyncio.to_thread(worker_started.wait, 1)
    assert manager._task is not None
    manager._task.cancel()
    manager.cancel_install()

    with pytest.raises(RuntimeError, match="worker must stop"):
        manager.erase_installation()

    joined = asyncio.create_task(manager.wait_for_install())
    await asyncio.sleep(0)
    assert not joined.done()
    allow_worker_exit.set()
    await joined
    assert late_file.read_bytes() == b"worker-finished"

    manager.erase_installation()
    assert not late_file.exists()
    assert manager._worker_done.is_set()


@pytest.mark.asyncio
async def test_destructive_quiesce_tolerates_completed_failed_install_task(
    tmp_path,
    monkeypatch,
) -> None:
    manager = ManagedRuntime(tmp_path)
    private_file = manager.model_root / "failed-install-private.bin"
    private_file.parent.mkdir(parents=True)
    private_file.write_bytes(b"partial")

    async def failed_task() -> None:
        raise RuntimeError("catalog setup failed")

    manager._task = asyncio.create_task(failed_task())
    await asyncio.sleep(0)
    assert manager._task.done()
    assert manager._worker_done.is_set()
    monkeypatch.setattr(managed_runtime_module, "get_managed_runtime", lambda: manager)

    await quiesce_managed_runtime_installation()
    manager.erase_installation()

    assert not private_file.exists()
