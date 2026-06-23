# src/middleware/auth.py
# Authentication middleware
# Validates API keys for all incoming requests
# Excludes health check and documentation endpoints

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List
from loguru import logger


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for API key validation
    Skips authentication for public endpoints
    """
    
    # Public endpoints that don't require authentication
    PUBLIC_PATHS = [
        "/api/v1/health",
        "/api/docs",
        "/api/redoc",
        "/openapi.json",
        "/"
    ]
    
    async def dispatch(self, request: Request, call_next):
        """
        Process each request through authentication
        """
        # Skip authentication for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        
        # Check for API key in headers
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            logger.warning(f"Unauthorized request to {request.url.path} from {request.client.host}")
            return Response(
                content='{"detail": "API key required"}',
                status_code=401,
                media_type="application/json"
            )
        
        # Add API key to request state for route handlers
        request.state.api_key = api_key
        
        # Continue processing
        response = await call_next(request)
        
        return response
