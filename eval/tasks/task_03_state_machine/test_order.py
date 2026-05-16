import pytest
from order import Order


def test_initial_state():
    o = Order("001")
    assert o.state == "pending"


def test_valid_transition():
    o = Order("001")
    o.transition("confirmed")
    assert o.state == "confirmed"


def test_invalid_transition_raises():
    o = Order("001")
    with pytest.raises(ValueError):
        o.transition("delivered")  # can't go pending -> delivered


def test_can_transition():
    o = Order("001")
    assert o.can_transition("confirmed") == True
    assert o.can_transition("delivered") == False


def test_history_recorded():
    o = Order("001")
    o.transition("confirmed")
    o.transition("shipped")
    h = o.get_history()
    assert len(h) == 2
    assert h[0]["from"] == "pending"
    assert h[0]["to"] == "confirmed"
    assert h[1]["from"] == "confirmed"
    assert h[1]["to"] == "shipped"


def test_history_has_timestamp():
    o = Order("001")
    o.transition("confirmed")
    h = o.get_history()
    assert "timestamp" in h[0]


def test_cancel_from_pending():
    o = Order("001")
    o.cancel()
    assert o.state == "cancelled"


def test_cancel_from_shipped_raises():
    o = Order("001")
    o.transition("confirmed")
    o.transition("shipped")
    with pytest.raises(ValueError):
        o.cancel()  # can't cancel after shipping


def test_full_lifecycle():
    o = Order("001")
    o.transition("confirmed")
    o.transition("shipped")
    o.transition("delivered")
    assert o.state == "delivered"
    assert len(o.get_history()) == 3
