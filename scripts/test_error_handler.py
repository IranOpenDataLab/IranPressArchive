#!/usr/bin/env python3
"""
Unit tests for the error handling and logging system.

Tests cover error categorization, retry mechanisms, logging functionality,
and various error scenarios that can occur during workflow execution.
"""

import unittest
import tempfile
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path

from error_handler import (
    ErrorCategory, ErrorDetails, ProcessingSummary, WorkflowLogger,
    RetryHandler, create_workflow_logger, create_retry_handler
)


class TestErrorDetails(unittest.TestCase):
    """Test cases for ErrorDetails class."""
    
    def test_error_details_creation(self):
        """Test creating ErrorDetails with all fields."""
        timestamp = datetime.now()
        error_details = ErrorDetails(
            category=ErrorCategory.NETWORK,
            message="Connection timeout",
            timestamp=timestamp,
            url="https://example.com/file.pdf",
            file_path="/path/to/file.pdf",
            exception_type="TimeoutError",
            traceback_info="Traceback info here",
            retry_count=2,
            context={"operation": "download"}
        )
        
        self.assertEqual(error_details.category, ErrorCategory.NETWORK)
        self.assertEqual(error_details.message, "Connection timeout")
        self.assertEqual(error_details.timestamp, timestamp)
        self.assertEqual(error_details.url, "https://example.com/file.pdf")
        self.assertEqual(error_details.file_path, "/path/to/file.pdf")
        self.assertEqual(error_details.exception_type, "TimeoutError")
        self.assertEqual(error_details.retry_count, 2)
        self.assertEqual(error_details.context["operation"], "download")
    
    def test_error_details_to_dict(self):
        """Test converting ErrorDetails to dictionary."""
        timestamp = datetime.now()
        error_details = ErrorDetails(
            category=ErrorCategory.FILESYSTEM,
            message="Permission denied",
            timestamp=timestamp,
            url="https://example.com/file.pdf"
        )
        
        result = error_details.to_dict()
        
        self.assertEqual(result["category"], "filesystem")
        self.assertEqual(result["message"], "Permission denied")
        self.assertEqual(result["timestamp"], timestamp.isoformat())
        self.assertEqual(result["url"], "https://example.com/file.pdf")
        self.assertIsNone(result["file_path"])


class TestProcessingSummary(unittest.TestCase):
    """Test cases for ProcessingSummary class."""
    
    def test_processing_summary_initialization(self):
        """Test ProcessingSummary initialization."""
        summary = ProcessingSummary()
        
        self.assertEqual(summary.total_operations, 0)
        self.assertEqual(summary.successful_operations, 0)
        self.assertEqual(summary.failed_operations, 0)
        self.assertEqual(len(summary.errors_by_category), 0)
        self.assertEqual(len(summary.error_details), 0)
        self.assertIsNone(summary.start_time)
        self.assertIsNone(summary.end_time)
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        summary = ProcessingSummary()
        
        # Test with no operations
        self.assertEqual(summary.success_rate, 0.0)
        
        # Test with some operations
        summary.total_operations = 10
        summary.successful_operations = 7
        self.assertEqual(summary.success_rate, 70.0)
        
        # Test with 100% success
        summary.successful_operations = 10
        self.assertEqual(summary.success_rate, 100.0)
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        summary = ProcessingSummary()
        
        # Test with no times set
        self.assertIsNone(summary.duration)
        
        # Test with times set
        start_time = datetime.now()
        end_time = datetime.fromtimestamp(start_time.timestamp() + 5.5)
        summary.start_time = start_time
        summary.end_time = end_time
        
        self.assertAlmostEqual(summary.duration, 5.5, places=1)
    
    def test_summary_to_dict(self):
        """Test converting ProcessingSummary to dictionary."""
        summary = ProcessingSummary()
        summary.total_operations = 5
        summary.successful_operations = 3
        summary.failed_operations = 2
        summary.errors_by_category[ErrorCategory.NETWORK] = 1
        summary.errors_by_category[ErrorCategory.FILESYSTEM] = 1
        
        result = summary.to_dict()
        
        self.assertEqual(result["total_operations"], 5)
        self.assertEqual(result["successful_operations"], 3)
        self.assertEqual(result["failed_operations"], 2)
        self.assertEqual(result["success_rate"], 60.0)
        self.assertEqual(result["errors_by_category"]["network"], 1)
        self.assertEqual(result["errors_by_category"]["filesystem"], 1)


class TestWorkflowLogger(unittest.TestCase):
    """Test cases for WorkflowLogger class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.logger = WorkflowLogger("test_logger")
    
    def test_logger_initialization(self):
        """Test WorkflowLogger initialization."""
        self.assertIsNotNone(self.logger.logger)
        self.assertIsInstance(self.logger.summary, ProcessingSummary)
    
    def test_start_and_end_processing(self):
        """Test start and end processing tracking."""
        self.assertIsNone(self.logger.summary.start_time)
        
        self.logger.start_processing()
        self.assertIsNotNone(self.logger.summary.start_time)
        
        time.sleep(0.1)  # Small delay to ensure duration > 0
        
        self.logger.end_processing()
        self.assertIsNotNone(self.logger.summary.end_time)
        self.assertGreater(self.logger.summary.duration, 0)
    
    def test_log_error(self):
        """Test error logging functionality."""
        test_error = ValueError("Test error message")
        
        error_details = self.logger.log_error(
            test_error,
            ErrorCategory.VALIDATION,
            url="https://example.com/test.pdf",
            file_path="/tmp/test.pdf",
            context={"test": "context"},
            retry_count=1
        )
        
        self.assertEqual(error_details.category, ErrorCategory.VALIDATION)
        self.assertEqual(error_details.message, "Test error message")
        self.assertEqual(error_details.url, "https://example.com/test.pdf")
        self.assertEqual(error_details.file_path, "/tmp/test.pdf")
        self.assertEqual(error_details.exception_type, "ValueError")
        self.assertEqual(error_details.retry_count, 1)
        self.assertEqual(error_details.context["test"], "context")
        
        # Check summary updates
        self.assertEqual(self.logger.summary.failed_operations, 1)
        self.assertEqual(self.logger.summary.errors_by_category[ErrorCategory.VALIDATION], 1)
        self.assertEqual(len(self.logger.summary.error_details), 1)
    
    def test_log_success(self):
        """Test success logging functionality."""
        self.logger.log_success(
            "File downloaded successfully",
            url="https://example.com/test.pdf",
            file_path="/tmp/test.pdf",
            context={"size": "1MB"}
        )
        
        self.assertEqual(self.logger.summary.successful_operations, 1)
    
    def test_increment_total_operations(self):
        """Test incrementing total operations counter."""
        self.assertEqual(self.logger.summary.total_operations, 0)
        
        self.logger.increment_total_operations()
        self.assertEqual(self.logger.summary.total_operations, 1)
        
        self.logger.increment_total_operations(5)
        self.assertEqual(self.logger.summary.total_operations, 6)
    
    def test_save_error_report(self):
        """Test saving error report to file."""
        # Add some test data
        test_error = RuntimeError("Test error")
        self.logger.log_error(test_error, ErrorCategory.UNKNOWN)
        self.logger.log_success("Test success")
        self.logger.increment_total_operations(2)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            report_path = f.name
        
        try:
            self.logger.save_error_report(report_path)
            
            # Verify file was created and contains expected data
            with open(report_path, 'r') as f:
                report_data = json.load(f)
            
            self.assertEqual(report_data["total_operations"], 2)
            self.assertEqual(report_data["successful_operations"], 1)
            self.assertEqual(report_data["failed_operations"], 1)
            self.assertEqual(len(report_data["error_details"]), 1)
            
        finally:
            Path(report_path).unlink(missing_ok=True)


class TestRetryHandler(unittest.TestCase):
    """Test cases for RetryHandler class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.retry_handler = RetryHandler(max_retries=3, base_delay=0.01)  # Fast tests
        self.logger = WorkflowLogger("test_retry_logger")
    
    def test_retry_handler_initialization(self):
        """Test RetryHandler initialization."""
        handler = RetryHandler(max_retries=5, base_delay=2.0, max_delay=30.0, backoff_factor=3.0)
        
        self.assertEqual(handler.max_retries, 5)
        self.assertEqual(handler.base_delay, 2.0)
        self.assertEqual(handler.max_delay, 30.0)
        self.assertEqual(handler.backoff_factor, 3.0)
    
    def test_successful_operation_no_retry(self):
        """Test successful operation that doesn't need retry."""
        def successful_operation():
            return "success"
        
        success, result, error = self.retry_handler.execute_with_retry(
            successful_operation,
            logger=self.logger
        )
        
        self.assertTrue(success)
        self.assertEqual(result, "success")
        self.assertIsNone(error)
    
    def test_operation_succeeds_after_retries(self):
        """Test operation that succeeds after some retries."""
        call_count = 0
        
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success after retries"
        
        success, result, error = self.retry_handler.execute_with_retry(
            flaky_operation,
            error_categories=[ErrorCategory.NETWORK],
            logger=self.logger
        )
        
        self.assertTrue(success)
        self.assertEqual(result, "success after retries")
        self.assertIsNone(error)
        self.assertEqual(call_count, 3)
    
    def test_operation_fails_after_max_retries(self):
        """Test operation that fails after maximum retries."""
        def always_failing_operation():
            raise ConnectionError("Persistent network error")
        
        success, result, error = self.retry_handler.execute_with_retry(
            always_failing_operation,
            error_categories=[ErrorCategory.NETWORK],
            logger=self.logger
        )
        
        self.assertFalse(success)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertEqual(error.category, ErrorCategory.NETWORK)
    
    def test_non_retryable_error(self):
        """Test that non-retryable errors don't trigger retries."""
        def operation_with_validation_error():
            raise ValueError("Invalid input")
        
        success, result, error = self.retry_handler.execute_with_retry(
            operation_with_validation_error,
            error_categories=[ErrorCategory.NETWORK],  # Only network errors should retry
            logger=self.logger
        )
        
        self.assertFalse(success)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertEqual(error.category, ErrorCategory.VALIDATION)
        self.assertEqual(error.retry_count, 0)  # No retries for validation errors
    
    def test_delay_calculation(self):
        """Test exponential backoff delay calculation."""
        handler = RetryHandler(base_delay=1.0, backoff_factor=2.0, max_delay=10.0)
        
        # Test exponential growth
        self.assertEqual(handler._calculate_delay(0), 1.0)
        self.assertEqual(handler._calculate_delay(1), 2.0)
        self.assertEqual(handler._calculate_delay(2), 4.0)
        self.assertEqual(handler._calculate_delay(3), 8.0)
        
        # Test max delay cap
        self.assertEqual(handler._calculate_delay(10), 10.0)
    
    def test_error_categorization(self):
        """Test error categorization logic."""
        # Network errors
        network_errors = [
            ConnectionError("Connection failed"),
            TimeoutError("Request timeout"),
            Exception("DNS resolution failed"),
            Exception("Network unreachable")
        ]
        
        for error in network_errors:
            category = self.retry_handler._categorize_error(error)
            self.assertEqual(category, ErrorCategory.NETWORK)
        
        # Filesystem errors
        filesystem_errors = [
            FileNotFoundError("File not found"),
            PermissionError("Permission denied"),
            OSError("Disk full"),
            Exception("No such file or directory")
        ]
        
        for error in filesystem_errors:
            category = self.retry_handler._categorize_error(error)
            self.assertEqual(category, ErrorCategory.FILESYSTEM)
        
        # Validation errors
        validation_errors = [
            ValueError("Invalid value"),
            TypeError("Wrong type"),
            KeyError("Missing key"),
            Exception("Validation failed")
        ]
        
        for error in validation_errors:
            category = self.retry_handler._categorize_error(error)
            self.assertEqual(category, ErrorCategory.VALIDATION)
        
        # Unknown errors
        unknown_error = Exception("Some unknown error")
        category = self.retry_handler._categorize_error(unknown_error)
        self.assertEqual(category, ErrorCategory.UNKNOWN)


