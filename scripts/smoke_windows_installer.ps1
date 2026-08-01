[CmdletBinding()]
param(
    [ValidateSet("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")]
    [string]$Target = "x86_64-pc-windows-msvc",
    [switch]$IncludeNsisInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BundleRoot = Join-Path $ProjectRoot "frontend\src-tauri\target\$Target\release\bundle"
$ArtifactsRoot = Join-Path $ProjectRoot ".artifacts"
$SmokeRoot = Join-Path $ArtifactsRoot "i"
$ExtractRoot = Join-Path $SmokeRoot "x"
$MsiLog = Join-Path $SmokeRoot "msiexec.log"
$Succeeded = $false
$NsisInstallRoot = $null
$NsisUninstaller = $null
$NsisUninstallCompleted = $false
$InjectedMsiRegistryValues = $false
$InstallerRegistrySubKey = "Software\careeros\CareerOS Local"
$ManufacturerRegistrySubKey = "Software\careeros"
$MsiRegistryValueNames = @(
    "InstallDir",
    "Desktop Shortcut",
    "Uninstaller Shortcut",
    "Start Menu Shortcut"
)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

function Assert-RegularDirectory([string]$Directory, [string]$Label) {
    $Item = Get-Item -LiteralPath $Directory -Force -ErrorAction Stop
    if (-not $Item.PSIsContainer -or
        ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "$Label must be a regular directory: $Directory"
    }
}

if (Test-Path -LiteralPath $ArtifactsRoot) {
    Assert-RegularDirectory $ArtifactsRoot "Installer artifact root"
}
New-Item -ItemType Directory -Path $ArtifactsRoot -Force | Out-Null
Assert-RegularDirectory $ArtifactsRoot "Installer artifact root"
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
        Assert-RegularDirectory $SmokeRoot "Installer smoke root"
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
    $Matches = @(Get-ChildItem -LiteralPath $Directory -Recurse -Filter $Filter |
        Where-Object {
            -not $_.PSIsContainer -and
            -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)
        })
    if ($Matches.Count -ne 1) {
        throw "Expected exactly one $Filter under $Directory; found $($Matches.Count)"
    }
    return $Matches[0]
}

