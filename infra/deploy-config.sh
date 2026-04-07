#!/usr/bin/env bash
# infra/deploy-config.sh — Deployment environment configuration
# Source this file before running deploy operations.

# === Azure Subscription ===
AZURE_SUBSCRIPTION="ME-MngEnv894848-kangminghe-2"

# === Resource Group ===
RESOURCE_GROUP="rg-drug-target-agent"
REGION="southeastasia"

# === Container Registry ===
ACR_NAME="drugtargetacr"
ACR_LOGIN_SERVER="drugtargetacr.azurecr.io"

# === Container Apps ===
CONTAINER_ENV="drugtarget-env-v2"
BACKEND_APP_NAME="drugtarget-backend"
FRONTEND_APP_NAME="drugtarget-frontend"
BACKEND_PORT=8000
FRONTEND_PORT=80

# === Image Names ===
BACKEND_IMAGE="${ACR_LOGIN_SERVER}/backend"
FRONTEND_IMAGE="${ACR_LOGIN_SERVER}/frontend"
