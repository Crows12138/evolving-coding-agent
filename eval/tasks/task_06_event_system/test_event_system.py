from event_system import EventEmitter


def test_on_and_emit():
    emitter = EventEmitter()
    results = []
    emitter.on("click", lambda: results.append("clicked"))
    emitter.emit("click")
    assert results == ["clicked"]


def test_emit_with_args():
    emitter = EventEmitter()
    results = []
    emitter.on("data", lambda x, y: results.append(x + y))
    emitter.emit("data", 3, 4)
    assert results == [7]


def test_emit_with_kwargs():
    emitter = EventEmitter()
    results = []
    emitter.on("greet", lambda name="world": results.append(f"hello {name}"))
    emitter.emit("greet", name="alice")
    assert results == ["hello alice"]


def test_multiple_listeners():
    emitter = EventEmitter()
    results = []
    emitter.on("event", lambda: results.append("a"))
    emitter.on("event", lambda: results.append("b"))
    emitter.emit("event")
    assert results == ["a", "b"]


def test_off_removes_specific_listener():
    emitter = EventEmitter()
    results = []
    fn_a = lambda: results.append("a")
    fn_b = lambda: results.append("b")
    emitter.on("event", fn_a)
    emitter.on("event", fn_b)
    emitter.off("event", fn_a)
    emitter.emit("event")
    assert results == ["b"]


def test_off_nonexistent_event():
    emitter = EventEmitter()
    emitter.off("no_such_event", lambda: None)  # should not raise


def test_once_fires_once():
    emitter = EventEmitter()
    results = []
    emitter.once("init", lambda: results.append("fired"))
    emitter.emit("init")
    emitter.emit("init")
    assert results == ["fired"]


def test_once_with_args():
    emitter = EventEmitter()
    results = []
    emitter.once("data", lambda x: results.append(x))
    emitter.emit("data", 42)
    assert results == [42]


def test_listener_count():
    emitter = EventEmitter()
    emitter.on("a", lambda: None)
    emitter.on("a", lambda: None)
    emitter.once("a", lambda: None)
    assert emitter.listener_count("a") == 3


def test_listener_count_after_off():
    emitter = EventEmitter()
    fn = lambda: None
    emitter.on("a", fn)
    emitter.on("a", lambda: None)
    emitter.off("a", fn)
    assert emitter.listener_count("a") == 1


def test_emit_unknown_event():
    emitter = EventEmitter()
    emitter.emit("nope")  # should not raise
