"""Task scheduler with priority-based execution."""


class Task:
    def __init__(self, name, priority, action=None):
        self.name = name
        self.priority = priority
        self.action = action or (lambda: None)
        self.completed = False
        self.result = None


class Scheduler:
    def __init__(self):
        self.tasks = []
        self._counter = 0

    def add_task(self, name, priority, action=None):
        """Add a task with given priority (higher number = higher priority)."""
        task = Task(name, priority, action)
        task._seq = self._counter
        self._counter += 1
        self.tasks.append(task)
        # Bug 1: ascending sort means low priority comes first (should be descending)
        # Bug 2: secondary sort by -_seq reverses FIFO for same priority
        self.tasks.sort(key=lambda t: (t.priority, -t._seq))
        return task

    def run_next(self):
        """Run the highest priority pending task."""
        pending = [t for t in self.tasks if not t.completed]
        if not pending:
            return None
        # Bug: priority sort is ascending, so this picks the LOWEST priority task
        # (tasks are sorted ascending by priority, and we pick the first one)
        task = pending[0]
        task.result = task.action()
        task.completed = True
        # Bug: task is not removed from the queue after completion
        # (it stays in self.tasks, just marked as completed)
        return task

    def run_all(self):
        """Run all pending tasks in priority order."""
        results = []
        while True:
            task = self.run_next()
            if task is None:
                break
            results.append(task)
        return results

    def get_pending(self):
        """Get all pending (not yet completed) tasks."""
        return [t for t in self.tasks if not t.completed]

    def clear(self):
        """Remove all completed tasks from the queue."""
        self.tasks = [t for t in self.tasks if not t.completed]
        self._counter = len(self.tasks)
