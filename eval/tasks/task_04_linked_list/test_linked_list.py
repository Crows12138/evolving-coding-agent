from linked_list import LinkedList, Node


def test_insert_into_empty_list():
    ll = LinkedList()
    ll.insert(0, "a")
    assert ll.to_list() == ["a"]
    assert len(ll) == 1


def test_insert_at_head():
    ll = LinkedList()
    ll.insert(0, "b")
    ll.insert(0, "a")
    assert ll.to_list() == ["a", "b"]


def test_insert_at_tail():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.insert(1, "b")
    ll.insert(2, "c")
    assert ll.to_list() == ["a", "b", "c"]


def test_insert_in_middle():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.insert(1, "c")
    ll.insert(1, "b")
    assert ll.to_list() == ["a", "b", "c"]


def test_delete_middle_node():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.insert(1, "b")
    ll.insert(2, "c")
    assert ll.delete("b") is True
    assert ll.to_list() == ["a", "c"]
    assert len(ll) == 2


def test_delete_tail_node():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.insert(1, "b")
    ll.insert(2, "c")
    assert ll.delete("c") is True
    assert ll.to_list() == ["a", "b"]


def test_delete_nonexistent():
    ll = LinkedList()
    ll.insert(0, "a")
    assert ll.delete("z") is False
    assert ll.to_list() == ["a"]


def test_find_returns_node():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.insert(1, "b")
    result = ll.find("b")
    assert isinstance(result, Node)
    assert result.value == "b"


def test_find_nonexistent_returns_none():
    ll = LinkedList()
    ll.insert(0, "a")
    assert ll.find("z") is None


def test_reverse():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.insert(1, "b")
    ll.insert(2, "c")
    ll.reverse()
    assert ll.to_list() == ["c", "b", "a"]


def test_reverse_single_element():
    ll = LinkedList()
    ll.insert(0, "a")
    ll.reverse()
    assert ll.to_list() == ["a"]


def test_reverse_empty():
    ll = LinkedList()
    ll.reverse()
    assert ll.to_list() == []
