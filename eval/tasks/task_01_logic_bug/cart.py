"""Shopping cart with discount logic."""

class Cart:
    def __init__(self):
        self.items = []

    def add(self, name, price, qty=1):
        self.items.append({"name": name, "price": price, "qty": qty})

    def subtotal(self):
        return sum(i["price"] * i["qty"] for i in self.items)

    def total(self, discount_pct=0):
        return self.subtotal() * discount_pct / 100

    def remove(self, name):
        self.items = [i for i in self.items if i["name"] != name]

    def item_count(self):
        return len(self.items)
