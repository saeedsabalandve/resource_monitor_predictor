# src/api/dependencies.py
# FastAPI dependencies and middleware support
# Handles authentication, rate limiting, and common dependencies

from fastapi import HTTPException, Request, Depends
from fastapi.security import APIKeyHeader
from typing import Optional
from loguru import logger
import time
from collections import defaultdict

from config.settings import Settings


# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    """
    Verify API key for protected endpoints
    Supports both header-based and query parameter authentication
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key is required. Use X-API-Key header."
        )
    
    # Load settings for API key validation
    settings = Settings()
    
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    
    return api_key


async def get_influx_client(request: Request):
    """
    Dependency to get InfluxDB client
    """
    return request.app.state.influx_client


async def get_prediction_manager(request: Request):
    """
    Dependency to get prediction manager
    """
    return request.app.state.prediction_manager


async def get_collection_scheduler(request: Request):
    """
    Dependency to get collection scheduler
    """
    return request.app.state.collection_scheduler


# Simple in-memory rate limiter
class RateLimiter:
    """
    Simple rate limiter using in-memory storage
    For production, use Redis-based rate limiting
    """
    
    def __init__(self):
        self.requests = defaultdict(list)
    
    def is_allowed(self, client_id: str, max_requests: int = 100, period: int = 60) -> bool:
        """
        Check if request is allowed under rate limit
        """
        now = time.time()
        cutoff = now - period
        
        # Clean old requests
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if req_time > cutoff
        ]
        
        # Check if under limit
        if len(self.requests[client_id]) < max_requests:
            self.requests[client_id].append(now)
            return True
        
        return False


rate_limiter = RateLimiter()


async def check_rate_limit(request: Request):
    """
    Rate limiting dependency
    Limits API requests per client
    """
    client_id = request.client.host if request.client else "unknown"
    settings = Settings()
    
    if not rate_limiter.is_allowed(
        client_id,
        max_requests=settings.RATE_LIMIT_REQUESTS,
        period=settings.RATE_LIMIT_PERIOD
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )
    
    return client_id
