import asyncio
import json
import math
import os
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.ai.contracts import CoachResult, JobMatchResult
from backend.ai.task_specs import TASK_SPECS
from backend.core.config import settings
from backend.inference.catalog import public_catalog
from backend.inference.endpoint import LocalInferenceEndpointError, validate_local_inference_url
from backend.inference.managed_runtime import (
    ManagedRuntimeSnapshot,
    get_managed_runtime,
)
from backend.inference.ports import StructuredInferenceRequest
from backend.providers.llm.factory import get_provider_for_step


class ManagedModelStatus(BaseModel):
    phase: str
    model_key: str | None = None
    bytes_downloaded: int = 0
    bytes_total: int = 0
    runtime_installed: bool = False
    model_installed: bool = False
    ready: bool = False
    endpoint: str | None = None
    error_code: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: ManagedRuntimeSnapshot) -> "ManagedModelStatus":
        return cls.model_validate(snapshot.as_dict())


class LocalModelStatus(BaseModel):
    required: bool = True
    analysis_required: bool = True
    available: bool
    ready: bool
    endpoint: str
    configured_model: str
    installed_models: list[str]
    error_code: str | None = None
    runtime: str = "ollama"
    privacy_boundary: Literal["local-only"] = "local-only"
    managed: ManagedModelStatus | None = None


class LocalModelReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "endpoint_allowed",
        "runtime_reachable",
        "model_available",
        "structured_output",
    ]
    status: Literal["passed", "failed"]


class LocalModelReadiness(BaseModel):
    required: bool = True
    ready: bool
    runtime: str
    configured_model: str
    model_id: str | None = None
    privacy_boundary: Literal["local-only"] = "local-only"
    error_code: str | None = None
    checks: list[LocalModelReadinessCheck]


_READINESS_JOB_MATCH = {
    "results": [
        {
            "skill_match_score": 50,
            "experience_match_score": 50,
            "intent_match_score": 50,
            "language_match_score": 50,
            "location_match_score": 50,
            "transferability_score": 50,
            "qualification_gap_score": 50,
        }
    ]
}
_READINESS_COACH = {
    "answer": "Synthetic evidence only.",
    "claims": [
        {
            "text": "Synthetic evidence only.",
            "fact_ids": ["11111111-1111-4111-8111-111111111111"],
            "job_ids": [],
        }
    ],
    "fact_citations": ["11111111-1111-4111-8111-111111111111"],
    "job_citations": [],
    "confidence": 1.0,
    "missing_evidence": [],
}


_READINESS_READY_TTL_SECONDS = 120.0
_READINESS_FAILURE_TTL_SECONDS = 5.0
_readiness_lock = asyncio.Lock()
_readiness_cache: (
    tuple[float, tuple[str, str, str, bool, bool, str | None], LocalModelReadiness] | None
) = None


class ModelInstallRequest(BaseModel):
    model_key: str = Field(min_length=2, max_length=80)
    license_accepted: bool


class ModelRemovalResult(BaseModel):
    model_files: int
    model_bytes: int
    status: ManagedModelStatus


def get_local_model_catalog() -> dict[str, object]:
    return public_catalog()


