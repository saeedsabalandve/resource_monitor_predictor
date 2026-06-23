# src/middleware/rate_limit.py
# Rate limiting middleware
# Protects API from excessive requests
# Uses token bucket algorithm with sliding window

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple
import time
from loguru import logger


class TokenBucket:
    """
    Token bucket rate limiting algorithm
    Allows burst traffic while maintaining average rate
    """
    
    def __init__(self, rate: int, burst: int):
        self.rate = rate  # Tokens per second
        self.burst = burst  # Maximum burst size
        self.tokens = burst
        self.last_update = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens
        Returns True if allowed, False if rate limited
        """
        now = time.time()
        time_passed = now - self.last_update
        
        # Refill tokens based on time passed
        self.tokens = min(
            self.burst,
            self.tokens + time_passed * self.rate
        )
        self.last_update = now
        
        # Check if enough tokens available
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using token bucket algorithm
    Limits requests per client IP
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.buckets: Dict[str, TokenBucket] = {}
        
        # Default rate limits
        self.default_rate = 100  # requests per second
        self.default_burst = 200  # maximum burst size
        
        # Cleanup old entries periodically
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
    
    def get_client_identifier(self, request: Request) -> str:
        """
        Get unique client identifier
        Uses X-Forwarded-For header or client IP
        """
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request through rate limiter
        """
        # Skip rate limiting for health check
        if request.url.path == "/api/v1/health":
            return await call_next(request)
        
        client_id = self.get_client_identifier(request)
        
        # Get or create token bucket for client
        if client_id not in self.buckets:
            self.buckets[client_id] = TokenBucket(
                rate=self.default_rate,
                burst=self.default_burst
            )
        
        bucket = self.buckets[client_id]
        
        # Try to consume token
        if not bucket.consume():
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            
            # Calculate retry-after time
            retry_after = int(1 / self.default_rate)
            
            return Response(
                content='{"detail": "Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)}
            )
        
        # Periodic cleanup of old buckets
        await self._cleanup_buckets()
        
        # Continue processing
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))
        response.headers["X-RateLimit-Limit"] = str(self.default_rate)
        
        return response
    
    async def _cleanup_buckets(self):
        """
        Clean up old token buckets periodically
        """
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            # Remove buckets for clients that haven't been active
            to_remove = []
            for client_id, bucket in self.buckets.items():
                if now - bucket.last_update > self.cleanup_interval:
                    to_remove.append(client_id)
            
            for client_id in to_remove:
                del self.buckets[client_id]
            
            self.last_cleanup = now
            
            if to_remove:
                logger.debug(f"Cleaned up {len(to_remove)} rate limit buckets")
