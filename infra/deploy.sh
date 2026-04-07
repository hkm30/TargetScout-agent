#!/usr/bin/env bash
# infra/deploy.sh — Build, push, and deploy to Azure Container Apps
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load deployment configuration
source "$SCRIPT_DIR/deploy-config.sh"

# ============================================================
# Pre-push checks
# ============================================================
echo ">>> Pre-push checks..."

# 1. Verify correct subscription
CURRENT_SUB=$(az account show --query name -o tsv 2>/dev/null || true)
if [[ "$CURRENT_SUB" != "$AZURE_SUBSCRIPTION" ]]; then
  echo "    Subscription mismatch: current='$CURRENT_SUB', expected='$AZURE_SUBSCRIPTION'"
  echo "    Switching subscription..."
  az account set --subscription "$AZURE_SUBSCRIPTION"
  CURRENT_SUB=$(az account show --query name -o tsv)
fi
echo "    Subscription: $CURRENT_SUB  ✓"

# 2. Verify subscription is enabled
SUB_STATE=$(az account show --query state -o tsv)
if [[ "$SUB_STATE" != "Enabled" ]]; then
  echo "    ERROR: Subscription state is '$SUB_STATE', not 'Enabled'. Aborting."
  exit 1
fi
echo "    Subscription state: $SUB_STATE  ✓"

# 3. Verify resource group exists
if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
  echo "    ERROR: Resource group '$RESOURCE_GROUP' not found. Aborting."
  exit 1
fi
echo "    Resource group: $RESOURCE_GROUP  ✓"

# 4. Verify ACR exists and is accessible
if ! az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
  echo "    ERROR: ACR '$ACR_NAME' not found in '$RESOURCE_GROUP'. Aborting."
  exit 1
fi
echo "    ACR: $ACR_LOGIN_SERVER  ✓"

# 5. Verify Docker daemon is running
if ! docker info &>/dev/null; then
  echo "    ERROR: Docker daemon is not running. Start Docker Desktop and retry."
  exit 1
fi
echo "    Docker daemon: running  ✓"

# 6. Verify container apps exist
for APP in "$BACKEND_APP_NAME" "$FRONTEND_APP_NAME"; do
  if ! az containerapp show --name "$APP" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo "    ERROR: Container App '$APP' not found. Run initial provisioning first."
    exit 1
  fi
done
echo "    Container Apps: $BACKEND_APP_NAME, $FRONTEND_APP_NAME  ✓"

echo ">>> All checks passed."
echo ""

# ============================================================
# Build and push
# ============================================================
TAG="${1:-$(git -C "$PROJECT_DIR" rev-parse --short HEAD)}"
echo ">>> Image tag: $TAG"

az acr login --name "$ACR_NAME"

echo ">>> Building backend image..."
docker build -t "$BACKEND_IMAGE:$TAG" "$PROJECT_DIR/backend"
docker push "$BACKEND_IMAGE:$TAG"
echo "    Pushed: $BACKEND_IMAGE:$TAG  ✓"

echo ">>> Building frontend image..."
docker build -t "$FRONTEND_IMAGE:$TAG" "$PROJECT_DIR/frontend"
docker push "$FRONTEND_IMAGE:$TAG"
echo "    Pushed: $FRONTEND_IMAGE:$TAG  ✓"

# ============================================================
# Deploy (update existing container apps)
# ============================================================
echo ">>> Updating backend container app..."
az containerapp update \
  --name "$BACKEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$BACKEND_IMAGE:$TAG"

echo ">>> Updating frontend container app..."
az containerapp update \
  --name "$FRONTEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$FRONTEND_IMAGE:$TAG"

FRONTEND_URL=$(az containerapp show \
  --name "$FRONTEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo ""
echo "=== Deployment Complete ==="
echo "Frontend: https://$FRONTEND_URL"
