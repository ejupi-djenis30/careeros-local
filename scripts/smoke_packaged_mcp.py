"""Exercise the installed console MCP over real stdio across desktop restarts.

All data is synthetic and stored in an OS temporary directory. Credentials stay
in memory/environment and are never included in the token-free report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class PackagedDesktop:
    def __init__(self, binary: Path, data_dir: Path):
        self.binary = binary
        self.data_dir = data_dir
        self.descriptor = data_dir / "mcp" / "connection.json"
        self.process: subprocess.Popen | None = None
        self.session_token = secrets.token_urlsafe(48)
        self.url = ""

    def request(self, method: str, path: str, *, payload=None, token=None):
        headers = {"X-CareerOS-Session": self.session_token}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=3) as client:
            response = client.request(method, self.url + path, json=payload, headers=headers)
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Packaged API {method} {path} returned HTTP {response.status_code}")
        return response.json()

    def start(self, port: int) -> str:
        self.url = f"http://127.0.0.1:{port}/api/v1"
        environment = os.environ.copy()
        environment.pop("TESTING", None)
        environment["CAREEROS_DESKTOP_SESSION_TOKEN"] = self.session_token
        self.process = subprocess.Popen(
            [
                str(self.binary),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--data-dir",
                str(self.data_dir),
                "--parent-pid",
                str(os.getpid()),
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Packaged desktop exited before readiness: {self.process.returncode}"
                )
            try:
                if self.request("GET", "/health/ready").get("status") == "ready":
                    descriptor: object = json.loads(self.descriptor.read_bytes())
                    if not isinstance(descriptor, dict):
                        raise RuntimeError("Packaged desktop published an invalid descriptor")
                    instance_id = descriptor.get("instance_id")
                    if descriptor.get("api_base_url") == self.url and isinstance(
                        instance_id, str
                    ):
                        return instance_id
            except (OSError, ValueError, httpx.HTTPError, RuntimeError):
                pass
            time.sleep(0.1)
        raise RuntimeError("Packaged desktop did not publish a ready connection")

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        self.process = None
        try:
            if process.poll() is None:
                try:
                    self.request("POST", "/desktop/shutdown")
                except (httpx.HTTPError, RuntimeError):
                    process.terminate()
            if process.wait(timeout=30) != 0:
                raise RuntimeError("Packaged desktop did not stop cleanly")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        if self.descriptor.exists():
            raise RuntimeError("Packaged desktop left its connection descriptor after shutdown")


async def exercise(binary: Path, console: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="careeros-packaged-mcp-") as temporary:
        desktop = PackagedDesktop(binary, Path(temporary).resolve())
        port = _free_port()
        try:
            first = await asyncio.to_thread(desktop.start, port)
            password = "PackageSmoke123"
            account = await asyncio.to_thread(
                desktop.request,
                "POST",
                "/auth/register",
                payload={"username": "mcp_package_smoke", "password": password},
            )
            grant = await asyncio.to_thread(
                desktop.request,
                "POST",
                "/automation/grants",
                token=account["access_token"],
                payload={
                    "label": "Packaged MCP smoke",
                    "scopes": ["context:read", "proposals:write"],
                    "password": password,
                    "lifetime_days": 1,
                    "acknowledge_external_disclosure": True,
                },
            )
            environment = os.environ.copy()
            environment["CAREEROS_MCP_TOKEN"] = grant["token"]
            # Neither the bootstrap session nor an account token belongs to MCP.
            environment.pop("CAREEROS_DESKTOP_SESSION_TOKEN", None)
            parameters = StdioServerParameters(
                command=str(console),
                args=[
                    "--connection-file",
                    str(desktop.descriptor),
                    "--acknowledge-agent-disclosure",
                ],
                env=environment,
            )
            with open(os.devnull, "w") as errors:
                async with stdio_client(parameters, errlog=errors) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        names = {tool.name for tool in listed.tools}
                        expected = {
                            "get_agent_status",
                            "list_work_requests",
                            "get_work_context",
                            "submit_work_result",
                            "get_work_result",
                            "list_resume_templates",
                        }
                        if names != expected:
                            raise RuntimeError("Packaged MCP exposed an unexpected tool surface")
                        for name in (
                            "get_agent_status",
                            "list_work_requests",
                            "list_resume_templates",
                        ):
                            result = await session.call_tool(name, {})
                            if result.isError:
                                raise RuntimeError(f"Packaged MCP {name} failed")
                        await asyncio.to_thread(desktop.stop)
                        unavailable = await session.call_tool("get_agent_status", {})
                        if not unavailable.isError:
                            raise RuntimeError("MCP reused a stopped desktop connection")
                        second = await asyncio.to_thread(desktop.start, port)
                        if (
                            first == second
                            or (await session.call_tool("get_agent_status", {})).isError
                        ):
                            raise RuntimeError("MCP failed to refresh after a same-port restart")
                        await asyncio.to_thread(desktop.stop)
                        new_port = _free_port()
                        while new_port == port:
                            new_port = _free_port()
                        third = await asyncio.to_thread(desktop.start, new_port)
                        if (
                            second == third
                            or (await session.call_tool("get_agent_status", {})).isError
                        ):
                            raise RuntimeError(
                                "MCP failed to refresh after a different-port restart"
                            )
                        return {
                            "tools": len(names),
                            "stdioInitialize": True,
                            "samePortRestart": True,
                            "differentPortRestart": True,
                            "missingDescriptorFailsClosed": True,
                        }
        finally:
            await asyncio.to_thread(desktop.stop)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--mcp-binary", type=Path, required=True)
    arguments = parser.parse_args()
    for path in (arguments.binary, arguments.mcp_binary):
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise RuntimeError("An absolute regular packaged executable is required")
    report = asyncio.run(exercise(arguments.binary, arguments.mcp_binary))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
