#!/usr/bin/env bash
# infra/provision.sh — Provision all Azure resources for Drug Target Decision Support Agent
set -euo pipefail

# === Configuration ===
SUBSCRIPTION="ME-MngEnv894848-kangminghe-2"
RESOURCE_GROUP="rg-drug-target-agent"
AI_REGION="eastus2"
OTHER_REGION="southeastasia"
PROJECT_PREFIX="drugtarget"
AI_RESOURCE_NAME="${PROJECT_PREFIX}-foundry-v2"
PROJECT_NAME="${PROJECT_PREFIX}-project"

az account set --subscription "$SUBSCRIPTION"

# === Resource Group ===
az group create --name "$RESOURCE_GROUP" --location "$OTHER_REGION"

# === AI Foundry AIServices Resource (East US 2) ===
# Create AIServices resource with allowProjectManagement and managed identity via REST API.
# This replaces the old Hub/Project pattern — Projects are created directly under AIServices.
SUB_ID=$(az account show --query id -o tsv)

echo ">>> Creating AIServices resource: $AI_RESOURCE_NAME"
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AI_RESOURCE_NAME?api-version=2025-06-01" \
  --body "{
    \"kind\": \"AIServices\",
    \"location\": \"$AI_REGION\",
    \"sku\": {\"name\": \"S0\"},
    \"identity\": {\"type\": \"SystemAssigned\"},
    \"properties\": {
      \"customSubDomainName\": \"$AI_RESOURCE_NAME\",
      \"publicNetworkAccess\": \"Enabled\",
      \"allowProjectManagement\": true
    }
  }"

echo ">>> Creating AI Foundry Project: $PROJECT_NAME"
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AI_RESOURCE_NAME/projects/$PROJECT_NAME?api-version=2025-06-01" \
  --body "{
    \"location\": \"$AI_REGION\",
    \"identity\": {\"type\": \"SystemAssigned\"},
    \"properties\": {}
  }"

PROJECT_ENDPOINT="https://$AI_RESOURCE_NAME.services.ai.azure.com/api/projects/$PROJECT_NAME"

echo ">>> Deploy models (GPT-5.4 + text-embedding-3-large) in AI Foundry portal: $PROJECT_ENDPOINT"

# === Azure AI Search (Southeast Asia) ===
az search service create \
  --name "${PROJECT_PREFIX}-search" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --sku basic \
  --partition-count 1 \
  --replica-count 1

SEARCH_ENDPOINT="https://${PROJECT_PREFIX}-search.search.windows.net"
SEARCH_KEY=$(az search admin-key show \
  --service-name "${PROJECT_PREFIX}-search" \
  --resource-group "$RESOURCE_GROUP" \
  --query primaryKey -o tsv)

# === Cosmos DB (Southeast Asia) ===
az cosmosdb create \
  --name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --locations regionName="$OTHER_REGION" failoverPriority=0 \
  --kind GlobalDocumentDB

az cosmosdb sql database create \
  --account-name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --name "drugtargetdb"

az cosmosdb sql container create \
  --account-name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --database-name "drugtargetdb" \
  --name "reports" \
  --partition-key-path "/target"

az cosmosdb sql container create \
  --account-name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --database-name "drugtargetdb" \
  --name "documents" \
  --partition-key-path "/id"

COSMOS_ENDPOINT="https://${PROJECT_PREFIX}-cosmos.documents.azure.com:443/"
COSMOS_KEY=$(az cosmosdb keys list \
  --name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --query primaryMasterKey -o tsv)

# === Blob Storage (Southeast Asia) ===
az storage account create \
  --name "${PROJECT_PREFIX}storage" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --sku Standard_LRS

az storage container create \
  --name "reports" \
  --account-name "${PROJECT_PREFIX}storage"

az storage container create \
  --name "snapshots" \
  --account-name "${PROJECT_PREFIX}storage"

az storage container create \
  --name "private-documents" \
  --account-name "${PROJECT_PREFIX}storage"

