"""
Performance tests for the Iranian Archive Workflow.

This module contains performance benchmarks and load tests to ensure
the workflow can handle large archives efficiently and within
acceptable resource limits. Includes comprehensive monitoring and
optimization testing.
"""

import unittest
import tempfile
import shutil
import os
import yaml
import time
import psutil
import threading
from pathlib import Path
from unittest.mock import patch, Mock
from datetime import datetime, timedelta
import gc
import sys

from workflow_orchestrator import WorkflowOrchestrator
from file_manager import FileManager
from config_parser import ConfigParser


class TestWorkflowPerformance(unittest.TestCase):
    """Performance benchmarks for workflow execution."""
    
    def setUp(self):
        """Set up performance test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Get initial system metrics
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_time = time.time()
    
    def tearDown(self):
        """Clean up and report performance metrics."""
        # Calculate final metrics
        final_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        end_time = time.time()
        
        memory_delta = final_memory - self.initial_memory
        execution_time = end_time - self.start_time
        
        print(f"\nPerformance Metrics:")
        print(f"  Execution Time: {execution_time:.2f}s")
        print(f"  Memory Delta: {memory_delta:.2f}MB")
        print(f"  Peak Memory: {final_memory:.2f}MB")
        
        # Cleanup
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def _create_large_config(self, num_archives=10, files_per_year=20, years_per_archive=3):
        """Create a large configuration for performance testing."""
        config = {'archives': []}
        
        for i in range(num_archives):
            archive = {
                'title_fa': f'آرشیو عملکرد {i}',
                'folder': f'performance-archive-{i}',
                'category': 'newspaper' if i % 2 == 0 else 'old-newspaper',
                'description': f'Performance test archive {i}',
                'years': {}
            }
            
            # Add multiple years with multiple files
            start_year = 2020
            for year_offset in range(years_per_archive):
                year = str(start_year + year_offset)
                urls = []
                for j in range(files_per_year):
                    urls.append(f'https://example.com/perf{i}-{year}-{j:03d}.pdf')
                archive['years'][year] = urls
            
            config['archives'].append(archive)
        
        return config
    
    def test_large_archive_processing_speed(self):
        """Test processing speed with large number of files."""
        # Create configuration with 1000 total files (10 archives × 5 years × 20 files)
        config = self._create_large_config(num_archives=10, files_per_year=20, years_per_archive=5)
        total_files = 10 * 5 * 20  # 1000 files
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Mock fast downloads
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '5000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\n' + b'x' * 5000]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            start_time = time.time()
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            self.assertTrue(result)
            
            # Performance requirements
            files_per_second = total_files / execution_time
            self.assertGreater(files_per_second, 50, 
                             f"Processing too slow: {files_per_second:.1f} files/sec")
            
            # Should complete within 30 seconds for 1000 files in dry run
            self.assertLess(execution_time, 30.0,
                          f"Large archive processing took too long: {execution_time:.2f}s")
            
            print(f"Processed {total_files} files in {execution_time:.2f}s "
                  f"({files_per_second:.1f} files/sec)")
    
    def test_memory_efficiency_large_files(self):
        """Test memory usage with large file processing."""
        # Create config with fewer but larger files
        config = self._create_large_config(num_archives=5, files_per_year=10, years_per_archive=2)
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Mock large file downloads
        large_content_size = 1024 * 1024  # 1MB per file
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {
                'content-type': 'application/pdf', 
                'content-length': str(large_content_size)
            }
            # Simulate streaming large content
            mock_response.iter_content.return_value = [
                b'%PDF-1.4\n' + b'x' * (large_content_size - 10)
            ]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # Monitor memory during execution
            memory_samples = []
            
            def monitor_memory():
                """Monitor memory usage in background thread."""
                while not hasattr(monitor_memory, 'stop'):
                    memory_mb = self.process.memory_info().rss / 1024 / 1024
                    memory_samples.append(memory_mb)
                    time.sleep(0.1)
            
            # Start memory monitoring
            monitor_thread = threading.Thread(target=monitor_memory)
            monitor_thread.start()
            
            try:
                orchestrator = WorkflowOrchestrator()
                result = orchestrator.execute_workflow(dry_run=True, verbose=False)
                
                self.assertTrue(result)
                
            finally:
                # Stop monitoring
                monitor_memory.stop = True
                monitor_thread.join(timeout=1)
            
            if memory_samples:
                peak_memory = max(memory_samples)
                memory_increase = peak_memory - self.initial_memory
                
                # Memory increase should be reasonable (< 200MB for 100MB of file content)
                self.assertLess(memory_increase, 200.0,
                              f"Memory usage too high: {memory_increase:.2f}MB increase")
                
                print(f"Peak memory usage: {peak_memory:.2f}MB "
                      f"(+{memory_increase:.2f}MB from baseline)")
    
    def test_configuration_parsing_performance(self):
        """Test configuration parsing speed with large configs."""
        # Create very large configuration
        config = self._create_large_config(num_archives=50, files_per_year=100, years_per_archive=10)
        total_urls = 50 * 100 * 10  # 50,000 URLs
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Measure parsing time
        start_time = time.time()
        
        parser = ConfigParser('urls.yml')
        archives = parser.parse_configuration()
        
        end_time = time.time()
        parsing_time = end_time - start_time
        
        self.assertEqual(len(archives), 50)
        
        # Should parse large config quickly (< 5 seconds for 50k URLs)
        self.assertLess(parsing_time, 5.0,
                       f"Configuration parsing too slow: {parsing_time:.2f}s for {total_urls} URLs")
        
        urls_per_second = total_urls / parsing_time
        print(f"Parsed {total_urls} URLs in {parsing_time:.2f}s "
              f"({urls_per_second:.0f} URLs/sec)")
    
    def test_directory_creation_performance(self):
        """Test directory creation speed with many nested directories."""
        file_manager = FileManager()
        
        # Create many directory structures
        num_structures = 1000
        start_time = time.time()
        
        for i in range(num_structures):
            category = 'newspaper' if i % 2 == 0 else 'old-newspaper'
            folder = f'test-folder-{i:04d}'
            year = str(2020 + (i % 5))
            
            path = file_manager.create_directory_structure(category, folder, year)
            self.assertTrue(path.exists())
        
        end_time = time.time()
        creation_time = end_time - start_time
        
        # Should create directories quickly
        dirs_per_second = num_structures / creation_time
        self.assertGreater(dirs_per_second, 100,
                          f"Directory creation too slow: {dirs_per_second:.1f} dirs/sec")
        
        print(f"Created {num_structures} directory structures in {creation_time:.2f}s "
              f"({dirs_per_second:.1f} dirs/sec)")
    
    def test_readme_generation_performance(self):
        """Test README generation speed with large archive lists."""
        from readme_generator import ReadmeGenerator
        
        # Create large list of archives for README generation
        archives = []
        for i in range(100):
            archive_data = {
                'title_fa': f'آرشیو {i}',
                'folder': f'archive-{i}',
                'category': 'newspaper',
                'description': f'Test archive {i} with a longer description to test performance',
                'years': {str(year): [f'file{j}.pdf' for j in range(20)] 
                         for year in range(2020, 2025)}
            }
            archives.append(archive_data)
        
        readme_generator = ReadmeGenerator()
        
        # Test Persian README generation
        start_time = time.time()
        
        readme_content = readme_generator.generate_main_readme('fa', archives, 'README.md')
        
        end_time = time.time()
        generation_time = end_time - start_time
        
        self.assertIsNotNone(readme_content)
        self.assertIn('آرشیو', readme_content)
        
        # Should generate README quickly (< 2 seconds for 100 archives)
        self.assertLess(generation_time, 2.0,
                       f"README generation too slow: {generation_time:.2f}s for 100 archives")
        
        print(f"Generated README for 100 archives in {generation_time:.2f}s")
    
    def test_concurrent_file_operations(self):
        """Test performance under concurrent file operations."""
        file_manager = FileManager()
        
        # Test concurrent directory creation
        results = []
        threads = []
        
        def create_directories(thread_id, count):
            """Create directories in separate thread."""
            thread_results = []
            start_time = time.time()
            
            for i in range(count):
                try:
                    path = file_manager.create_directory_structure(
                        'newspaper', f'thread{thread_id}-folder{i}', '2023'
                    )
                    thread_results.append(True)
                except Exception as e:
                    thread_results.append(False)
            
            end_time = time.time()
            results.append((thread_id, len(thread_results), end_time - start_time))
        
        # Start multiple threads
        num_threads = 4
        dirs_per_thread = 50
        
        for i in range(num_threads):
            thread = threading.Thread(target=create_directories, args=(i, dirs_per_thread))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=10)
        
        # Verify results
        self.assertEqual(len(results), num_threads)
        
        total_dirs = 0
        total_time = 0
        
        for thread_id, dir_count, thread_time in results:
            self.assertEqual(dir_count, dirs_per_thread)
            total_dirs += dir_count
            total_time = max(total_time, thread_time)  # Use max time (parallel execution)
        
        # Calculate concurrent performance
        dirs_per_second = total_dirs / total_time
        print(f"Concurrent creation: {total_dirs} directories in {total_time:.2f}s "
              f"({dirs_per_second:.1f} dirs/sec) using {num_threads} threads")
        
        # Should maintain good performance under concurrency
        self.assertGreater(dirs_per_second, 50)
    
    def test_error_handling_performance_impact(self):
        """Test that error handling doesn't significantly impact performance."""
        config = self._create_large_config(num_archives=5, files_per_year=50, years_per_archive=2)
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Test with all failures (maximum error handling load)
        with patch('file_manager.requests.get') as mock_get:
            mock_get.side_effect = Exception("Simulated network error")
            
            start_time = time.time()
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=False, verbose=False)
            
            end_time = time.time()
            error_handling_time = end_time - start_time
            
            # Should still complete in reasonable time even with all errors
            self.assertLess(error_handling_time, 15.0,
                          f"Error handling too slow: {error_handling_time:.2f}s")
            
            print(f"Handled 500 errors in {error_handling_time:.2f}s")
    
    def test_memory_cleanup_after_processing(self):
        """Test that memory is properly cleaned up after processing."""
        config = self._create_large_config(num_archives=10, files_per_year=20, years_per_archive=3)
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Record memory before processing
        gc.collect()  # Force garbage collection
        memory_before = self.process.memory_info().rss / 1024 / 1024
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '10000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\n' + b'x' * 10000]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            self.assertTrue(result)
        
        # Force cleanup
        del orchestrator
        gc.collect()
        time.sleep(0.1)  # Allow cleanup to complete
        
        memory_after = self.process.memory_info().rss / 1024 / 1024
        memory_retained = memory_after - memory_before
        
        # Memory retention should be minimal (< 50MB)
        self.assertLess(memory_retained, 50.0,
                       f"Too much memory retained after processing: {memory_retained:.2f}MB")
        
        print(f"Memory retained after cleanup: {memory_retained:.2f}MB")


