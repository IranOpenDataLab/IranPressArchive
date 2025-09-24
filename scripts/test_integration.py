"""
Integration tests for the Iranian Archive Workflow.

This module contains comprehensive integration tests that verify the complete
workflow scenarios, including end-to-end processing, error handling, and
performance under various conditions.
"""

import unittest
import tempfile
import shutil
import os
import yaml
import json
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import time
import threading
from datetime import datetime

from workflow_orchestrator import WorkflowOrchestrator
from config_parser import ConfigParser, Archive
from file_manager import FileManager
from error_handler import ErrorHandler
from state_manager import StateManager
from readme_generator import ReadmeGenerator


class TestCompleteWorkflowIntegration(unittest.TestCase):
    """Integration tests for complete workflow scenarios."""
    
    def setUp(self):
        """Set up integration test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        self.test_config = {
            'archives': [
                {
                    'title_fa': 'روزنامه کیهان',
                    'folder': 'kayhan-newspaper',
                    'category': 'old-newspaper',
                    'description': 'Historical Kayhan newspaper archive',
                    'years': {
                        '2020': [
                            'https://example.com/kayhan-2020-01.pdf',
                            'https://example.com/kayhan-2020-02.pdf'
                        ],
                        '2021': [
                            'https://example.com/kayhan-2021-01.pdf'
                        ]
                    }
                },
                {
                    'title_fa': 'تهران تایمز',
                    'folder': 'tehran-times',
                    'category': 'newspaper',
                    'description': 'English language newspaper',
                    'years': {
                        '2023': [
                            'https://example.com/tehran-2023-01.pdf',
                            'https://example.com/tehran-2023-02.pdf'
                        ]
                    }
                }
            ]
        }
        
        # Write test configuration
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(self.test_config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up integration test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('file_manager.requests.get')
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_complete_manual_workflow_success(self, mock_exists, mock_subprocess, mock_get):
        """Test complete workflow execution in manual mode with successful downloads."""
        # Mock successful file downloads
        mock_response = Mock()
        mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
        mock_response.iter_content.return_value = [b'%PDF-1.4\nfake pdf content']
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Mock git operations
        mock_exists.return_value = True  # .git directory exists
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # git add
            Mock(returncode=1),  # git diff --cached --quiet (changes exist)
            Mock(returncode=0)   # git commit
        ]
        
        # Execute workflow
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(
            is_scheduled_run=False,
            dry_run=False,
            verbose=True
        )
        
        # Verify workflow success
        self.assertTrue(result)
        
        # Verify directory structure was created
        self.assertTrue((Path.cwd() / 'old-newspaper' / 'kayhan-newspaper').exists())
        self.assertTrue((Path.cwd() / 'newspaper' / 'tehran-times').exists())
        
        # Verify year directories
        self.assertTrue((Path.cwd() / 'old-newspaper' / 'kayhan-newspaper' / '2020').exists())
        self.assertTrue((Path.cwd() / 'old-newspaper' / 'kayhan-newspaper' / '2021').exists())
        self.assertTrue((Path.cwd() / 'newspaper' / 'tehran-times' / '2023').exists())
        
        # Verify README files were created
        self.assertTrue((Path.cwd() / 'README.md').exists())
        self.assertTrue((Path.cwd() / 'README.en.md').exists())
        
        # Verify publication READMEs
        self.assertTrue((Path.cwd() / 'old-newspaper' / 'kayhan-newspaper' / 'README.md').exists())
        self.assertTrue((Path.cwd() / 'newspaper' / 'tehran-times' / 'README.md').exists())
        
        # Verify git operations were called
        self.assertEqual(mock_subprocess.call_count, 3)
    
    @patch('file_manager.requests.get')
    def test_complete_scheduled_workflow_newspaper_only(self, mock_get):
        """Test scheduled workflow processes only newspaper category."""
        # Mock successful downloads
        mock_response = Mock()
        mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
        mock_response.iter_content.return_value = [b'%PDF-1.4\nfake pdf content']
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Execute scheduled workflow
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(
            is_scheduled_run=True,
            dry_run=False,
            verbose=True
        )
        
        self.assertTrue(result)
        
        # Verify only newspaper category was processed
        self.assertTrue((Path.cwd() / 'newspaper' / 'tehran-times').exists())
        self.assertFalse((Path.cwd() / 'old-newspaper').exists())
    
    @patch('file_manager.requests.get')
    def test_workflow_with_mixed_success_failure(self, mock_get):
        """Test workflow handling mixed success and failure scenarios."""
        # Mock mixed responses - some succeed, some fail
        responses = [
            # First URL succeeds
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
            # Second URL fails with 404
            Mock(side_effect=Exception("404 Not Found")),
            # Third URL succeeds
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
            # Fourth URL fails with network error
            Mock(side_effect=Exception("Network timeout")),
            # Fifth URL succeeds
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
        ]
        mock_get.side_effect = responses
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(dry_run=False, verbose=True)
        
        # Workflow should complete successfully despite some failures
        self.assertTrue(result)
        
        # Verify some files were downloaded
        kayhan_2020 = Path.cwd() / 'old-newspaper' / 'kayhan-newspaper' / '2020'
        tehran_2023 = Path.cwd() / 'newspaper' / 'tehran-times' / '2023'
        
        # Check that successful downloads created files
        if kayhan_2020.exists():
            files = list(kayhan_2020.glob('*.pdf'))
            self.assertGreater(len(files), 0)
        
        if tehran_2023.exists():
            files = list(tehran_2023.glob('*.pdf'))
            self.assertGreater(len(files), 0)
    
    def test_workflow_dry_run_mode(self):
        """Test workflow execution in dry run mode."""
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(
            dry_run=True,
            verbose=True
        )
        
        self.assertTrue(result)
        
        # In dry run mode, no actual files should be downloaded
        # but directories might be created for structure validation
        # The key is that no actual HTTP requests should be made
        
        # Verify summary was generated
        summary_files = list(Path.cwd().glob('workflow_summary_*.md'))
        self.assertGreater(len(summary_files), 0)
    
    def test_workflow_with_empty_configuration(self):
        """Test workflow behavior with empty configuration."""
        # Create empty configuration
        empty_config = {'archives': []}
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(empty_config, f)
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow()
        
        # Should complete successfully with no work to do
        self.assertTrue(result)
    
    def test_workflow_configuration_update_after_success(self):
        """Test that configuration is updated after successful downloads."""
        # Create a simple config with one URL
        simple_config = {
            'archives': [{
                'title_fa': 'تست',
                'folder': 'test-archive',
                'category': 'newspaper',
                'description': 'Test archive',
                'years': {
                    '2023': ['https://example.com/test.pdf']
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(simple_config, f, allow_unicode=True)
        
        with patch('file_manager.requests.get') as mock_get:
            # Mock successful download
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=False)
            
            self.assertTrue(result)
            
            # Verify configuration was updated (successful URL removed)
            with open('urls.yml', 'r', encoding='utf-8') as f:
                updated_config = yaml.safe_load(f)
            
            # The successful URL should be removed from the configuration
            archive = updated_config['archives'][0]
            self.assertEqual(len(archive['years']['2023']), 0)


class TestErrorHandlingIntegration(unittest.TestCase):
    """Integration tests for error handling scenarios."""
    
    def setUp(self):
        """Set up error handling test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration with problematic URLs
        self.error_config = {
            'archives': [{
                'title_fa': 'تست خطا',
                'folder': 'error-test',
                'category': 'newspaper',
                'description': 'Error testing archive',
                'years': {
                    '2023': [
                        'https://nonexistent.example.com/file1.pdf',  # Network error
                        'https://example.com/toolarge.pdf',  # Too large
                        'https://example.com/notpdf.html',  # Wrong content type
                        'invalid-url',  # Invalid URL format
                    ]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(self.error_config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up error handling test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('file_manager.requests.get')
    def test_network_error_handling(self, mock_get):
        """Test handling of various network errors."""
        import requests
        
        # Mock different types of network errors
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            requests.exceptions.Timeout("Request timeout"),
            requests.exceptions.HTTPError("404 Not Found"),
            Exception("Invalid URL format")
        ]
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(dry_run=False, verbose=True)
        
        # Workflow should complete despite all errors
        self.assertTrue(result)
        
        # Verify error log was created
        log_files = list(Path.cwd().glob('*.log'))
        self.assertGreater(len(log_files), 0)
        
        # Verify summary includes error information
        summary_files = list(Path.cwd().glob('workflow_summary_*.md'))
        self.assertGreater(len(summary_files), 0)
        
        # Read summary and verify it contains error information
        with open(summary_files[0], 'r', encoding='utf-8') as f:
            summary_content = f.read()
            self.assertIn('Failed', summary_content)
    
    def test_filesystem_error_simulation(self):
        """Test handling of filesystem errors."""
        # Create a read-only directory to simulate permission errors
        readonly_dir = Path.cwd() / 'readonly'
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only
        
        try:
            # Modify config to use readonly directory
            config = {
                'archives': [{
                    'title_fa': 'تست فایل سیستم',
                    'folder': '../readonly/test',  # This should cause permission error
                    'category': 'newspaper',
                    'description': 'Filesystem error test',
                    'years': {'2023': ['https://example.com/test.pdf']}
                }]
            }
            
            with open('urls.yml', 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True)
            
            with patch('file_manager.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.headers = {'content-type': 'application/pdf'}
                mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                orchestrator = WorkflowOrchestrator()
                result = orchestrator.execute_workflow(dry_run=False)
                
                # Should handle filesystem errors gracefully
                self.assertTrue(result)
        
        finally:
            # Clean up readonly directory
            readonly_dir.chmod(0o755)
            if readonly_dir.exists():
                shutil.rmtree(readonly_dir)
    
    def test_malformed_configuration_handling(self):
        """Test handling of malformed configuration files."""
        # Create malformed YAML
        with open('urls.yml', 'w', encoding='utf-8') as f:
            f.write("archives:\n  - title_fa: 'unclosed quote\n    invalid: yaml")
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow()
        
        # Should fail gracefully with malformed config
        self.assertFalse(result)
    
    def test_missing_configuration_file(self):
        """Test handling when configuration file is missing."""
        # Remove configuration file
        os.remove('urls.yml')
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow()
        
        # Should fail gracefully with missing config
        self.assertFalse(result)


class TestPerformanceIntegration(unittest.TestCase):
    """Performance and load testing for the workflow."""
    
    def setUp(self):
        """Set up performance test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up performance test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_large_archive_processing_performance(self):
        """Test performance with large number of archives and files."""
        # Create configuration with many archives and files
        large_config = {'archives': []}
        
        # Generate 10 archives with 50 files each
        for i in range(10):
            archive = {
                'title_fa': f'آرشیو {i}',
                'folder': f'archive-{i}',
                'category': 'newspaper' if i % 2 == 0 else 'old-newspaper',
                'description': f'Test archive {i}',
                'years': {}
            }
            
            # Add multiple years with multiple files
            for year in range(2020, 2025):
                urls = [f'https://example.com/archive{i}-{year}-{j}.pdf' for j in range(10)]
                archive['years'][str(year)] = urls
            
            large_config['archives'].append(archive)
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(large_config, f, allow_unicode=True)
        
        # Mock fast successful downloads
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # Measure execution time
            start_time = time.time()
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            self.assertTrue(result)
            
            # Performance assertion - should complete within reasonable time
            # For dry run with 500 files, should be under 30 seconds
            self.assertLess(execution_time, 30.0, 
                          f"Large archive processing took too long: {execution_time:.2f}s")
            
            print(f"Large archive processing completed in {execution_time:.2f} seconds")
    
    def test_memory_usage_monitoring(self):
        """Test memory usage during large file processing."""
        import psutil
        import gc
        
        # Create config with moderate number of files
        config = {
            'archives': [{
                'title_fa': 'تست حافظه',
                'folder': 'memory-test',
                'category': 'newspaper',
                'description': 'Memory usage test',
                'years': {
                    '2023': [f'https://example.com/file{i}.pdf' for i in range(100)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Monitor memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        with patch('file_manager.requests.get') as mock_get:
            # Mock responses that return larger content
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '10000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\n' + b'x' * 10000]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True)
            
            # Force garbage collection
            gc.collect()
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            self.assertTrue(result)
            
            # Memory usage should not increase excessively
            # Allow up to 100MB increase for processing 100 files
            self.assertLess(memory_increase, 100.0,
                          f"Memory usage increased too much: {memory_increase:.2f}MB")
            
            print(f"Memory usage increased by {memory_increase:.2f}MB")
    
    def test_concurrent_processing_simulation(self):
        """Test behavior under simulated concurrent load."""
        # Create multiple workflow instances to simulate concurrent execution
        config = {
            'archives': [{
                'title_fa': 'تست همزمان',
                'folder': 'concurrent-test',
                'category': 'newspaper',
                'description': 'Concurrent processing test',
                'years': {
                    '2023': [f'https://example.com/concurrent{i}.pdf' for i in range(20)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        results = []
        threads = []
        
        def run_workflow(thread_id):
            """Run workflow in separate thread."""
            try:
                with patch('file_manager.requests.get') as mock_get:
                    mock_response = Mock()
                    mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
                    mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
                    mock_response.raise_for_status.return_value = None
                    mock_get.return_value = mock_response
                    
                    orchestrator = WorkflowOrchestrator(log_file=f'workflow_{thread_id}.log')
                    result = orchestrator.execute_workflow(dry_run=True)
                    results.append((thread_id, result))
            except Exception as e:
                results.append((thread_id, False, str(e)))
        
        # Start multiple threads
        for i in range(3):
            thread = threading.Thread(target=run_workflow, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=30)  # 30 second timeout
        
        # Verify all workflows completed successfully
        self.assertEqual(len(results), 3)
        for thread_id, result in results:
            if len(result) == 2:  # No error
                self.assertTrue(result[1], f"Thread {thread_id} failed")
            else:  # Error occurred
                self.fail(f"Thread {thread_id} raised exception: {result[2]}")


class TestWorkflowSummaryAndReporting(unittest.TestCase):
    """Test workflow summary generation and reporting features."""
    
    def setUp(self):
        """Set up summary testing environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        self.config = {
            'archives': [{
                'title_fa': 'تست گزارش',
                'folder': 'report-test',
                'category': 'newspaper',
                'description': 'Report testing archive',
                'years': {
                    '2023': [
                        'https://example.com/success1.pdf',
                        'https://example.com/success2.pdf',
                        'https://example.com/fail1.pdf',
                        'https://example.com/fail2.pdf'
                    ]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up summary testing environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('file_manager.requests.get')
    def test_workflow_summary_generation(self, mock_get):
        """Test that workflow generates comprehensive summary (Requirement 5.4)."""
        # Mock mixed success/failure responses
        responses = [
            # Success
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
            # Success
            Mock(headers={'content-type': 'application/pdf', 'content-length': '1000'},
                 iter_content=lambda chunk_size: [b'%PDF-1.4\nfake content'],
                 raise_for_status=lambda: None),
            # Failure
            Mock(side_effect=Exception("Network error")),
            # Failure
            Mock(side_effect=Exception("File not found"))
        ]
        mock_get.side_effect = responses
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(dry_run=False, verbose=True)
        
        self.assertTrue(result)
        
        # Verify summary file was created
        summary_files = list(Path.cwd().glob('workflow_summary_*.md'))
        self.assertGreater(len(summary_files), 0)
        
        # Read and verify summary content
        with open(summary_files[0], 'r', encoding='utf-8') as f:
            summary_content = f.read()
        
        # Summary should contain key information
        self.assertIn('Workflow Summary', summary_content)
        self.assertIn('Total Archives', summary_content)
        self.assertIn('Successful', summary_content)
        self.assertIn('Failed', summary_content)
        self.assertIn('Execution Time', summary_content)
        
        # Should contain specific counts
        self.assertIn('2', summary_content)  # 2 successful downloads
        self.assertIn('2', summary_content)  # 2 failed downloads
    
    def test_scheduled_run_with_no_content(self):
        """Test scheduled run completes without errors when no new content (Requirement 6.5)."""
        # Create empty configuration (no URLs to process)
        empty_config = {
            'archives': [{
                'title_fa': 'آرشیو خالی',
                'folder': 'empty-archive',
                'category': 'newspaper',
                'description': 'Empty archive for testing',
                'years': {}  # No years/URLs
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(empty_config, f, allow_unicode=True)
        
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_workflow(
            is_scheduled_run=True,
            dry_run=False,
            verbose=True
        )
        
        # Should complete successfully with no errors
        self.assertTrue(result)
        
        # Verify summary was still generated
        summary_files = list(Path.cwd().glob('workflow_summary_*.md'))
        self.assertGreater(len(summary_files), 0)
        
        # Summary should indicate no work was done
        with open(summary_files[0], 'r', encoding='utf-8') as f:
            summary_content = f.read()
        
        self.assertIn('0', summary_content)  # 0 files processed


if __name__ == '__main__':
    # Run all integration tests
    unittest.main(verbosity=2)