BLOB_CONNECTION=$(az storage account show-connection-string \
  --name "${PROJECT_PREFIX}storage" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

# === Azure Document Intelligence (Southeast Asia) ===
az cognitiveservices account create \
  --name "${PROJECT_PREFIX}-docintel" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --kind FormRecognizer \
  --sku S0

DOC_INTEL_ENDPOINT="https://${PROJECT_PREFIX}-docintel.cognitiveservices.azure.com/"
DOC_INTEL_KEY=$(az cognitiveservices account keys list \
  --name "${PROJECT_PREFIX}-docintel" \
  --resource-group "$RESOURCE_GROUP" \
  --query key1 -o tsv)

# === Container Registry (Southeast Asia) ===
az acr create \
  --name "${PROJECT_PREFIX}acr" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --sku Basic \
  --admin-enabled true

# === VNet (Southeast Asia) ===
az network vnet create \
  --name "${PROJECT_PREFIX}-vnet" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --address-prefixes 10.0.0.0/16 \
  --subnet-name snet-cae \
  --subnet-prefixes 10.0.0.0/23

az network vnet subnet update \
  --name snet-cae \
  --vnet-name "${PROJECT_PREFIX}-vnet" \
  --resource-group "$RESOURCE_GROUP" \
  --delegations Microsoft.App/environments

az network vnet subnet create \
  --name snet-pe \
  --vnet-name "${PROJECT_PREFIX}-vnet" \
  --resource-group "$RESOURCE_GROUP" \
  --address-prefixes 10.0.2.0/24

CAE_SUBNET_ID=$(az network vnet subnet show \
  --name snet-cae \
  --vnet-name "${PROJECT_PREFIX}-vnet" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

# === Container Apps Environment with VNet (Southeast Asia) ===
az containerapp env create \
  --name "${PROJECT_PREFIX}-env-v2" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --infrastructure-subnet-resource-id "$CAE_SUBNET_ID"

# === Cosmos DB Private Endpoint + DNS ===
COSMOS_ID=$(az cosmosdb show --name "${PROJECT_PREFIX}-cosmos" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

az network private-dns zone create \
  --name "privatelink.documents.azure.com" \
  --resource-group "$RESOURCE_GROUP"

az network private-dns link vnet create \
  --name "link-${PROJECT_PREFIX}-vnet" \
  --zone-name "privatelink.documents.azure.com" \
  --resource-group "$RESOURCE_GROUP" \
  --virtual-network "${PROJECT_PREFIX}-vnet" \
  --registration-enabled false

az network private-endpoint create \
  --name "pe-cosmos-${PROJECT_PREFIX}" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --vnet-name "${PROJECT_PREFIX}-vnet" \
  --subnet snet-pe \
  --private-connection-resource-id "$COSMOS_ID" \
  --group-id Sql \
  --connection-name cosmos-connection

az network private-endpoint dns-zone-group create \
  --name cosmos-dns-group \
  --endpoint-name "pe-cosmos-${PROJECT_PREFIX}" \
  --resource-group "$RESOURCE_GROUP" \
  --private-dns-zone "privatelink.documents.azure.com" \
  --zone-name cosmos

# === Application Insights (Southeast Asia) ===
az monitor app-insights component create \
  --app "${PROJECT_PREFIX}-insights" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION"

APPINSIGHTS_KEY=$(az monitor app-insights component show \
  --app "${PROJECT_PREFIX}-insights" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

# === RBAC: Assign roles to Container App managed identity ===
echo ">>> After deploying Container Apps, assign these roles to its managed identity:"
echo "    - Azure AI Developer (on AIServices resource and project)"
echo "    - Cognitive Services Contributor (on AIServices resource and project)"
echo "    - Cognitive Services User (on AIServices resource and project)"

# === Output configuration to .env file (secrets not printed to stdout) ===
ENV_FILE="$(dirname "$0")/../backend/.env.provisioned"
cat > "$ENV_FILE" <<EOF
PROJECT_ENDPOINT=$PROJECT_ENDPOINT
SEARCH_ENDPOINT=$SEARCH_ENDPOINT
SEARCH_API_KEY=$SEARCH_KEY
COSMOS_ENDPOINT=$COSMOS_ENDPOINT
COSMOS_KEY=$COSMOS_KEY
BLOB_CONNECTION_STRING=$BLOB_CONNECTION
APPLICATIONINSIGHTS_CONNECTION_STRING=$APPINSIGHTS_KEY
AZURE_DOC_INTELLIGENCE_ENDPOINT=$DOC_INTEL_ENDPOINT
AZURE_DOC_INTELLIGENCE_KEY=$DOC_INTEL_KEY
EOF
chmod 600 "$ENV_FILE"

echo ""
echo "=== Resource Provisioning Complete ==="
echo "Secrets written to: $ENV_FILE (chmod 600)"
echo "Non-secret endpoints:"
echo "  PROJECT_ENDPOINT=$PROJECT_ENDPOINT"
echo "  SEARCH_ENDPOINT=$SEARCH_ENDPOINT"
echo "  COSMOS_ENDPOINT=$COSMOS_ENDPOINT"
echo ""
echo ">>> Next steps:"
echo "    1. Deploy GPT-5.4 + text-embedding-3-large in AI Foundry portal"
echo "    2. Copy secrets from $ENV_FILE into .env or Container App secrets"
echo "    3. Run infra/deploy.sh to build and deploy containers"
