#!/usr/bin/env python3
"""
Error handling and logging system for Iranian Archive Workflow.

This module provides comprehensive error handling with categorization,
retry mechanisms, and detailed logging for workflow operations.
"""

import logging
import time
import traceback
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import json


class ErrorCategory(Enum):
    """Categories of errors that can occur during workflow execution."""
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


@dataclass
class ErrorDetails:
    """Detailed information about an error occurrence."""
    category: ErrorCategory
    message: str
    timestamp: datetime
    url: Optional[str] = None
    file_path: Optional[str] = None
    exception_type: Optional[str] = None
    traceback_info: Optional[str] = None
    retry_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error details to dictionary for serialization."""
        return {
            'category': self.category.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'url': self.url,
            'file_path': self.file_path,
            'exception_type': self.exception_type,
            'traceback_info': self.traceback_info,
            'retry_count': self.retry_count,
            'context': self.context
        }


@dataclass
class ProcessingSummary:
    """Summary of processing results including errors and successes."""
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    errors_by_category: Dict[ErrorCategory, int] = field(default_factory=dict)
    error_details: List[ErrorDetails] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_operations == 0:
            return 0.0
        return (self.successful_operations / self.total_operations) * 100
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate processing duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary for serialization."""
        return {
            'total_operations': self.total_operations,
            'successful_operations': self.successful_operations,
            'failed_operations': self.failed_operations,
            'success_rate': round(self.success_rate, 2),
            'duration_seconds': self.duration,
            'errors_by_category': {cat.value: count for cat, count in self.errors_by_category.items()},
            'error_details': [error.to_dict() for error in self.error_details],
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None
        }


