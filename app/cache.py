"""
Simple TTL-based cache for query results.

This module provides a thread-safe cache with automatic expiration
for caching database query results. Particularly useful for the
filtered sensor readings endpoint which can be called frequently
by multiple dashboard widgets with the same filter parameters.
"""

import hashlib
import json
import threading
import time
from functools import wraps
from typing import Any, Callable, Optional

# Global cache storage
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()

# Default TTL in seconds (2 minutes - sensor data updates every ~10 minutes)
DEFAULT_TTL = 120


def _make_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a stable cache key from function arguments."""
    # Create a deterministic string representation of arguments
    key_data = {
        'args': [_serialize_arg(arg) for arg in args],
        'kwargs': {k: _serialize_arg(v) for k, v in sorted(kwargs.items())}
    }
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_str.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def _serialize_arg(arg: Any) -> Any:
    """Serialize an argument for cache key generation."""
    if arg is None:
        return None
    if isinstance(arg, (str, int, float, bool)):
        return arg
    if isinstance(arg, (list, tuple)):
        return [_serialize_arg(item) for item in arg]
    if isinstance(arg, dict):
        return {k: _serialize_arg(v) for k, v in sorted(arg.items())}
    # For objects with __dict__, use their attributes
    if hasattr(arg, '__dict__'):
        return {k: _serialize_arg(v) for k, v in sorted(vars(arg).items()) if not k.startswith('_')}
    # Fallback to string representation
    return str(arg)


def get_cached(key: str) -> Optional[Any]:
    """Get a value from cache if it exists and hasn't expired."""
    with _cache_lock:
        if key in _cache:
            value, expiry = _cache[key]
            if time.time() < expiry:
                return value
            # Expired - remove from cache
            del _cache[key]
    return None


def set_cached(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Set a value in cache with expiration."""
    with _cache_lock:
        _cache[key] = (value, time.time() + ttl)


def clear_cache(prefix: Optional[str] = None) -> int:
    """Clear cache entries. If prefix provided, only clear matching entries."""
    with _cache_lock:
        if prefix is None:
            count = len(_cache)
            _cache.clear()
            return count

        keys_to_remove = [k for k in _cache if k.startswith(prefix)]
        for key in keys_to_remove:
            del _cache[key]
        return len(keys_to_remove)


def cached_query(ttl: int = DEFAULT_TTL) -> Callable:
    """
    Decorator specifically for GraphQL resolver methods.
    Automatically uses function name as cache prefix and handles
    GraphQL resolver signature (self, info, **kwargs).

    Args:
        ttl: Time-to-live in seconds

    Usage:
        @cached_query(ttl=60)
        def resolve_filtered_sensor_readings(self, info, filters):
            # expensive database query
            return results
    """
    def decorator(func: Callable) -> Callable:
        prefix = func.__name__

        @wraps(func)
        def wrapper(self, info, *args, **kwargs):
            # Build cache key from filter arguments only (not self or info)
            cache_key = _make_cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_value = get_cached(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute resolver and cache result
            result = func(self, info, *args, **kwargs)

            # Only cache non-empty results
            if result:
                set_cached(cache_key, result, ttl)

            return result

        return wrapper
    return decorator
