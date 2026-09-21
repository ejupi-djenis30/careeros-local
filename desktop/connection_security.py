"""Native ACL and path checks for the token-free MCP connection descriptor."""

from __future__ import annotations

import ctypes
import os
import stat
from functools import lru_cache
from pathlib import Path
from typing import Any


def _windows() -> tuple[Any, Any]:
    loader = getattr(ctypes, "WinDLL")
    advapi, kernel = (
        loader("advapi32", use_last_error=True),
        loader("kernel32", use_last_error=True),
    )
    pointer = ctypes.c_void_p
    advapi.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        *([ctypes.POINTER(pointer)] * 5),
    ]
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi.GetAce.argtypes = [pointer, ctypes.c_uint32, ctypes.POINTER(pointer)]
    advapi.GetAclInformation.argtypes = [pointer, pointer, ctypes.c_uint32, ctypes.c_uint32]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.POINTER(pointer),
        pointer,
    ]
    advapi.GetSecurityDescriptorDacl.argtypes = [
        pointer,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(pointer),
        ctypes.POINTER(ctypes.c_int),
    ]
    advapi.SetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        pointer,
        pointer,
        pointer,
        pointer,
    ]
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    kernel.GetCurrentProcess.restype = pointer
    kernel.CloseHandle.argtypes = [pointer]
    advapi.OpenProcessToken.argtypes = [pointer, ctypes.c_uint32, ctypes.POINTER(pointer)]
    advapi.GetTokenInformation.argtypes = [
        pointer,
        ctypes.c_uint32,
        pointer,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    return advapi, kernel


def _sid_text(pointer: Any, advapi: Any, kernel: Any) -> str:
    value = ctypes.c_wchar_p()
    if not advapi.ConvertSidToStringSidW(pointer, ctypes.byref(value)):
        raise ValueError("Cannot verify descriptor access control")
    try:
        return str(value.value)
    finally:
        kernel.LocalFree(ctypes.cast(value, ctypes.c_void_p))


@lru_cache(maxsize=1)
def current_user_sid() -> str:
    advapi, kernel = _windows()
    token = ctypes.c_void_p()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ValueError("Cannot verify descriptor owner")
    try:
        size = ctypes.c_uint32()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not 0 < size.value < 65536:
            raise ValueError("Cannot verify descriptor owner")
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size.value, ctypes.byref(size)):
            raise ValueError("Cannot verify descriptor owner")
        return _sid_text(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0], advapi, kernel)
    finally:
        kernel.CloseHandle(token)


def secure_private(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    advapi, kernel = _windows()
    descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    present, defaulted = ctypes.c_int(), ctypes.c_int()
    sddl = f"D:P(A;OICI;FA;;;{current_user_sid()})(A;OICI;FA;;;SY)"
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        raise ValueError("Cannot secure descriptor permissions")
    try:
        if (
            not advapi.GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
            )
            or not present.value
        ):
            raise ValueError("Cannot secure descriptor permissions")
        if advapi.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None):
            raise ValueError("Cannot secure descriptor permissions")
    finally:
        kernel.LocalFree(descriptor)


def verify_private(path: Path, metadata: os.stat_result) -> None:
    if os.name != "nt":
        if metadata.st_uid != getattr(os, "geteuid")() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("Descriptor permissions are not private")
        return
    # Windows chmod does not validate the DACL. Read owner and every allowed ACE.
    advapi, kernel = _windows()
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    if advapi.GetNamedSecurityInfoW(
        str(path),
        1,
        5,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    ):
        raise ValueError("Cannot verify descriptor access control")
    try:
        user = current_user_sid()
        if _sid_text(owner, advapi, kernel) != user or not dacl:
            raise ValueError("Descriptor permissions are not private")
        size = (ctypes.c_uint32 * 3)()
        if (
            not advapi.GetAclInformation(dacl, ctypes.byref(size), ctypes.sizeof(size), 2)
            or size[0] > 1024
        ):
            raise ValueError("Cannot verify descriptor access control")
        for index in range(size[0]):
            ace = ctypes.c_void_p()
            if not advapi.GetAce(dacl, index, ctypes.byref(ace)) or not ace.value:
                raise ValueError("Cannot verify descriptor access control")
            kind = ctypes.cast(ace, ctypes.POINTER(ctypes.c_ubyte))[0]
            if kind == 1:  # Denies cannot grant another user access.
                continue
            if kind != 0 or _sid_text(ace.value + 8, advapi, kernel) not in {
                user,
                "S-1-5-18",
                "S-1-5-32-544",
            }:
                raise ValueError("Descriptor permissions are not private")
    finally:
        kernel.LocalFree(descriptor)


def checked_path(value: str | Path, *, exists: bool = True) -> Path:
    raw = os.fspath(value)
    path = Path(raw)
    if (
        not path.is_absolute()
        or path.drive.startswith("\\\\")
        or os.path.normpath(raw) != raw
        or any(part in {".", ".."} for part in path.parts)
        or (
            os.name == "nt"
            and any(
                part.rstrip(". ") != part or any(char in part for char in ':<>"|?*')
                for part in path.parts[1:]
            )
        )
    ):
        raise ValueError("Descriptor path must be absolute and canonical")
    for component in (*reversed(path.parents), path):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            if not exists and component == path:
                continue
            raise ValueError("Descriptor path is unavailable") from None
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ValueError("Descriptor path must not contain links or reparse points")
        if component == path and stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
            raise ValueError("Descriptor must not have hard-link aliases")
    return path