class WorkflowLogger:
    """Enhanced logger with structured error handling and categorization."""
    
    def __init__(self, name: str = "iranian_archive_workflow", log_level: int = logging.INFO):
        """Initialize the workflow logger.
        
        Args:
            name: Logger name
            log_level: Logging level (default: INFO)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create console handler with detailed formatting
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Create detailed formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Track processing summary
        self.summary = ProcessingSummary()
    
    def start_processing(self) -> None:
        """Mark the start of processing operations."""
        self.summary.start_time = datetime.now()
        self.logger.info("Starting workflow processing")
    
    def end_processing(self) -> None:
        """Mark the end of processing operations."""
        self.summary.end_time = datetime.now()
        self.logger.info(f"Workflow processing completed in {self.summary.duration:.2f} seconds")
        self._log_summary()
    
    def log_error(self, error: Exception, category: ErrorCategory, 
                  url: Optional[str] = None, file_path: Optional[str] = None,
                  context: Optional[Dict[str, Any]] = None, retry_count: int = 0) -> ErrorDetails:
        """Log an error with detailed categorization and context.
        
        Args:
            error: The exception that occurred
            category: Category of the error
            url: URL related to the error (if applicable)
            file_path: File path related to the error (if applicable)
            context: Additional context information
            retry_count: Number of retry attempts made
            
        Returns:
            ErrorDetails object containing structured error information
        """
        error_details = ErrorDetails(
            category=category,
            message=str(error),
            timestamp=datetime.now(),
            url=url,
            file_path=file_path,
            exception_type=type(error).__name__,
            traceback_info=traceback.format_exc(),
            retry_count=retry_count,
            context=context or {}
        )
        
        # Add to summary
        self.summary.error_details.append(error_details)
        self.summary.failed_operations += 1
        
        # Update category counts
        if category not in self.summary.errors_by_category:
            self.summary.errors_by_category[category] = 0
        self.summary.errors_by_category[category] += 1
        
        # Log the error
        log_message = self._format_error_message(error_details)
        self.logger.error(log_message)
        
        return error_details
    
    def log_success(self, operation: str, url: Optional[str] = None, 
                   file_path: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """Log a successful operation.
        
        Args:
            operation: Description of the successful operation
            url: URL related to the operation (if applicable)
            file_path: File path related to the operation (if applicable)
            context: Additional context information
        """
        self.summary.successful_operations += 1
        
        log_parts = [operation]
        if url:
            log_parts.append(f"URL: {url}")
        if file_path:
            log_parts.append(f"File: {file_path}")
        if context:
            log_parts.append(f"Context: {context}")
        
        self.logger.info(" | ".join(log_parts))
    
    def increment_total_operations(self, count: int = 1) -> None:
        """Increment the total operations counter.
        
        Args:
            count: Number of operations to add (default: 1)
        """
        self.summary.total_operations += count
    
    def _format_error_message(self, error_details: ErrorDetails) -> str:
        """Format error details into a readable log message.
        
        Args:
            error_details: Error details to format
            
        Returns:
            Formatted error message
        """
        parts = [
            f"[{error_details.category.value.upper()}]",
            error_details.message
        ]
        
        if error_details.url:
            parts.append(f"URL: {error_details.url}")
        
        if error_details.file_path:
            parts.append(f"File: {error_details.file_path}")
        
        if error_details.retry_count > 0:
            parts.append(f"Retry: {error_details.retry_count}")
        
        if error_details.exception_type:
            parts.append(f"Type: {error_details.exception_type}")
        
        return " | ".join(parts)
    
    def _log_summary(self) -> None:
        """Log processing summary statistics."""
        self.logger.info("=" * 60)
        self.logger.info("WORKFLOW PROCESSING SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total Operations: {self.summary.total_operations}")
        self.logger.info(f"Successful: {self.summary.successful_operations}")
        self.logger.info(f"Failed: {self.summary.failed_operations}")
        self.logger.info(f"Success Rate: {self.summary.success_rate:.1f}%")
        
        if self.summary.duration:
            self.logger.info(f"Duration: {self.summary.duration:.2f} seconds")
        
        if self.summary.errors_by_category:
            self.logger.info("Errors by Category:")
            for category, count in self.summary.errors_by_category.items():
                self.logger.info(f"  {category.value}: {count}")
        
        self.logger.info("=" * 60)
    
    def save_error_report(self, file_path: str) -> None:
        """Save detailed error report to JSON file.
        
        Args:
            file_path: Path to save the error report
        """
        try:
            report_data = self.summary.to_dict()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Error report saved to: {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to save error report: {e}")


class RetryHandler:
    """Handles retry logic with exponential backoff for network operations."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, 
                 max_delay: float = 60.0, backoff_factor: float = 2.0):
        """Initialize retry handler.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for first retry
            max_delay: Maximum delay in seconds between retries
            backoff_factor: Multiplier for exponential backoff
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def execute_with_retry(self, operation: Callable, *args, 
                          error_categories: Optional[List[ErrorCategory]] = None,
                          logger: Optional[WorkflowLogger] = None,
                          context: Optional[Dict[str, Any]] = None, **kwargs) -> Tuple[bool, Any, Optional[ErrorDetails]]:
        """Execute an operation with retry logic.
        
        Args:
            operation: Function to execute
            *args: Positional arguments for the operation
            error_categories: List of error categories that should trigger retries
            logger: Logger instance for error reporting
            context: Additional context for error logging
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Tuple of (success: bool, result: Any, error_details: Optional[ErrorDetails])
        """
        if error_categories is None:
            error_categories = [ErrorCategory.NETWORK]
        
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = operation(*args, **kwargs)
                
                if logger and attempt > 0:
                    logger.log_success(
                        f"Operation succeeded after {attempt} retries",
                        context={'operation': operation.__name__, 'attempts': attempt + 1}
                    )
                
                return True, result, None
                
            except Exception as e:
                # Categorize the error
                error_category = self._categorize_error(e)
                
                # Log the error
                if logger:
                    last_error = logger.log_error(
                        e, error_category, 
                        context=context, 
                        retry_count=attempt
                    )
                
                # Check if this error type should trigger a retry
                if attempt < self.max_retries and error_category in error_categories:
                    delay = self._calculate_delay(attempt)
                    
                    if logger:
                        logger.logger.warning(
                            f"Retrying operation in {delay:.1f} seconds "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                    
                    time.sleep(delay)
                    continue
                else:
                    # No more retries or error type doesn't warrant retry
                    if logger:
                        logger.logger.error(
                            f"Operation failed after {attempt + 1} attempts: {e}"
                        )
                    return False, None, last_error
        
        return False, None, last_error
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)
    
    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize an error based on its type and message.
        
        Args:
            error: Exception to categorize
            
        Returns:
            ErrorCategory enum value
        """
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # Network-related errors
        network_indicators = [
            'requests.exceptions', 'connectionerror', 'timeout', 'httperror',
            'urlerror', 'socket', 'dns', 'network', 'connection', 'unreachable'
        ]
        
        if any(indicator in error_type.lower() or indicator in error_message 
               for indicator in network_indicators):
            return ErrorCategory.NETWORK
        
        # Filesystem-related errors
        filesystem_indicators = [
            'oserror', 'ioerror', 'permissionerror', 'filenotfounderror',
            'isadirectoryerror', 'notadirectoryerror', 'disk', 'space',
            'permission denied', 'no such file', 'directory'
        ]
        
        if any(indicator in error_type.lower() or indicator in error_message 
               for indicator in filesystem_indicators):
            return ErrorCategory.FILESYSTEM
        
        # Validation errors (check first for specific validation types)
        validation_indicators = [
            'valueerror', 'typeerror', 'keyerror', 'indexerror'
        ]
        
        if any(indicator in error_type.lower() for indicator in validation_indicators):
            return ErrorCategory.VALIDATION
        
        # Configuration-related errors
        configuration_indicators = [
            'configurationerror', 'yaml', 'json', 'parsing', 'configuration',
            'missing', 'malformed'
        ]
        
        if any(indicator in error_type.lower() or indicator in error_message 
               for indicator in configuration_indicators):
            return ErrorCategory.CONFIGURATION
        
        # Check for validation-specific messages
        validation_message_indicators = ['validation', 'invalid', 'format']
        
        if any(indicator in error_message for indicator in validation_message_indicators):
            return ErrorCategory.VALIDATION
        
        return ErrorCategory.UNKNOWN


