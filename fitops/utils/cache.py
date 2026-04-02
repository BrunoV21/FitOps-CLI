from functools import lru_cache

# Module-level registry of all caches so they can be cleared on logout
_cache_functions: list = []


def cached(maxsize: int = 32):
    """Decorator that registers the cache for later clearing."""

    def decorator(fn):
        cached_fn = lru_cache(maxsize=maxsize)(fn)
        _cache_functions.append(cached_fn)
        return cached_fn

    return decorator


def clear_all_caches() -> None:
    """Clear all registered LRU caches (call on logout or re-auth)."""
    for fn in _cache_functions:
        fn.cache_clear()
