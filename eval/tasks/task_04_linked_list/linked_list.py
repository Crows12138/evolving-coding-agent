"""Singly linked list implementation."""


class Node:
    def __init__(self, value):
        self.value = value
        self.next = None


class LinkedList:
    def __init__(self):
        self.head = None
        self._size = 0

    def insert(self, index, value):
        """Insert a value at the given index."""
        if index < 0 or index > self._size:
            raise IndexError("index out of range")
        new_node = Node(value)
        if index == 0:
            new_node.next = self.head.next  # BUG: should be self.head, crashes on empty list
            self.head = new_node
        else:
            current = self.head
            for _ in range(index - 1):
                current = current.next
            new_node.next = current.next
            current.next = new_node
        self._size += 1

    def delete(self, value):
        """Delete the first node with the given value. Returns True if found."""
        if self.head is None:
            return False
        if self.head.value == value:
            self.head = self.head.next
            self._size -= 1
            return True
        current = self.head
        while current.next is not None:
            if current.next.value == value:
                current.next = current.next  # BUG: should be current.next.next
                self._size -= 1
                return True
            current = current.next
        return False

    def find(self, value):
        """Find the first node with the given value. Returns the node or None."""
        current = self.head
        index = 0
        while current is not None:
            if current.value == value:
                return index  # BUG: should return current (the node)
            current = current.next
            index += 1
        return None

    def reverse(self):
        """Reverse the linked list in place."""
        prev = None
        current = self.head
        while current is not None:
            next_node = current.next
            current.next = prev
            prev = current
            current = next_node
        # BUG: missing self.head = prev

    def to_list(self):
        """Convert the linked list to a Python list."""
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        return result

    def __len__(self):
        return self._size