function Get-PackagedSidecars([string]$DataDirectory) {
    return @(Get-CimInstance Win32_Process -Filter "Name = 'careeros-backend.exe'" |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.IndexOf(
                $DataDirectory,
                [StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        })
}

function Wait-PackagedSidecarExit([string]$DataDirectory) {
    $Deadline = [DateTime]::UtcNow.AddSeconds(35)
    do {
        $Sidecars = @(Get-PackagedSidecars $DataDirectory)
        if ($Sidecars.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw "Packaged sidecar did not exit within the bounded cleanup window"
}

function Wait-NsisInstallationRemoved([string]$InstallationRoot) {
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if (-not (Test-Path -LiteralPath $InstallationRoot)) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw "NSIS uninstall left its installation root behind: $InstallationRoot"
}

function Open-InstallerRegistryKey(
    [Microsoft.Win32.RegistryView]$View,
    [bool]$Writable,
    [bool]$Create
) {
    $BaseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::CurrentUser,
        $View
    )
    try {
        if ($Create) {
            return $BaseKey.CreateSubKey($InstallerRegistrySubKey, $Writable)
        }
        return $BaseKey.OpenSubKey($InstallerRegistrySubKey, $Writable)
    }
    finally {
        $BaseKey.Dispose()
    }
}

function Assert-NsisLocationMetadataRemoved {
    $Key = Open-InstallerRegistryKey `
        ([Microsoft.Win32.RegistryView]::Registry32) $false $false
    if ($null -eq $Key) { return }
    try {
        if ($Key.GetValueNames() -contains "" -or
            $Key.GetValueNames() -contains "Installer Language") {
            throw "NSIS uninstall left installer location metadata"
        }
    }
    finally {
        $Key.Dispose()
    }
}

function Assert-NoExistingInstallerRegistration {
    foreach ($View in @(
            [Microsoft.Win32.RegistryView]::Registry32,
            [Microsoft.Win32.RegistryView]::Registry64
        )) {
        $Key = Open-InstallerRegistryKey $View $false $false
        if ($null -eq $Key) { continue }
        try {
            throw "Installer smoke refuses to overwrite an existing CareerOS registration in $View"
        }
        finally {
            $Key.Dispose()
        }
    }
}

function Add-SmokeMsiRegistration([string]$InstallDirectory) {
    Assert-NoMsiRegistration
    $Key = Open-InstallerRegistryKey `
        ([Microsoft.Win32.RegistryView]::Registry64) $true $true
    $script:InjectedMsiRegistryValues = $true
    try {
        $Key.SetValue(
            "InstallDir",
            $InstallDirectory,
            [Microsoft.Win32.RegistryValueKind]::String
        )
        foreach ($Name in $MsiRegistryValueNames | Where-Object { $_ -ne "InstallDir" }) {
            $Key.SetValue($Name, 1, [Microsoft.Win32.RegistryValueKind]::DWord)
        }
    }
    finally {
        $Key.Dispose()
    }
}

function Assert-NoMsiRegistration {
    $Key = Open-InstallerRegistryKey `
        ([Microsoft.Win32.RegistryView]::Registry64) $false $false
    if ($null -eq $Key) { return }
    try {
        $Present = @($Key.GetValueNames() | Where-Object { $_ -in $MsiRegistryValueNames })
        if ($Present.Count -gt 0) {
            throw "Installer smoke found an existing MSI registration: $($Present -join ', ')"
        }
    }
    finally {
        $Key.Dispose()
    }
}

function Assert-SmokeMsiRegistration([string]$InstallDirectory) {
    $Key = Open-InstallerRegistryKey `
        ([Microsoft.Win32.RegistryView]::Registry64) $false $false
    if ($null -eq $Key) { throw "Blocked NSIS uninstall removed the MSI registry key" }
    try {
        if ($Key.GetValue("InstallDir") -ne $InstallDirectory) {
            throw "Blocked NSIS uninstall did not preserve the MSI InstallDir"
        }
        foreach ($Name in $MsiRegistryValueNames | Where-Object { $_ -ne "InstallDir" }) {
            if ($Key.GetValue($Name) -ne 1) {
                throw "Blocked NSIS uninstall did not preserve MSI value: $Name"
            }
        }
    }
    finally {
        $Key.Dispose()
    }
}

function Remove-SmokeMsiRegistration {
    if (-not $script:InjectedMsiRegistryValues) { return }
    $BaseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::CurrentUser,
        [Microsoft.Win32.RegistryView]::Registry64
    )
    try {
        $Key = $BaseKey.OpenSubKey($InstallerRegistrySubKey, $true)
        if ($null -ne $Key) {
            try {
                foreach ($Name in $MsiRegistryValueNames) {
                    $Key.DeleteValue($Name, $false)
                }
            }
            finally {
                $Key.Dispose()
            }
        }
        $ProductKey = $BaseKey.OpenSubKey($InstallerRegistrySubKey, $false)
        if ($null -ne $ProductKey) {
            try {
                $ProductKeyIsEmpty = (
                    $ProductKey.GetValueNames().Count -eq 0 -and
                    $ProductKey.GetSubKeyNames().Count -eq 0
                )
            }
            finally {
                $ProductKey.Dispose()
            }
            if ($ProductKeyIsEmpty) {
                $BaseKey.DeleteSubKey($InstallerRegistrySubKey, $false)
            }
        }
        $ManufacturerKey = $BaseKey.OpenSubKey($ManufacturerRegistrySubKey, $false)
        if ($null -ne $ManufacturerKey) {
            try {
                $ManufacturerKeyIsEmpty = (
                    $ManufacturerKey.GetValueNames().Count -eq 0 -and
                    $ManufacturerKey.GetSubKeyNames().Count -eq 0
                )
            }
            finally {
                $ManufacturerKey.Dispose()
            }
            if ($ManufacturerKeyIsEmpty) {
                $BaseKey.DeleteSubKey($ManufacturerRegistrySubKey, $false)
            }
        }
        $script:InjectedMsiRegistryValues = $false
    }
    finally {
        $BaseKey.Dispose()
    }
}

function Assert-NsisRegistryCoexistenceOrdering([string]$Template) {
    if (-not (Test-Path -LiteralPath $Template -PathType Leaf)) {
        throw "Generated NSIS template is missing: $Template"
    }
    $Source = Get-Content -Raw -LiteralPath $Template -ErrorAction Stop
    $PreHook = $Source.IndexOf(
        '!insertmacro NSIS_HOOK_PREUNINSTALL',
        [StringComparison]::Ordinal
    )
    $SharedKeyDelete = $Source.IndexOf(
        'DeleteRegKey SHCTX "${MANUPRODUCTKEY}"',
        [StringComparison]::Ordinal
    )
    $PostHook = $Source.IndexOf(
        '!insertmacro NSIS_HOOK_POSTUNINSTALL',
        [StringComparison]::Ordinal
    )
    if ($PreHook -lt 0 -or $SharedKeyDelete -lt 0 -or $PostHook -lt 0 -or
        -not ($PreHook -lt $SharedKeyDelete -and $SharedKeyDelete -lt $PostHook)) {
        throw "Generated NSIS template no longer preserves the reviewed MSI coexistence order"
    }
}

function Invoke-NativeSmoke(
    [string]$Application,
    [string]$DataDirectory,
    [switch]$Offline
) {
    if (Test-Path -LiteralPath $DataDirectory) {
        Assert-RegularDirectory $DataDirectory "Installer smoke data root"
    }
    else {
        New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
        Assert-RegularDirectory $DataDirectory "Installer smoke data root"
    }
    $ReadinessEvidence = Join-Path $DataDirectory ".careeros-desktop-ready-v1"
    if (Test-Path -LiteralPath $ReadinessEvidence) {
        Remove-Item -LiteralPath $ReadinessEvidence -Force -ErrorAction Stop
    }
    if (Test-Path -LiteralPath $ReadinessEvidence) {
        throw "Could not clear stale desktop readiness evidence"
    }
    $env:CAREEROS_DESKTOP_SMOKE = "1"
    $env:CAREEROS_DESKTOP_SMOKE_DATA_DIR = $DataDirectory
    if ($Offline) { $env:OFFLINE_MODE = "true" }
    else { Remove-Item Env:OFFLINE_MODE -ErrorAction SilentlyContinue }
    $Process = $null
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
        if ($null -ne $Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
            throw "Packaged desktop smoke timed out"
        }
        if ($Process.ExitCode -ne 0) {
            throw "Packaged desktop smoke exited with code $($Process.ExitCode)"
        }
        if (-not $SawWindow) {
            throw "Packaged desktop smoke never created a native window"
        }
        if (-not (Test-Path -LiteralPath $ReadinessEvidence -PathType Leaf) -or
            (Get-Content -LiteralPath $ReadinessEvidence -Raw) -ne "backend-ready+frontend-committed`n") {
            throw "Packaged desktop smoke did not complete the frontend/backend readiness handshake"
        }
        $Database = Join-Path $DataDirectory "vault\careeros.db"
        if (-not (Test-Path -LiteralPath $Database) -or (Get-Item $Database).Length -eq 0) {
            throw "Packaged desktop smoke did not initialize the career vault"
        }
        return [pscustomobject]@{
            appExitCode = $Process.ExitCode
            databaseBytes = (Get-Item $Database).Length
            readinessEvidence = (Split-Path -Leaf $ReadinessEvidence)
            sidecarOrphaned = $false
        }
    }
    finally {
        Remove-Item Env:OFFLINE_MODE -ErrorAction SilentlyContinue
        if ($null -ne $Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            if (-not $Process.WaitForExit(10000)) {
                throw "Packaged desktop process did not exit after forced cleanup"
            }
        }
        Wait-PackagedSidecarExit $DataDirectory
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

function Assert-PackagedNotices([string]$PackageRoot) {
    $Output = & $Python (Join-Path $ProjectRoot "scripts\third_party_notices.py") `
        --package-root $PackageRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged third-party notice verification failed with code $LASTEXITCODE"
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
    $MsiNotices = Assert-PackagedNotices ($MsiApp.Directory.FullName)
    $MsiData = Join-Path $SmokeRoot "data-msi"
    $MsiExport = Invoke-ExportSmoke $MsiBackend.FullName $MsiData
    $MsiResult = Invoke-ReopenSmoke $MsiApp.FullName $MsiData

    $NsisResult = $null
    $NsisExport = $null
    $NsisLicense = $null
    $NsisNotices = $null
    if ($IncludeNsisInstall) {
        $Nsis = Get-OnlyFile (Join-Path $BundleRoot "nsis") "*.exe"
        $NsisArchitecture = if ($Target -eq "x86_64-pc-windows-msvc") { "x64" } else { "arm64" }
        $NsisTemplate = Join-Path `
            (Split-Path -Parent $BundleRoot) `
            "nsis\$NsisArchitecture\installer.nsi"
        Assert-NsisRegistryCoexistenceOrdering $NsisTemplate
        Assert-NoExistingInstallerRegistration
        $InstallRoot = Join-Path $SmokeRoot "n"
        # Record the bounded destination before launching NSIS so the outer
        # finally block can roll back an installation that writes its
        # uninstaller and then exits non-zero.
        $NsisInstallRoot = $InstallRoot
        $NsisInstall = Start-Process `
            -FilePath $Nsis.FullName `
            -ArgumentList @("/S", "/D=$InstallRoot") `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($NsisInstall.ExitCode -ne 0) {
            throw "NSIS silent installation failed with code $($NsisInstall.ExitCode)"
        }
        $NsisUninstaller = Get-OnlyFile $InstallRoot "uninstall*.exe"
        $NsisApp = Get-OnlyFile $InstallRoot "careeros-local.exe"
        $NsisBackend = Get-OnlyFile $InstallRoot "careeros-backend.exe"
        $NsisLicense = Assert-PackagedLicense ($NsisApp.Directory.FullName)
        $NsisNotices = Assert-PackagedNotices ($NsisApp.Directory.FullName)
        $NsisData = Join-Path $SmokeRoot "data-nsis"
        $NsisExport = Invoke-ExportSmoke $NsisBackend.FullName $NsisData
        $NsisResult = Invoke-ReopenSmoke $NsisApp.FullName $NsisData

        # Reproduce the supported cross-installer boundary: MSI can inherit
        # this exact directory. NSIS must fail closed without deleting any
        # shared payload or MSI-owned registration.
        Add-SmokeMsiRegistration $InstallRoot
        # Run the real uninstaller in place so its fail-closed exit code is
        # observable; the default NSIS bootstrapper returns before its
        # temporary child and masks that child's error level.
        $BlockedNsisUninstall = Start-Process `
            -FilePath $NsisUninstaller.FullName `
            -ArgumentList @("/S", "_?=$InstallRoot") `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($BlockedNsisUninstall.ExitCode -eq 0) {
            throw "NSIS uninstall did not reject a coexisting MSI registration"
        }
        Assert-SmokeMsiRegistration $InstallRoot
        foreach ($RequiredPayload in @($NsisApp.FullName, $NsisBackend.FullName, $NsisUninstaller.FullName)) {
            if (-not (Test-Path -LiteralPath $RequiredPayload -PathType Leaf)) {
                throw "Blocked NSIS uninstall removed MSI-owned payload: $RequiredPayload"
            }
        }

        $BlockedNsisUpdate = Start-Process `
            -FilePath $NsisUninstaller.FullName `
            -ArgumentList @("/S", "/UPDATE", "_?=$InstallRoot") `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($BlockedNsisUpdate.ExitCode -eq 0) {
            throw "NSIS update uninstall did not reject a coexisting MSI registration"
        }
        Assert-SmokeMsiRegistration $InstallRoot
        foreach ($RequiredPayload in @($NsisApp.FullName, $NsisBackend.FullName, $NsisUninstaller.FullName)) {
            if (-not (Test-Path -LiteralPath $RequiredPayload -PathType Leaf)) {
                throw "Blocked NSIS update uninstall removed MSI-owned payload: $RequiredPayload"
            }
        }
        Remove-SmokeMsiRegistration

        $NsisUninstall = Start-Process `
            -FilePath $NsisUninstaller.FullName `
            -ArgumentList "/S" `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($NsisUninstall.ExitCode -ne 0) {
            throw "NSIS silent uninstall failed with code $($NsisUninstall.ExitCode)"
        }
        Wait-NsisInstallationRemoved $InstallRoot
        Assert-NsisLocationMetadataRemoved
        if (-not (Test-Path -LiteralPath (Join-Path $NsisData "vault\careeros.db"))) {
            throw "NSIS uninstall unexpectedly erased the user-owned vault"
        }
        if (-not (Test-Path -LiteralPath (Join-Path $NsisData "vault\smoke-preserve.marker"))) {
            throw "NSIS uninstall unexpectedly erased the vault preservation marker"
        }
        $NsisUninstallCompleted = $true
    }

    $Succeeded = $true
    [pscustomobject]@{
        result = "pass"
        target = $Target
        msiBytes = $Msi.Length
        msiExports = $MsiExport
        msiLicense = $MsiLicense
        msiNotices = $MsiNotices
        msi = $MsiResult
        nsisInstalledAndUninstalled = $IncludeNsisInstall.IsPresent
        nsisExports = $NsisExport
        nsisLicense = $NsisLicense
        nsisNotices = $NsisNotices
        nsis = $NsisResult
    } | ConvertTo-Json -Compress -Depth 4
}
finally {
    Remove-Item Env:CAREEROS_DESKTOP_SMOKE -ErrorAction SilentlyContinue
    Remove-Item Env:CAREEROS_DESKTOP_SMOKE_DATA_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:OFFLINE_MODE -ErrorAction SilentlyContinue
    Remove-SmokeMsiRegistration
    if ($null -ne $NsisInstallRoot -and -not $NsisUninstallCompleted) {
        if ($null -eq $NsisUninstaller -or
            -not (Test-Path -LiteralPath $NsisUninstaller.FullName -PathType Leaf)) {
            $PartialUninstallers = @()
            if (Test-Path -LiteralPath $NsisInstallRoot -PathType Container) {
                Assert-RegularDirectory $NsisInstallRoot "NSIS installation root"
                $PartialUninstallers = @(Get-ChildItem `
                        -LiteralPath $NsisInstallRoot `
                        -Recurse `
                        -Filter "uninstall*.exe" |
                    Where-Object {
                        -not $_.PSIsContainer -and
                        -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)
                    })
            }
            if ($PartialUninstallers.Count -gt 1) {
                throw "Expected at most one partial NSIS uninstaller; found $($PartialUninstallers.Count)"
            }
            if ($PartialUninstallers.Count -eq 1) {
                $NsisUninstaller = $PartialUninstallers[0]
            }
        }
        if ($null -ne $NsisUninstaller) {
            $NsisFailureCleanup = Start-Process `
                -FilePath $NsisUninstaller.FullName `
                -ArgumentList "/S" `
                -Wait `
                -PassThru `
                -WindowStyle Hidden
            if ($NsisFailureCleanup.ExitCode -ne 0) {
                throw "NSIS failure cleanup failed with code $($NsisFailureCleanup.ExitCode)"
            }
            Wait-NsisInstallationRemoved $NsisInstallRoot
            Assert-NsisLocationMetadataRemoved
            $NsisUninstallCompleted = $true
        }
    }
    if ($Succeeded -and (Test-Path -LiteralPath $SmokeRoot)) { Remove-SmokeTree }
}
