"""Explicit current-logon security for the local Windows console pipe."""

from __future__ import annotations

import hashlib
import sys

if sys.platform == "win32":
    import ntsecuritycon
    import pywintypes
    import win32api
    import win32con
    import win32security


def _require_windows() -> None:
    if sys.platform != "win32":
        raise OSError("the V20 console named pipe requires Windows")


def current_logon_sid() -> str:
    """Return the token-group SID marked as this interactive logon session."""

    _require_windows()
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        groups = win32security.GetTokenInformation(token, win32security.TokenGroups)
    finally:
        token.Close()
    logon_sids = [
        sid
        for sid, attributes in groups
        if attributes & win32con.SE_GROUP_LOGON_ID == win32con.SE_GROUP_LOGON_ID
    ]
    if len(logon_sids) != 1:
        raise OSError("current token does not contain one logon SID")
    return win32security.ConvertSidToStringSid(logon_sids[0])


def pipe_name(logon_sid: str) -> str:
    """Derive the stable, non-identifying pipe name for one logon session."""

    suffix = hashlib.sha256(logon_sid.encode("utf-8")).hexdigest()[:16]
    return rf"\\.\pipe\vesper-v20-tui-{suffix}"


def current_user_security_attributes() -> "pywintypes.SECURITY_ATTRIBUTES":
    """Build a protected DACL that grants only the current logon SID."""

    _require_windows()
    sid = win32security.ConvertStringSidToSid(current_logon_sid())
    rights = (
        ntsecuritycon.FILE_READ_DATA
        | ntsecuritycon.FILE_WRITE_DATA
        | ntsecuritycon.FILE_READ_ATTRIBUTES
        | ntsecuritycon.FILE_WRITE_ATTRIBUTES
        | ntsecuritycon.FILE_READ_EA
        | ntsecuritycon.FILE_WRITE_EA
        | ntsecuritycon.READ_CONTROL
        | ntsecuritycon.SYNCHRONIZE
    )
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, rights, sid)
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.Initialize()
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED,
        win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes
