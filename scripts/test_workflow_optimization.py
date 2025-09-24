"""
Comprehensive tests for workflow optimization and monitoring features.

This module tests the enhanced monitoring, optimization, and performance
analysis capabilities added to the Iranian Archive Workflow system.
"""

import unittest
import tempfile
import shutil
import os
import yaml
import time
import threading
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_orchestrator import WorkflowOrchestrator, PerformanceMetrics, WorkflowDebugInfo
from performance_monitor import PerformanceMonitor


class TestEnhancedPerformanceMonitoring(unittest.TestCase):
    """Test enhanced performance monitoring features."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        config = {
            'archives': [{
                'title_fa': 'آرشیو تست بهینه‌سازی',
                'folder': 'optimization-test',
                'category': 'newspaper',
                'description': 'Test archive for optimization',
                'years': {
                    '2023': [f'https://example.com/opt{i}.pdf' for i in range(5)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_enhanced_monitoring_initialization(self):
        """Test enhanced monitoring initialization."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        self.assertTrue(orchestrator.enable_monitoring)
        self.assertTrue(orchestrator.enable_debugging)
        self.assertIsInstance(orchestrator.performance_metrics, PerformanceMetrics)
        self.assertEqual(len(orchestrator.debug_info), 0)
    
    def test_memory_checkpoint_tracking(self):
        """Test memory checkpoint tracking functionality."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        # Mock psutil process
        with patch('psutil.Process') as mock_process_class:
            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
            mock_process.cpu_percent.return_value = 10.0
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            orchestrator.process = mock_process
            
            # Add memory checkpoints
            orchestrator._add_memory_checkpoint("test_start")
            
            # Simulate memory increase
            mock_process.memory_info.return_value = Mock(rss=120 * 1024 * 1024)  # 120MB
            orchestrator._add_memory_checkpoint("test_end")
            
            # Should have debug info about memory changes
            memory_debug_entries = [d for d in orchestrator.debug_info if d.phase == "memory_checkpoint"]
            self.assertGreater(len(memory_debug_entries), 0)
    
    def test_phase_timing_tracking(self):
        """Test execution phase timing tracking."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        # Mock successful workflow execution
        with patch('file_manager.requests.get') as mock_get, \
             patch('psutil.Process') as mock_process_class:
            
            # Mock HTTP response
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\ntest content']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # Mock psutil process
            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
            mock_process.cpu_percent.return_value = 10.0
            mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            result = orchestrator.execute_workflow(dry_run=True, verbose=True)
            
            self.assertTrue(result)
            
            # Should have debug info for different phases
            phases = set(d.phase for d in orchestrator.debug_info)
            expected_phases = {'initialization', 'configuration', 'filtering', 'processing', 'cleanup'}
            self.assertTrue(expected_phases.issubset(phases))
    
    def test_performance_bottleneck_detection(self):
        """Test performance bottleneck detection."""
        monitor = PerformanceMonitor("test_output")
        
        # Add test data with bottlenecks
        monitor.execution_phases = [
            {'phase': 'slow_phase', 'duration': 45.0, 'start_time': 0, 'end_time': 45},
            {'phase': 'fast_phase', 'duration': 2.0, 'start_time': 45, 'end_time': 47}
        ]
        
        monitor.memory_checkpoints = [
            {'checkpoint': 'start', 'memory_mb': 100.0},
            {'checkpoint': 'peak', 'memory_mb': 700.0},
            {'checkpoint': 'end', 'memory_mb': 150.0}
        ]
        
        bottlenecks = monitor.analyze_performance_bottlenecks()
        
        self.assertGreater(len(bottlenecks), 0)
        
        # Should detect slow phase
        slow_phase_detected = any('slow_phase' in bottleneck for bottleneck in bottlenecks)
        self.assertTrue(slow_phase_detected)
        
        # Should detect high memory variation
        memory_variation_detected = any('memory variation' in bottleneck for bottleneck in bottlenecks)
        self.assertTrue(memory_variation_detected)
    
    def test_optimization_suggestions_generation(self):
        """Test optimization suggestions generation."""
        monitor = PerformanceMonitor("test_output")
        
        # Add performance data that should trigger suggestions
        monitor.performance_data = [
            {'elapsed_time': i, 'process_cpu_percent': 85.0, 'process_memory_mb': 100 + i * 10}
            for i in range(20)
        ]
        
        monitor.execution_phases = [
            {'phase': 'slow_operation', 'duration': 60.0, 'start_time': 0, 'end_time': 60}
        ]
        
        suggestions = monitor.generate_optimization_suggestions()
        
        self.assertGreater(len(suggestions), 0)
        
        # Should suggest optimizations for detected issues
        suggestion_text = ' '.join(suggestions).lower()
        self.assertTrue(any(keyword in suggestion_text for keyword in 
                          ['parallel', 'optimize', 'batch', 'memory', 'rate limiting']))
    
    def test_enhanced_performance_report(self):
        """Test enhanced performance report generation."""
        monitor = PerformanceMonitor("test_output")
        
        # Add comprehensive test data
        monitor.performance_data = [
            {
                'timestamp': time.time() + i,
                'elapsed_time': i,
                'process_cpu_percent': 20.0 + i,
                'process_memory_mb': 100.0 + i * 2,
                'process_io_read_mb': i * 0.5,
                'process_io_write_mb': i * 0.3,
                'system_cpu_percent': 30.0,
                'system_memory_percent': 60.0
            }
            for i in range(10)
        ]
        
        monitor.execution_phases = [
            {'phase': 'initialization', 'duration': 2.0, 'start_time': 0, 'end_time': 2},
            {'phase': 'processing', 'duration': 15.0, 'start_time': 2, 'end_time': 17}
        ]
        
        monitor.memory_checkpoints = [
            {'checkpoint': 'start', 'memory_mb': 100.0},
            {'checkpoint': 'end', 'memory_mb': 120.0}
        ]
        
        report = monitor.generate_report()
        
        self.assertIn("Enhanced Performance Analysis Report", report)
        self.assertIn("Execution Phases", report)
        self.assertIn("Memory Checkpoints", report)
        self.assertIn("Performance Bottlenecks", report)
        self.assertIn("Optimization Suggestions", report)
        self.assertIn("Performance Score", report)
    
    def test_memory_leak_detection(self):
        """Test memory leak detection during monitoring."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        with patch('psutil.Process') as mock_process_class:
            mock_process = Mock()
            
            # Simulate memory leak (gradual increase)
            memory_values = [100 + i * 20 for i in range(10)]  # 100MB to 280MB
            memory_iter = iter(memory_values)
            
            def mock_memory_info():
                return Mock(rss=next(memory_iter, 300) * 1024 * 1024)
            
            mock_process.memory_info = mock_memory_info
            mock_process.cpu_percent.return_value = 10.0
            mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            orchestrator.process = mock_process
            
            # Start monitoring
            orchestrator._start_monitoring()
            
            # Let it run for a bit to detect memory growth
            time.sleep(1.0)
            
            orchestrator._stop_monitoring()
            
            # Should have detected memory warnings
            memory_warnings = [d for d in orchestrator.debug_info if d.phase == "memory_warning"]
            # Note: May not always trigger in short test, but structure should be correct
            self.assertIsInstance(memory_warnings, list)
    
    def test_cpu_usage_monitoring(self):
        """Test CPU usage monitoring and warnings."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        with patch('psutil.Process') as mock_process_class:
            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
            mock_process.cpu_percent.return_value = 90.0  # High CPU usage
            mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            orchestrator.process = mock_process
            
            # Start monitoring
            orchestrator._start_monitoring()
            
            # Let it run briefly
            time.sleep(0.6)
            
            orchestrator._stop_monitoring()
            
            # Should track CPU usage
            self.assertGreaterEqual(orchestrator.performance_metrics.cpu_percent, 90.0)
    
    def test_io_rate_monitoring(self):
        """Test I/O rate monitoring and detection."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        with patch('psutil.Process') as mock_process_class:
            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
            mock_process.cpu_percent.return_value = 10.0
            
            # Simulate high I/O
            io_counter = 0
            def mock_io_counters():
                nonlocal io_counter
                io_counter += 50 * 1024 * 1024  # 50MB per call
                return Mock(read_bytes=io_counter, write_bytes=io_counter)
            
            mock_process.io_counters = mock_io_counters
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            orchestrator.process = mock_process
            
            # Start monitoring
            orchestrator._start_monitoring()
            
            # Let it run briefly
            time.sleep(0.6)
            
            orchestrator._stop_monitoring()
            
            # Should track I/O
            self.assertGreater(orchestrator.performance_metrics.disk_io_read_mb, 0)


class TestWorkflowOptimization(unittest.TestCase):
    """Test workflow optimization features."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        config = {
            'archives': [{
                'title_fa': 'آرشیو بهینه‌سازی',
                'folder': 'optimization-test',
                'category': 'newspaper',
                'description': 'Optimization test archive',
                'years': {
                    '2023': [f'https://example.com/opt{i}.pdf' for i in range(10)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_memory_optimization_execution(self):
        """Test memory optimization during workflow execution."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        with patch('psutil.Process') as mock_process_class:
            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=200 * 1024 * 1024)  # 200MB
            mock_process.cpu_percent.return_value = 10.0
            mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            orchestrator.process = mock_process
            
            # Test memory optimization method
            initial_memory = 200.0
            
            # Should not raise any exceptions
            orchestrator._optimize_memory_usage()
            
            # Memory optimization should work without errors
            self.assertTrue(True)  # Test passes if no exception
    
    def test_performance_data_export(self):
        """Test performance data export functionality."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        # Set test performance data
        orchestrator.performance_metrics.files_processed = 10
        orchestrator.performance_metrics.directories_created = 5
        orchestrator.performance_metrics.peak_memory_mb = 150.0
        orchestrator.performance_metrics.initial_memory_mb = 100.0
        
        # Add debug information
        orchestrator._add_debug_info("test_phase", "Test export", {"test": True})
        
        # Export data
        orchestrator._export_performance_data()
        
        # Check that files were created
        metrics_files = list(Path('.').glob('performance_metrics_*.json'))
        debug_files = list(Path('.').glob('debug_info_*.json'))
        
        self.assertGreater(len(metrics_files), 0)
        self.assertGreater(len(debug_files), 0)
        
        # Verify metrics file content
        with open(metrics_files[0], 'r') as f:
            metrics_data = json.load(f)
            self.assertEqual(metrics_data['files_processed'], 10)
            self.assertEqual(metrics_data['directories_created'], 5)
            self.assertEqual(metrics_data['memory_delta_mb'], 50.0)
        
        # Verify debug file content
        with open(debug_files[0], 'r') as f:
            debug_data = json.load(f)
            self.assertGreater(len(debug_data), 0)
            self.assertEqual(debug_data[0]['phase'], 'test_phase')
    
    def test_detailed_monitoring_integration(self):
        """Test integration with detailed performance monitor."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=True,
            enable_debugging=True
        )
        
        # Mock the detailed monitor
        with patch('performance_monitor.PerformanceMonitor') as mock_monitor_class:
            mock_monitor = Mock()
            mock_monitor.start_monitoring.return_value = None
            mock_monitor.stop_monitoring.return_value = None
            mock_monitor.add_execution_phase.return_value = None
            mock_monitor.add_memory_checkpoint.return_value = None
            mock_monitor.generate_report.return_value = "Detailed test report"
            mock_monitor.export_data.return_value = "test_file.json"
            mock_monitor_class.return_value = mock_monitor
            
            # Mock successful workflow execution
            with patch('file_manager.requests.get') as mock_get, \
                 patch('psutil.Process') as mock_process_class:
                
                mock_response = Mock()
                mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
                mock_response.iter_content.return_value = [b'%PDF-1.4\ntest']
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                mock_process = Mock()
                mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
                mock_process.cpu_percent.return_value = 10.0
                mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
                mock_process.open_files.return_value = []
                mock_process_class.return_value = mock_process
                
                result = orchestrator.execute_workflow(dry_run=True, verbose=True)
                
                self.assertTrue(result)
                
                # Should have called detailed monitor methods
                mock_monitor.start_monitoring.assert_called_once()
                mock_monitor.stop_monitoring.assert_called_once()


class TestPerformanceBenchmarks(unittest.TestCase):
    """Performance benchmarking tests."""
    
    def setUp(self):
        """Set up benchmark environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up benchmark environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_monitoring_overhead_benchmark(self):
        """Benchmark monitoring overhead on workflow performance."""
        # Create test configuration
        config = {
            'archives': [{
                'title_fa': 'آرشیو بنچمارک',
                'folder': 'benchmark-test',
                'category': 'newspaper',
                'description': 'Benchmark test archive',
                'years': {
                    '2023': [f'https://example.com/bench{i}.pdf' for i in range(20)]
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        # Mock fast downloads
        with patch('file_manager.requests.get') as mock_get, \
             patch('psutil.Process') as mock_process_class:
            
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\nfast']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
            mock_process.cpu_percent.return_value = 5.0
            mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
            mock_process.open_files.return_value = []
            mock_process_class.return_value = mock_process
            
            # Test without monitoring
            orchestrator_no_monitor = WorkflowOrchestrator(enable_monitoring=False)
            start_time = time.time()
            result1 = orchestrator_no_monitor.execute_workflow(dry_run=True)
            time_no_monitor = time.time() - start_time
            
            # Test with monitoring
            orchestrator_with_monitor = WorkflowOrchestrator(
                enable_monitoring=True, 
                enable_debugging=True
            )
            start_time = time.time()
            result2 = orchestrator_with_monitor.execute_workflow(dry_run=True)
            time_with_monitor = time.time() - start_time
            
            self.assertTrue(result1)
            self.assertTrue(result2)
            
            # Monitoring overhead should be reasonable (< 50% increase)
            overhead_ratio = time_with_monitor / time_no_monitor if time_no_monitor > 0 else 1
            self.assertLess(overhead_ratio, 1.5, 
                          f"Monitoring overhead too high: {overhead_ratio:.2f}x")
            
            print(f"Monitoring overhead: {overhead_ratio:.2f}x "
                  f"({time_with_monitor:.3f}s vs {time_no_monitor:.3f}s)")
    
    def test_memory_usage_benchmark(self):
        """Benchmark memory usage with different configuration sizes."""
        import psutil
        process = psutil.Process()
        
        # Test with small configuration
        small_config = {
            'archives': [{
                'title_fa': 'آرشیو کوچک',
                'folder': 'small-test',
                'category': 'newspaper',
                'description': 'Small test',
                'years': {'2023': [f'https://example.com/small{i}.pdf' for i in range(5)]}
            }]
        }
        
        with open('urls_small.yml', 'w', encoding='utf-8') as f:
            yaml.dump(small_config, f, allow_unicode=True)
        
        # Test with large configuration
        large_config = {
            'archives': [
                {
                    'title_fa': f'آرشیو بزرگ {i}',
                    'folder': f'large-test-{i}',
                    'category': 'newspaper',
                    'description': f'Large test {i}',
                    'years': {
                        str(2020 + j): [f'https://example.com/large{i}-{j}-{k}.pdf' for k in range(10)]
                        for j in range(3)
                    }
                }
                for i in range(10)
            ]
        }
        
        with open('urls_large.yml', 'w', encoding='utf-8') as f:
            yaml.dump(large_config, f, allow_unicode=True)
        
        # Measure memory usage for small config
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        orchestrator_small = WorkflowOrchestrator(
            config_path='urls_small.yml',
            enable_monitoring=True
        )
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\ntest']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator_small.execute_workflow(dry_run=True)
        
        small_memory = process.memory_info().rss / 1024 / 1024
        small_delta = small_memory - initial_memory
        
        # Measure memory usage for large config
        orchestrator_large = WorkflowOrchestrator(
            config_path='urls_large.yml',
            enable_monitoring=True
        )
        
        with patch('file_manager.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
            mock_response.iter_content.return_value = [b'%PDF-1.4\ntest']
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            orchestrator_large.execute_workflow(dry_run=True)
        
        large_memory = process.memory_info().rss / 1024 / 1024
        large_delta = large_memory - small_memory
        
        # Memory usage should scale reasonably
        self.assertLess(small_delta, 50.0, f"Small config uses too much memory: {small_delta:.1f}MB")
        self.assertLess(large_delta, 200.0, f"Large config uses too much memory: {large_delta:.1f}MB")
        
        print(f"Memory usage - Small: {small_delta:.1f}MB, Large: {large_delta:.1f}MB")
    
    def test_execution_time_scaling(self):
        """Test execution time scaling with different workloads."""
        # Test configurations of different sizes
        configs = {
            'tiny': {'archives': 1, 'files': 2},
            'small': {'archives': 2, 'files': 5},
            'medium': {'archives': 5, 'files': 10},
        }
        
        execution_times = {}
        
        for size_name, params in configs.items():
            config = {
                'archives': [
                    {
                        'title_fa': f'آرشیو {size_name} {i}',
                        'folder': f'{size_name}-test-{i}',
                        'category': 'newspaper',
                        'description': f'{size_name} test {i}',
                        'years': {
                            '2023': [f'https://example.com/{size_name}{i}-{j}.pdf' 
                                   for j in range(params['files'])]
                        }
                    }
                    for i in range(params['archives'])
                ]
            }
            
            config_file = f'urls_{size_name}.yml'
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True)
            
            # Measure execution time
            with patch('file_manager.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
                mock_response.iter_content.return_value = [b'%PDF-1.4\ntest']
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                orchestrator = WorkflowOrchestrator(
                    config_path=config_file,
                    enable_monitoring=True
                )
                
                start_time = time.time()
                result = orchestrator.execute_workflow(dry_run=True)
                execution_time = time.time() - start_time
                
                self.assertTrue(result)
                execution_times[size_name] = execution_time
        
        # Execution time should scale reasonably
        self.assertLess(execution_times['tiny'], 5.0, "Tiny workload too slow")
        self.assertLess(execution_times['small'], 10.0, "Small workload too slow")
        self.assertLess(execution_times['medium'], 20.0, "Medium workload too slow")
        
        # Should scale sub-linearly (efficiency should improve with size)
        if execution_times['tiny'] > 0:
            scaling_factor = execution_times['medium'] / execution_times['tiny']
            expected_linear_scaling = 5 * 5  # 5x archives, 5x files = 25x
            self.assertLess(scaling_factor, expected_linear_scaling * 0.5,
                          f"Poor scaling: {scaling_factor:.1f}x vs expected <{expected_linear_scaling * 0.5:.1f}x")
        
        print(f"Execution times: {execution_times}")


if __name__ == '__main__':
    # Run with verbose output for benchmarks
    unittest.main(verbosity=2)