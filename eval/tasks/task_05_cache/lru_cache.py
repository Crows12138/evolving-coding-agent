"""LRU Cache implementation using OrderedDict."""

from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._cache = OrderedDict()
        self._total_puts = 0

    def get(self, key):
        """Get value by key. Returns None if not found. Should update access order."""
        if key not in self._cache:
            return None
        # BUG: should call self._cache.move_to_end(key) to update access order
        return self._cache[key]

    def put(self, key, value):
        """Put a key-value pair. Evicts LRU item if over capacity."""
        if key in self._cache:
            self._cache[key] = value
            self._cache.move_to_end(key)
        else:
            self._cache[key] = value
            self._total_puts += 1
            # BUG: should check and evict when len > capacity
            # missing: if len(self._cache) > self.capacity: self._cache.popitem(last=False)

    def evict(self):
        """Manually evict the least recently used item. Returns (key, value) or None."""
        if not self._cache:
            return None
        return self._cache.popitem(last=False)

    def size(self):
        """Return the number of items currently in the cache."""
        return self._total_puts  # BUG: should return len(self._cache)

    def contains(self, key):
        """Check if key exists in cache."""
        return key in self._cache

    def clear(self):
        """Clear all items from the cache."""
        self._cache.clear()
        self._total_puts = 0
