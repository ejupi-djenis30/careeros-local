"""Read native process birth identities without application or third-party imports."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def process_identity(pid: int) -> str:
    if type(pid) is not int or not 1 <= pid <= 0x7FFFFFFF:
        raise ValueError("Invalid desktop process identity")
    if os.name == "nt":
        from ctypes import wintypes

        kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            *([ctypes.POINTER(wintypes.FILETIME)] * 4),
        ]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise ValueError("Desktop process is unavailable")
        try:
            creation, exit_time, system, user = (wintypes.FILETIME() for _ in range(4))
            status = wintypes.DWORD()
            if (
                not kernel.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(system),
                    ctypes.byref(user),
                )
                or not kernel.GetExitCodeProcess(handle, ctypes.byref(status))
                or status.value != 259
            ):
                raise ValueError("Desktop process is unavailable")
            return f"win:{creation.dwHighDateTime << 32 | creation.dwLowDateTime}"
        finally:
            kernel.CloseHandle(handle)
    if sys.platform.startswith("linux"):
        directory = Path("/proc") / str(pid)
        if directory.stat().st_uid != os.geteuid():
            raise ValueError("Desktop process has a different owner")
        with (directory / "stat").open("r", encoding="ascii") as source:
            fields = source.read(4096).rsplit(")", 1)[1].split()
        if len(fields) < 20 or fields[0] in {"Z", "X"} or not fields[19].isdigit():
            raise ValueError("Desktop process is unavailable")
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        return f"linux:{boot}:{fields[19]}"
    if sys.platform == "darwin":
        # proc_bsdinfo: https://github.com/apple/darwin-xnu/blob/main/bsd/sys/proc_info.h
        class BsdInfo(ctypes.Structure):
            _fields_ = [
                ("header", ctypes.c_uint32 * 12),
                ("comm", ctypes.c_char * 16),
                ("name", ctypes.c_char * 32),
                ("counts", ctypes.c_uint32 * 6),
                ("start_seconds", ctypes.c_uint64),
                ("start_microseconds", ctypes.c_uint64),
            ]

        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        library.proc_pidinfo.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        info = BsdInfo()
        if (
            library.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
            != ctypes.sizeof(info)
            or info.header[5] != os.geteuid()
            or info.header[1] == 5  # SZOMB: a dead process awaiting reaping.
            or info.header[3] != pid
            or not info.start_seconds
        ):
            raise ValueError("Desktop process is unavailable")
        return f"mac:{info.start_seconds}:{info.start_microseconds}"
    raise ValueError("Native process identity is unsupported")
