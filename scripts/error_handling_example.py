#!/usr/bin/env python3
"""
Example demonstrating the error handling and logging system.

This script shows how to use the WorkflowLogger and RetryHandler
for robust error handling in the Iranian Archive Workflow.
"""

import tempfile
from pathlib import Path
from config_parser import ConfigParser, ConfigurationError
from file_manager import FileManager
from error_handler import (
    WorkflowLogger, RetryHandler, ErrorCategory,
    create_workflow_logger, create_retry_handler
)


def demonstrate_error_handling():
    """Demonstrate comprehensive error handling capabilities."""
    
    # Create workflow logger
    logger = create_workflow_logger("demo_workflow")
    logger.start_processing()
    
    print("=== Iranian Archive Workflow Error Handling Demo ===\n")
    
    # 1. Configuration parsing with error handling
    print("1. Testing Configuration Parsing...")
    
    # Create a temporary invalid config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write("invalid: yaml: content:\n  - missing quotes")
        invalid_config_path = f.name
    
    try:
        config_parser = ConfigParser(invalid_config_path, logger=logger)
        archives = config_parser.parse_configuration()
    except ConfigurationError as e:
        print(f"   ✓ Caught configuration error: {e}")
    
    # Clean up
    Path(invalid_config_path).unlink(missing_ok=True)
    
    # 2. File download with retry mechanism
    print("\n2. Testing File Download with Retries...")
    
    file_manager = FileManager(logger=logger, max_retries=2)
    
    # Test invalid URL
    logger.increment_total_operations()
    success, error = file_manager.download_file("invalid-url", Path("test.pdf"))
    if not success:
        print(f"   ✓ Invalid URL handled: {error}")
    
    # Test non-existent URL (will trigger retries)
    logger.increment_total_operations()
    success, error = file_manager.download_file(
        "https://nonexistent-domain-12345.com/file.pdf", 
        Path("test.pdf")
    )
    if not success:
        print(f"   ✓ Network error with retries: {error}")
    
    # 3. Demonstrate retry handler directly
    print("\n3. Testing Retry Handler...")
    
    retry_handler = create_retry_handler(max_retries=3, base_delay=0.1)
    
    def flaky_operation(attempt_count=[0]):
        """Simulated operation that fails twice then succeeds."""
        attempt_count[0] += 1
        if attempt_count[0] <= 2:
            raise ConnectionError(f"Network failure #{attempt_count[0]}")
        return f"Success after {attempt_count[0]} attempts"
    
    logger.increment_total_operations()
    success, result, error_details = retry_handler.execute_with_retry(
        flaky_operation,
        error_categories=[ErrorCategory.NETWORK],
        logger=logger,
        context={"operation": "demo_flaky_operation"}
    )
    
    if success:
        print(f"   ✓ Operation succeeded: {result}")
        logger.log_success("Flaky operation completed", context={"result": result})
    
    # 4. Error categorization demonstration
    print("\n4. Testing Error Categorization...")
    
    test_errors = [
        (ValueError("Invalid input format"), ErrorCategory.VALIDATION),
        (FileNotFoundError("File not found"), ErrorCategory.FILESYSTEM),
        (ConnectionError("Network timeout"), ErrorCategory.NETWORK),
        (Exception("Unknown error"), ErrorCategory.UNKNOWN)
    ]
    
    for error, expected_category in test_errors:
        categorized = retry_handler._categorize_error(error)
        print(f"   ✓ {type(error).__name__}: {categorized.value} "
              f"{'✓' if categorized == expected_category else '✗'}")
        
        # Log the error for demonstration
        logger.log_error(error, categorized, context={"demo": "error_categorization"})
    
    # 5. Processing summary
    print("\n5. Processing Summary...")
    logger.end_processing()
    
    summary = logger.summary
    print(f"   Total Operations: {summary.total_operations}")
    print(f"   Successful: {summary.successful_operations}")
    print(f"   Failed: {summary.failed_operations}")
    print(f"   Success Rate: {summary.success_rate:.1f}%")
    print(f"   Duration: {summary.duration:.2f} seconds")
    
    if summary.errors_by_category:
        print("   Errors by Category:")
        for category, count in summary.errors_by_category.items():
            print(f"     {category}: {count}")
    
    # 6. Save error report
    print("\n6. Saving Error Report...")
    report_path = "error_report_demo.json"
    logger.save_error_report(report_path)
    print(f"   ✓ Error report saved to: {report_path}")
    
    print("\n=== Demo Complete ===")
    
    return logger.summary


def demonstrate_graceful_continuation():
    """Demonstrate how errors don't stop workflow execution."""
    
    print("\n=== Graceful Error Handling Demo ===\n")
    
    logger = create_workflow_logger("graceful_demo")
    logger.start_processing()
    
    # Simulate processing multiple files where some fail
    urls = [
        "https://example.com/valid1.pdf",
        "invalid-url-format",
        "https://nonexistent-domain.com/file.pdf",
        "https://example.com/valid2.pdf",
    ]
    
    file_manager = FileManager(logger=logger, max_retries=1)
    
    successful_downloads = 0
    failed_downloads = 0
    
    for i, url in enumerate(urls, 1):
        print(f"Processing file {i}/{len(urls)}: {url}")
        logger.increment_total_operations()
        
        target_path = Path(f"download_{i}.pdf")
        success, error = file_manager.download_file(url, target_path)
        
        if success:
            successful_downloads += 1
            print(f"   ✓ Success")
        else:
            failed_downloads += 1
            print(f"   ✗ Failed: {error}")
        
        # Workflow continues regardless of individual failures
    
    logger.end_processing()
    
    print(f"\nResults:")
    print(f"   Successful downloads: {successful_downloads}")
    print(f"   Failed downloads: {failed_downloads}")
    print(f"   Workflow completed successfully despite {failed_downloads} failures")
    
    return logger.summary


if __name__ == "__main__":
    # Run demonstrations
    summary1 = demonstrate_error_handling()
    summary2 = demonstrate_graceful_continuation()
    
    print(f"\n=== Overall Statistics ===")
    print(f"Demo 1 - Success Rate: {summary1.success_rate:.1f}%")
    print(f"Demo 2 - Success Rate: {summary2.success_rate:.1f}%")
    print(f"Total Errors Handled: {len(summary1.error_details) + len(summary2.error_details)}")