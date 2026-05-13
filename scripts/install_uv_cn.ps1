#requires -version 5.1
<#
Install uv system-wide on Windows with China mirrors, then diagnose the result.

Run from an elevated PowerShell:
  powershell -ExecutionPolicy Bypass -File D:\python\BidX_simple\scripts\install_uv_cn.ps1

If the mirror keeps returning a browser verification page, download the ZIP in
your browser first and then run:
  powershell -ExecutionPolicy Bypass -File D:\python\BidX_simple\scripts\install_uv_cn.ps1 -SkipInstaller -LocalZip C:\path\to\uv-x86_64-pc-windows-msvc.zip
#>

[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:ProgramFiles "uv"),
    [string]$MirrorBase = "https://mirrors.ustc.edu.cn/github-release/astral-sh/uv/LatestRelease/",
    [string]$DefaultIndex = "https://mirrors.ustc.edu.cn/pypi/simple",
    [string]$PythonInstallMirror = "https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/",
    [string]$LocalZip = "",
    [switch]$SkipInstaller
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $RepoRoot "log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$script:LogFile = Join-Path $LogDir "install_uv_cn_$RunStamp.log"
New-Item -ItemType File -Force -Path $script:LogFile | Out-Null

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "OK", "CMD")][string]$Level = "INFO"
    )

    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    Add-Content -LiteralPath $script:LogFile -Encoding UTF8 -Value $line
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Get-UvAssetName {
    switch ($env:PROCESSOR_ARCHITECTURE) {
        "ARM64" { return "uv-aarch64-pc-windows-msvc.zip" }
        "AMD64" { return "uv-x86_64-pc-windows-msvc.zip" }
        "x86" { return "uv-i686-pc-windows-msvc.zip" }
        default {
            if ([Environment]::Is64BitOperatingSystem) {
                return "uv-x86_64-pc-windows-msvc.zip"
            }
            return "uv-i686-pc-windows-msvc.zip"
        }
    }
}

function Invoke-NativeLogged {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Log ("Running: {0} {1}" -f $FilePath, ($Arguments -join " ")) "CMD"
    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    foreach ($line in $output) {
        if ($null -ne $line) {
            Write-Log ($line.ToString()) "CMD"
        }
    }
    Write-Log ("Exit code: {0}" -f $exitCode) "CMD"
    return $exitCode
}

function Test-ZipSignature {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $item = Get-Item -LiteralPath $Path
    if ($item.Length -lt 1048576) {
        Write-Log ("Downloaded file is suspiciously small: {0} bytes" -f $item.Length) "WARN"
        return $false
    }

    $stream = [IO.File]::OpenRead($Path)
    try {
        $bytes = New-Object byte[] 2
        [void]$stream.Read($bytes, 0, 2)
        return ($bytes[0] -eq 0x50 -and $bytes[1] -eq 0x4B)
    }
    finally {
        $stream.Dispose()
    }
}

function Get-UstcVerificationCookie {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $item = Get-Item -LiteralPath $Path
    if ($item.Length -gt 65536) {
        return $null
    }

    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    }
    catch {
        return $null
    }

    if ($content -notmatch "Verifying your browser") {
        return $null
    }

    if ($content -match 'document\.cookie\s*=\s*"([^";]+=[^";]+);') {
        return $Matches[1]
    }

    return $null
}

function Invoke-WebRequestDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$OutFile,
        [hashtable]$Headers = @{}
    )

    $requestHeaders = @{
        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        "Accept" = "application/zip,application/octet-stream,*/*"
    }
    foreach ($key in $Headers.Keys) {
        $requestHeaders[$key] = $Headers[$key]
    }

    Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -TimeoutSec 300 -Headers $requestHeaders
}

