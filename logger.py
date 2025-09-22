"""
Logging system for KC868-AP Control System
Provides structured logging with different levels and output methods
"""

import time
import sys
from config import config

class Logger:
    """Simple but effective logging system for MicroPython"""
    
    LEVELS = {
        'DEBUG': 0,
        'INFO': 1,
        'WARNING': 2,
        'ERROR': 3,
        'CRITICAL': 4
    }
    
    def __init__(self, name="KC868-AP"):
        self.name = name
        self.level = self.LEVELS.get(config.get_log_level(), 1)
        self.debug_mode = config.is_debug_mode()
    
    def _format_message(self, level, message, *args):
        """Format log message with timestamp and level"""
        timestamp = time.ticks_ms()
        level_name = level.upper()
        
        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                message = f"{message} {args}"
        
        return f"[{timestamp:08d}] {level_name:8s} [{self.name}] {message}"
    
    def _log(self, level, message, *args):
        """Internal logging method"""
        if self.LEVELS[level] >= self.level:
            formatted_msg = self._format_message(level, message, *args)
            print(formatted_msg)
            
            # In debug mode, also print to stderr for better visibility
            if self.debug_mode and level in ['ERROR', 'CRITICAL']:
                sys.print_exception()
    
    def debug(self, message, *args):
        """Log debug message"""
        self._log('DEBUG', message, *args)
    
    def info(self, message, *args):
        """Log info message"""
        self._log('INFO', message, *args)
    
    def warning(self, message, *args):
        """Log warning message"""
        self._log('WARNING', message, *args)
    
    def error(self, message, *args):
        """Log error message"""
        self._log('ERROR', message, *args)
    
    def critical(self, message, *args):
        """Log critical message"""
        self._log('CRITICAL', message, *args)
    
    def exception(self, message="Exception occurred"):
        """Log exception with traceback"""
        self.error(message)
        if self.debug_mode:
            sys.print_exception()

# Global logger instance
logger = Logger()
