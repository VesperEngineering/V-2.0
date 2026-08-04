[CmdletBinding()]
param(
    [switch]$ConfirmInstall,
    [string]$Executable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ConfirmInstall) {
    throw 'Pass -ConfirmInstall to create the current-user shortcut.'
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($Executable)) {
    $Executable = Join-Path $repoRoot 'dist\tui\vesper-ratatui-console.exe'
}
$target = [IO.Path]::GetFullPath($Executable)
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw 'Build dist\tui\vesper-ratatui-console.exe first.'
}

$programs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcutPath = Join-Path $programs 'Vesper V20 TUI.lnk'
$appUserModelId = 'Vesper.V20.TUI'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = 'Vesper V20 TUI'
$shortcut.Save()

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ShortcutPropertyStore
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct PropertyKey
    {
        internal Guid FormatId;
        internal uint PropertyId;

        internal PropertyKey(Guid formatId, uint propertyId)
        {
            FormatId = formatId;
            PropertyId = propertyId;
        }
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct PropVariant
    {
        [FieldOffset(0)] internal ushort VariantType;
        [FieldOffset(8)] internal IntPtr PointerValue;

        internal static PropVariant FromString(string value)
        {
            return new PropVariant
            {
                VariantType = 31,
                PointerValue = Marshal.StringToCoTaskMemUni(value)
            };
        }
    }

    [ComImport]
    [Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = true)]
    private static extern int SHGetPropertyStoreFromParsingName(
        string path,
        IntPtr bindContext,
        uint flags,
        ref Guid interfaceId,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

    [DllImport("ole32.dll", PreserveSig = true)]
    private static extern int PropVariantClear(ref PropVariant value);

    public static void SetAppUserModelId(string shortcutPath, string appUserModelId)
    {
        Guid interfaceId = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
        IPropertyStore store;
        int result = SHGetPropertyStoreFromParsingName(
            shortcutPath,
            IntPtr.Zero,
            2,
            ref interfaceId,
            out store);
        Marshal.ThrowExceptionForHR(result);
        var key = new PropertyKey(
            new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            5);
        var value = PropVariant.FromString(appUserModelId);
        try
        {
            Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
            Marshal.ThrowExceptionForHR(store.Commit());
        }
        finally
        {
            PropVariantClear(ref value);
            Marshal.ReleaseComObject(store);
        }
    }
}
'@

[ShortcutPropertyStore]::SetAppUserModelId($shortcutPath, $appUserModelId)

$registration = "HKCU:\Software\Classes\AppUserModelId\$appUserModelId"
New-Item -Path $registration -Force | Out-Null
New-ItemProperty -Path $registration -Name DisplayName -Value 'Vesper V20 TUI' -PropertyType String -Force | Out-Null

[ordered]@{
    shortcut = $shortcutPath
    executable = $target
    app_user_model_id = $appUserModelId
} | ConvertTo-Json -Depth 3
