"""
Database logging configuration and custom handlers
"""

import logging
import json
import traceback
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from flask import request, has_request_context, Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError

class DatabaseLogHandler(logging.Handler):
    """Custom logging handler that writes logs to the ApplicationErrorLog table"""
    
    def __init__(self, db: SQLAlchemy, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self.db = db
        self.request_id = None
        
    def emit(self, record: logging.LogRecord) -> None:
        """Write log record to database"""
        try:
            # Import here to avoid circular imports
            from app.models import ApplicationErrorLog
            
            # Get request context if available
            request_id = getattr(record, 'request_id', None)
            if not request_id and has_request_context():
                request_id = getattr(request, 'request_id', None)
            
            # Extract source location info
            source_file = getattr(record, 'pathname', None)
            source_function = getattr(record, 'funcName', None)
            source_line = getattr(record, 'lineno', None)
            
            # Build context data
            context = {
                'logger_name': record.name,
                'module': getattr(record, 'module', None),
                'process': record.process,
                'thread': record.thread,
                'thread_name': record.threadName,
            }
            
            # Add extra context if available
            if hasattr(record, 'extra_context'):
                context.update(record.extra_context)
            
            # Get stack trace for errors
            stack_trace = None
            if record.exc_info:
                stack_trace = ''.join(traceback.format_exception(*record.exc_info))
            
            # Create database log entry
            log_entry = ApplicationErrorLog(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelname,
                message=record.getMessage(),
                context=context,
                request_id=request_id,
                user_id=getattr(record, 'user_id', None),
                stack_trace=stack_trace,
                source_file=source_file,
                source_function=source_function,
                source_line=source_line
            )
            
            # Save to database
            self.db.session.add(log_entry)
            self.db.session.commit()
            
        except SQLAlchemyError as e:
            # Avoid infinite recursion by not logging database errors
            # Use stderr to ensure error is captured in production logs
            import sys
            sys.stderr.write(f"Database logging error: {e}\n")
            self.db.session.rollback()
        except Exception as e:
            # Handle other logging errors
            import sys
            sys.stderr.write(f"Logging handler error: {e}\n")

class RequestIDFilter(logging.Filter):
    """Filter to add request ID to log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            # Get or create request ID
            if not hasattr(request, 'request_id'):
                request.request_id = str(uuid.uuid4())
            record.request_id = request.request_id
        else:
            record.request_id = None
        return True

def setup_logging(app: Flask, db: SQLAlchemy) -> logging.Logger:
    """Setup application logging configuration"""
    
    # Create custom formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(request_id)s - %(message)s'
    )
    
    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIDFilter())
    
    # Setup database handler for production
    db_handler = DatabaseLogHandler(db)
    db_handler.setLevel(logging.WARNING)  # Only log warnings and above to database
    db_handler.addFilter(RequestIDFilter())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Add database handler in production
    if not app.debug:
        root_logger.addHandler(db_handler)
    
    # Configure app logger
    app.logger.addHandler(console_handler)
    if not app.debug:
        app.logger.addHandler(db_handler)
    
    return root_logger

def log_error(message: str, context: Optional[Dict[str, Any]] = None, exc_info: Optional[bool] = None, level: int = logging.ERROR) -> None:
    """Helper function to log errors with context"""
    logger = logging.getLogger(__name__)
    
    # Add extra context to log record
    extra = {}
    if context:
        extra['extra_context'] = context
    
    logger.log(level, message, exc_info=exc_info, extra=extra)

def log_performance(operation: str, duration: float, context: Optional[Dict[str, Any]] = None) -> None:
    """Helper function to log performance metrics"""
    logger = logging.getLogger('performance')
    
    context = context or {}
    context.update({
        'operation': operation,
        'duration_ms': duration * 1000,  # Convert to milliseconds
        'performance_metric': True
    })
    
    extra = {'extra_context': context}
    logger.info(f"Performance: {operation} took {duration:.3f}s", extra=extra)