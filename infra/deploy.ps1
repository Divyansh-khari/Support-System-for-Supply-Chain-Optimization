# Deploy both architectures to Azure Container Apps.
#
#   .\infra\deploy.ps1
#
# Safe to re-run: anything that already exists is reused, and the apps are
# updated to the image built from the current commit.
#
# What it creates (all inside one resource group):
#   - Azure Container Registry (Basic)         stores our Docker image
#   - Container Apps environment               shared network + Log Analytics
#   - scso-mono  1.5 CPU                       the monolith
#   - scso-api   0.5 CPU                       microservices gateway
#   - scso-opt   0.5 CPU                       optimization service
#   - scso-sim   0.5 CPU                       simulation service
# Same 1.5 CPU budget either way, as in docker-compose (fair Experiment A).
#
# Note: the student subscription gets an Azure Container Apps "express"
# environment, which has no plain-HTTP ingress and no app-to-app calls by
# name. So every app gets a public HTTPS address, and the gateway calls the
# optimizer and simulation through those addresses.

. "$PSScriptRoot\config.ps1"

function Step($what) { Write-Host "`n==> $what" -ForegroundColor Cyan }

# Run an az command; stop the script if it fails.
function Az-Must([scriptblock]$cmd, [string]$what) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "FAILED: $what" }
}

# True if an az 'show' command finds the resource.
function Az-Exists([scriptblock]$cmd) {
    & $cmd 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

Write-Host "Deploying image tag $TAG to resource group $RG ($LOCATION)" -ForegroundColor Green

# ---------------------------------------------------------------- 1. basics
Step "Registering resource providers (first time only; can take a few minutes)"
foreach ($ns in "Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.ContainerRegistry") {
    Az-Must { az provider register --namespace $ns --wait } "register $ns"
}

Step "Resource group $RG"
Az-Must { az group create --name $RG --location $LOCATION -o none } "create resource group"

# ---------------------------------------------------------------- 2. registry + image
Step "Container registry $ACR"
if (Az-Exists { az acr show --name $ACR --resource-group $RG }) {
    Write-Host "already exists"
} else {
    Az-Must { az acr create --resource-group $RG --name $ACR --sku Basic --admin-enabled true -o none } "create registry"
}

Step "Image $IMAGE"
$existingTags = az acr repository show-tags --name $ACR --repository $IMAGE_REPO -o tsv 2>$null
if ($existingTags -contains $TAG) {
    Write-Host "already in the registry, skipping build"
} else {
    # Preferred: build in the cloud (ACR Tasks), no local Docker needed.
    az acr build --registry $ACR --image "${IMAGE_REPO}:${TAG}" .
    if ($LASTEXITCODE -ne 0) {
        # Azure for Students blocks ACR Tasks. Fall back to Docker on this laptop.
        Write-Host "Cloud build not available; building with local Docker and pushing instead" -ForegroundColor Yellow
        Az-Must { az acr login --name $ACR } "registry login"
        Az-Must { docker build -t $IMAGE . } "docker build"
        Az-Must { docker push $IMAGE } "docker push"
    }
}

$ACR_USER = az acr credential show --name $ACR --query username -o tsv
$ACR_PASS = az acr credential show --name $ACR --query "passwords[0].value" -o tsv

# ---------------------------------------------------------------- 3. environment
Step "Container Apps environment $ENV_NAME (first time: ~3-5 minutes)"
if (Az-Exists { az containerapp env show --name $ENV_NAME --resource-group $RG }) {
    Write-Host "already exists"
} else {
    # A Log Analytics workspace is created automatically for the logs.
    Az-Must { az containerapp env create --name $ENV_NAME --resource-group $RG --location $LOCATION -o none } "create environment"
}

# ---------------------------------------------------------------- 4. apps
function Deploy-App($name, $cpu, $memory, [string[]]$envVars) {
    Step "App $name ($cpu CPU)"
    if (Az-Exists { az containerapp show --name $name --resource-group $RG }) {
        Az-Must { az containerapp update --name $name --resource-group $RG `
                    --image $IMAGE --set-env-vars $envVars -o none } "update $name"
    } else {
        Az-Must { az containerapp create --name $name --resource-group $RG `
                    --environment $ENV_NAME --image $IMAGE `
                    --registry-server "${ACR}.azurecr.io" `
                    --registry-username $ACR_USER --registry-password $ACR_PASS `
                    --ingress external --target-port 8000 `
                    --cpu $cpu --memory $memory `
                    --min-replicas 0 --max-replicas 1 `
                    --env-vars $envVars -o none } "create $name"
    }
}

function App-Url($name) {
    return "https://" + (az containerapp show --name $name --resource-group $RG `
                           --query properties.configuration.ingress.fqdn -o tsv)
}

# Downstream services first: the gateway needs their addresses.
Deploy-App $APP_OPT  0.5 "1.0Gi" @("SERVICE=optimizer")
Deploy-App $APP_SIM  0.5 "1.0Gi" @("SERVICE=simulation")
$OPT_URL = App-Url $APP_OPT
$SIM_URL = App-Url $APP_SIM
Deploy-App $APP_API  0.5 "1.0Gi" @("SERVICE=api", "MODE=microservices",
                                   "OPTIMIZER_URL=$OPT_URL",
                                   "SIMULATION_URL=$SIM_URL")
Deploy-App $APP_MONO 1.5 "3.0Gi" @("SERVICE=api", "MODE=monolith")

# ---------------------------------------------------------------- 5. where to find it
$monoUrl = App-Url $APP_MONO
$apiUrl  = App-Url $APP_API

Write-Host "`nDone. Image: $IMAGE" -ForegroundColor Green
Write-Host "Monolith       : $monoUrl"
Write-Host "Microservices  : $apiUrl"
Write-Host "`nTry:  python scripts\try_api.py $monoUrl"
Write-Host "Apps scale to zero when idle; the first request after a pause takes ~10-30 s."