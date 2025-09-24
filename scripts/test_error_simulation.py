"""
Error simulation tests for the Iranian Archive Workflow.

This module contains comprehensive tests that simulate various error
conditions including network failures, filesystem errors, and
configuration problems to ensure robust error handling.
"""

import unittest
import tempfile
import shutil
import os
import yaml
import time
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, side_effect
import requests
import socket
import errno

from workflow_orchestrator import WorkflowOrchestrator
from file_manager import FileManager
from config_parser import ConfigParser, ConfigurationError
from error_handler import ErrorHandler
from test_data.mock_configs import MockConfigurations, MockResponses


class TestNetworkErrorSimulation(unittest.TestCase):
    """Test network error handling and recovery mechanisms."""
    
    def setUp(self):
        """Set up network error test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        self.config = MockConfigurations.error_prone_config()
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up network error test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('file_manager.requests.get')
    @patch('file_manager.time.sleep')  # Mock sleep to speed up tests
    def test_connection_error_retry_mechanism(self, mock_sleep, mock_get):
        """Test retry mechanism for connection errors."""
        # Simulate connection errors followed by success
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.ConnectionError("Connection timeout"),
            Mock(  # Success on third attempt
                headers={'content-type': 'application/pdf', 'content-length': '1000'},
                iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                raise_for_status=lambda: None
            )
        ]
        
        file_manager = FileManager(max_retries=3, timeout=10)
        target_path = self.temp_dir / "test.pdf"
        
        success, error = file_manager.download_file("https://example.com/test.pdf", target_path)
        
        # Should succeed after retries
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify retry attempts
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # Sleep between retries
    
    @patch('file_manager.requests.get')
    @patch('file_manager.time.sleep')
    def test_timeout_error_handling(self, mock_sleep, mock_get):
        """Test handling of request timeout errors."""
        # Simulate persistent timeout
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")
        
        file_manager = FileManager(max_retries=2, timeout=5)
        target_path = self.temp_dir / "timeout_test.pdf"
        
        success, error = file_manager.download_file("https://example.com/timeout.pdf", target_path)
        
        # Should fail after max retries
        self.assertFalse(success)
        self.assertIn("timeout", error.lower())
        
        # Verify all retry attempts were made
        self.assertEqual(mock_get.call_count, 3)  # Initial + 2 retries
    
    @patch('file_manager.requests.get')
    def test_http_error_codes(self, mock_get):
        """Test handling of various HTTP error codes."""
        error_codes = [404, 403, 500, 502, 503]
        
        for status_code in error_codes:
            with self.subTest(status_code=status_code):
                # Reset mock
                mock_get.reset_mock()
                
                # Create mock response with error status
                mock_response = Mock()
                mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                    f"{status_code} Error"
                )
                mock_get.return_value = mock_response
                
                file_manager = FileManager()
                target_path = self.temp_dir / f"error_{status_code}.pdf"
                
                success, error = file_manager.download_file(
                    f"https://example.com/error{status_code}.pdf", target_path
                )
                
                self.assertFalse(success)
                self.assertIn(str(status_code), error)
    
    @patch('file_manager.requests.get')
    def test_dns_resolution_failure(self, mock_get):
        """Test handling of DNS resolution failures."""
        # Simulate DNS resolution error
        mock_get.side_effect = socket.gaierror("Name resolution failed")
        
        file_manager = FileManager()
        target_path = self.temp_dir / "dns_test.pdf"
        
        success, error = file_manager.download_file("https://nonexistent.domain.com/test.pdf", target_path)
        
        self.assertFalse(success)
        self.assertIn("resolution", error.lower())
    
    @patch('file_manager.requests.get')
    def test_ssl_certificate_error(self, mock_get):
        """Test handling of SSL certificate errors."""
        # Simulate SSL certificate error
        mock_get.side_effect = requests.exceptions.SSLError("Certificate verification failed")
        
        file_manager = FileManager()
        target_path = self.temp_dir / "ssl_test.pdf"
        
        success, error = file_manager.download_file("https://badssl.example.com/test.pdf", target_path)
        
        self.assertFalse(success)
        self.assertIn("ssl", error.lower())
    
    @patch('file_manager.requests.get')
    def test_network_unreachable_error(self, mock_get):
        """Test handling of network unreachable errors."""
        # Simulate network unreachable
        mock_get.side_effect = OSError(errno.ENETUNREACH, "Network is unreachable")
        
        file_manager = FileManager()
        target_path = self.temp_dir / "network_test.pdf"
        
        success, error = file_manager.download_file("https://192.0.2.1/test.pdf", target_path)
        
        self.assertFalse(success)
        self.assertIn("network", error.lower())


class TestFilesystemErrorSimulation(unittest.TestCase):
    """Test filesystem error handling and recovery."""
    
    def setUp(self):
        """Set up filesystem error test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up filesystem error test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_permission_denied_error(self):
        """Test handling of permission denied errors."""
        # Create a read-only directory
        readonly_dir = self.temp_dir / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only permissions
        
        try:
            file_manager = FileManager()
            
            # Try to create directory structure in read-only location
            with self.assertRaises(PermissionError):
                file_manager.create_directory_structure("newspaper", "../readonly/test", "2023")
        
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)
    
    def test_disk_space_simulation(self):
        """Test handling when disk space is insufficient."""
        # This is difficult to simulate reliably, so we mock the file writing
        with patch('builtins.open', side_effect=OSError(errno.ENOSPC, "No space left on device")):
            file_manager = FileManager()
            target_path = self.temp_dir / "diskfull_test.pdf"
            
            with patch('file_manager.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
                mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                success, error = file_manager.download_file("https://example.com/test.pdf", target_path)
                
                self.assertFalse(success)
                self.assertIn("space", error.lower())
    
    def test_file_path_too_long(self):
        """Test handling of file paths that are too long."""
        file_manager = FileManager()
        
        # Create very long path
        long_folder_name = "a" * 200
        
        # This should be handled gracefully by truncation
        result_path = file_manager.create_directory_structure("newspaper", long_folder_name, "2023")
        
        # Path should be created but folder name should be truncated
        self.assertTrue(result_path.exists())
        self.assertLessEqual(len(result_path.parent.name), 100)
    
    def test_invalid_characters_in_path(self):
        """Test handling of invalid characters in file paths."""
        file_manager = FileManager()
        
        # Test various invalid characters
        invalid_names = [
            "folder<>:\"/\\|?*",
            "folder\x00with\x00nulls",
            "folder\twith\ttabs",
            "folder\nwith\nnewlines"
        ]
        
        for invalid_name in invalid_names:
            with self.subTest(invalid_name=invalid_name):
                # Should sanitize the name and create valid path
                result_path = file_manager.create_directory_structure("newspaper", invalid_name, "2023")
                
                self.assertTrue(result_path.exists())
                # Sanitized name should not contain invalid characters
                sanitized_name = result_path.parent.name
                invalid_chars = '<>:"/\\|?*\x00\t\n'
                self.assertFalse(any(char in sanitized_name for char in invalid_chars))
    
    def test_concurrent_file_access(self):
        """Test handling of concurrent file access conflicts."""
        import threading
        import time
        
        file_manager = FileManager()
        target_path = self.temp_dir / "concurrent_test.pdf"
        results = []
        
        def download_file(thread_id):
            """Download file in separate thread."""
            with patch('file_manager.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
                mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                success, error = file_manager.download_file(
                    f"https://example.com/test{thread_id}.pdf", target_path
                )
                results.append((thread_id, success, error))
        
        # Start multiple threads trying to download to same file
        threads = []
        for i in range(3):
            thread = threading.Thread(target=download_file, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # At least one should succeed, others might fail due to file conflicts
        successes = [result[1] for result in results]
        self.assertTrue(any(successes), "At least one download should succeed")


class TestConfigurationErrorSimulation(unittest.TestCase):
    """Test configuration parsing and validation error handling."""
    
    def setUp(self):
        """Set up configuration error test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up configuration error test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_malformed_yaml_handling(self):
        """Test handling of malformed YAML configurations."""
        malformed_configs = MockConfigurations.malformed_configs()
        
        for i, malformed_yaml in enumerate(malformed_configs):
            with self.subTest(config_index=i):
                config_file = f'malformed_{i}.yml'
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.write(malformed_yaml)
                
                parser = ConfigParser(config_file)
                
                with self.assertRaises(ConfigurationError):
                    parser.parse_configuration()
    
    def test_missing_configuration_file(self):
        """Test handling when configuration file is missing."""
        parser = ConfigParser('nonexistent.yml')
        
        with self.assertRaises(ConfigurationError) as cm:
            parser.parse_configuration()
        
        self.assertIn("not found", str(cm.exception).lower())
    
    def test_empty_configuration_file(self):
        """Test handling of empty configuration file."""
        # Create empty file
        with open('empty.yml', 'w') as f:
            f.write('')
        
        parser = ConfigParser('empty.yml')
        
        with self.assertRaises(ConfigurationError):
            parser.parse_configuration()
    
    def test_configuration_with_unicode_errors(self):
        """Test handling of configuration files with encoding issues."""
        # Create file with invalid UTF-8 sequences
        with open('invalid_encoding.yml', 'wb') as f:
            f.write(b'archives:\n  - title_fa: \xff\xfe invalid utf-8')
        
        parser = ConfigParser('invalid_encoding.yml')
        
        with self.assertRaises(ConfigurationError):
            parser.parse_configuration()
    
    def test_configuration_security_validation(self):
        """Test security validation of configuration content."""
        # Test configuration with potentially malicious content
        malicious_config = {
            'archives': [{
                'title_fa': '<script>alert("xss")</script>',
                'folder': '../../../etc/passwd',
                'category': 'newspaper',
                'description': 'javascript:alert("xss")',
                'years': {
                    '2023': ['file:///etc/passwd']
                }
            }]
        }
        
        with open('malicious.yml', 'w', encoding='utf-8') as f:
            yaml.dump(malicious_config, f, allow_unicode=True)
        
        parser = ConfigParser('malicious.yml')
        
        # Should either reject malicious content or sanitize it
        try:
            archives = parser.parse_configuration()
            # If parsing succeeds, content should be sanitized
            archive = archives[0]
            self.assertNotIn('<script>', archive.title_fa)
            self.assertNotIn('javascript:', archive.description)
            self.assertNotIn('file:///', archive.years['2023'][0])
        except ConfigurationError:
            # Rejecting malicious content is also acceptable
            pass


class TestWorkflowErrorRecovery(unittest.TestCase):
    """Test workflow-level error recovery and continuation."""
    
    def setUp(self):
        """Set up workflow error recovery test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create mixed success/failure configuration
        self.config = MockConfigurations.mixed_success_failure_config()
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up workflow error recovery test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('file_manager.requests.get')
    def test_workflow_continues_after_download_failures(self, mock_get):
        """Test that workflow continues processing after individual download failures."""
        # Mock mixed responses - some succeed, some fail
        responses = [
            # Success
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
            # Failure
            Mock(side_effect=requests.exceptions.ConnectionError("Network error")),
            # Success
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
            # Failure
            Mock(side_effect=requests.exceptions.HTTPError("404 Not Found")),
            # Success
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
        ]
        mock_get.side_effect = responses
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(dry_run=False, verbose=True)
        
        # Workflow should complete successfully despite some failures
        self.assertTrue(result)
        
        # Verify that successful downloads created files
        archive_dir = Path.cwd() / 'newspaper' / 'mixed-results' / '2023'
        if archive_dir.exists():
            pdf_files = list(archive_dir.glob('*.pdf'))
            # Should have some successful downloads
            self.assertGreater(len(pdf_files), 0)
    
    def test_workflow_handles_partial_archive_failures(self):
        """Test workflow handling when entire archives fail."""
        # Create config with multiple archives
        multi_config = MockConfigurations.multi_archive_config()
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(multi_config, f, allow_unicode=True)
        
        with patch('file_manager.requests.get') as mock_get:
            # Make first archive fail, second succeed, third fail
            def side_effect_func(*args, **kwargs):
                url = args[0]
                if 'kayhan' in url:
                    raise requests.exceptions.ConnectionError("Kayhan server down")
                elif 'tehran-times' in url:
                    # Success for Tehran Times
                    mock_response = Mock()
                    mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
                    mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
                    mock_response.raise_for_status.return_value = None
                    return mock_response
                else:  # student magazine
                    raise requests.exceptions.HTTPError("Student server error")
            
            mock_get.side_effect = side_effect_func
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=False, verbose=True)
            
            # Should complete successfully
            self.assertTrue(result)
            
            # Tehran Times should have been processed
            tehran_dir = Path.cwd() / 'newspaper' / 'tehran-times'
            self.assertTrue(tehran_dir.exists())
    
    def test_workflow_error_logging_and_reporting(self):
        """Test that errors are properly logged and reported."""
        with patch('file_manager.requests.get') as mock_get:
            # All downloads fail with different errors
            mock_get.side_effect = [
                requests.exceptions.ConnectionError("Connection failed"),
                requests.exceptions.Timeout("Request timeout"),
                requests.exceptions.HTTPError("404 Not Found"),
            ]
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=False, verbose=True)
            
            # Should complete (not crash) despite all failures
            self.assertTrue(result)
            
            # Verify error log was created
            log_files = list(Path.cwd().glob('*.log'))
            self.assertGreater(len(log_files), 0)
            
            # Verify summary contains error information
            summary_files = list(Path.cwd().glob('workflow_summary_*.md'))
            self.assertGreater(len(summary_files), 0)
            
            with open(summary_files[0], 'r', encoding='utf-8') as f:
                summary_content = f.read()
                self.assertIn('Failed', summary_content)
                self.assertIn('Error', summary_content)
    
    def test_workflow_graceful_shutdown_on_critical_error(self):
        """Test workflow graceful shutdown on critical errors."""
        # Simulate critical error during workflow initialization
        with patch('workflow_orchestrator.ConfigParser') as mock_parser:
            mock_parser.side_effect = Exception("Critical system error")
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow()
            
            # Should fail gracefully without crashing
            self.assertFalse(result)
    
    def test_workflow_memory_cleanup_after_errors(self):
        """Test that memory is properly cleaned up after errors."""
        import gc
        import psutil
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Run workflow that will encounter many errors
        with patch('file_manager.requests.get') as mock_get:
            mock_get.side_effect = Exception("Persistent error")
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=False)
            
            # Clean up
            del orchestrator
            gc.collect()
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            # Memory increase should be minimal even after errors
            self.assertLess(memory_increase, 50.0,
                          f"Excessive memory retained after errors: {memory_increase:.2f}MB")


