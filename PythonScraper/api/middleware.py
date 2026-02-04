"""
Authentication middleware for BetSnipe.ai v3.0

Provides JWT validation for Supabase Auth integration.
"""

import logging
from typing import Optional
from functools import wraps

import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Authenticated user information extracted from JWT."""
    id: str  # UUID from Supabase
    email: Optional[str] = None
    role: str = "authenticated"
    app_metadata: dict = {}
    user_metadata: dict = {}


class SupabaseAuth:
    """
    Supabase JWT Authentication handler.

    Validates JWTs issued by Supabase Auth and extracts user information.
    """

    def __init__(self):
        self.jwt_secret = settings.supabase_jwt_secret
        self.algorithms = ["HS256"]

    def decode_token(self, token: str) -> dict:
        """
        Decode and validate a Supabase JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        if not self.jwt_secret:
            logger.error("SUPABASE_JWT_SECRET not configured")
            raise HTTPException(
                status_code=500,
                detail="Authentication not configured"
            )

        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=self.algorithms,
                audience="authenticated"
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token"
            )

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        """
        Extract user information from a validated JWT.

        Args:
            token: JWT token string

        Returns:
            AuthenticatedUser with user details
        """
        payload = self.decode_token(token)

        return AuthenticatedUser(
            id=payload.get("sub"),
            email=payload.get("email"),
            role=payload.get("role", "authenticated"),
            app_metadata=payload.get("app_metadata", {}),
            user_metadata=payload.get("user_metadata", {})
        )


# Global auth handler instance
auth_handler = SupabaseAuth()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency to get the current authenticated user.

    Usage:
        @router.get("/protected")
        async def protected_route(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.id}

    Raises:
        HTTPException 401: If no token provided or token is invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return auth_handler.get_user_from_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthenticatedUser]:
    """
    FastAPI dependency for optional authentication.

    Returns None if no token provided, user if valid token,
    or raises exception if invalid token.

    Usage:
        @router.get("/public-or-private")
        async def route(user: Optional[AuthenticatedUser] = Depends(get_optional_user)):
            if user:
                return {"personalized": True, "user_id": user.id}
            return {"personalized": False}
    """
    if not credentials:
        return None

    try:
        return auth_handler.get_user_from_token(credentials.credentials)
    except HTTPException:
        # Re-raise auth errors even for optional routes
        raise


def require_role(required_role: str):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.delete("/admin-only")
        async def admin_route(user: AuthenticatedUser = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
    """
    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user)
    ) -> AuthenticatedUser:
        if user.role != required_role and user.role != "service_role":
            raise HTTPException(
                status_code=403,
                detail=f"Role '{required_role}' required"
            )
        return user

    return role_checker


class AuthMiddleware:
    """
    ASGI middleware for request-level authentication.

    Adds user info to request.state if valid Bearer token present.
    Does not block requests - use dependencies for route protection.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Extract token from headers
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()

            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                try:
                    user = auth_handler.get_user_from_token(token)
                    # Store in scope for access in routes
                    scope["state"] = scope.get("state", {})
                    scope["state"]["user"] = user
                except Exception:
                    # Invalid token - don't block, let route handle it
                    pass

        await self.app(scope, receive, send)


# WebSocket authentication helper
async def authenticate_websocket(token: str) -> Optional[AuthenticatedUser]:
    """
    Authenticate a WebSocket connection.

    Args:
        token: JWT token (usually passed as query param)

    Returns:
        AuthenticatedUser if valid, None otherwise
    """
    try:
        return auth_handler.get_user_from_token(token)
    except Exception as e:
        logger.debug(f"WebSocket auth failed: {e}")
        return None