function Invoke-DownloadFile {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$OutFile
    )

    if (Test-Path -LiteralPath $OutFile) {
        Remove-Item -LiteralPath $OutFile -Force
    }

    Write-Log ("Downloading: {0}" -f $Uri)
    Write-Log ("Destination: {0}" -f $OutFile)

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequestDownload -Uri $Uri -OutFile $OutFile
        if (Test-Path -LiteralPath $OutFile) {
            $verificationCookie = Get-UstcVerificationCookie -Path $OutFile
            if ($null -ne $verificationCookie) {
                Write-Log ("Mirror returned browser verification page; retrying with cookie: {0}" -f $verificationCookie) "WARN"
                Remove-Item -LiteralPath $OutFile -Force
                Invoke-WebRequestDownload -Uri $Uri -OutFile $OutFile -Headers @{ "Cookie" = $verificationCookie }
            }
            Write-Log "Download succeeded with Invoke-WebRequest." "OK"
            return
        }
    }
    catch {
        Write-Log ("Invoke-WebRequest failed: {0}" -f $_.Exception.Message) "WARN"
    }

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -ne $curl) {
        $curlArgs = @("--location", "--fail", "--show-error", "--connect-timeout", "30", "--max-time", "300", "--output", $OutFile, $Uri)
        $exitCode = Invoke-NativeLogged -FilePath $curl.Source -Arguments $curlArgs
        if ($exitCode -eq 0 -and (Test-Path -LiteralPath $OutFile)) {
            Write-Log "Download succeeded with curl.exe." "OK"
            return
        }

        $curlArgsNoRevoke = @("--ssl-no-revoke", "--location", "--fail", "--show-error", "--connect-timeout", "30", "--max-time", "300", "--output", $OutFile, $Uri)
        $exitCode = Invoke-NativeLogged -FilePath $curl.Source -Arguments $curlArgsNoRevoke
        if ($exitCode -eq 0 -and (Test-Path -LiteralPath $OutFile)) {
            Write-Log "Download succeeded with curl.exe --ssl-no-revoke." "OK"
            return
        }
    }

    try {
        $webClient = New-Object Net.WebClient
        $webClient.DownloadFile($Uri, $OutFile)
        if (Test-Path -LiteralPath $OutFile) {
            Write-Log "Download succeeded with WebClient." "OK"
            return
        }
    }
    catch {
        Write-Log ("WebClient failed: {0}" -f $_.Exception.Message) "WARN"
    }

    throw "All download methods failed for $Uri"
}

function Add-MachinePathEntry {
    param([Parameter(Mandatory = $true)][string]$PathEntry)

    $current = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ([string]::IsNullOrWhiteSpace($current)) {
        $parts = @()
    }
    else {
        $parts = $current -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }

    $alreadyPresent = $false
    foreach ($part in $parts) {
        if ($part.TrimEnd("\") -ieq $PathEntry.TrimEnd("\")) {
            $alreadyPresent = $true
            break
        }
    }

    if ($alreadyPresent) {
        Write-Log ("Machine PATH already contains: {0}" -f $PathEntry) "OK"
    }
    else {
        $newPath = (($parts + $PathEntry) -join ";")
        [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
        Write-Log ("Added to Machine PATH: {0}" -f $PathEntry) "OK"
    }

    $processParts = $env:Path -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $inProcessPath = $false
    foreach ($part in $processParts) {
        if ($part.TrimEnd("\") -ieq $PathEntry.TrimEnd("\")) {
            $inProcessPath = $true
            break
        }
    }
    if (-not $inProcessPath) {
        $env:Path = "$PathEntry;$env:Path"
    }
}

function Set-MachineEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    [Environment]::SetEnvironmentVariable($Name, $Value, "Machine")
    Set-Item -Path ("Env:{0}" -f $Name) -Value $Value
    Write-Log ("Machine environment set: {0}={1}" -f $Name, $Value) "OK"
}

function Install-UvManually {
    param(
        [Parameter(Mandatory = $true)][string]$WorkDir,
        [Parameter(Mandatory = $true)][string]$AssetUrl,
        [Parameter(Mandatory = $true)][string]$AssetName,
        [Parameter(Mandatory = $true)][string]$TargetDir,
        [string]$LocalZip = ""
    )

    Write-Log "Starting manual ZIP install fallback."
    $zipPath = Join-Path $WorkDir $AssetName
    if (-not [string]::IsNullOrWhiteSpace($LocalZip)) {
        $resolvedLocalZip = Resolve-Path -LiteralPath $LocalZip -ErrorAction Stop
        Write-Log ("Using local ZIP: {0}" -f $resolvedLocalZip.Path)
        Copy-Item -LiteralPath $resolvedLocalZip.Path -Destination $zipPath -Force
    }
    else {
        Invoke-DownloadFile -Uri $AssetUrl -OutFile $zipPath
    }

    if (-not (Test-ZipSignature -Path $zipPath)) {
        throw "Downloaded file is not a valid uv ZIP. Check the mirror, proxy, or verification page in the log."
    }

    $extractDir = Join-Path $WorkDir "extract"
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    Write-Log ("Expanded ZIP to: {0}" -f $extractDir) "OK"

    $uvExe = Get-ChildItem -LiteralPath $extractDir -Recurse -Filter "uv.exe" -File | Select-Object -First 1
    if ($null -eq $uvExe) {
        throw "uv.exe was not found after extracting the ZIP."
    }

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    $sourceDir = $uvExe.Directory.FullName
    foreach ($file in Get-ChildItem -LiteralPath $sourceDir -File) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $TargetDir $file.Name) -Force
        Write-Log ("Installed file: {0}" -f (Join-Path $TargetDir $file.Name)) "OK"
    }
}

