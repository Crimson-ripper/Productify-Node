; Installs/removes the Productify Node background service alongside the app.
; The installer runs per-machine (elevated), so the service can be registered here.

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Registering the Productify Node service..."
  ; Remove an older registration first (upgrade). Its result doesn't matter.
  nsExec::ExecToLog '"$INSTDIR\productify-agent.exe" uninstall'
  Pop $0
  nsExec::ExecToLog '"$INSTDIR\productify-agent.exe" install'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION|MB_OK "Productify Node was installed, but its background service couldn't be started (code $0). Restart your computer, or reinstall."
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Stopping the Productify Node service and removing renter jobs..."
  nsExec::ExecToLog '"$INSTDIR\productify-agent.exe" uninstall'
  Pop $0
!macroend
