"""
Unit tests for State Manager module.
"""

import unittest
import tempfile
import os
import yaml
from unittest.mock import patch, mock_open
from datetime import datetime, timedelta

from state_manager import StateManager, ProcessingResult, WorkflowSummary


class TestStateManager(unittest.TestCase):
    """Test cases for StateManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False)
        self.config_path = self.temp_config.name
        
        # Create sample configuration
        sample_config = {
            'old-newspaper': [
                {
                    'folder': 'kayhan-newspaper',
                    'title_fa': 'روزنامه کیهان',
                    'urls': ['http://example.com/kayhan1.pdf']
                },
                {
                    'folder': 'ettelaat-newspaper',
                    'title_fa': 'روزنامه اطلاعات',
                    'urls': ['http://example.com/ettelaat1.pdf']
                }
            ],
            'newspaper': [
                {
                    'folder': 'tehran-times',
                    'urls': ['http://example.com/tehran1.pdf']
                }
            ]
        }
        
        yaml.dump(sample_config, self.temp_config, default_flow_style=False)
        self.temp_config.close()
        
        self.state_manager = StateManager(self.config_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)
    
    def test_track_download_result_success(self):
        """Test tracking successful download result."""
        self.state_manager.track_download_result(
            archive_name='kayhan-newspaper',
            category='old-newspaper',
            success=True,
            files_downloaded=5,
            files_failed=0,
            processing_time=10.5
        )
        
        self.assertEqual(len(self.state_manager.processing_results), 1)
        result = self.state_manager.processing_results[0]
        
        self.assertEqual(result.archive_name, 'kayhan-newspaper')
        self.assertEqual(result.category, 'old-newspaper')
        self.assertTrue(result.success)
        self.assertEqual(result.files_downloaded, 5)
        self.assertEqual(result.files_failed, 0)
        self.assertEqual(result.processing_time, 10.5)
        self.assertEqual(len(result.errors), 0)
    
    def test_track_download_result_failure(self):
        """Test tracking failed download result."""
        errors = ['Network timeout', 'File not found']
        
        self.state_manager.track_download_result(
            archive_name='ettelaat-newspaper',
            category='old-newspaper',
            success=False,
            files_downloaded=2,
            files_failed=3,
            errors=errors,
            processing_time=15.2
        )
        
        self.assertEqual(len(self.state_manager.processing_results), 1)
        result = self.state_manager.processing_results[0]
        
        self.assertEqual(result.archive_name, 'ettelaat-newspaper')
        self.assertFalse(result.success)
        self.assertEqual(result.files_downloaded, 2)
        self.assertEqual(result.files_failed, 3)
        self.assertEqual(result.errors, errors)
    
    def test_remove_successful_urls_single_archive(self):
        """Test removing single successful archive from configuration."""
        successful_archives = ['kayhan-newspaper']
        
        result = self.state_manager.remove_successful_urls(successful_archives)
        self.assertTrue(result)
        
        # Verify configuration was updated
        with open(self.config_path, 'r', encoding='utf-8') as f:
            updated_config = yaml.safe_load(f)
        
        # kayhan-newspaper should be removed
        old_newspaper_folders = [arch['folder'] for arch in updated_config['old-newspaper']]
        self.assertNotIn('kayhan-newspaper', old_newspaper_folders)
        self.assertIn('ettelaat-newspaper', old_newspaper_folders)
        
        # newspaper category should remain unchanged
        self.assertEqual(len(updated_config['newspaper']), 1)
    
    def test_remove_successful_urls_multiple_archives(self):
        """Test removing multiple successful archives from configuration."""
        successful_archives = ['kayhan-newspaper', 'tehran-times']
        
        result = self.state_manager.remove_successful_urls(successful_archives)
        self.assertTrue(result)
        
        # Verify configuration was updated
        with open(self.config_path, 'r', encoding='utf-8') as f:
            updated_config = yaml.safe_load(f)
        
        # kayhan-newspaper should be removed from old-newspaper
        old_newspaper_folders = [arch['folder'] for arch in updated_config['old-newspaper']]
        self.assertNotIn('kayhan-newspaper', old_newspaper_folders)
        self.assertIn('ettelaat-newspaper', old_newspaper_folders)
        
        # tehran-times should be removed from newspaper
        self.assertEqual(len(updated_config['newspaper']), 0)
    
    def test_remove_successful_urls_no_archives(self):
        """Test removing no archives returns False."""
        result = self.state_manager.remove_successful_urls([])
        self.assertFalse(result)
        
        # Configuration should remain unchanged
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self.assertEqual(len(config['old-newspaper']), 2)
        self.assertEqual(len(config['newspaper']), 1)
    
    def test_remove_successful_urls_nonexistent_file(self):
        """Test removing URLs when config file doesn't exist."""
        os.unlink(self.config_path)
        
        result = self.state_manager.remove_successful_urls(['kayhan-newspaper'])
        self.assertFalse(result)    

    def test_generate_processing_summary(self):
        """Test generating processing summary."""
        # Add some test results
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0, processing_time=10.0
        )
        self.state_manager.track_download_result(
            'ettelaat-newspaper', 'old-newspaper', False, 2, 3, ['Error 1'], processing_time=5.0
        )
        
        summary = self.state_manager.generate_processing_summary()
        
        self.assertEqual(summary.total_archives, 2)
        self.assertEqual(summary.successful_archives, 1)
        self.assertEqual(summary.failed_archives, 1)
        self.assertEqual(summary.total_files_downloaded, 7)
        self.assertEqual(summary.total_files_failed, 3)
        self.assertGreater(summary.execution_time, 0)
        self.assertEqual(len(summary.results), 2)
    
    def test_generate_commit_message_single_success(self):
        """Test generating commit message for single successful archive."""
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0
        )
        
        message = self.state_manager.generate_commit_message()
        self.assertIn('feat: add 5 files from kayhan-newspaper', message)
    
    def test_generate_commit_message_multiple_success(self):
        """Test generating commit message for multiple successful archives."""
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0
        )
        self.state_manager.track_download_result(
            'tehran-times', 'newspaper', True, 3, 0
        )
        
        message = self.state_manager.generate_commit_message()
        self.assertIn('feat: add 8 files from 2 archives', message)
        self.assertIn('✅ kayhan-newspaper: 5 files', message)
        self.assertIn('✅ tehran-times: 3 files', message)
    
    def test_generate_commit_message_mixed_results(self):
        """Test generating commit message for mixed success/failure results."""
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0
        )
        self.state_manager.track_download_result(
            'ettelaat-newspaper', 'old-newspaper', False, 0, 2, ['Network error']
        )
        
        message = self.state_manager.generate_commit_message()
        self.assertIn('feat: add 5 files from kayhan-newspaper', message)
        self.assertIn('fix: processing failed for ettelaat-newspaper', message)
        self.assertIn('✅ kayhan-newspaper: 5 files', message)
        self.assertIn('❌ ettelaat-newspaper: 0 files', message)
    
    def test_generate_commit_message_no_results(self):
        """Test generating commit message when no results."""
        message = self.state_manager.generate_commit_message()
        self.assertEqual(message, 'chore: workflow execution with no changes')
    
    def test_generate_commit_message_only_failures(self):
        """Test generating commit message for only failed archives."""
        self.state_manager.track_download_result(
            'ettelaat-newspaper', 'old-newspaper', False, 0, 2, ['Network error']
        )
        
        message = self.state_manager.generate_commit_message()
        self.assertIn('fix: processing failed for ettelaat-newspaper', message)
    
    def test_get_successful_archives(self):
        """Test getting list of successful archives."""
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0
        )
        self.state_manager.track_download_result(
            'ettelaat-newspaper', 'old-newspaper', False, 0, 2
        )
        self.state_manager.track_download_result(
            'tehran-times', 'newspaper', True, 3, 0
        )
        
        successful = self.state_manager.get_successful_archives()
        self.assertEqual(len(successful), 2)
        self.assertIn('kayhan-newspaper', successful)
        self.assertIn('tehran-times', successful)
        self.assertNotIn('ettelaat-newspaper', successful)
    
    def test_get_failed_archives(self):
        """Test getting list of failed archives."""
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0
        )
        self.state_manager.track_download_result(
            'ettelaat-newspaper', 'old-newspaper', False, 0, 2
        )
        
        failed = self.state_manager.get_failed_archives()
        self.assertEqual(len(failed), 1)
        self.assertIn('ettelaat-newspaper', failed)
        self.assertNotIn('kayhan-newspaper', failed)
    
    def test_export_summary_to_file(self):
        """Test exporting summary to file."""
        # Add test results
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0, processing_time=10.0
        )
        self.state_manager.track_download_result(
            'ettelaat-newspaper', 'old-newspaper', False, 2, 3, 
            ['Network timeout', 'File not found'], processing_time=5.0
        )
        
        # Export to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp:
            output_path = tmp.name
        
        try:
            self.state_manager.export_summary_to_file(output_path)
            
            # Verify file was created and contains expected content
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.assertIn('# Workflow Execution Summary', content)
            self.assertIn('Total Archives:** 2', content)
            self.assertIn('Successful:** 1', content)
            self.assertIn('Failed:** 1', content)
            self.assertIn('kayhan-newspaper (old-newspaper) - ✅ SUCCESS', content)
            self.assertIn('ettelaat-newspaper (old-newspaper) - ❌ FAILED', content)
            self.assertIn('Network timeout', content)
            self.assertIn('File not found', content)
            
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def test_reset_state(self):
        """Test resetting state manager."""
        # Add some results
        self.state_manager.track_download_result(
            'kayhan-newspaper', 'old-newspaper', True, 5, 0
        )
        
        self.assertEqual(len(self.state_manager.processing_results), 1)
        
        # Reset state
        self.state_manager.reset_state()
        
        self.assertEqual(len(self.state_manager.processing_results), 0)
        # workflow_start_time should be updated (approximately now)
        time_diff = datetime.now() - self.state_manager.workflow_start_time
        self.assertLess(time_diff.total_seconds(), 1.0)