def create_workflow_logger(name: str = "iranian_archive_workflow", 
                          log_level: int = logging.INFO) -> WorkflowLogger:
    """Factory function to create a configured workflow logger.
    
    Args:
        name: Logger name
        log_level: Logging level
        
    Returns:
        Configured WorkflowLogger instance
    """
    return WorkflowLogger(name, log_level)


def create_retry_handler(max_retries: int = 3, base_delay: float = 1.0) -> RetryHandler:
    """Factory function to create a configured retry handler.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff
        
    Returns:
        Configured RetryHandler instance
    """
    return RetryHandler(max_retries=max_retries, base_delay=base_delay)


class ErrorHandler:
    """Main error handler that combines logging and retry functionality."""
    
    def __init__(self, log_file: str = "workflow_errors.log"):
        self.logger = WorkflowLogger(log_file)
        self.retry_handler = RetryHandler()
    
    def log_error(self, message: str, category: str, **kwargs) -> None:
        """Log an error with the specified category."""
        try:
            error_category = ErrorCategory(category)
        except ValueError:
            error_category = ErrorCategory.UNKNOWN
        
        self.logger.log_error(message, error_category, **kwargs)
    
    def execute_with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with retry logic."""
        return self.retry_handler.execute_with_retry(operation, *args, **kwargs)
    
    def get_error_summary(self) -> ProcessingSummary:
        """Get summary of logged errors."""
        return self.logger.get_processing_summary()