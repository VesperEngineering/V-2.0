from __future__ import annotations

import hashlib
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows named-pipe security")

if sys.platform == "win32":
    import ntsecuritycon
    import win32api
    import win32con
    import win32file
    import win32pipe
    import win32security

from vesper.platform.tui.pipe_security import (
    current_logon_sid,
    current_user_security_attributes,
    pipe_name,
)


def test_current_logon_sid_comes_from_logon_token_group() -> None:
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        groups = win32security.GetTokenInformation(token, win32security.TokenGroups)
    finally:
        token.Close()
    expected = {
        win32security.ConvertSidToStringSid(sid)
        for sid, attributes in groups
        if attributes & win32con.SE_GROUP_LOGON_ID == win32con.SE_GROUP_LOGON_ID
    }

    assert expected
    assert current_logon_sid() in expected


def test_pipe_name_is_deterministic_sha256() -> None:
    sid = "S-1-5-5-123-456"
    suffix = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16]

    assert pipe_name(sid) == rf"\\.\pipe\vesper-v20-tui-{suffix}"


def test_security_attributes_are_explicit_protected_current_logon_only() -> None:
    logon_sid = current_logon_sid()
    attributes = current_user_security_attributes()

    assert type(attributes).__name__ == "PySECURITY_ATTRIBUTES"
    handle = win32pipe.CreateNamedPipe(
        pipe_name(logon_sid),
        win32pipe.PIPE_ACCESS_DUPLEX | win32pipe.FILE_FLAG_FIRST_PIPE_INSTANCE,
        win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
        4,
        1_048_576,
        1_048_576,
        0,
        attributes,
    )
    try:
        descriptor = win32security.GetSecurityInfo(
            handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
    finally:
        win32file.CloseHandle(handle)
    assert descriptor is not None
    control, _ = descriptor.GetSecurityDescriptorControl()
    assert control & win32security.SE_DACL_PROTECTED
    assert descriptor.GetSecurityDescriptorDacl() is not None

    dacl = descriptor.GetSecurityDescriptorDacl()
    allowed: dict[str, int] = {}
    for index in range(dacl.GetAceCount()):
        ace_header, access_mask, sid = dacl.GetAce(index)
        if ace_header[0] == win32security.ACCESS_ALLOWED_ACE_TYPE:
            sid_text = win32security.ConvertSidToStringSid(sid)
            allowed[sid_text] = allowed.get(sid_text, 0) | access_mask

    assert set(allowed) == {logon_sid}
    required = (
        ntsecuritycon.FILE_READ_DATA
        | ntsecuritycon.FILE_WRITE_DATA
        | ntsecuritycon.FILE_READ_ATTRIBUTES
        | ntsecuritycon.FILE_WRITE_ATTRIBUTES
        | ntsecuritycon.FILE_READ_EA
        | ntsecuritycon.FILE_WRITE_EA
        | ntsecuritycon.READ_CONTROL
        | ntsecuritycon.SYNCHRONIZE
    )
    rights = allowed[logon_sid]
    assert rights & required == required
    assert rights & ntsecuritycon.FILE_APPEND_DATA == 0
    file_create_pipe_instance = 0x00000004
    assert rights & file_create_pipe_instance == 0

    denied_well_known = {
        win32security.ConvertSidToStringSid(win32security.CreateWellKnownSid(kind, None))
        for kind in (
            win32security.WinWorldSid,
            win32security.WinAnonymousSid,
            win32security.WinNetworkSid,
        )
    }
    assert denied_well_known.isdisjoint(allowed)
