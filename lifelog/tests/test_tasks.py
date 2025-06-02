from lifelog.commands import task_module
import os
import sys
import unittest
from typer.testing import CliRunner

# Patch problematic imports *before* importing your module
import builtins
from unittest import mock

# Patch all external CLI dependencies
sys.modules["plotext"] = mock.Mock()
sys.modules["paho"] = mock.Mock()
sys.modules["paho.mqtt"] = mock.Mock()
sys.modules["paho.mqtt.publish"] = mock.Mock()
sys.modules["rich"] = mock.Mock()
sys.modules["rich.console"] = mock.Mock()
sys.modules["rich.prompt"] = mock.Mock()
sys.modules["rich.table"] = mock.Mock()
sys.modules["rich.panel"] = mock.Mock()
sys.modules["rich.text"] = mock.Mock()

# Your app entrypoint (change if it's not the main Typer object in task_module.py)

runner = CliRunner()

# Helper to clear the DB between tests if needed


def clear_tasks():
    from lifelog.commands.utils.db.database_manager import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()


class TestTaskModule(unittest.TestCase):
    def setUp(self):
        # Start each test with a clean DB
        clear_tasks()

    def tearDown(self):
        clear_tasks()

    def test_add_task(self):
        """Test the add command creates a new task."""
        result = runner.invoke(
            task_module.app,  # This should be your Typer object
            ["add", "Test Task", "--category", "Work", "--project",
                "Proj", "--impt", "2", "--due", "2099-12-31"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Task", result.output)
        # Confirm it was really added
        from lifelog.commands.utils.db.task_repository import query_tasks
        tasks = query_tasks(title_contains="Test Task")
        self.assertTrue(any("Test Task" in t.title for t in tasks))

    def test_list_tasks(self):
        """Test listing tasks shows the added task."""
        # First add a task
        runner.invoke(
            task_module.app,
            ["add", "TaskToList", "--category", "Other", "--impt", "1"]
        )
        result = runner.invoke(task_module.app, ["list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("TaskToList", result.output)

    def test_info_found(self):
        """Test info command shows details for a real task."""
        runner.invoke(
            task_module.app,
            ["add", "InfoTask", "--category", "X"]
        )
        # Get the ID from the repo
        from lifelog.commands.utils.db.task_repository import query_tasks
        tid = query_tasks(title_contains="InfoTask")[0].id
        result = runner.invoke(task_module.app, ["info", str(tid)])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("InfoTask", result.output)

    def test_info_not_found(self):
        """Test info command errors for missing task."""
        result = runner.invoke(task_module.app, ["info", "99999"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not found", result.output.lower())

    def test_modify_task(self):
        """Test modifying a task updates it."""
        runner.invoke(
            task_module.app,
            ["add", "OldTitle", "--category", "Cat"]
        )
        from lifelog.commands.utils.db.task_repository import query_tasks
        tid = query_tasks(title_contains="OldTitle")[0].id
        result = runner.invoke(
            task_module.app,
            ["modify", str(tid), "--title", "NewTitle", "--category", "NewCat"]
        )
        self.assertEqual(result.exit_code, 0)
        tasks = query_tasks(title_contains="NewTitle")
        self.assertTrue(any("NewTitle" in t.title for t in tasks))

    def test_delete_task(self):
        """Test deleting a task removes it."""
        runner.invoke(
            task_module.app,
            ["add", "TaskToDelete", "--category", "Z"]
        )
        from lifelog.commands.utils.db.task_repository import query_tasks
        tid = query_tasks(title_contains="TaskToDelete")[0].id
        result = runner.invoke(
            task_module.app,
            ["delete", str(tid)]
        )
        self.assertEqual(result.exit_code, 0)
        # Confirm it no longer exists
        tasks = query_tasks(title_contains="TaskToDelete")
        self.assertFalse(any("TaskToDelete" in t.title for t in tasks))

    def test_start_stop_done(self):
        """Test full start/stop/done flow."""
        runner.invoke(
            task_module.app,
            ["add", "FlowTask", "--category", "T"]
        )
        from lifelog.commands.utils.db.task_repository import query_tasks
        tid = query_tasks(title_contains="FlowTask")[0].id
        start_result = runner.invoke(task_module.app, ["start", str(tid)])
        self.assertEqual(start_result.exit_code, 0)
        stop_result = runner.invoke(task_module.app, ["stop"])
        self.assertEqual(stop_result.exit_code, 0)
        done_result = runner.invoke(task_module.app, ["done", str(tid)])
        self.assertEqual(done_result.exit_code, 0)
        self.assertIn("done", done_result.output.lower())

    def test_list_empty(self):
        """Test that listing when there are no tasks gives a friendly message."""
        result = runner.invoke(task_module.app, ["list"])
        self.assertIn("no tasks", result.output.lower())

    def test_modify_task_not_found(self):
        """Test modifying a missing task errors."""
        result = runner.invoke(
            task_module.app,
            ["modify", "9999", "--title", "Nothing"]
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not found", result.output.lower())

    def test_delete_task_not_found(self):
        """Test deleting a missing task errors."""
        result = runner.invoke(task_module.app, ["delete", "9999"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not found", result.output.lower())

    def test_burndown_runs(self):
        """Test that burndown does not crash even if no tasks."""
        result = runner.invoke(task_module.app, ["burndown"])
        self.assertEqual(result.exit_code, 0)
        # Not much to assert unless you check output details

    def test_auto_recur_creates_task(self):
        """Test that recurring tasks are recreated."""
        # Add a recurring task
        runner.invoke(
            task_module.app,
            [
                "add", "RecurTask",
                "--category", "R",
                "--recur", "--due", "2099-01-01"
            ]
        )
        result = runner.invoke(task_module.app, ["auto-recur"])
        self.assertEqual(result.exit_code, 0)
        # This is a very basic check—expand as your logic matures
        self.assertIn("recurring", result.output.lower())


if __name__ == "__main__":
    unittest.main()
