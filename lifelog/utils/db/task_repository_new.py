# lifelog/utils/db/task_repository_new.py
"""
New TaskRepository implementation using BaseRepository.
This runs alongside the existing task_repository.py for testing.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from lifelog.utils.db.base_repository import BaseRepository
from lifelog.utils.db.models import Task, TaskStatus, task_from_row
from lifelog.utils.shared_utils import calculate_priority
from lifelog.utils.db import safe_query, should_sync

logger = logging.getLogger(__name__)


class TaskRepository(BaseRepository[Task]):
    """Repository for Task operations with sync support."""
    
    def __init__(self):
        super().__init__("tasks", Task, task_from_row)
    
    def get_sync_endpoint(self) -> str:
        return "tasks"
    
    def validate_before_save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize task data before saving."""
        data = data.copy()
        
        # Handle TaskStatus enum
        if 'status' in data:
            status_val = data['status']
            try:
                if isinstance(status_val, TaskStatus):
                    data['status'] = status_val.value
                else:
                    data['status'] = TaskStatus(status_val).value
            except Exception:
                logger.warning(f"Invalid status '{status_val}', defaulting to BACKLOG")
                data['status'] = TaskStatus.BACKLOG.value
        else:
            data['status'] = TaskStatus.BACKLOG.value
        
        # Set defaults
        data.setdefault('importance', 1)
        
        # Handle due date
        if 'due' in data and isinstance(data['due'], str):
            try:
                data['due'] = datetime.fromisoformat(data['due'])
            except Exception:
                data['due'] = None
        
        # Calculate priority if not set
        if 'priority' not in data or data.get('priority') is None:
            try:
                data['priority'] = calculate_priority(data)
            except Exception as e:
                logger.error(f"Priority calculation failed: {e}", exc_info=True)
                data['priority'] = 1.0
        
        # Set created timestamp for new tasks
        if 'created' not in data or data.get('created') is None:
            data['created'] = datetime.now()
        
        return data
    
    # ─── TASK-SPECIFIC QUERIES ───
    
    def query_tasks(
        self,
        title_contains: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        show_completed: bool = False,
        sort: str = "priority",
        **kwargs
    ) -> List[Task]:
        """Flexible task query with multiple filters."""
        # Pull latest changes if in sync mode
        if should_sync():
            self._pull_changed_from_host()
        
        query = f"SELECT * FROM {self.table_name} WHERE 1=1"
        params: List[Any] = []
        
        # Apply filters
        if title_contains:
            query += " AND title LIKE ?"
            params.append(f"%{title_contains}%")
        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)
        if not show_completed and status is None:
            query += " AND (status IS NULL OR status != 'done')"
        
        # Apply sorting
        sort_map = {
            "priority": "priority DESC",
            "due": "due ASC",
            "created": "created ASC",
            "id": "id ASC",
        }
        query += f" ORDER BY {sort_map.get(sort, 'priority DESC')}"
        
        rows = safe_query(query, tuple(params))
        
        result = []
        for row in rows:
            try:
                result.append(self.from_row_func(dict(row)))
            except Exception as e:
                logger.error(f"Failed to parse task row: {e}", exc_info=True)
        
        return result
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get all tasks with specific status."""
        return self.query_tasks(status=status.value)
    
    def get_active_tasks(self) -> List[Task]:
        """Get all active tasks."""
        return self.get_tasks_by_status(TaskStatus.ACTIVE)


# Simple test function
def test_new_task_repository():
    """Quick test to verify the new repository works."""
    try:
        repo = TaskRepository()
        
        # Test basic operations
        print("Testing TaskRepository...")
        
        # Test get_all (should work with existing data)
        tasks = repo.get_all()
        print(f"✅ Found {len(tasks)} existing tasks")
        
        # Test creating a new task
        test_task_data = {
            'title': 'Test Repository Task',
            'project': 'Architecture Test',
            'importance': 3,
            'status': TaskStatus.BACKLOG
        }
        
        new_task = repo.add(test_task_data)
        print(f"✅ Created task: {new_task.title} (ID: {new_task.id})")
        
        # Test get_by_id
        retrieved = repo.get_by_id(new_task.id)
        print(f"✅ Retrieved task: {retrieved.title}")
        
        # Test query_tasks
        filtered = repo.query_tasks(title_contains="Repository")
        print(f"✅ Query returned {len(filtered)} tasks")
        
        # Test update
        repo.update(new_task.id, {'notes': 'Updated via new repository'})
        updated = repo.get_by_id(new_task.id)
        print(f"✅ Updated task notes: {updated.notes}")
        
        print("🎉 All tests passed! New repository is working.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_new_task_repository()
