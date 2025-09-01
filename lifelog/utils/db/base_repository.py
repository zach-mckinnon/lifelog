# lifelog/utils/db/base_repository.py
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union

from lifelog.config.config_manager import is_host_server
from lifelog.utils.db import (
    safe_execute, safe_query, fetch_from_server, get_last_synced, 
    set_last_synced, should_sync, is_direct_db_mode, 
    queue_sync_operation, process_sync_queue, add_record, update_record
)

logger = logging.getLogger(__name__)

T = TypeVar('T')  # Model type


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base class for all repositories in the lifelog system.
    Handles common CRUD operations, sync logic, and validation.
    """
    
    def __init__(self, table_name: str, model_class: Type[T], from_row_func):
        self.table_name = table_name
        self.model_class = model_class
        self.from_row_func = from_row_func
        self._field_names = None
    
    @property
    def field_names(self) -> List[str]:
        """Get field names excluding 'id' (cached)."""
        if self._field_names is None:
            from dataclasses import fields
            self._field_names = [
                f.name for f in fields(self.model_class) 
                if f.name != "id"
            ]
        return self._field_names
    
    # ─── ABSTRACT METHODS ───
    
    @abstractmethod
    def get_sync_endpoint(self) -> str:
        """Return sync endpoint name (e.g., 'tasks', 'time_history')."""
        pass
    
    @abstractmethod
    def validate_before_save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize data before saving. Override in subclasses."""
        return data
    
    # ─── SYNC OPERATIONS ───
    
    def _pull_changed_from_host(self) -> None:
        """Pull changed records from host since last sync."""
        if not should_sync():
            return
            
        try:
            # Push local changes first
            process_sync_queue()
            
            # Get last sync timestamp
            last_ts = get_last_synced(self.get_sync_endpoint())
            params = {"since": last_ts} if last_ts else {}
            
            # Fetch remote changes
            remote_list = fetch_from_server(self.get_sync_endpoint(), params=params) or []
            
            # Upsert each remote record
            for remote in remote_list:
                self.upsert_local(remote)
                
            # Update last sync timestamp
            set_last_synced(self.get_sync_endpoint(), datetime.now().isoformat())
            
        except Exception as e:
            logger.error(f"Failed to pull changes for {self.table_name}: {e}", exc_info=True)
    
    def upsert_local(self, data: Dict[str, Any]) -> None:
        """Upsert a record from server payload."""
        uid_val = data.get("uid")
        if not uid_val:
            logger.warning(f"Cannot upsert {self.table_name} without uid")
            return
            
        try:
            # Normalize deleted flag
            if 'deleted' in data:
                data['deleted'] = 1 if data.get('deleted') else 0
                
            # Check if record exists
            rows = safe_query(f"SELECT id FROM {self.table_name} WHERE uid = ?", (uid_val,))
            
            if rows:
                # Update existing
                local_id = rows[0]["id"]
                updates = {k: data[k] for k in self.field_names if k in data}
                if updates:
                    update_record(self.table_name, local_id, updates)
            else:
                # Insert new
                record = {}
                for k in self.field_names:
                    if k in data:
                        record[k] = data[k]
                
                # Set defaults
                now_iso = datetime.now().isoformat()
                record.setdefault('uid', uid_val)
                record.setdefault('updated_at', now_iso)
                record.setdefault('deleted', 0)
                
                add_record(self.table_name, record, self.field_names)
                
        except Exception as e:
            logger.error(f"Failed to upsert {self.table_name} uid={uid_val}: {e}", exc_info=True)
    
    # ─── CRUD OPERATIONS ───
    
    def get_all(self, **filters) -> List[T]:
        """Get all records with optional filters."""
        if should_sync():
            self._pull_changed_from_host()
            
        query = f"SELECT * FROM {self.table_name} WHERE 1=1"
        params = []
        
        # Apply filters
        for key, value in filters.items():
            if value is not None:
                query += f" AND {key} = ?"
                params.append(value)
        
        query += " ORDER BY id ASC"
        rows = safe_query(query, tuple(params))
        
        result = []
        for row in rows:
            try:
                result.append(self.from_row_func(dict(row)))
            except Exception as e:
                logger.error(f"Failed to parse {self.table_name} row: {e}", exc_info=True)
        
        return result
    
    def get_by_id(self, record_id: int) -> Optional[T]:
        """Get record by numeric ID."""
        if should_sync():
            self._pull_changed_from_host()
            
        rows = safe_query(f"SELECT * FROM {self.table_name} WHERE id = ?", (record_id,))
        if not rows:
            return None
            
        try:
            return self.from_row_func(dict(rows[0]))
        except Exception as e:
            logger.error(f"Failed to parse {self.table_name} row for id={record_id}: {e}", exc_info=True)
            return None
    
    def get_by_uid(self, uid_val: str) -> Optional[T]:
        """Get record by UID."""
        if should_sync():
            self._pull_changed_from_host()
            
        rows = safe_query(f"SELECT * FROM {self.table_name} WHERE uid = ?", (uid_val,))
        if not rows:
            return None
            
        try:
            return self.from_row_func(dict(rows[0]))
        except Exception as e:
            logger.error(f"Failed to parse {self.table_name} row for uid={uid_val}: {e}", exc_info=True)
            return None
    
    def add(self, data: Dict[str, Any]) -> T:
        """Add new record."""
        # Validate and normalize
        data = self.validate_before_save(data)
        
        # Set defaults
        now = datetime.now()
        data.setdefault('uid', str(uuid.uuid4()))
        data.setdefault('updated_at', now)
        data.setdefault('deleted', 0)
        
        # Ensure all fields exist
        for field in self.field_names:
            data.setdefault(field, None)
        
        # Insert locally
        if is_direct_db_mode():
            new_id = add_record(self.table_name, data, self.field_names)
            return self.get_by_id(new_id)
        else:
            add_record(self.table_name, data, self.field_names)
            queue_sync_operation(self.get_sync_endpoint(), "create", data)
            process_sync_queue()
            return self.get_by_uid(data["uid"])
    
    def update(self, record_id: int, updates: Dict[str, Any]) -> None:
        """Update existing record."""
        # Validate and normalize
        updates = self.validate_before_save(updates)
        updates['updated_at'] = datetime.now()
        
        # Update locally
        update_record(self.table_name, record_id, updates)
        
        # Sync if needed
        if not is_direct_db_mode() and should_sync():
            # Get full record for sync
            rows = safe_query(f"SELECT * FROM {self.table_name} WHERE id = ?", (record_id,))
            if rows:
                full_record = dict(rows[0])
                queue_sync_operation(self.get_sync_endpoint(), "update", full_record)
                process_sync_queue()
    
    def delete(self, record_id: int) -> None:
        """Delete record (soft delete in client mode)."""
        if is_direct_db_mode():
            safe_execute(f"DELETE FROM {self.table_name} WHERE id = ?", (record_id,))
        else:
            # Soft delete
            rows = safe_query(f"SELECT uid FROM {self.table_name} WHERE id = ?", (record_id,))
            uid_val = rows[0]["uid"] if rows and rows[0]["uid"] else None
            
            now_iso = datetime.now().isoformat()
            safe_execute(
                f"UPDATE {self.table_name} SET deleted = 1, updated_at = ? WHERE id = ?", 
                (now_iso, record_id)
            )
            
            if uid_val and should_sync():
                payload = {"uid": uid_val, "deleted": True, "updated_at": now_iso}
                queue_sync_operation(self.get_sync_endpoint(), "delete", payload)
                process_sync_queue()
    
    # ─── HOST-ONLY OPERATIONS ───
    
    def update_by_uid(self, uid_val: str, updates: Dict[str, Any]) -> None:
        """Host-only: Update record by UID."""
        if not is_host_server():
            return
            
        updates = self.validate_before_save(updates)
        updates['updated_at'] = datetime.now()
        
        cols = ", ".join(f"{k}=?" for k in updates)
        params = tuple(updates.values()) + (uid_val,)
        safe_execute(f"UPDATE {self.table_name} SET {cols} WHERE uid = ?", params)
    
    def delete_by_uid(self, uid_val: str) -> None:
        """Host-only: Soft delete by UID."""
        if not is_host_server():
            return
            
        now_iso = datetime.now().isoformat()
        safe_execute(
            f"UPDATE {self.table_name} SET deleted = 1, updated_at = ? WHERE uid = ?", 
            (now_iso, uid_val)
        )
