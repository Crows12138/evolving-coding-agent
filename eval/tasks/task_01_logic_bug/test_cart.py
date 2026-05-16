from cart import Cart

def test_subtotal():
    c = Cart()
    c.add("apple", 1.0, 3)
    c.add("banana", 0.5, 2)
    assert c.subtotal() == 4.0

def test_total_no_discount():
    c = Cart()
    c.add("apple", 10.0)
    assert c.total() == 10.0

def test_total_with_discount():
    c = Cart()
    c.add("apple", 10.0)
    assert c.total(20) == 8.0

def test_total_full_discount():
    c = Cart()
    c.add("apple", 10.0)
    assert c.total(100) == 0.0

def test_remove_first_only():
    c = Cart()
    c.add("apple", 1.0)
    c.add("banana", 2.0)
    c.add("apple", 1.5)
    c.remove("apple")
    assert len(c.items) == 2
    assert c.items[0]["name"] == "banana"
    assert c.items[1]["name"] == "apple"

def test_item_count():
    c = Cart()
    c.add("apple", 1.0, 3)
    c.add("banana", 0.5, 2)
    assert c.item_count() == 5
