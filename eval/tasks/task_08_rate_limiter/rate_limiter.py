"""Token bucket style rate limiter."""

import time


class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        """
        Args:
            max_requests: Maximum number of requests allowed in the window.
            window_seconds: Time window in seconds.
        """
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("max_requests and window_seconds must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests = []
        self._total_requests = 0

    def _clean_expired(self, now=None):
        """Remove requests outside the current window."""
        if now is None:
            now = time.time()
        cutoff = now + self.window_seconds  # BUG: should be now - self.window_seconds
        self._requests = [t for t in self._requests if t > cutoff]

    def allow(self, now=None):
        """Check if a request is allowed. Returns True if allowed."""
        if now is None:
            now = time.time()
        self._clean_expired(now)
        if len(self._requests) < self.max_requests:
            # BUG: not appending `now` to self._requests
            # should be: self._requests.append(now)
            self._total_requests += 1
            return True
        return False

    def remaining(self, now=None):
        """Return the number of remaining allowed requests in current window."""
        if now is None:
            now = time.time()
        self._clean_expired(now)
        return max(0, self.max_requests - len(self._requests))

    def reset(self):
        """Reset the rate limiter."""
        self._total_requests = 0
        # BUG: missing self._requests = [] (doesn't clear the request timestamps)

    def wait_time(self, now=None):
        """Return seconds to wait before next request is allowed, or 0 if allowed now."""
        if now is None:
            now = time.time()
        self._clean_expired(now)
        if len(self._requests) < self.max_requests:
            return 0.0
        oldest = min(self._requests)
        return max(0.0, oldest + self.window_seconds - now)
