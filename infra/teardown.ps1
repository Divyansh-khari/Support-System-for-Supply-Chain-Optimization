# Delete EVERYTHING this project created on Azure (stops all charges).
#
#   .\infra\teardown.ps1
#
# Deletes the whole resource group: registry, image, environment, apps, logs.
# Run deploy.ps1 again to recreate it all.

. "$PSScriptRoot\config.ps1"

$answer = Read-Host "Delete resource group '$RG' and everything in it? Type yes to confirm"
if ($answer -ne "yes") { Write-Host "Cancelled."; exit }

az group delete --name $RG --yes --no-wait
Write-Host "Deletion started; it finishes in the background in ~5-10 minutes."
Write-Host "Check with:  az group exists --name $RG   (prints false when gone)"