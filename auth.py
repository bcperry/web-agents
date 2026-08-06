"""
Azure AD bearer token validation middleware for FastAPI.

Supports:
- JWKS-based JWT validation against Azure AD (Azure Government)
- AUTH_DISABLED=true bypass for local development
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Cache for JWKS keys
_jwks_cache: Optional[dict] = None


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents a validated user from an Azure AD token."""
    user_id: str
    username: str


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").lower() in ("true", "1", "yes")


_DEFAULT_DEV_USER = AuthenticatedUser(user_id="dev-user", username="developer")


async def _fetch_jwks(tenant_id: str, authority: str, *, force_refresh: bool = False) -> dict:
    """Fetch JWKS keys from Azure AD's OpenID configuration."""
    global _jwks_cache
    if _jwks_cache is not None and not force_refresh:
        return _jwks_cache

    openid_url = f"{authority}/{tenant_id}/v2.0/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(openid_url, timeout=10.0)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]

        resp = await client.get(jwks_uri, timeout=10.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache


def _get_signing_key(jwks: dict, kid: str) -> dict:
    """Find the signing key matching the token's kid header."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(status_code=401, detail="Unable to find matching signing key")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency that validates the Azure AD bearer token.

    When AUTH_DISABLED=true, returns a default dev user without validation.
    """
    if _auth_disabled():
        return _DEFAULT_DEV_USER

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = credentials.credentials
    tenant_id = os.getenv("OAUTH_AZURE_GOV_AD_TENANT_ID", "") or os.getenv("AZURE_AD_TENANT_ID", "")
    client_id = os.getenv("OAUTH_AZURE_GOV_AD_CLIENT_ID", "") or os.getenv("AZURE_AD_CLIENT_ID", "")
    authority = os.getenv(
        "AZURE_AD_AUTHORITY", "https://login.microsoftonline.us"
    )

    if not tenant_id or not client_id:
        logger.error("AZURE_AD_TENANT_ID and AZURE_AD_CLIENT_ID must be set when auth is enabled")
        raise HTTPException(status_code=500, detail="Server authentication not configured")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token header")

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing key ID")

    try:
        jwks = await _fetch_jwks(tenant_id, authority)
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch JWKS: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to validate token signing keys")

    try:
        signing_key = _get_signing_key(jwks, kid)
    except HTTPException:
        logger.info("Signing key %s not found in cached JWKS; refreshing keys", kid)
        try:
            jwks = await _fetch_jwks(tenant_id, authority, force_refresh=True)
        except httpx.HTTPError as exc:
            logger.error("Failed to refresh JWKS: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to validate token signing keys")
        signing_key = _get_signing_key(jwks, kid)

    # Accept both v1 and v2 token issuers
    v2_issuer = f"{authority}/{tenant_id}/v2.0"
    v1_issuer = f"https://sts.windows.net/{tenant_id}/"

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=[v2_issuer, v1_issuer],
        )
    except JWTError as exc:
        # Log details to help diagnose issuer/audience mismatches
        try:
            unverified = jwt.get_unverified_claims(token)
            logger.warning(
                "Token validation failed: %s | token iss=%s aud=%s | expected iss=%s or %s, aud=%s",
                exc,
                unverified.get("iss"),
                unverified.get("aud"),
                v2_issuer,
                v1_issuer,
                client_id,
            )
        except Exception:
            logger.warning("Token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("oid", payload.get("sub", ""))
    username = payload.get("preferred_username", payload.get("name", "unknown"))

    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user identifier")

    return AuthenticatedUser(user_id=user_id, username=username)


def clear_jwks_cache() -> None:
    """Clear the cached JWKS keys (useful for testing or key rotation)."""
    global _jwks_cache
    _jwks_cache = None
