# Shared settings for every infra script.
# Load into the current terminal with:   . .\infra\config.ps1

$RG         = "rg-scso"                 # resource group: one folder holding everything
$LOCATION   = "eastasia"                # Azure region (allowed by the student subscription policy and supports Container Apps)
$ACR        = "scso2026jtm2029"         # container registry; globally unique, lowercase letters/digits only
$ENV_NAME   = "scso-env"                # Container Apps environment (shared network + logs)
$IMAGE_REPO = "scso-app"

# Tag each image with the current git commit, so every deployed image
# can be traced back to the exact code that produced it.
$TAG   = (git rev-parse --short HEAD)
$IMAGE = "${ACR}.azurecr.io/${IMAGE_REPO}:${TAG}"

# App names (lowercase, start with a letter)
$APP_MONO = "scso-mono"    # monolith: everything in one container, 1.5 CPU
$APP_API  = "scso-api"     # microservices gateway, 0.5 CPU
$APP_OPT  = "scso-opt"     # optimization service, 0.5 CPU, internal only
$APP_SIM  = "scso-sim"     # simulation service, 0.5 CPU, internal only