"""System and public configuration endpoints."""

import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "healthy"}


@router.get("/api/auth/config")
async def auth_config():
    """Return OAuth configuration so the frontend can build MSAL config at runtime."""
    return {
        "authDisabled": os.getenv("AUTH_DISABLED", "").lower() in ("true", "1", "yes"),
        "tenantId": os.getenv("OAUTH_AZURE_GOV_AD_TENANT_ID", "") or os.getenv("AZURE_AD_TENANT_ID", ""),
        "clientId": os.getenv("OAUTH_AZURE_GOV_AD_CLIENT_ID", "") or os.getenv("AZURE_AD_CLIENT_ID", ""),
        "authority": os.getenv("AZURE_AD_AUTHORITY", "https://login.microsoftonline.us"),
        "classificationBanner": os.getenv("CLASSIFICATION_BANNER", "UNCLASSIFIED"),
        "appName": os.getenv("APP_NAME", "Web-Agents"),
        "appTagline": os.getenv("APP_TAGLINE", "AI Agent Framework"),
        "appLogo": os.getenv("APP_LOGO", "/Microsoft.png"),
    }