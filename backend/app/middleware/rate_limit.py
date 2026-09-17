"""Rate limiting middleware."""
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiting middleware."""
    
    def __init__(self, app, requests_per_minute: int = 10):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)  # IP -> list of request timestamps
        self.cleanup_interval = timedelta(minutes=5)
        self.last_cleanup = datetime.now()
    
    def _cleanup_old_requests(self):
        """Remove old request timestamps to prevent memory leak."""
        now = datetime.now()
        if now - self.last_cleanup > self.cleanup_interval:
            cutoff = now - timedelta(minutes=2)
            for ip in list(self.requests.keys()):
                self.requests[ip] = [
                    ts for ts in self.requests[ip] if ts > cutoff
                ]
                if not self.requests[ip]:
                    del self.requests[ip]
            self.last_cleanup = now
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Check for forwarded IP (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next):
        is_knowledge = request.url.path.endswith("/knowledge/ask")
        if (request.url.path.endswith("/plan-itinerary") or is_knowledge) and request.method == "POST":
            self._cleanup_old_requests()
            
            client_ip = self._get_client_ip(request)
            if is_knowledge:
                # Separate budget; caller-supplied forwarded headers cannot bypass it.
                client_ip = "knowledge:" + (request.client.host if request.client else "unknown")
            now = datetime.now()
            minute_ago = now - timedelta(minutes=1)
            
            # Filter requests in the last minute
            self.requests[client_ip] = [
                ts for ts in self.requests[client_ip] if ts > minute_ago
            ]
            
            # Check if limit exceeded
            if len(self.requests[client_ip]) >= self.requests_per_minute:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
                        "details": {
                            "retry_after_seconds": 60
                        }
                    }
                )
            
            # Record this request
            self.requests[client_ip].append(now)
        
        response = await call_next(request)
        return response