def _desktop_mode() -> bool:
    return os.getenv("CAREEROS_DESKTOP_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def get_local_model_status() -> LocalModelStatus:
    """Return a non-sensitive local runtime status; unavailability is not exceptional."""
    manager = get_managed_runtime()
    managed_snapshot = manager.snapshot()
    managed = ManagedModelStatus.from_snapshot(managed_snapshot)
    if managed_snapshot.ready:
        return LocalModelStatus(
            available=True,
            ready=True,
            endpoint=managed_snapshot.endpoint or "",
            configured_model=managed_snapshot.model_key or "",
            installed_models=[managed_snapshot.model_key] if managed_snapshot.model_key else [],
            runtime="llama.cpp",
            managed=managed,
        )
    # Desktop installations may use the signed, loopback-only Ollama adapter when Windows
    # application-control policy rejects the bundled llama.cpp DLL. This is a local runtime
    # fallback, never a cloud or remote inference fallback.
    if _desktop_mode():
        try:
            provider = get_provider_for_step("default")
            installed = await provider.list_models_async()
            configured = settings.LOCAL_MODEL
            if configured in installed or f"{configured}:latest" in installed:
                return LocalModelStatus(
                    available=True,
                    ready=True,
                    endpoint=settings.LOCAL_INFERENCE_URL,
                    configured_model=configured,
                    installed_models=installed,
                    runtime="ollama",
                    managed=managed,
                )
        except Exception:
            pass
    if _desktop_mode() or managed_snapshot.phase != "idle" or managed_snapshot.model_installed:
        return LocalModelStatus(
            available=managed_snapshot.runtime_installed,
            ready=False,
            endpoint="managed-loopback",
            configured_model=managed_snapshot.model_key or "",
            installed_models=[managed_snapshot.model_key]
            if managed_snapshot.model_installed and managed_snapshot.model_key
            else [],
            error_code=managed_snapshot.error_code
            or (
                "managed_model_setup_required"
                if not managed_snapshot.model_installed
                else "managed_runtime_not_ready"
            ),
            runtime="llama.cpp",
            managed=managed,
        )
    try:
        provider = get_provider_for_step("default")
        installed = await provider.list_models_async()
    except Exception:
        return LocalModelStatus(
            available=False,
            ready=False,
            endpoint=settings.LOCAL_INFERENCE_URL,
            configured_model=settings.LOCAL_MODEL,
            installed_models=[],
            error_code="local_runtime_unreachable",
            managed=managed,
        )

    configured = settings.LOCAL_MODEL
    ready = configured in installed or f"{configured}:latest" in installed
    return LocalModelStatus(
        available=True,
        ready=ready,
        endpoint=settings.LOCAL_INFERENCE_URL,
        configured_model=configured,
        installed_models=installed,
        error_code=None if ready else "configured_model_missing",
        managed=managed,
    )


def _readiness_key(status: LocalModelStatus) -> tuple[str, str, str, bool, bool, str | None]:
    return (
        status.runtime,
        status.endpoint,
        status.configured_model,
        status.available,
        status.ready,
        status.error_code,
    )


def _endpoint_allowed(status: LocalModelStatus, provider: object | None = None) -> bool:
    endpoint = getattr(provider, "endpoint", None) or status.endpoint
    if not isinstance(endpoint, str):
        return False
    if endpoint == "managed-loopback" and status.runtime == "llama.cpp":
        return True
    try:
        validate_local_inference_url(
            str(endpoint),
            allowed_hosts=settings.local_inference_allowed_hosts,
        )
    except (LocalInferenceEndpointError, ValueError):
        return False
    return True


def _provider_matches_status(status: LocalModelStatus, provider: object) -> bool:
    runtime_name = getattr(provider, "runtime_name", None)
    model = getattr(provider, "model", None)
    endpoint = getattr(provider, "endpoint", None)
    if not isinstance(runtime_name, str) or not runtime_name:
        return False
    if not isinstance(model, str) or not model:
        return False
    if not isinstance(endpoint, str) or not endpoint:
        return False
    if runtime_name != status.runtime or model != status.configured_model:
        return False
    if status.endpoint == "managed-loopback":
        return bool(runtime_name == "llama.cpp")
    try:
        expected_endpoint = validate_local_inference_url(
            status.endpoint,
            allowed_hosts=settings.local_inference_allowed_hosts,
        )
        actual_endpoint = validate_local_inference_url(
            endpoint,
            allowed_hosts=settings.local_inference_allowed_hosts,
        )
    except (LocalInferenceEndpointError, ValueError):
        return False
    return expected_endpoint == actual_endpoint


def clear_local_model_readiness_cache() -> None:
    """Drop the short-lived readiness attestation after runtime configuration changes."""
    global _readiness_cache
    _readiness_cache = None


def _remaining_readiness_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


def _readiness_timeout_result(status: LocalModelStatus | None = None) -> LocalModelReadiness:
    endpoint_ok = status is None or _endpoint_allowed(status)
    runtime_reachable = status is not None and status.available
    model_available = status is not None and status.ready
    return LocalModelReadiness(
        ready=False,
        runtime=status.runtime if status is not None else "unknown",
        configured_model=(status.configured_model if status is not None else settings.LOCAL_MODEL),
        error_code="structured_probe_timeout",
        checks=[
            LocalModelReadinessCheck(
                code="endpoint_allowed",
                status="passed" if endpoint_ok else "failed",
            ),
            LocalModelReadinessCheck(
                code="runtime_reachable",
                status="passed" if runtime_reachable else "failed",
            ),
            LocalModelReadinessCheck(
                code="model_available",
                status="passed" if model_available else "failed",
            ),
            LocalModelReadinessCheck(code="structured_output", status="failed"),
        ],
    )


async def check_local_model_readiness(
    *,
    timeout_seconds: float = 45.0,
    force: bool = False,
) -> LocalModelReadiness:
    """Verify that required local analysis can produce validated structured output.

    The probe contains no vault data and exposes only stable diagnostics. Adapter construction
    retains the endpoint allowlist, and both supported runtimes enforce local-only transport.
    """
    global _readiness_cache
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be finite and greater than zero")
    request_started = time.monotonic()
    deadline = request_started + timeout
    try:
        status_timeout = _remaining_readiness_timeout(deadline)
        status = await asyncio.wait_for(
            get_local_model_status(),
            timeout=status_timeout,
        )
    except TimeoutError:
        return _readiness_timeout_result()
    key = _readiness_key(status)
    now = time.monotonic()
    if _readiness_cache is not None:
        cached_at, cached_key, cached = _readiness_cache
        ttl = _READINESS_READY_TTL_SECONDS if cached.ready else _READINESS_FAILURE_TTL_SECONDS
        if cached_key == key and now - cached_at <= ttl and not force:
            return cached.model_copy(deep=True)

    lock_acquired = False
    try:
        lock_timeout = _remaining_readiness_timeout(deadline)
        await asyncio.wait_for(
            _readiness_lock.acquire(),
            timeout=lock_timeout,
        )
        lock_acquired = True
        now = time.monotonic()
        if _readiness_cache is not None:
            cached_at, cached_key, cached = _readiness_cache
            ttl = _READINESS_READY_TTL_SECONDS if cached.ready else _READINESS_FAILURE_TTL_SECONDS
            fresh_for_forced_caller = force and cached_at >= request_started
            if (
                cached_key == key
                and (now - cached_at <= ttl)
                and (not force or fresh_for_forced_caller)
            ):
                return cached.model_copy(deep=True)
        result = await _probe_local_model_readiness(status, deadline=deadline)
        _readiness_cache = (time.monotonic(), key, result)
        return result.model_copy(deep=True)
    except TimeoutError:
        return _readiness_timeout_result(status)
    finally:
        if lock_acquired:
            _readiness_lock.release()


async def _probe_local_model_readiness(
    status: LocalModelStatus,
    *,
    deadline: float,
) -> LocalModelReadiness:
    endpoint_ok = _endpoint_allowed(status)
    checks = [
        LocalModelReadinessCheck(
            code="endpoint_allowed",
            status="passed" if endpoint_ok else "failed",
        )
    ]
    if not endpoint_ok:
        checks.extend(
            [
                LocalModelReadinessCheck(code="runtime_reachable", status="failed"),
                LocalModelReadinessCheck(code="model_available", status="failed"),
                LocalModelReadinessCheck(code="structured_output", status="failed"),
            ]
        )
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            error_code="inference_endpoint_not_allowed",
            checks=checks,
        )
    if not status.available:
        checks.extend(
            [
                LocalModelReadinessCheck(code="runtime_reachable", status="failed"),
                LocalModelReadinessCheck(code="model_available", status="failed"),
                LocalModelReadinessCheck(code="structured_output", status="failed"),
            ]
        )
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            error_code=status.error_code or "local_runtime_unreachable",
            checks=checks,
        )

    checks.append(LocalModelReadinessCheck(code="runtime_reachable", status="passed"))
    if not status.ready:
        checks.extend(
            [
                LocalModelReadinessCheck(code="model_available", status="failed"),
                LocalModelReadinessCheck(code="structured_output", status="failed"),
            ]
        )
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            error_code=status.error_code or "configured_model_missing",
            checks=checks,
        )

    checks.append(LocalModelReadinessCheck(code="model_available", status="passed"))
    try:
        provider = get_provider_for_step("default")
    except Exception:
        checks.append(LocalModelReadinessCheck(code="structured_output", status="failed"))
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            error_code="structured_probe_failed",
            checks=checks,
        )
    if not _endpoint_allowed(status, provider):
        checks[0] = LocalModelReadinessCheck(code="endpoint_allowed", status="failed")
        checks.append(LocalModelReadinessCheck(code="structured_output", status="failed"))
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            model_id=getattr(provider, "model_id", None),
            error_code="inference_endpoint_not_allowed",
            checks=checks,
        )
    if not _provider_matches_status(status, provider):
        checks.append(LocalModelReadinessCheck(code="structured_output", status="failed"))
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            error_code="provider_identity_changed",
            checks=checks,
        )
    try:
        match_timeout = _remaining_readiness_timeout(deadline)
        generated = await asyncio.wait_for(
            provider.generate_structured_async(
                StructuredInferenceRequest(
                    system_prompt=(
                        "This is a synthetic, content-free local readiness check. Return only "
                        "the supplied JSON object and match the full job-analysis schema."
                    ),
                    user_prompt="Return this exact synthetic JSON:\n"
                    + json.dumps(_READINESS_JOB_MATCH, separators=(",", ":")),
                    json_schema=JobMatchResult.model_json_schema(),
                    max_tokens=512,
                    temperature=0.0,
                    top_p=0.9,
                    seed=0,
                    task_id="readiness",
                )
            ),
            timeout=match_timeout,
        )
        JobMatchResult.model_validate(generated.payload)
        if generated.runtime != status.runtime or generated.model_id != provider.model_id:
            raise RuntimeError("local inference provider changed during readiness probe")
        coach_timeout = _remaining_readiness_timeout(deadline)
        coach_generated = await asyncio.wait_for(
            provider.generate_structured_async(
                StructuredInferenceRequest(
                    system_prompt=(
                        "This is a synthetic, content-free local readiness check. Return only "
                        "the supplied JSON object and match the full coach schema."
                    ),
                    user_prompt="Return this exact synthetic JSON:\n"
                    + json.dumps(_READINESS_COACH, separators=(",", ":")),
                    json_schema=CoachResult.model_json_schema(),
                    max_tokens=TASK_SPECS["coach"].max_output_tokens,
                    temperature=0.0,
                    top_p=0.9,
                    seed=0,
                    task_id="readiness",
                )
            ),
            timeout=coach_timeout,
        )
        CoachResult.model_validate(coach_generated.payload)
        if (
            coach_generated.runtime != status.runtime
            or coach_generated.model_id != provider.model_id
        ):
            raise RuntimeError("local inference provider changed during readiness probe")
    except TimeoutError:
        checks.append(LocalModelReadinessCheck(code="structured_output", status="failed"))
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            model_id=getattr(provider, "model_id", None),
            error_code="structured_probe_timeout",
            checks=checks,
        )
    except Exception:
        checks.append(LocalModelReadinessCheck(code="structured_output", status="failed"))
        return LocalModelReadiness(
            ready=False,
            runtime=status.runtime,
            configured_model=status.configured_model,
            model_id=getattr(provider, "model_id", None),
            error_code="structured_probe_failed",
            checks=checks,
        )

    checks.append(LocalModelReadinessCheck(code="structured_output", status="passed"))
    return LocalModelReadiness(
        ready=True,
        runtime=generated.runtime,
        configured_model=str(getattr(provider, "model", status.configured_model)),
        model_id=generated.model_id,
        checks=checks,
    )


