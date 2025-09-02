# lifelog/utils/error_handler.py
"""
Centralized error handling and validation for lifelog.
"""
import sqlite3
import logging
from functools import wraps
from typing import Any, Dict, Optional, Union
from datetime import datetime
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

class ValidationError(ValueError):
    """Raised when data validation fails."""
    pass

class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass

def handle_db_errors(operation_name: str):
    """Decorator for consistent database error handling."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if 'locked' in error_msg or 'busy' in error_msg:
                    logger.warning(f"{operation_name} - Database busy: {e}")
                    console.print(f"[yellow]Database busy, please try again in a moment[/yellow]")
                else:
                    logger.error(f"{operation_name} - DB operational error: {e}")
                    console.print(f"[red]Database error in {operation_name}[/red]")
                raise DatabaseError(f"Database operation failed: {e}")
            except sqlite3.Error as e:
                logger.error(f"{operation_name} - DB error: {e}")
                console.print(f"[red]Database error in {operation_name}[/red]")
                raise DatabaseError(f"Database error: {e}")
            except ValidationError as e:
                logger.warning(f"{operation_name} - Validation error: {e}")
                console.print(f"[red]Validation error: {e}[/red]")
                raise
            except Exception as e:
                logger.error(f"{operation_name} - Unexpected error: {e}", exc_info=True)
                console.print(f"[red]Unexpected error in {operation_name}[/red]")
                raise
        return wrapper
    return decorator

def validate_task_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize task data before database operations."""
    if not data:
        raise ValidationError("Task data cannot be empty")
    
    # Title validation
    title = data.get("title", "").strip()
    if not title:
        raise ValidationError("Task title is required")
    if len(title) > 200:
        raise ValidationError("Task title cannot exceed 200 characters")
    data["title"] = title
    
    # Importance validation  
    if "importance" in data and data["importance"] is not None:
        try:
            importance = int(data["importance"])
            if not 1 <= importance <= 5:
                raise ValidationError("Importance must be between 1 and 5")
            data["importance"] = importance
        except (ValueError, TypeError):
            raise ValidationError("Importance must be a valid integer")
    
    # Date validation
    for date_field in ["due", "created"]:
        if date_field in data and data[date_field]:
            if isinstance(data[date_field], str):
                try:
                    datetime.fromisoformat(data[date_field])
                except ValueError:
                    raise ValidationError(f"Invalid {date_field} date format")
    
    # String field sanitization
    for field in ["notes", "category", "project", "tags"]:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
            if len(data[field]) > 500:  # Reasonable limit
                data[field] = data[field][:500]
    
    return data

def validate_time_entry_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize time entry data."""
    if not data:
        raise ValidationError("Time entry data cannot be empty")
    
    # Title validation
    title = data.get("title", "").strip()
    if not title:
        raise ValidationError("Time entry title is required") 
    if len(title) > 200:
        raise ValidationError("Time entry title cannot exceed 200 characters")
    data["title"] = title
    
    # Time validation
    start_time = data.get("start")
    end_time = data.get("end")
    
    if start_time and end_time:
        try:
            if isinstance(start_time, str):
                start_dt = datetime.fromisoformat(start_time)
            else:
                start_dt = start_time
                
            if isinstance(end_time, str):
                end_dt = datetime.fromisoformat(end_time)
            else:
                end_dt = end_time
                
            if end_dt <= start_dt:
                raise ValidationError("End time must be after start time")
        except ValueError as e:
            raise ValidationError(f"Invalid time format: {e}")
    
    # Duration validation
    if "duration_minutes" in data and data["duration_minutes"] is not None:
        try:
            duration = float(data["duration_minutes"])
            if duration < 0:
                raise ValidationError("Duration cannot be negative")
            if duration > 1440:  # 24 hours in minutes
                logger.warning(f"Very long duration detected: {duration} minutes")
            data["duration_minutes"] = duration
        except (ValueError, TypeError):
            raise ValidationError("Duration must be a valid number")
    
    # Distracted minutes validation
    if "distracted_minutes" in data and data["distracted_minutes"] is not None:
        try:
            distracted = float(data["distracted_minutes"])
            if distracted < 0:
                raise ValidationError("Distracted minutes cannot be negative")
            data["distracted_minutes"] = distracted
        except (ValueError, TypeError):
            raise ValidationError("Distracted minutes must be a valid number")
    
    # String field sanitization
    for field in ["notes", "category", "project", "tags"]:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
            if len(data[field]) > 500:
                data[field] = data[field][:500]
    
    return data

def validate_tracker_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize tracker data."""
    if not data:
        raise ValidationError("Tracker data cannot be empty")
    
    # Title validation
    title = data.get("title", "").strip()
    if not title:
        raise ValidationError("Tracker title is required")
    if len(title) > 100:
        raise ValidationError("Tracker title cannot exceed 100 characters")
    data["title"] = title
    
    # Type validation
    tracker_type = data.get("type", "").strip()
    valid_types = ["bool", "number", "scale", "duration", "count", "text"]
    if tracker_type not in valid_types:
        raise ValidationError(f"Tracker type must be one of: {', '.join(valid_types)}")
    
    # String field sanitization
    for field in ["notes", "category", "tags"]:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
            if len(data[field]) > 500:
                data[field] = data[field][:500]
    
    return data

def safe_convert_to_int(value: Any, field_name: str, default: Optional[int] = None) -> Optional[int]:
    """Safely convert a value to integer with proper error handling."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        if default is not None:
            logger.warning(f"Could not convert {field_name} '{value}' to int, using default {default}")
            return default
        raise ValidationError(f"Invalid {field_name}: must be a valid integer")

def safe_convert_to_float(value: Any, field_name: str, default: Optional[float] = None) -> Optional[float]:
    """Safely convert a value to float with proper error handling."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        if default is not None:
            logger.warning(f"Could not convert {field_name} '{value}' to float, using default {default}")
            return default
        raise ValidationError(f"Invalid {field_name}: must be a valid number")

def sanitize_string(value: Any, max_length: int = 500) -> Optional[str]:
    """Sanitize and truncate string values."""
    if value is None:
        return None
    
    sanitized = str(value).strip()
    if not sanitized:
        return None
    
    if len(sanitized) > max_length:
        logger.warning(f"Truncating string from {len(sanitized)} to {max_length} characters")
        sanitized = sanitized[:max_length]
    
    return sanitized