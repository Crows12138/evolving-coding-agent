"""Event publish/subscribe system."""


class EventEmitter:
    def __init__(self):
        self._listeners = {}
        self._once_listeners = {}

    def on(self, event, callback):
        """Register a listener for an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event, callback):
        """Remove a specific listener for an event."""
        if event not in self._listeners:
            return
        # BUG: removes ALL listeners for the event instead of just the specified one
        del self._listeners[event]

    def emit(self, event, *args, **kwargs):
        """Emit an event, calling all registered listeners."""
        listeners = self._listeners.get(event, [])
        for listener in listeners:
            listener()  # BUG: should be listener(*args, **kwargs)

        once_listeners = self._once_listeners.get(event, [])
        for listener in once_listeners:
            listener()  # BUG: same - should be listener(*args, **kwargs)
        # BUG: should clear once_listeners after firing
        # missing: self._once_listeners[event] = []

    def once(self, event, callback):
        """Register a listener that fires only once."""
        if event not in self._once_listeners:
            self._once_listeners[event] = []
        self._once_listeners[event].append(callback)

    def listener_count(self, event):
        """Return the number of listeners for an event."""
        regular = len(self._listeners.get(event, []))
        once = len(self._once_listeners.get(event, []))
        return regular + once
