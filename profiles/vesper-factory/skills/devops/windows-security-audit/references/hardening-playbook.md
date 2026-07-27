# Windows Listener Hardening Playbook (verified 2026-07 on Win11 build 26200)

Session-specific detail from a live audit + remediation. All service changes below were
applied and verified on a real workstation.

## 1. The big gotcha: stopping a service does NOT always close its ports

### SMB server stack (ports 445 / 139)
- `Stop-Service LanmanServer` succeeds, but ports **445 and 139 stay LISTENING** because
  kernel drivers hold them:
  - `srv2` + `srvnet` → port 445 (PID 4, System)
  - `netbt` → port 139 (per-interface, includes VMware/WSL virtual NICs)
- To close now, also stop the drivers (elevated): `sc.exe stop srv2; sc.exe stop srvnet; sc.exe stop netbt`
- **Observed**: `srv2` stopped cleanly; `srvnet` and `netbt` hung in `STOP_PENDING`
  (in-session references can't unload). They were still set `start= disabled`
  successfully, so the ports close fully **after reboot**. Don't force anything riskier —
  report "ports close after next reboot" and move on.
- Persistent config that worked:
  - `Set-Service LanmanServer -StartupType Disabled`
  - `sc.exe config srv2 start= disabled` / `srvnet` / `netbt` (note the space: `start= disabled`)
- Client-side outbound SMB (LanmanWorkstation) is a SEPARATE component — untouched,
  user can still connect TO other shares.
- Check `Get-SmbSession` is empty before stopping LanmanServer.

### TeamViewer (port 5939)
- `Stop-Service TeamViewer` + `Set-Service ... -StartupType Disabled` worked cleanly;
  listener (loopback-only 5939) gone immediately. No user software depends on it.

### VMware Workstation (ports 902/912 on 0.0.0.0)
- Stopped + disabled: `VMAuthdService`, `VMnetDHCP`, `VMware NAT Service`, `VMUSBArbService`.
  Ports 902/912 closed immediately.
- **Dependency check that mattered**: Claude Desktop's `CoworkVMService`
  (cowork-svc.exe) is a VM-branded service but runs on **Hyper-V** (`vmcompute`,
  Hyper-V Host Compute Service), NOT VMware. Docker Desktop and WSL2 also use Hyper-V.
  So disabling VMware Workstation services does not break Claude Cowork / Docker / WSL.
- Verify no actual VMs before killing: search for `*.vmx` on user drives (none found →
  VMware services were running for zero VMs).
- Side note: with Hyper-V active (`vmcompute` running), VMware Workstation VMs are
  degraded anyway on modern Windows.

## 2. RDP registry keys (not yet applied in that session; flagged 🔴)

```
HKLM:\System\CurrentControlSet\Control\Terminal Server   fDenyTSConnections  0=ON 1=OFF
HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp   UserAuthentication  0=NLA OFF 1=ON
```
RDP on + NLA off = unauthenticated attackers reach a full logon prompt (brute-force +
pre-auth RDP CVE surface). Fix: `fDenyTSConnections=1` if unused, else `UserAuthentication=1`.

## 3. Reversibility (always include in the report)

```powershell
Set-Service <Name> -StartupType Automatic; Start-Service <Name>
# drivers: sc.exe config srvnet start= demand; sc.exe config netbt start= system (defaults)
```

## 4. Verified-good audit findings (baseline for a healthy machine)

- All running process binaries `Get-AuthenticodeSignature` Status = Valid.
- Zero Security 4625 (failed) and zero 4624 LogonType 3/10 (remote) in 7 days.
- Defender off BUT Bitdefender registered in SecurityCenter2 with same-day timestamp → expected, not a gap.
- Firewall all profiles Enabled; `NotConfigured` default actions = Windows defaults (block unsolicited inbound).
- hosts file: only Docker Desktop entries. ProxyEnable=0. DNS = router only.
- Persistence (Run keys / startup folder / non-Microsoft scheduled tasks / non-system32 services)
  fully mapped to known user software.

## 5. Execution mechanics that worked

- Non-elevated git-bash shell → stage `.ps1` via write_file →
  `powershell.exe -NoProfile -Command 'Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File <script>" -Wait'`
  → user approves UAC → read log via `Get-Content` (Out-File writes UTF-16 → read_file
  reports "binary"; sc.exe output piped through Out-File stays UTF-16 even with -Encoding ascii)
  → delete staged `.ps1` and `.log`.
- `wsl.exe -l -v` output arrives with NUL-spaced chars (UTF-16) in bash — still readable, don't panic.