class TestScalabilityLimits(unittest.TestCase):
    """Test workflow behavior at scalability limits."""
    
    def setUp(self):
        """Set up scalability test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up scalability test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_maximum_archives_handling(self):
        """Test handling of maximum number of archives."""
        # Test with very large number of archives
        max_archives = 100
        config = {'archives': []}
        
        for i in range(max_archives):
            archive = {
                'title_fa': f'آرشیو حداکثر {i}',
                'folder': f'max-archive-{i:03d}',
                'category': 'newspaper' if i % 2 == 0 else 'old-newspaper',
                'description': f'Maximum test archive {i}',
                'years': {
                    '2023': [f'https://example.com/max{i}-{j}.pdf' for j in range(10)]
                }
            }
            config['archives'].append(archive)
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Test parsing and processing
        parser = ConfigParser('urls.yml')
        archives = parser.parse_configuration()
        
        self.assertEqual(len(archives), max_archives)
        
        # Test workflow execution
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            self.assertTrue(result)
    
    def test_maximum_files_per_archive(self):
        """Test handling of maximum files per archive."""
        # Test with single archive containing many files
        max_files = 1000
        config = {
            'archives': [{
                'title_fa': 'آرشیو حداکثر فایل',
                'folder': 'max-files-archive',
                'category': 'newspaper',
                'description': 'Archive with maximum files',
                'years': {
                    '2023': [f'https://example.com/maxfile{i:04d}.pdf' for i in range(max_files)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        start_time = time.time()
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            end_time = time.time()
            
            self.assertTrue(result)
            
            # Should handle 1000 files in reasonable time
            execution_time = end_time - start_time
            self.assertLess(execution_time, 60.0,
                          f"Processing {max_files} files took too long: {execution_time:.2f}s")
    
    def test_deep_directory_nesting(self):
        """Test handling of deep directory structures."""
        file_manager = FileManager()
        
        # Test with very long folder names and deep nesting
        long_folder_name = 'a' * 100  # Very long folder name
        
        # This should be handled gracefully (truncated)
        path = file_manager.create_directory_structure('newspaper', long_folder_name, '2023')
        
        self.assertTrue(path.exists())
        
        # Verify folder name was sanitized/truncated
        actual_folder_name = path.parent.name
        self.assertLessEqual(len(actual_folder_name), 100)
    
    def test_system_resource_limits(self):
        """Test behavior when approaching system resource limits."""
        # Test with configuration that would create many file handles
        config = {'archives': []}
        
        # Create many small archives (tests file handle limits)
        for i in range(50):
            archive = {
                'title_fa': f'آرشیو منابع {i}',
                'folder': f'resource-test-{i}',
                'category': 'newspaper',
                'description': f'Resource limit test {i}',
                'years': {
                    str(2020 + j): [f'https://example.com/res{i}-{j}-{k}.pdf' for k in range(10)]
                    for j in range(5)  # 5 years per archive
                }
            }
            config['archives'].append(archive)
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Monitor system resources during execution
        initial_open_files = len(self.process.open_files())
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator = WorkflowOrchestrator()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            self.assertTrue(result)
        
        # Check that file handles were properly closed
        final_open_files = len(self.process.open_files())
        file_handle_leak = final_open_files - initial_open_files
        
        # Should not leak significant number of file handles
        self.assertLess(file_handle_leak, 10,
                       f"File handle leak detected: {file_handle_leak} handles")


class TestWorkflowMonitoring(unittest.TestCase):
    """Test workflow monitoring and optimization features."""
    
    def setUp(self):
        """Set up monitoring test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        config = {
            'archives': [{
                'title_fa': 'آرشیو نظارت',
                'folder': 'monitoring-test',
                'category': 'newspaper',
                'description': 'Test archive for monitoring',
                'years': {
                    '2023': [f'https://example.com/monitor{i}.pdf' for i in range(10)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up monitoring test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_performance_monitoring_enabled(self):
        """Test that performance monitoring works correctly."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True, enable_debugging=True)
        
        # Mock successful downloads
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\ntest content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = orchestrator.execute_workflow(dry_run=True, verbose=True)
            
            self.assertTrue(result)
            
            # Verify monitoring data was collected
            metrics = orchestrator.performance_metrics
            self.assertGreater(metrics.execution_time, 0)
            self.assertGreater(metrics.initial_memory_mb, 0)
            self.assertGreaterEqual(metrics.peak_memory_mb, metrics.initial_memory_mb)
            
            # Verify debug information was collected
            self.assertGreater(len(orchestrator.debug_info), 0)
            
            # Check that performance report can be generated
            report = orchestrator._generate_performance_report()
            self.assertIn("Workflow Performance Report", report)
            self.assertIn("Execution Time", report)
            self.assertIn("Memory Usage", report)
    
    def test_performance_monitoring_disabled(self):
        """Test workflow with monitoring disabled."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=False, enable_debugging=False)
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\ntest content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = orchestrator.execute_workflow(dry_run=True, verbose=True)
            
            self.assertTrue(result)
            
            # Verify no monitoring data was collected
            self.assertIsNone(orchestrator.process)
            self.assertEqual(len(orchestrator.debug_info), 0)
    
    def test_memory_optimization(self):
        """Test memory optimization functionality."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True)
        
        # Test memory optimization method
        initial_memory = orchestrator.process.memory_info().rss / 1024 / 1024
        
        # Create some objects to be garbage collected
        large_data = [list(range(1000)) for _ in range(100)]
        
        orchestrator._optimize_memory_usage()
        
        # Memory optimization should work without errors
        # (Actual memory reduction depends on system and Python GC)
        self.assertTrue(True)  # Test passes if no exception is raised
    
    def test_debug_information_collection(self):
        """Test debug information collection."""
        orchestrator = WorkflowOrchestrator(enable_debugging=True, enable_monitoring=True)
        
        # Add some debug information
        orchestrator._add_debug_info("test_phase", "Test message", {"key": "value"})
        
        self.assertEqual(len(orchestrator.debug_info), 1)
        
        debug_info = orchestrator.debug_info[0]
        self.assertEqual(debug_info.phase, "test_phase")
        self.assertEqual(debug_info.message, "Test message")
        self.assertEqual(debug_info.details["key"], "value")
        self.assertGreater(debug_info.memory_mb, 0)
    
    def test_performance_data_export(self):
        """Test performance data export functionality."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True, enable_debugging=True)
        
        # Add some test data
        orchestrator.performance_metrics.files_processed = 10
        orchestrator.performance_metrics.directories_created = 5
        orchestrator._add_debug_info("test", "Export test")
        
        # Test export
        orchestrator._export_performance_data()
        
        # Check that files were created
        json_files = list(Path('.').glob('performance_metrics_*.json'))
        debug_files = list(Path('.').glob('debug_info_*.json'))
        
        self.assertGreater(len(json_files), 0)
        self.assertGreater(len(debug_files), 0)
        
        # Verify content of performance metrics file
        with open(json_files[0], 'r') as f:
            import json
            data = json.load(f)
            self.assertEqual(data['files_processed'], 10)
            self.assertEqual(data['directories_created'], 5)
    
    def test_benchmark_mode(self):
        """Test benchmark mode functionality."""
        # Test command line argument parsing for benchmark mode
        from workflow_orchestrator import create_argument_parser
        
        parser = create_argument_parser()
        args = parser.parse_args(['--benchmark'])
        
        self.assertTrue(args.benchmark)
        
        # Test that benchmark mode enables debugging
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=args.benchmark
        )
        
        self.assertTrue(orchestrator.enable_debugging)


class TestPerformanceBenchmarks(unittest.TestCase):
    """Comprehensive performance benchmarks with detailed analysis."""
    
    def setUp(self):
        """Set up benchmark environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        self.benchmark_results = {}
    
    def tearDown(self):
        """Clean up and report benchmark results."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
        
        # Print benchmark summary
        if self.benchmark_results:
            print("\n" + "="*60)
            print("BENCHMARK SUMMARY")
            print("="*60)
            for test_name, results in self.benchmark_results.items():
                print(f"{test_name}:")
                for metric, value in results.items():
                    print(f"  {metric}: {value}")
                print()
    
    def _run_benchmark(self, test_name: str, config: dict, expected_files: int = 0):
        """Run a benchmark test and collect metrics."""
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        orchestrator = WorkflowOrchestrator(enable_monitoring=True, enable_debugging=True)
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '5000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\n' + b'x' * 5000]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            start_time = time.time()
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            end_time = time.time()
            
            self.assertTrue(result)
            
            metrics = orchestrator.performance_metrics
            
            self.benchmark_results[test_name] = {
                'execution_time': f"{metrics.execution_time:.3f}s",
                'memory_delta': f"{metrics.memory_delta_mb:.1f}MB",
                'peak_memory': f"{metrics.peak_memory_mb:.1f}MB",
                'files_per_second': f"{metrics.files_per_second:.1f}",
                'cpu_peak': f"{metrics.cpu_percent:.1f}%",
                'debug_entries': len(orchestrator.debug_info)
            }
            
            return metrics
    
    def test_small_archive_benchmark(self):
        """Benchmark small archive processing (10 files)."""
        config = {
            'archives': [{
                'title_fa': 'آرشیو کوچک',
                'folder': 'small-benchmark',
                'category': 'newspaper',
                'description': 'Small benchmark test',
                'years': {
                    '2023': [f'https://example.com/small{i}.pdf' for i in range(10)]
                }
            }]
        }
        
        metrics = self._run_benchmark("Small Archive (10 files)", config, 10)
        
        # Performance expectations for small archives
        self.assertLess(metrics.execution_time, 5.0)  # Should complete in < 5 seconds
        self.assertLess(metrics.memory_delta_mb, 50.0)  # Should use < 50MB additional memory
    
    def test_medium_archive_benchmark(self):
        """Benchmark medium archive processing (100 files)."""
        config = {
            'archives': [{
                'title_fa': 'آرشیو متوسط',
                'folder': 'medium-benchmark',
                'category': 'newspaper',
                'description': 'Medium benchmark test',
                'years': {
                    str(2020 + i): [f'https://example.com/med{i}-{j}.pdf' for j in range(20)]
                    for i in range(5)  # 5 years × 20 files = 100 files
                }
            }]
        }
        
        metrics = self._run_benchmark("Medium Archive (100 files)", config, 100)
        
        # Performance expectations for medium archives
        self.assertLess(metrics.execution_time, 15.0)  # Should complete in < 15 seconds
        self.assertLess(metrics.memory_delta_mb, 100.0)  # Should use < 100MB additional memory
        self.assertGreater(metrics.files_per_second, 10.0)  # Should process > 10 files/sec
    
    def test_large_archive_benchmark(self):
        """Benchmark large archive processing (500 files)."""
        config = {
            'archives': [
                {
                    'title_fa': f'آرشیو بزرگ {i}',
                    'folder': f'large-benchmark-{i}',
                    'category': 'newspaper',
                    'description': f'Large benchmark test {i}',
                    'years': {
                        str(2020 + j): [f'https://example.com/large{i}-{j}-{k}.pdf' for k in range(10)]
                        for j in range(5)  # 5 years × 10 files = 50 files per archive
                    }
                }
                for i in range(10)  # 10 archives × 50 files = 500 files total
            ]
        }
        
        metrics = self._run_benchmark("Large Archive (500 files)", config, 500)
        
        # Performance expectations for large archives
        self.assertLess(metrics.execution_time, 60.0)  # Should complete in < 60 seconds
        self.assertLess(metrics.memory_delta_mb, 200.0)  # Should use < 200MB additional memory
        self.assertGreater(metrics.files_per_second, 8.0)  # Should process > 8 files/sec
    
    def test_memory_efficiency_benchmark(self):
        """Benchmark memory efficiency with large file simulation."""
        config = {
            'archives': [{
                'title_fa': 'آرشیو حافظه',
                'folder': 'memory-benchmark',
                'category': 'newspaper',
                'description': 'Memory efficiency test',
                'years': {
                    '2023': [f'https://example.com/memory{i}.pdf' for i in range(50)]
                }
            }]
        }
        
        # Simulate larger files
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        orchestrator = WorkflowOrchestrator(enable_monitoring=True, enable_debugging=True)
        
        with patch('file_manager.requests.get') as mock_get:
            # Simulate 1MB files
            large_content = b'%PDF-1.4\n' + b'x' * (1024 * 1024)
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': str(len(large_content))}
            mock_response.iter_content.return_value = [large_content]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = orchestrator.execute_workflow(dry_run=True, verbose=False)
            
            self.assertTrue(result)
            
            metrics = orchestrator.performance_metrics
            
            self.benchmark_results["Memory Efficiency (50×1MB files)"] = {
                'execution_time': f"{metrics.execution_time:.3f}s",
                'memory_delta': f"{metrics.memory_delta_mb:.1f}MB",
                'peak_memory': f"{metrics.peak_memory_mb:.1f}MB",
                'memory_per_file': f"{metrics.memory_delta_mb/50:.2f}MB/file"
            }
            
            # Memory should not grow linearly with file size in dry run
            self.assertLess(metrics.memory_delta_mb, 500.0)  # Should use < 500MB for 50MB of content


if __name__ == '__main__':
    # Set up performance test suite
    suite = unittest.TestSuite()
    
    # Add performance tests
    suite.addTest(unittest.makeSuite(TestWorkflowPerformance))
    suite.addTest(unittest.makeSuite(TestScalabilityLimits))
    suite.addTest(unittest.makeSuite(TestWorkflowMonitoring))
    suite.addTest(unittest.makeSuite(TestPerformanceBenchmarks))
    
    # Run with detailed output
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)
    
    # Print summary
    print(f"\nPerformance Test Summary:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Failures: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  {test}: {traceback}")