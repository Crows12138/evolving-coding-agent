from lru_cache import LRUCache


def test_put_and_get():
    cache = LRUCache(3)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    assert cache.get("b") == 2


def test_get_nonexistent():
    cache = LRUCache(3)
    assert cache.get("x") is None


def test_eviction_on_capacity():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    # "a" should have been evicted as LRU
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_get_updates_access_order():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")  # access "a" so "b" becomes LRU
    cache.put("c", 3)
    # "b" should be evicted, not "a"
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_size_after_puts():
    cache = LRUCache(3)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.size() == 2


def test_size_after_eviction():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.size() == 2


def test_manual_evict():
    cache = LRUCache(3)
    cache.put("a", 1)
    cache.put("b", 2)
    result = cache.evict()
    assert result == ("a", 1)
    assert cache.size() == 1


def test_evict_empty_cache():
    cache = LRUCache(3)
    assert cache.evict() is None


def test_put_update_existing():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    assert cache.get("a") == 10
    assert cache.size() == 2


def test_contains():
    cache = LRUCache(3)
    cache.put("a", 1)
    assert cache.contains("a") is True
    assert cache.contains("z") is False


def test_clear():
    cache = LRUCache(3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.clear()
    assert cache.size() == 0
    assert cache.get("a") is None