class TestProcessingResult(unittest.TestCase):
    """Test cases for ProcessingResult dataclass."""
    
    def test_processing_result_creation(self):
        """Test creating ProcessingResult with all fields."""
        errors = ['Error 1', 'Error 2']
        result = ProcessingResult(
            archive_name='test-archive',
            category='old-newspaper',
            success=True,
            files_downloaded=5,
            files_failed=2,
            errors=errors,
            processing_time=10.5
        )
        
        self.assertEqual(result.archive_name, 'test-archive')
        self.assertEqual(result.category, 'old-newspaper')
        self.assertTrue(result.success)
        self.assertEqual(result.files_downloaded, 5)
        self.assertEqual(result.files_failed, 2)
        self.assertEqual(result.errors, errors)
        self.assertEqual(result.processing_time, 10.5)
    
    def test_processing_result_defaults(self):
        """Test ProcessingResult with default values."""
        result = ProcessingResult(
            archive_name='test-archive',
            category='newspaper',
            success=False
        )
        
        self.assertEqual(result.files_downloaded, 0)
        self.assertEqual(result.files_failed, 0)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.processing_time, 0.0)


class TestWorkflowSummary(unittest.TestCase):
    """Test cases for WorkflowSummary dataclass."""
    
    def test_workflow_summary_creation(self):
        """Test creating WorkflowSummary with all fields."""
        results = [
            ProcessingResult('archive1', 'old-newspaper', True),
            ProcessingResult('archive2', 'newspaper', False)
        ]
        
        summary = WorkflowSummary(
            total_archives=2,
            successful_archives=1,
            failed_archives=1,
            total_files_downloaded=10,
            total_files_failed=2,
            execution_time=30.5,
            results=results
        )
        
        self.assertEqual(summary.total_archives, 2)
        self.assertEqual(summary.successful_archives, 1)
        self.assertEqual(summary.failed_archives, 1)
        self.assertEqual(summary.total_files_downloaded, 10)
        self.assertEqual(summary.total_files_failed, 2)
        self.assertEqual(summary.execution_time, 30.5)
        self.assertEqual(len(summary.results), 2)
        self.assertIsInstance(summary.timestamp, str)
    
    def test_workflow_summary_defaults(self):
        """Test WorkflowSummary with default values."""
        summary = WorkflowSummary()
        
        self.assertEqual(summary.total_archives, 0)
        self.assertEqual(summary.successful_archives, 0)
        self.assertEqual(summary.failed_archives, 0)
        self.assertEqual(summary.total_files_downloaded, 0)
        self.assertEqual(summary.total_files_failed, 0)
        self.assertEqual(summary.execution_time, 0.0)
        self.assertEqual(len(summary.results), 0)
        self.assertIsInstance(summary.timestamp, str)


if __name__ == '__main__':
    unittest.main()