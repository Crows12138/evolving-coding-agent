"""Order state machine."""

VALID_TRANSITIONS = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["shipped", "cancelled"],
    "shipped": ["delivered"],
    "delivered": [],
    "cancelled": [],
}

class Order:
    def __init__(self, order_id):
        self.order_id = order_id
        self.state = "pending"
        self.history = []

    def transition(self, new_state):
        self.state = new_state

    def can_transition(self, new_state):
        return True

    def cancel(self):
        self.state = "cancelled"

    def get_history(self):
        return self.history