function Write-UvConfig {
    param(
        [Parameter(Mandatory = $true)][string]$IndexUrl
    )

    $configDir = Join-Path $env:ProgramData "uv"
    $configFile = Join-Path $configDir "uv.toml"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null

    $content = @"
# Written by install_uv_cn.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
default-index = "$IndexUrl"
"@

    Set-Content -LiteralPath $configFile -Encoding UTF8 -Value $content
    Write-Log ("Wrote uv system config: {0}" -f $configFile) "OK"
    Write-Log "uv.toml content:"
    foreach ($line in ($content -split "`r?`n")) {
        Write-Log $line "CMD"
    }
}

function Test-UvInstall {
    param([Parameter(Mandatory = $true)][string]$TargetDir)

    $uvExe = Join-Path $TargetDir "uv.exe"
    $result = [ordered]@{
        UvExeExists = $false
        UvExePath = $uvExe
        PathCommand = $null
        VersionExitCode = $null
        VersionText = $null
        Success = $false
    }

    if (Test-Path -LiteralPath $uvExe) {
        $result.UvExeExists = $true
        Write-Log ("uv.exe exists: {0}" -f $uvExe) "OK"
    }
    else {
        Write-Log ("uv.exe missing: {0}" -f $uvExe) "ERROR"
        return $result
    }

    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        $result.PathCommand = $cmd.Source
        Write-Log ("uv resolved from PATH: {0}" -f $cmd.Source) "OK"
    }
    else {
        Write-Log "uv is not visible through PATH in this process." "WARN"
    }

    $versionOutput = & $uvExe --version 2>&1
    $versionExit = $LASTEXITCODE
    $result.VersionExitCode = $versionExit
    $result.VersionText = (($versionOutput | ForEach-Object { $_.ToString() }) -join "`n")
    Write-Log ("uv --version exit code: {0}" -f $versionExit) "CMD"
    foreach ($line in $versionOutput) {
        Write-Log ($line.ToString()) "CMD"
    }

    if ($versionExit -eq 0 -and $result.VersionText -match "^uv\s+\d+\.\d+\.\d+") {
        $result.Success = $true
    }

    return $result
}

$exitCodeToReturn = 1

