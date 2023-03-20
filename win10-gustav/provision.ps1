# Powershell script to execute when a new Windows VM is set up. 

Write-Output "[*] Initializing Provision Script..."

$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
$DefaultUsername = "your username"
$DefaultPassword = "your password"
Set-ItemProperty $RegPath "AutoAdminLogon" -Value "1" -type String 
Set-ItemProperty $RegPath "DefaultUsername" -Value "vagrant" -type String 
Set-ItemProperty $RegPath "DefaultPassword" -Value "vagrant" -type String

Write-Output "[*] Autologon Configured"

powercfg.exe /SETACVALUEINDEX SCHEME_CURRENT SUB_VIDEO VIDEOCONLOCK 3600
powercfg.exe /SETACTIVE SCHEME_CURRENT

powercfg.exe /SETDCVALUEINDEX SCHEME_CURRENT SUB_VIDEO VIDEOCONLOCK 3600
powercfg.exe /SETACTIVE SCHEME_CURRENT

Write-Output "[*] Screen Timeout extended"

cd C:\Users\vagrant\vagrant_data
Set-ExecutionPolicy Unrestricted -Force

# Install PsExec with Choco 
$choco_command = Get-Command choco
if(-Not $choco_command) {
  iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
}
choco install -y psexec

# Attempt to disable the firewall and WinDefend
netsh advfirewall set allprofiles state off
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
Unblock-File disable-defender.ps1
.\disable-defender.ps1

# Launch Meterpreter at start up
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\vagrant\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\meterpreter-0.lnk")
$Shortcut.TargetPath = "C:\Users\vagrant\vagrant_data\meterpreter-0.exe"
$Shortcut.Save()