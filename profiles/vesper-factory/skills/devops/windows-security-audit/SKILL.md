---
name: windows-security-audit
title: "Windows Security Audit & Listener Hardening"
description: >
  Conduct a read-only (or minimally-invasive, user-authorized) security review of a
  Windows workstation: patch/AV/firewall posture, account hygiene, exposed listeners,
  persistence sweep, logon audit trail, and safe shutdown of unneeded services
  (TeamViewer, SMB server, VMware, RDP). Load whenever the user asks for a security
  review, hardening check, "is my PC compromised", or to close ports/services.
triggers:
  - "security review of my computer"
  - "audit my Windows machine for security issues"
  - "check if my PC is compromised"
  - "close open ports / disable unneeded services"
  - "harden this Windows box"
---

# Windows Security Audit & Listener Hardening

## Ground rules

1. **Default mode is read-only.** If the user asked for findings only, every command must be a query. No `Stop-Service`, `Set-Service`, `Set-ItemProperty`, `sc config`, or kills until the user explicitly authorizes specific changes.
2. **Explain before altering.** Before stopping anything, check what depends on it (active sessions, dependent services, related user software) and state the impact + reversibility in the report.
3. **All PowerShell runs through git-bash quirks** — see `windows-system-monitoring` §13: single-quote the `-Command` string, expect non-elevated shell, use the `Start-Process -Verb RunAs` + log-file pattern for changes, read logs back with `Get-Content`.
4. Batch independent read-only checks into parallel terminal calls; keep each output compact.

## Audit checklist (commands)

Wrap every command: `powershell.exe -NoProfile -Command '<cmd>'` (single quotes!).

1. **OS & patch level**: `Get-ComputerInfo OsName,OsVersion,OsBuildNumber,OsLastBootUpTime`; `Get-HotFix | Sort InstalledOn -Desc | Select -First 5`. Verify OS matches what the user/host metadata claims (host header may be stale).
2. **Accounts**: `Get-LocalUser` (enabled, last logon); `Get-LocalGroupMember Administrators`. Built-in Administrator/Guest should be disabled; question unexpected enabled accounts (know that tools like Codex CLI create sandbox accounts).
3. **AV posture**: `Get-MpComputerStatus` (Defender) AND `Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct` — Defender fully off is EXPECTED when a third-party AV is registered and current; check the third-party productState/timestamp before calling it a gap.
4. **Firewall**: `Get-NetFirewallProfile` — all three profiles Enabled; DefaultInbound/OutboundAction `NotConfigured` means Windows defaults apply (block unsolicited inbound), not "allow all".
5. **Listeners**: `Get-NetTCPConnection -State Listen` → map each non-system `OwningProcess` PID via `Get-Process -Id`. Classify: loopback-only (low risk) vs 0.0.0.0/:: (LAN-exposed). Common benign: 135/445/139 SMB, 49664+ RPC, 5040 CDP, 2869 SSDP, 11434 Ollama (loopback), wslrelay on 25 (loopback), VMware authd 902/912 (exposed), TeamViewer 5939 (loopback).
6. **Remote access config**: RDP = `(Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server').fDenyTSConnections` (0 = RDP ON) and NLA = `...\WinStations\RDP-Tcp` `UserAuthentication` (0 = NLA OFF — worst combo). `Get-SmbServerConfiguration` (SMB1 should be False). WinRM service state.
7. **Shares & sessions**: `Get-SmbShare` (default C$/ADMIN$/IPC$ only is normal), `Get-SmbSession` (should be empty before you touch LanmanServer).
8. **Outbound connections**: `Get-NetTCPConnection -State Established` excluding loopback; group by process name. Legit baseline: browsers, AV cloud (bdservicehost→GCP), Telegram, updaters. Flag unknown processes with internet connections.
9. **DNS/proxy/hosts**: `Get-DnsClientServerAddress`; `HKCU:\...\Internet Settings` ProxyEnable (should be 0, empty AutoConfigURL); hosts file non-comment lines (Docker entries are normal).
10. **Persistence sweep**: HKLM+HKCU `...\CurrentVersion\Run`; `Win32_StartupCommand`; `Get-ScheduledTask | ? TaskPath -notlike '\Microsoft*'`; running services with PathName outside system32. All should map to identifiable installed software.
11. **Signature sweep**: `Get-Process | ? Path | Select -Unique Path | % { Get-AuthenticodeSignature $_.Path }` — anything not `Valid` is a finding.
12. **Logon audit trail**: `Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddDays(-7)}` (failed logons) and Id=4624 filtered to LogonType 3/10 (network/RDP). Zero of both on an exposed machine = no brute-force evidence; say so.
13. **UAC**: `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System` — EnableLUA=1, PromptOnSecureDesktop=1 expected.
14. **Virtualization adjacencies**: WSL (`wsl.exe -l -v`, output is UTF-16-spaced), Docker, Hyper-V `vmcompute` — note which hypervisor stack the user's AI tools actually use before touching VMware (see references).

## Reporting

Severity-tiered report: 🔴 config exposures that enable remote attack (RDP+NLA-off, exposed SMB/VMware), 🟡 always-on remote-access tooling and LAN-exposed listeners, 🟢 positive findings (explicitly confirm: no unsigned binaries, no failed/remote logons, patching current, UAC on), ⚪ informational. End with a prioritized bottom line. State explicitly that nothing was altered (when true).

## Remediation (only with explicit user authorization)

- Verify dependencies FIRST (checklist items 7, 14, plus "does any user software need this?" — e.g. Claude Cowork VMs use Hyper-V/vmcompute, NOT VMware Workstation; Docker/WSL2 use Hyper-V too).
- Stop + disable via elevated script; verify listeners actually closed afterward — stopping a service does NOT always release its ports (see `references/hardening-playbook.md` for the SMB kernel-driver case).
- Always give the reverse commands (`Set-Service <name> -StartupType Automatic; Start-Service <name>`).

## Files

- `references/hardening-playbook.md` — verified shutdown behavior for TeamViewer, VMware services, and the SMB server stack (LanmanServer vs srv2/srvnet/netbt kernel drivers, STOP_PENDING hang, why a reboot finishes it), RDP/NLA registry keys, and per-item reversibility.