class TestErrorHandlerIntegration(unittest.TestCase):
    """Test integration of error handler with other components."""
    
    def setUp(self):
        """Set up error handler integration test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        self.error_handler = ErrorHandler('test_errors.log')
    
    def tearDown(self):
        """Clean up error handler integration test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_error_categorization(self):
        """Test that errors are properly categorized."""
        # Test different error types
        network_error = requests.exceptions.ConnectionError("Connection failed")
        filesystem_error = PermissionError("Permission denied")
        config_error = ConfigurationError("Invalid configuration")
        
        self.error_handler.log_error("https://example.com/test1.pdf", network_error, "network")
        self.error_handler.log_error("/path/to/file", filesystem_error, "filesystem")
        self.error_handler.log_error("config.yml", config_error, "configuration")
        
        # Verify errors were logged
        self.assertTrue(Path('test_errors.log').exists())
        
        with open('test_errors.log', 'r', encoding='utf-8') as f:
            log_content = f.read()
            self.assertIn('network', log_content.lower())
            self.assertIn('filesystem', log_content.lower())
            self.assertIn('configuration', log_content.lower())
    
    def test_error_aggregation_and_summary(self):
        """Test error aggregation and summary generation."""
        # Log multiple errors
        for i in range(5):
            error = requests.exceptions.ConnectionError(f"Error {i}")
            self.error_handler.log_error(f"https://example.com/file{i}.pdf", error, "network")
        
        for i in range(3):
            error = PermissionError(f"Permission error {i}")
            self.error_handler.log_error(f"/path/file{i}", error, "filesystem")
        
        # Generate summary
        summary = self.error_handler.generate_error_summary()
        
        self.assertIn('network', summary.lower())
        self.assertIn('filesystem', summary.lower())
        self.assertIn('5', summary)  # 5 network errors
        self.assertIn('3', summary)  # 3 filesystem errors
    
    def test_error_recovery_suggestions(self):
        """Test that error handler provides recovery suggestions."""
        # Test with recoverable error
        network_error = requests.exceptions.ConnectionError("Connection failed")
        self.error_handler.log_error("https://example.com/test.pdf", network_error, "network")
        
        suggestions = self.error_handler.get_recovery_suggestions()
        
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)
        
        # Should contain relevant suggestions
        suggestions_text = ' '.join(suggestions).lower()
        self.assertTrue(any(keyword in suggestions_text for keyword in 
                          ['retry', 'network', 'connection', 'check']))


if __name__ == '__main__':
    # Run all error simulation tests
    unittest.main(verbosity=2)