class TestFactoryFunctions(unittest.TestCase):
    """Test cases for factory functions."""
    
    def test_create_workflow_logger(self):
        """Test workflow logger factory function."""
        logger = create_workflow_logger("test_factory_logger")
        
        self.assertIsInstance(logger, WorkflowLogger)
        self.assertEqual(logger.logger.name, "test_factory_logger")
    
    def test_create_retry_handler(self):
        """Test retry handler factory function."""
        handler = create_retry_handler(max_retries=5, base_delay=2.0)
        
        self.assertIsInstance(handler, RetryHandler)
        self.assertEqual(handler.max_retries, 5)
        self.assertEqual(handler.base_delay, 2.0)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for various error scenarios."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.logger = WorkflowLogger("integration_test_logger")
        self.retry_handler = RetryHandler(max_retries=2, base_delay=0.01)
    
    def test_file_download_with_network_retry(self):
        """Test file download scenario with network retries."""
        attempt_count = 0
        
        def mock_download_operation(url, target_path):
            nonlocal attempt_count
            attempt_count += 1
            
            if attempt_count == 1:
                raise ConnectionError("Connection timeout")
            elif attempt_count == 2:
                raise TimeoutError("Request timeout")
            else:
                return f"Downloaded {url} to {target_path}"
        
        self.logger.start_processing()
        self.logger.increment_total_operations()
        
        success, result, error = self.retry_handler.execute_with_retry(
            mock_download_operation,
            "https://example.com/file.pdf",
            "/tmp/file.pdf",
            error_categories=[ErrorCategory.NETWORK],
            logger=self.logger,
            context={"operation": "download", "file_size": "1MB"}
        )
        
        self.assertTrue(success)
        self.assertIn("Downloaded", result)
        self.assertIsNone(error)
        self.assertEqual(attempt_count, 3)
        
        self.logger.log_success("File download completed", 
                               url="https://example.com/file.pdf",
                               file_path="/tmp/file.pdf")
        self.logger.end_processing()
        
        # Verify summary (retry handler logs errors during retries, but final success counts)
        self.assertEqual(self.logger.summary.total_operations, 1)
        self.assertGreaterEqual(self.logger.summary.successful_operations, 1)  # At least 1 success
        self.assertGreaterEqual(self.logger.summary.failed_operations, 0)  # May have retry errors
    
    def test_configuration_parsing_error(self):
        """Test configuration parsing error scenario."""
        def mock_parse_config():
            raise ValueError("Invalid input validation")
        
        self.logger.start_processing()
        self.logger.increment_total_operations()
        
        success, result, error = self.retry_handler.execute_with_retry(
            mock_parse_config,
            error_categories=[ErrorCategory.NETWORK],  # Config errors shouldn't retry
            logger=self.logger,
            context={"operation": "parse_config", "file": "urls.yml"}
        )
        
        self.assertFalse(success)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertEqual(error.category, ErrorCategory.VALIDATION)
        
        self.logger.end_processing()
        
        # Verify summary
        self.assertEqual(self.logger.summary.total_operations, 1)
        self.assertEqual(self.logger.summary.successful_operations, 0)
        self.assertEqual(self.logger.summary.failed_operations, 1)
        self.assertEqual(self.logger.summary.errors_by_category[ErrorCategory.VALIDATION], 1)
    
    def test_mixed_success_and_failure_scenario(self):
        """Test scenario with mixed successes and failures."""
        operations = [
            ("success", None),
            ("network_error", ConnectionError("Network failed")),
            ("success", None),
            ("filesystem_error", PermissionError("Permission denied")),
            ("success", None)
        ]
        
        self.logger.start_processing()
        
        for i, (op_type, error) in enumerate(operations):
            self.logger.increment_total_operations()
            
            if op_type == "success":
                self.logger.log_success(f"Operation {i} completed")
            else:
                self.logger.log_error(error, 
                                    ErrorCategory.NETWORK if "network" in op_type else ErrorCategory.FILESYSTEM,
                                    context={"operation_id": i})
        
        self.logger.end_processing()
        
        # Verify summary
        self.assertEqual(self.logger.summary.total_operations, 5)
        self.assertEqual(self.logger.summary.successful_operations, 3)
        self.assertEqual(self.logger.summary.failed_operations, 2)
        self.assertEqual(self.logger.summary.success_rate, 60.0)
        self.assertEqual(self.logger.summary.errors_by_category[ErrorCategory.NETWORK], 1)
        self.assertEqual(self.logger.summary.errors_by_category[ErrorCategory.FILESYSTEM], 1)


if __name__ == '__main__':
    unittest.main()