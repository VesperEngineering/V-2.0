# PowerShell Shortcut Creation — Reference Script

This is the exact script that worked to create a WSL launcher shortcut on the Windows desktop. Copy and adapt.

## Step 1: Write the PowerShell script to the desktop

Write this content to `C:\Users\<user>\Desktop\make-shortcut.ps1`:

```powershell
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\My Tool Name.lnk")
$Shortcut.TargetPath = "wsl.exe"
$Shortcut.Arguments = "/home/user/project/scripts/tool.sh"
$Shortcut.WorkingDirectory = "/home/user/project"
$Shortcut.WindowStyle = 7
$Shortcut.Description = "What this tool does"
$Shortcut.Save()
Write-Output "Shortcut created at $env:USERPROFILE\Desktop\My Tool Name.lnk"
```

## Step 2: Run it from git-bash/MSYS terminal

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\<user>\Desktop\make-shortcut.ps1"
```

## Step 3: Clean up

```bash
rm -f "C:\Users\<user>\Desktop\make-shortcut.ps1"
```

## Real Example (from this session — Vesper Live Runs dashboard)

### make-shortcut.ps1

```powershell
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Vesper Live Runs.lnk")
$Shortcut.TargetPath = "wsl.exe"
$Shortcut.Arguments = "/home/brennan/vesper-autoresearch/scripts/open-live-chart.sh"
$Shortcut.WorkingDirectory = "/home/brennan/vesper-autoresearch"
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Open the live Vesper autoresearch chart"
$Shortcut.Save()
Write-Output "Shortcut created"
```

### Run command

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\bgonn\Desktop\make-shortcut.ps1"
```
