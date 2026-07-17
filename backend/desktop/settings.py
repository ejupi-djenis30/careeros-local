from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUE_VALUES


@dataclass(frozen=True, slots=True)
class DesktopRuntimeSettings:
    enabled: bool
    host: str
    port: int
    session_token: str
    data_dir: Path | None

    @classmethod
    def from_environment(cls) -> "DesktopRuntimeSettings":
        enabled = _is_enabled(os.getenv("CAREEROS_DESKTOP_MODE"))
        if not enabled:
            return cls(
                enabled=False,
                host="127.0.0.1",
                port=0,
                session_token="",
                data_dir=None,
            )

        host = os.getenv("CAREEROS_DESKTOP_HOST", "127.0.0.1").strip()
        if host != "127.0.0.1":
            raise ValueError("Desktop service host must be the IPv4 loopback address")

        token = os.getenv("CAREEROS_DESKTOP_SESSION_TOKEN", "").strip()
        if len(token) < 32 or len(token) > 256:
            raise ValueError("Desktop session token must contain 32 to 256 characters")

        try:
            port = int(os.getenv("CAREEROS_DESKTOP_PORT", "0"))
        except ValueError as exc:
            raise ValueError("Desktop port must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("Desktop port must be between 1 and 65535")

        raw_data_dir = os.getenv("CAREEROS_DESKTOP_DATA_DIR", "").strip()
        if not raw_data_dir:
            raise ValueError("Desktop data directory is required")
        candidate = Path(raw_data_dir).expanduser()
        if not candidate.is_absolute():
            raise ValueError("Desktop data directory must be absolute")
        data_dir = candidate.resolve(strict=False)

        return cls(
            enabled=True,
            host=host,
            port=port,
            session_token=token,
            data_dir=data_dir,
        )

    @property
    def database_path(self) -> Path:
        if self.data_dir is None:
            raise RuntimeError("Browser mode has no desktop database path")
        return self.data_dir / "vault" / "careeros.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    def ensure_directories(self) -> None:
        if self.data_dir is None:
            return
        for relative in ("vault", "assets", "models", "backups", "logs", "staging"):
            path = self.data_dir / relative
            path.mkdir(parents=True, exist_ok=True)
            try:
                path.chmod(0o700)
            except OSError:
                # Windows ACLs are inherited from the per-user application-data directory.
                pass