try {
    $MirrorBase = $MirrorBase.TrimEnd("/")
    $PythonInstallMirror = $PythonInstallMirror.TrimEnd("/") + "/"
    $WorkDir = Join-Path $env:TEMP ("uv-cn-install-" + $RunStamp)
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

    Write-Log "uv China mirror installer started."
    Write-Log ("Log file: {0}" -f $script:LogFile)
    Write-Log ("Work dir: {0}" -f $WorkDir)
    Write-Log ("Install dir: {0}" -f $InstallDir)
    Write-Log ("Mirror base: {0}/" -f $MirrorBase)
    Write-Log ("PyPI default index: {0}" -f $DefaultIndex)
    Write-Log ("Python install mirror: {0}" -f $PythonInstallMirror)
    if (-not [string]::IsNullOrWhiteSpace($LocalZip)) {
        Write-Log ("Local ZIP override: {0}" -f $LocalZip)
    }
    Write-Log ("Processor architecture: {0}" -f $env:PROCESSOR_ARCHITECTURE)
    Write-Log ("Is 64-bit OS: {0}" -f [Environment]::Is64BitOperatingSystem)

    if (-not (Test-IsAdministrator)) {
        throw "This script must be run from an elevated PowerShell because it writes to Program Files, ProgramData, Machine PATH, and Machine environment variables."
    }
    Write-Log "Administrator check passed." "OK"

    $assetName = Get-UvAssetName
    $assetUrl = "{0}/{1}" -f $MirrorBase, $assetName
    $installerUrl = "{0}/uv-installer.ps1" -f $MirrorBase
    $uvExe = Join-Path $InstallDir "uv.exe"

    Set-MachineEnvironment -Name "UV_DOWNLOAD_URL" -Value ($MirrorBase + "/")
    Set-MachineEnvironment -Name "UV_PYTHON_INSTALL_MIRROR" -Value $PythonInstallMirror
    Set-MachineEnvironment -Name "UV_DEFAULT_INDEX" -Value $DefaultIndex
    Set-MachineEnvironment -Name "UV_INDEX_URL" -Value $DefaultIndex

    $env:UV_INSTALL_DIR = $InstallDir
    Write-Log ("Process environment set: UV_INSTALL_DIR={0}" -f $InstallDir) "OK"

    if (-not $SkipInstaller) {
        try {
            Write-Log "Trying official uv installer script from mirror."
            $installerPath = Join-Path $WorkDir "uv-installer.ps1"
            Invoke-DownloadFile -Uri $installerUrl -OutFile $installerPath
            $installExit = Invoke-NativeLogged -FilePath "powershell.exe" -Arguments @("-ExecutionPolicy", "Bypass", "-NoProfile", "-File", $installerPath)
            if ($installExit -eq 0 -and (Test-Path -LiteralPath $uvExe)) {
                Write-Log "Installer script completed and uv.exe exists." "OK"
            }
            else {
                Write-Log "Installer script did not produce uv.exe; manual fallback will run." "WARN"
            }
        }
        catch {
            Write-Log ("Installer script path failed: {0}" -f $_.Exception.Message) "WARN"
        }
    }
    else {
        Write-Log "Skipping installer script because -SkipInstaller was supplied." "WARN"
    }

    if (-not (Test-Path -LiteralPath $uvExe)) {
        Install-UvManually -WorkDir $WorkDir -AssetUrl $assetUrl -AssetName $assetName -TargetDir $InstallDir -LocalZip $LocalZip
    }

    Add-MachinePathEntry -PathEntry $InstallDir
    Write-UvConfig -IndexUrl $DefaultIndex

    $diagnosis = Test-UvInstall -TargetDir $InstallDir

    Write-Log "Final diagnosis:"
    foreach ($key in $diagnosis.Keys) {
        Write-Log ("{0}: {1}" -f $key, $diagnosis[$key]) "CMD"
    }

    if ($diagnosis.Success) {
        Write-Log "RESULT: SUCCESS. uv is installed and responds to uv --version." "OK"
        Write-Log "Open a new PowerShell window before relying on the updated Machine PATH." "INFO"
        $exitCodeToReturn = 0
    }
    else {
        Write-Log "RESULT: FAILED. uv.exe was not installed correctly or uv --version failed." "ERROR"
        $exitCodeToReturn = 1
    }
}
catch {
    Write-Log ("RESULT: FAILED. {0}" -f $_.Exception.Message) "ERROR"
    Write-Log ("Exception type: {0}" -f $_.Exception.GetType().FullName) "ERROR"
    $exitCodeToReturn = 1
}
finally {
    Write-Log ("Log saved to: {0}" -f $script:LogFile)
}

exit $exitCodeToReturn
