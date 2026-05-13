#requires -version 5.1
<#
Fix Windows PATH for a manually installed uv at C:\uv, then broadcast an
environment refresh message. Run from an elevated PowerShell for Machine PATH.

  powershell -ExecutionPolicy Bypass -File D:\python\BidX_simple\scripts\fix_uv_path.ps1
#>

[CmdletBinding()]
param(
    [string]$UvDir = "C:\uv"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $RepoRoot "log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("fix_uv_path_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Encoding UTF8 -Value $line
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Add-PathEntry {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("User", "Machine")][string]$Target,
        [Parameter(Mandatory = $true)][string]$Entry
    )

    $current = [Environment]::GetEnvironmentVariable("Path", $Target)
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        $parts = $current -split ";" | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }

    $parts = @($parts | Where-Object { $_.TrimEnd("\") -ine $Entry.TrimEnd("\") })
    $newPath = (@($parts) + $Entry) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, $Target)
    Write-Log "$Target PATH contains $Entry"
}

function Broadcast-EnvironmentChange {
    $source = @"
using System;
using System.Runtime.InteropServices;

public static class EnvBroadcast {
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        uint Msg,
        UIntPtr wParam,
        string lParam,
        uint fuFlags,
        uint uTimeout,
        out UIntPtr lpdwResult);
}
"@
    Add-Type -TypeDefinition $source -ErrorAction SilentlyContinue
    $result = [UIntPtr]::Zero
    [void][EnvBroadcast]::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, "Environment", 0x0002, 5000, [ref]$result)
    Write-Log "Broadcasted environment change."
}

try {
    Write-Log "Fix uv PATH started."
    Write-Log "UvDir: $UvDir"
    if (-not (Test-Path -LiteralPath (Join-Path $UvDir "uv.exe"))) {
        throw "uv.exe not found at $UvDir"
    }

    Add-PathEntry -Target "User" -Entry $UvDir
    if (Test-IsAdministrator) {
        Add-PathEntry -Target "Machine" -Entry $UvDir
    }
    else {
        Write-Log "Not elevated; Machine PATH skipped."
    }

    [Environment]::SetEnvironmentVariable("UV_DEFAULT_INDEX", "https://mirrors.ustc.edu.cn/pypi/simple", "User")
    [Environment]::SetEnvironmentVariable("UV_INDEX_URL", "https://mirrors.ustc.edu.cn/pypi/simple", "User")
    [Environment]::SetEnvironmentVariable("UV_DOWNLOAD_URL", "https://mirrors.ustc.edu.cn/github-release/astral-sh/uv/LatestRelease/", "User")
    [Environment]::SetEnvironmentVariable("UV_PYTHON_INSTALL_MIRROR", "https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/", "User")

    Broadcast-EnvironmentChange

    $env:Path = "$UvDir;$env:Path"
    Write-Log "Version via absolute path: $(& (Join-Path $UvDir "uv.exe") --version)"
    Write-Log "Version via PATH in this process: $(& uv --version)"
    Write-Log "Log saved to: $LogFile"
}
catch {
    Write-Log "FAILED: $($_.Exception.Message)"
    Write-Log "Log saved to: $LogFile"
    exit 1
}
