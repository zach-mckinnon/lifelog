# lifelog/utils/pi_optimizer.py
"""
Raspberry Pi Zero 2W specific optimizations for memory and performance.
"""
import os
import gc
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

logger = logging.getLogger(__name__)

class PiOptimizer:
    """Optimize lifelog for Raspberry Pi Zero 2W constraints."""
    
    def __init__(self):
        self._memory_mb = None
        self._is_pi = None
        self._settings = None
    
    @property 
    def memory_mb(self) -> float:
        """Get total system memory in MB (cached)."""
        if self._memory_mb is None:
            try:
                if HAS_PSUTIL:
                    self._memory_mb = psutil.virtual_memory().total / 1024 / 1024
                else:
                    # Fallback: try to get from /proc/meminfo on Linux
                    try:
                        with open('/proc/meminfo', 'r') as f:
                            meminfo = f.read()
                            for line in meminfo.split('\n'):
                                if line.startswith('MemTotal:'):
                                    kb = int(line.split()[1])
                                    self._memory_mb = kb / 1024
                                    break
                            else:
                                self._memory_mb = 1024  # Default assumption
                    except (FileNotFoundError, OSError, ValueError):
                        self._memory_mb = 1024  # Default assumption
            except Exception:
                self._memory_mb = 1024  # Default assumption
        return self._memory_mb
    
    @property
    def is_raspberry_pi(self) -> bool:
        """Detect if running on Raspberry Pi (cached)."""
        if self._is_pi is None:
            try:
                # Check for Pi-specific files
                pi_files = [
                    "/sys/firmware/devicetree/base/model",
                    "/proc/device-tree/model",
                    "/sys/firmware/devicetree/base/compatible"
                ]
                self._is_pi = any(Path(f).exists() for f in pi_files)
                
                # Also check for common Pi characteristics
                if not self._is_pi:
                    # ARM architecture check
                    with open('/proc/cpuinfo', 'r') as f:
                        cpu_info = f.read().lower()
                        self._is_pi = 'arm' in cpu_info and 'raspberry' in cpu_info
            except Exception:
                self._is_pi = False
        return self._is_pi
    
    def get_optimized_settings(self) -> Dict[str, Any]:
        """Get Pi-optimized settings based on available resources."""
        if self._settings is not None:
            return self._settings
            
        if self.is_raspberry_pi and self.memory_mb < 1024:  # Pi Zero/Pi 1
            self._settings = {
                "database": {
                    "cache_size": 5000,  # 5MB cache instead of 10MB
                    "mmap_size": 134217728,  # 128MB instead of 256MB
                    "temp_store": "MEMORY",
                    "journal_mode": "WAL",
                    "synchronous": "NORMAL",
                    "page_size": 1024,  # Smaller page size for limited RAM
                },
                "performance": {
                    "batch_size": 50,  # Smaller batches
                    "connection_timeout": 30,
                    "query_limit": 100,  # Limit result sets
                    "lazy_load_heavy_imports": True,
                },
                "memory": {
                    "gc_frequency": 50,  # More frequent garbage collection
                    "pandas_chunk_size": 1000,
                    "max_result_cache": 10,
                }
            }
        elif self.is_raspberry_pi:  # Pi 3/4 with more memory
            self._settings = {
                "database": {
                    "cache_size": 10000,  # 10MB cache
                    "mmap_size": 268435456,  # 256MB
                    "temp_store": "MEMORY", 
                    "journal_mode": "WAL",
                    "synchronous": "NORMAL",
                    "page_size": 4096,
                },
                "performance": {
                    "batch_size": 100,
                    "connection_timeout": 30,
                    "query_limit": 500,
                    "lazy_load_heavy_imports": True,
                },
                "memory": {
                    "gc_frequency": 100,
                    "pandas_chunk_size": 5000,
                    "max_result_cache": 50,
                }
            }
        else:  # Development/Desktop
            self._settings = {
                "database": {
                    "cache_size": 20000,  # 20MB cache
                    "mmap_size": 536870912,  # 512MB
                    "temp_store": "MEMORY",
                    "journal_mode": "WAL", 
                    "synchronous": "NORMAL",
                    "page_size": 4096,
                },
                "performance": {
                    "batch_size": 500,
                    "connection_timeout": 10,
                    "query_limit": 1000,
                    "lazy_load_heavy_imports": False,
                },
                "memory": {
                    "gc_frequency": 500,
                    "pandas_chunk_size": 10000,
                    "max_result_cache": 100,
                }
            }
        
        logger.info(f"Pi Optimizer initialized - Pi: {self.is_raspberry_pi}, Memory: {self.memory_mb}MB")
        return self._settings
    
    def optimize_connection_settings(self, connection) -> None:
        """Apply Pi-optimized SQLite settings to a connection."""
        settings = self.get_optimized_settings()["database"]
        
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA journal_mode = {settings['journal_mode']}")
            connection.execute(f"PRAGMA synchronous = {settings['synchronous']}")
            connection.execute(f"PRAGMA cache_size = {settings['cache_size']}")
            connection.execute(f"PRAGMA temp_store = {settings['temp_store']}")
            connection.execute(f"PRAGMA mmap_size = {settings['mmap_size']}")
            connection.execute(f"PRAGMA page_size = {settings['page_size']}")
            
            # Pi-specific optimizations
            if self.is_raspberry_pi:
                connection.execute("PRAGMA optimize")  # SQLite query planner optimization
                connection.execute("PRAGMA analysis_limit = 1000")  # Limit analysis for speed
                
        except Exception as e:
            logger.warning(f"Failed to apply some connection optimizations: {e}")
    
    def periodic_cleanup(self) -> None:
        """Perform periodic cleanup optimized for Pi constraints."""
        settings = self.get_optimized_settings()
        
        try:
            # Garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collection freed {collected} objects")
            
            # Memory pressure check on Pi
            if self.is_raspberry_pi and HAS_PSUTIL:
                available_mb = psutil.virtual_memory().available / 1024 / 1024
                if available_mb < 100:  # Less than 100MB available
                    logger.warning(f"Low memory: {available_mb:.1f}MB available")
                    # More aggressive cleanup
                    gc.collect()
                    
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

    @contextmanager
    def memory_efficient_operation(self, operation_name: str):
        """Context manager for memory-efficient operations."""
        settings = self.get_optimized_settings()
        gc_freq = settings["memory"]["gc_frequency"]
        
        try:
            logger.debug(f"Starting memory-efficient operation: {operation_name}")
            yield
        finally:
            # Cleanup after potentially memory-intensive operation
            if self.is_raspberry_pi:
                gc.collect()
            logger.debug(f"Completed memory-efficient operation: {operation_name}")

# Global instance
pi_optimizer = PiOptimizer()

def get_pi_settings() -> Dict[str, Any]:
    """Get Pi-optimized settings - convenience function."""
    return pi_optimizer.get_optimized_settings()

def is_raspberry_pi() -> bool:
    """Check if running on Raspberry Pi - convenience function."""
    return pi_optimizer.is_raspberry_pi

def optimize_for_pi():
    """Apply Pi-specific optimizations - convenience function."""
    pi_optimizer.periodic_cleanup()
    return pi_optimizer.get_optimized_settings()