async def install_managed_model(request: ModelInstallRequest) -> ManagedModelStatus:
    if not request.license_accepted:
        raise ValueError("model license consent is required")
    clear_local_model_readiness_cache()
    snapshot = await get_managed_runtime().install(request.model_key)
    return ManagedModelStatus.from_snapshot(snapshot)


async def replace_managed_model(request: ModelInstallRequest) -> ManagedModelStatus:
    if not request.license_accepted:
        raise ValueError("model license consent is required")
    clear_local_model_readiness_cache()
    snapshot = await get_managed_runtime().install(request.model_key, replace=True)
    return ManagedModelStatus.from_snapshot(snapshot)


async def cancel_managed_model_install() -> ManagedModelStatus:
    clear_local_model_readiness_cache()
    manager = get_managed_runtime()
    manager.cancel_install()
    await manager.wait_for_install()
    manager.discard_partial_downloads()
    return ManagedModelStatus.from_snapshot(manager.snapshot())


def pause_managed_model_install() -> ManagedModelStatus:
    clear_local_model_readiness_cache()
    return ManagedModelStatus.from_snapshot(get_managed_runtime().pause_install())


async def resume_managed_model_install() -> ManagedModelStatus:
    clear_local_model_readiness_cache()
    snapshot = await get_managed_runtime().resume_install()
    return ManagedModelStatus.from_snapshot(snapshot)


async def remove_managed_model() -> ModelRemovalResult:
    clear_local_model_readiness_cache()
    manager = get_managed_runtime()
    manager.cancel_install()
    await manager.wait_for_install()
    removed = await asyncio.to_thread(manager.erase_installation)
    return ModelRemovalResult(
        **removed,
        status=ManagedModelStatus.from_snapshot(manager.snapshot()),
    )


async def restart_managed_model() -> ManagedModelStatus:
    clear_local_model_readiness_cache()
    snapshot = await asyncio.to_thread(get_managed_runtime().restart)
    return ManagedModelStatus.from_snapshot(snapshot)
