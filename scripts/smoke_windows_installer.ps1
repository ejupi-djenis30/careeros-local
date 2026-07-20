[CmdletBinding()]
param(
    [string]$Target = "x86_64-pc-windows-msvc",
    [switch]$IncludeNsisInstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BundleRoot = Join-Path $ProjectRoot "frontend\src-tauri\target\$Target\release\bundle"
$ArtifactsRoot = Join-Path $ProjectRoot ".artifacts"
$SmokeRoot = Join-Path $ArtifactsRoot "i"
$ExtractRoot = Join-Path $SmokeRoot "x"
$MsiLog = Join-Path $SmokeRoot "msiexec.log"
$Succeeded = $false
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

New-Item -ItemType Directory -Path $ArtifactsRoot -Force | Out-Null
$ResolvedArtifacts = [IO.Path]::GetFullPath($ArtifactsRoot)
$ResolvedSmoke = [IO.Path]::GetFullPath($SmokeRoot)
if (-not $ResolvedSmoke.StartsWith(
        $ResolvedArtifacts + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
    throw "Unsafe installer smoke directory: $ResolvedSmoke"
}

function Remove-SmokeTree {
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        if (-not (Test-Path -LiteralPath $SmokeRoot)) { return }
        try {
            Remove-Item -LiteralPath $SmokeRoot -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            if ($Attempt -eq 20) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
}

function Get-OnlyFile([string]$Directory, [string]$Filter) {
    $Matches = @(Get-ChildItem -LiteralPath $Directory -Recurse -Filter $Filter)
    if ($Matches.Count -ne 1) {
        throw "Expected exactly one $Filter under $Directory; found $($Matches.Count)"
    }
    return $Matches[0]
}

function Invoke-NativeSmoke(
    [string]$Application,
    [string]$DataDirectory,
    [switch]$Offline
) {
    New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
    $env:CAREEROS_DESKTOP_SMOKE = "1"
    $env:CAREEROS_DESKTOP_SMOKE_DATA_DIR = $DataDirectory
    if ($Offline) { $env:OFFLINE_MODE = "true" }
    else { Remove-Item Env:OFFLINE_MODE -ErrorAction SilentlyContinue }
    $Process = Start-Process -FilePath $Application -PassThru
    $Deadline = [DateTime]::UtcNow.AddSeconds(120)
    $SawWindow = $false
    try {
        while ([DateTime]::UtcNow -lt $Deadline) {
            Start-Sleep -Milliseconds 200
            $Process.Refresh()
            $SawWindow = $SawWindow -or $Process.MainWindowHandle -ne 0
            if ($Process.HasExited) { break }
        }
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
            throw "Packaged desktop smoke timed out"
        }
        if ($Process.ExitCode -ne 0) {
            throw "Packaged desktop smoke exited with code $($Process.ExitCode)"
        }
        if (-not $SawWindow) {
            throw "Packaged desktop smoke never created a native window"
        }
        $Database = Join-Path $DataDirectory "vault\careeros.db"
        if (-not (Test-Path -LiteralPath $Database) -or (Get-Item $Database).Length -eq 0) {
            throw "Packaged desktop smoke did not initialize the career vault"
        }
        $Orphans = @(Get-CimInstance Win32_Process -Filter "Name = 'careeros-backend.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine.Contains($DataDirectory) })
        if ($Orphans.Count -ne 0) {
            throw "Packaged sidecar remained orphaned after native app exit"
        }
        return [pscustomobject]@{
            appExitCode = $Process.ExitCode
            databaseBytes = (Get-Item $Database).Length
            sidecarOrphaned = $false
        }
    }
    finally {
        Remove-Item Env:OFFLINE_MODE -ErrorAction SilentlyContinue
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-ReopenSmoke([string]$Application, [string]$DataDirectory) {
    $First = Invoke-NativeSmoke $Application $DataDirectory
    $Marker = Join-Path $DataDirectory "vault\smoke-preserve.marker"
    $MarkerValue = "careeros-vault-preservation-v1"
    Set-Content -LiteralPath $Marker -Value $MarkerValue -NoNewline -Encoding utf8
    $Second = Invoke-NativeSmoke $Application $DataDirectory -Offline
    if (-not (Test-Path -LiteralPath $Marker) -or
        (Get-Content -LiteralPath $Marker -Raw) -ne $MarkerValue) {
        throw "Offline reopen did not preserve the existing user vault marker"
    }
    return [pscustomobject]@{
        initial = $First
        offlineReopen = $Second
        vaultMarkerPreserved = $true
    }
}

function Invoke-ExportSmoke([string]$Backend, [string]$DataDirectory) {
    $Output = & $Python (Join-Path $ProjectRoot "scripts\smoke_packaged_backend.py") `
        --binary $Backend --data-dir $DataDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged backend export smoke failed with code $LASTEXITCODE"
    }
    return $Output | ConvertFrom-Json
}

function Assert-PackagedLicense([string]$PackageRoot) {
    $Output = & $Python (Join-Path $ProjectRoot "scripts\license_contract.py") `
        --package-root $PackageRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged project license verification failed with code $LASTEXITCODE"
    }
    return $Output | ConvertFrom-Json
}

try {
    if (Test-Path -LiteralPath $SmokeRoot) { Remove-SmokeTree }
    New-Item -ItemType Directory -Path $ExtractRoot -Force | Out-Null

    $Msi = Get-OnlyFile (Join-Path $BundleRoot "msi") "*.msi"
    $Arguments = "/a `"$($Msi.FullName)`" /qn TARGETDIR=`"$ExtractRoot`" /l*v `"$MsiLog`""
    $Installer = Start-Process `
        -FilePath "$env:SystemRoot\System32\msiexec.exe" `
        -ArgumentList $Arguments `
        -Wait `
        -PassThru `
        -WindowStyle Hidden
    if ($Installer.ExitCode -ne 0) {
        throw "MSI administrative extraction failed with code $($Installer.ExitCode)"
    }
    $MsiApp = Get-OnlyFile $ExtractRoot "careeros-local.exe"
    $MsiBackend = Get-OnlyFile $ExtractRoot "careeros-backend.exe"
    $MsiLicense = Assert-PackagedLicense ($MsiApp.Directory.FullName)
    $MsiData = Join-Path $SmokeRoot "data-msi"
    $MsiExport = Invoke-ExportSmoke $MsiBackend.FullName $MsiData
    $MsiResult = Invoke-ReopenSmoke $MsiApp.FullName $MsiData

    $NsisResult = $null
    $NsisLicense = $null
    if ($IncludeNsisInstall) {
        $Nsis = Get-OnlyFile (Join-Path $BundleRoot "nsis") "*.exe"
        $InstallRoot = Join-Path $SmokeRoot "n"
        $NsisInstall = Start-Process `
            -FilePath $Nsis.FullName `
            -ArgumentList @("/S", "/D=$InstallRoot") `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($NsisInstall.ExitCode -ne 0) {
            throw "NSIS silent installation failed with code $($NsisInstall.ExitCode)"
        }
        $NsisApp = Get-OnlyFile $InstallRoot "careeros-local.exe"
        $NsisBackend = Get-OnlyFile $InstallRoot "careeros-backend.exe"
        $NsisLicense = Assert-PackagedLicense ($NsisApp.Directory.FullName)
        $NsisData = Join-Path $SmokeRoot "data-nsis"
        $NsisExport = Invoke-ExportSmoke $NsisBackend.FullName $NsisData
        $NsisResult = Invoke-ReopenSmoke $NsisApp.FullName $NsisData
        $Uninstaller = Get-OnlyFile $InstallRoot "uninstall*.exe"
        $NsisUninstall = Start-Process `
            -FilePath $Uninstaller.FullName `
            -ArgumentList "/S" `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($NsisUninstall.ExitCode -ne 0) {
            throw "NSIS silent uninstall failed with code $($NsisUninstall.ExitCode)"
        }
        if (Test-Path -LiteralPath $NsisApp.FullName) {
            throw "NSIS uninstall left the application executable installed"
        }
        if (-not (Test-Path -LiteralPath (Join-Path $NsisData "vault\careeros.db"))) {
            throw "NSIS uninstall unexpectedly erased the user-owned vault"
        }
        if (-not (Test-Path -LiteralPath (Join-Path $NsisData "vault\smoke-preserve.marker"))) {
            throw "NSIS uninstall unexpectedly erased the vault preservation marker"
        }
    }

    $Succeeded = $true
    [pscustomobject]@{
        result = "pass"
        target = $Target
        msiBytes = $Msi.Length
        msiExports = $MsiExport
        msiLicense = $MsiLicense
        msi = $MsiResult
        nsisInstalledAndUninstalled = $IncludeNsisInstall.IsPresent
        nsisExports = $NsisExport
        nsisLicense = $NsisLicense
        nsis = $NsisResult
    } | ConvertTo-Json -Compress -Depth 4
}
finally {
    Remove-Item Env:CAREEROS_DESKTOP_SMOKE -ErrorAction SilentlyContinue
    Remove-Item Env:CAREEROS_DESKTOP_SMOKE_DATA_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:OFFLINE_MODE -ErrorAction SilentlyContinue
    if ($Succeeded -and (Test-Path -LiteralPath $SmokeRoot)) { Remove-SmokeTree }
}
