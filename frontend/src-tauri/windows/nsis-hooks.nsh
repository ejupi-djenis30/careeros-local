; The supported x64/ARM64 MSI stores its registration in the 64-bit HKCU
; registry view, while the NSIS engine uses the 32-bit view. MSI can also
; deliberately inherit the NSIS directory during migration, so refuse a full
; NSIS uninstall while Windows Installer still owns that shared payload.
Var CareerOSMsiInstallDir

!macro NSIS_HOOK_PREUNINSTALL
  SetRegView 64
  ClearErrors
  ReadRegStr $CareerOSMsiInstallDir HKCU "Software\careeros\CareerOS Local" "InstallDir"
  ${IfNot} ${Errors}
    ; Restore the NSIS registry view before leaving the generated section.
    SetRegView 32
    DetailPrint "ERROR: Windows Installer ownership detected; refusing to remove the shared payload."
    MessageBox MB_OK|MB_ICONSTOP "CareerOS Local is also registered with Windows Installer. Uninstall that MSI package first, then run this uninstaller again." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  SetRegView 32
!macroend

; Remove only NSIS-owned metadata from the 32-bit view. The MSI-owned values
; remain isolated in the 64-bit view, and the pre-hook above prevents payload
; deletion whenever that MSI registration exists.
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $UpdateMode <> 1
    SetRegView 32
    DeleteRegValue HKCU "Software\careeros\CareerOS Local" ""
    DeleteRegValue HKCU "Software\careeros\CareerOS Local" "Installer Language"
    DeleteRegKey /ifempty HKCU "Software\careeros\CareerOS Local"
    DeleteRegKey /ifempty HKCU "Software\careeros"
  ${EndIf}
!macroend
