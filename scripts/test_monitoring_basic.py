"""
Basic tests for monitoring functionality without external dependencies.
"""

import unittest
import tempfile
import shutil
import os
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_orchestrator import WorkflowOrchestrator, PerformanceMetrics, WorkflowDebugInfo


class TestBasicMonitoring(unittest.TestCase):
    """Test basic monitoring functionality without psutil/matplotlib."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_performance_metrics_dataclass(self):
        """Test PerformanceMetrics dataclass functionality."""
        metrics = PerformanceMetrics()
        
        # Test default values
        self.assertEqual(metrics.peak_memory_mb, 0.0)
        self.assertEqual(metrics.files_processed, 0)
        
        # Test calculated properties
        self.assertGreater(metrics.execution_time, 0)
        self.assertEqual(metrics.memory_delta_mb, 0.0)
        self.assertEqual(metrics.files_per_second, 0.0)
        
        # Test with data
        metrics.files_processed = 10
        metrics.end_time = metrics.start_time + 5.0
        self.assertEqual(metrics.files_per_second, 2.0)
    
    def test_workflow_debug_info_dataclass(self):
        """Test WorkflowDebugInfo dataclass functionality."""
        debug_info = WorkflowDebugInfo(
            phase="test_phase",
            message="Test message",
            details={"key": "value"}
        )
        
        self.assertEqual(debug_info.phase, "test_phase")
        self.assertEqual(debug_info.message, "Test message")
        self.assertEqual(debug_info.details["key"], "value")
        self.assertIsNotNone(debug_info.timestamp)
    
    def test_orchestrator_monitoring_disabled(self):
        """Test orchestrator with monitoring disabled."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=False,
            enable_debugging=False
        )
        
        self.assertFalse(orchestrator.enable_monitoring)
        self.assertFalse(orchestrator.enable_debugging)
        self.assertEqual(len(orchestrator.debug_info), 0)
    
    def test_orchestrator_debugging_enabled(self):
        """Test orchestrator with debugging enabled."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=False,  # Disable monitoring to avoid psutil
            enable_debugging=True
        )
        
        self.assertTrue(orchestrator.enable_debugging)
        
        # Test adding debug info
        orchestrator._add_debug_info("test", "Test message", {"test": True})
        
        self.assertEqual(len(orchestrator.debug_info), 1)
        debug_info = orchestrator.debug_info[0]
        self.assertEqual(debug_info.phase, "test")
        self.assertEqual(debug_info.message, "Test message")
        self.assertEqual(debug_info.details["test"], True)
    
    def test_performance_report_generation(self):
        """Test performance report generation."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=False,  # Disable to avoid psutil
            enable_debugging=True
        )
        
        # Set some test metrics
        orchestrator.performance_metrics.files_processed = 5
        orchestrator.performance_metrics.directories_created = 3
        orchestrator.performance_metrics.peak_memory_mb = 100.0
        orchestrator.performance_metrics.initial_memory_mb = 80.0
        
        # Add debug info
        orchestrator._add_debug_info("test", "Test debug message")
        
        report = orchestrator._generate_performance_report()
        
        self.assertIn("Workflow Performance Report", report)
        self.assertIn("Files Processed: 5", report)
        self.assertIn("Directories Created: 3", report)
        self.assertIn("Delta: 20.0 MB", report)
        self.assertIn("Debug Information", report)
    
    def test_memory_optimization_without_psutil(self):
        """Test memory optimization when psutil is not available."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=False)
        
        # Should not raise any exceptions
        orchestrator._optimize_memory_usage()
        
        # Test with monitoring enabled but no psutil
        orchestrator.enable_monitoring = True
        orchestrator.process = None
        orchestrator._optimize_memory_usage()
    
    def test_export_performance_data(self):
        """Test performance data export functionality."""
        orchestrator = WorkflowOrchestrator(
            enable_monitoring=False,
            enable_debugging=True
        )
        
        # Set test data
        orchestrator.performance_metrics.files_processed = 5
        orchestrator._add_debug_info("test", "Export test")
        
        # Test export (should create files)
        orchestrator._export_performance_data()
        
        # Check that JSON files were created
        json_files = list(Path('.').glob('workflow_performance_*.json'))
        debug_files = list(Path('.').glob('workflow_debug_*.json'))
        
        self.assertGreater(len(json_files), 0)
        self.assertGreater(len(debug_files), 0)
        
        # Verify content
        import json
        with open(json_files[0], 'r') as f:
            data = json.load(f)
            self.assertEqual(data['performance_metrics']['files_processed'], 5)


if __name__ == '__main__':
    unittest.main()