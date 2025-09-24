"""
Unit tests for Performance Monitor utility.
"""

import unittest
import tempfile
import shutil
import os
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from performance_monitor import PerformanceMonitor, monitor_workflow_execution


class TestPerformanceMonitor(unittest.TestCase):
    """Test cases for PerformanceMonitor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        self.monitor = PerformanceMonitor("test_performance_data")
    
    def tearDown(self):
        """Clean up test fixtures."""
        if self.monitor.monitoring_active:
            self.monitor.stop_monitoring()
        
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_monitor_initialization(self):
        """Test performance monitor initialization."""
        self.assertFalse(self.monitor.monitoring_active)
        self.assertIsNone(self.monitor.monitoring_thread)
        self.assertEqual(len(self.monitor.performance_data), 0)
        self.assertTrue(self.monitor.output_dir.exists())
    
    @patch('psutil.Process')
    def test_start_stop_monitoring(self, mock_process_class):
        """Test starting and stopping monitoring."""
        # Mock psutil.Process
        mock_process = Mock()
        mock_process.cpu_percent.return_value = 10.0
        mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_process.memory_percent.return_value = 5.0
        mock_process.num_threads.return_value = 2
        mock_process.open_files.return_value = []
        mock_process.io_counters.return_value = Mock(read_bytes=1024, write_bytes=2048)
        mock_process_class.return_value = mock_process
        
        # Mock system-wide psutil functions
        with patch('psutil.cpu_percent', return_value=15.0), \
             patch('psutil.virtual_memory', return_value=Mock(percent=60.0, available=2048*1024*1024)), \
             patch('psutil.disk_usage', return_value=Mock(percent=50.0)), \
             patch('psutil.net_io_counters', return_value=Mock(bytes_sent=1000, bytes_recv=2000)):
            
            # Start monitoring
            self.monitor.start_monitoring(interval=0.1)
            self.assertTrue(self.monitor.monitoring_active)
            self.assertIsNotNone(self.monitor.monitoring_thread)
            
            # Let it collect some data
            time.sleep(0.3)
            
            # Stop monitoring
            self.monitor.stop_monitoring()
            self.assertFalse(self.monitor.monitoring_active)
            
            # Should have collected some data points
            self.assertGreater(len(self.monitor.performance_data), 0)
            
            # Verify data structure
            data_point = self.monitor.performance_data[0]
            self.assertIn('timestamp', data_point)
            self.assertIn('process_cpu_percent', data_point)
            self.assertIn('process_memory_mb', data_point)
            self.assertIn('system_cpu_percent', data_point)
    
    def test_export_data(self):
        """Test data export functionality."""
        # Add some test data
        test_data = [
            {'timestamp': time.time(), 'process_cpu_percent': 10.0, 'process_memory_mb': 100.0},
            {'timestamp': time.time() + 1, 'process_cpu_percent': 15.0, 'process_memory_mb': 105.0}
        ]
        self.monitor.performance_data = test_data
        
        # Export data
        filepath = self.monitor.export_data("test_export.json")
        
        # Verify file was created
        self.assertTrue(Path(filepath).exists())
        
        # Verify content
        with open(filepath, 'r') as f:
            exported_data = json.load(f)
        
        self.assertEqual(len(exported_data), 2)
        self.assertEqual(exported_data[0]['process_cpu_percent'], 10.0)
    
    def test_generate_report_empty_data(self):
        """Test report generation with no data."""
        report = self.monitor.generate_report()
        self.assertEqual(report, "No performance data available.")
    
    def test_generate_report_with_data(self):
        """Test report generation with sample data."""
        # Add sample data
        test_data = []
        for i in range(10):
            test_data.append({
                'timestamp': time.time() + i,
                'elapsed_time': i,
                'process_cpu_percent': 10.0 + i,
                'process_memory_mb': 100.0 + i * 5,
                'process_io_read_mb': i * 2,
                'process_io_write_mb': i * 3,
                'system_cpu_percent': 20.0 + i,
                'system_memory_percent': 50.0 + i
            })
        
        self.monitor.performance_data = test_data
        
        report = self.monitor.generate_report()
        
        self.assertIn("Performance Analysis Report", report)
        self.assertIn("CPU Usage:", report)
        self.assertIn("Memory Usage:", report)
        self.assertIn("I/O Operations:", report)
        # Note: System Performance section only available with pandas
    
    def test_analyze_performance_trends(self):
        """Test performance trend analysis."""
        # Add sample data with trends
        test_data = []
        for i in range(20):
            test_data.append({
                'elapsed_time': i,
                'process_cpu_percent': 10.0 + i * 2,  # Increasing trend
                'process_memory_mb': 100.0 + i * 5,   # Increasing trend
            })
        
        self.monitor.performance_data = test_data
        
        analysis = self.monitor.analyze_performance_trends()
        
        self.assertIn('duration', analysis)
        self.assertIn('cpu_trend', analysis)
        self.assertIn('memory_trend', analysis)
        self.assertIn('efficiency_score', analysis)
        
        # Should detect increasing trends
        self.assertEqual(analysis['cpu_trend'], 'increasing')
        self.assertEqual(analysis['memory_trend'], 'increasing')
        
        # Should have efficiency score
        self.assertIsInstance(analysis['efficiency_score'], float)
        self.assertGreaterEqual(analysis['efficiency_score'], 0)
        self.assertLessEqual(analysis['efficiency_score'], 100)
    
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.close')
    @patch('matplotlib.pyplot.tight_layout')
    @patch('matplotlib.pyplot.subplot')
    @patch('matplotlib.pyplot.plot')
    @patch('matplotlib.pyplot.figure')
    def test_create_visualizations(self, mock_figure, mock_plot, mock_subplot, 
                                 mock_tight_layout, mock_close, mock_savefig):
        """Test visualization creation."""
        # Add sample data
        test_data = []
        for i in range(10):
            test_data.append({
                'elapsed_time': i,
                'process_cpu_percent': 10.0 + i,
                'process_memory_mb': 100.0 + i * 5,
                'process_io_read_mb': i * 2,
                'process_io_write_mb': i * 3,
                'system_cpu_percent': 20.0,
                'process_threads': 2,
                'process_open_files': 5
            })
        
        self.monitor.performance_data = test_data
        
        chart_files = self.monitor.create_visualizations()
        
        # Should return list of chart files
        self.assertIsInstance(chart_files, list)
        self.assertGreater(len(chart_files), 0)
        
        # Should have called matplotlib functions
        mock_figure.assert_called_once()
        mock_savefig.assert_called_once()
        mock_close.assert_called_once()
    
    def test_create_visualizations_no_data(self):
        """Test visualization creation with no data."""
        chart_files = self.monitor.create_visualizations()
        self.assertEqual(chart_files, [])


class TestMonitorWorkflowExecution(unittest.TestCase):
    """Test cases for workflow execution monitoring."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        import yaml
        config = {
            'archives': [{
                'title_fa': 'آرشیو تست',
                'folder': 'test-archive',
                'category': 'newspaper',
                'description': 'Test archive for monitoring',
                'years': {
                    '2023': ['https://example.com/test1.pdf', 'https://example.com/test2.pdf']
                }
            }]
        }
        
        with open('urls.yml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('performance_monitor.PerformanceMonitor')
    @patch('workflow_orchestrator.WorkflowOrchestrator')
    def test_monitor_workflow_execution(self, mock_orchestrator_class, mock_monitor_class):
        """Test monitoring workflow execution."""
        # Mock monitor
        mock_monitor = Mock()
        mock_monitor.performance_data = [{'test': 'data'}]
        mock_monitor.output_dir = Path('test_output')
        mock_monitor.export_data.return_value = 'test_file.json'
        mock_monitor.generate_report.return_value = 'Test report'
        mock_monitor.create_visualizations.return_value = ['chart.png']
        mock_monitor.analyze_performance_trends.return_value = {
            'efficiency_score': 85.0,
            'cpu_trend': 'stable',
            'memory_trend': 'stable'
        }
        mock_monitor_class.return_value = mock_monitor
        
        # Mock orchestrator
        mock_orchestrator = Mock()
        mock_orchestrator.execute_workflow.return_value = True
        mock_orchestrator_class.return_value = mock_orchestrator
        
        # Run monitoring
        monitor_workflow_execution('urls.yml', 0.1, 'test_output')
        
        # Verify monitor was used correctly
        mock_monitor.start_monitoring.assert_called_once_with(0.1)
        mock_monitor.stop_monitoring.assert_called_once()
        mock_monitor.export_data.assert_called_once()
        mock_monitor.generate_report.assert_called_once()
        mock_monitor.create_visualizations.assert_called_once()
        mock_monitor.analyze_performance_trends.assert_called_once()
        
        # Verify orchestrator was used correctly
        mock_orchestrator.execute_workflow.assert_called_once_with(dry_run=True, verbose=True)


class TestPerformanceMonitorCLI(unittest.TestCase):
    """Test cases for performance monitor command line interface."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_argument_parsing(self):
        """Test command line argument parsing."""
        from performance_monitor import main
        import sys
        
        # Test default arguments
        with patch.object(sys, 'argv', ['performance_monitor.py']):
            with patch('performance_monitor.monitor_workflow_execution') as mock_monitor:
                with patch('sys.exit'):
                    try:
                        main()
                    except SystemExit:
                        pass
                
                mock_monitor.assert_called_once_with(
                    config_path='urls.yml',
                    monitoring_interval=0.5,
                    output_dir='performance_data'
                )
    
    def test_analyze_only_mode(self):
        """Test analyze-only mode."""
        from performance_monitor import main
        import sys
        
        # Create test data directory and file
        output_dir = Path('test_performance_data')
        output_dir.mkdir()
        
        test_data = [{'timestamp': time.time(), 'elapsed_time': 1.0, 'process_cpu_percent': 10.0, 'process_memory_mb': 100.0}]
        data_file = output_dir / 'performance_data_20231201_120000.json'
        with open(data_file, 'w') as f:
            json.dump(test_data, f)
        
        with patch.object(sys, 'argv', ['performance_monitor.py', '--analyze-only', '--output-dir', 'test_performance_data']):
            with patch('sys.exit') as mock_exit:
                with patch('builtins.print') as mock_print:
                    main()
                
                mock_exit.assert_called_once_with(0)
                
                # Should have printed analysis
                print_calls = [call[0][0] for call in mock_print.call_calls]
                analysis_printed = any('Performance Analysis Report' in call for call in print_calls)
                self.assertTrue(analysis_printed)


if __name__ == '__main__':
    unittest.main()