from scheduler import Scheduler


def test_add_task():
    s = Scheduler()
    task = s.add_task("task1", 5)
    assert task.name == "task1"
    assert task.priority == 5
    assert not task.completed


def test_run_next_highest_priority_first():
    """run_next should execute the highest priority task first."""
    s = Scheduler()
    s.add_task("low", 1)
    s.add_task("high", 10)
    s.add_task("mid", 5)
    task = s.run_next()
    assert task.name == "high"


def test_run_next_removes_from_pending():
    """After run_next, the completed task should not appear in get_pending."""
    s = Scheduler()
    s.add_task("task1", 5)
    s.add_task("task2", 3)
    s.run_next()
    pending = s.get_pending()
    assert len(pending) == 1
    assert pending[0].name == "task2"


def test_run_next_no_duplicate_execution():
    """Running run_next twice should execute two different tasks."""
    s = Scheduler()
    s.add_task("a", 5, lambda: "result_a")
    s.add_task("b", 3, lambda: "result_b")
    t1 = s.run_next()
    t2 = s.run_next()
    assert t1.name != t2.name


def test_run_next_empty():
    s = Scheduler()
    assert s.run_next() is None


def test_run_all_priority_order():
    """run_all should execute tasks from highest to lowest priority."""
    s = Scheduler()
    s.add_task("low", 1, lambda: "low")
    s.add_task("high", 10, lambda: "high")
    s.add_task("mid", 5, lambda: "mid")
    results = s.run_all()
    names = [t.name for t in results]
    assert names == ["high", "mid", "low"]


def test_same_priority_fifo():
    """Tasks with the same priority should execute in insertion order (FIFO)."""
    s = Scheduler()
    s.add_task("first", 5, lambda: "first")
    s.add_task("second", 5, lambda: "second")
    s.add_task("third", 5, lambda: "third")
    results = s.run_all()
    names = [t.name for t in results]
    assert names == ["first", "second", "third"]


def test_get_pending():
    s = Scheduler()
    s.add_task("a", 1)
    s.add_task("b", 2)
    s.add_task("c", 3)
    s.run_next()
    pending = s.get_pending()
    assert len(pending) == 2


def test_run_all_returns_results():
    s = Scheduler()
    s.add_task("task", 1, lambda: 42)
    results = s.run_all()
    assert len(results) == 1
    assert results[0].result == 42


def test_clear_removes_completed():
    s = Scheduler()
    s.add_task("a", 1)
    s.add_task("b", 2)
    s.run_next()
    s.clear()
    assert len(s.tasks) == 1
