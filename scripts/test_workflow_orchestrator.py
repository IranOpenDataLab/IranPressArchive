"""
Unit tests for Workflow Orchestrator module.
"""

import unittest
import tempfile
import os
import shutil
import argparse
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_orchestrator import WorkflowOrchestrator, create_argument_parser, main


class TestWorkflowOrchestrator(unittest.TestCase):
    """Test cases for WorkflowOrchestrator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration file
        self.config_path = 'test_urls.yml'
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write("""
archives:
  - title_fa: روزنامه کیهان
    folder: kayhan-newspaper
    category: old-newspaper
    description: Historical Iranian newspaper
    years:
      2020: ['file1.pdf']
    urls: ['http://example.com/kayhan1.pdf']
  - title_fa: تهران تایمز
    folder: tehran-times
    category: newspaper
    description: English language newspaper
    years:
      2023: ['file1.pdf']
    urls: ['http://example.com/tehran1.pdf']
""")
        
        self.orchestrator = WorkflowOrchestrator(
            config_path=self.config_path,
            log_file='test_workflow.log'
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('workflow_orchestrator.ConfigParser')
    @patch('workflow_orchestrator.FileManager')
    @patch('workflow_orchestrator.ErrorHandler')
    @patch('workflow_orchestrator.StateManager')
    @patch('workflow_orchestrator.ReadmeGenerator')
    @patch('workflow_orchestrator.WorkflowExecutor')
    def test_orchestrator_initialization(self, mock_executor, mock_readme, mock_state,
                                       mock_error, mock_file, mock_config):
        """Test orchestrator initialization."""
        orchestrator = WorkflowOrchestrator('test.yml', 'test.log')
        
        # Verify all components were initialized
        mock_config.assert_called_once()
        mock_file.assert_called_once()
        mock_error.assert_called_once_with('test.log')
        mock_state.assert_called_once_with('test.yml')
        mock_readme.assert_called_once()
        mock_executor.assert_called_once()
        
        # Verify monitoring is enabled by default
        self.assertTrue(orchestrator.enable_monitoring)
        self.assertFalse(orchestrator.enable_debugging)
    
    def test_orchestrator_initialization_with_monitoring_options(self):
        """Test orchestrator initialization with monitoring options."""
        orchestrator = WorkflowOrchestrator(
            'test.yml', 'test.log',
            enable_monitoring=False,
            enable_debugging=True
        )
        
        self.assertFalse(orchestrator.enable_monitoring)
        self.assertTrue(orchestrator.enable_debugging)
        self.assertIsNone(orchestrator.process)
    
    def test_load_configuration_success(self):
        """Test successful configuration loading."""
        # Mock the config parser
        from config_parser import Archive
        mock_archive = Archive(
            title_fa='تست',
            folder='test',
            category='old-newspaper',
            description='Test archive',
            years={'2023': ['file1.pdf']}
        )
        # Add urls attribute for workflow compatibility
        mock_archive.urls = ['http://example.com']
        self.orchestrator.config_parser.parse_configuration = Mock(return_value=[mock_archive])
        
        result = self.orchestrator._load_configuration()
        
        self.assertTrue(result)
        self.assertIsNotNone(self.orchestrator.archives)
    
    def test_load_configuration_file_not_found(self):
        """Test configuration loading when file doesn't exist."""
        orchestrator = WorkflowOrchestrator('nonexistent.yml')
        
        result = orchestrator._load_configuration()
        
        self.assertFalse(result)
    
    def test_load_configuration_empty_config(self):
        """Test configuration loading with empty configuration."""
        self.orchestrator.config_parser.parse_config = Mock(return_value={})
        
        result = self.orchestrator._load_configuration()
        
        self.assertFalse(result)
    
    def test_filter_archives_for_processing_manual(self):
        """Test archive filtering for manual execution."""
        self.orchestrator.archives = {
            'old-newspaper': [{'folder': 'old1'}],
            'newspaper': [{'folder': 'new1'}]
        }
        self.orchestrator.workflow_executor.get_archives_for_processing = Mock(
            return_value=self.orchestrator.archives
        )
        
        result = self.orchestrator._filter_archives_for_processing()
        
        self.orchestrator.workflow_executor.get_archives_for_processing.assert_called_once_with(
            self.orchestrator.archives, False
        )
        self.assertEqual(result, self.orchestrator.archives)
    
    def test_process_archives_live_mode(self):
        """Test archive processing in live mode."""
        archives = {'newspaper': [{'folder': 'test', 'urls': ['http://example.com']}]}
        self.orchestrator.workflow_executor.process_archives_by_category = Mock()
        
        self.orchestrator._process_archives(archives)
        
        self.orchestrator.workflow_executor.process_archives_by_category.assert_called_once_with(
            archives, False
        )
    
    def test_process_archives_dry_run(self):
        """Test archive processing in dry run mode."""
        archives = {'newspaper': [{'folder': 'test', 'urls': ['http://example.com']}]}
        self.orchestrator.dry_run = True
        self.orchestrator.state_manager.track_download_result = Mock()
        
        self.orchestrator._process_archives(archives)
        
        # Should track simulated results
        self.orchestrator.state_manager.track_download_result.assert_called_once()
        
        # Should not call actual processing
        self.orchestrator.workflow_executor.process_archives_by_category = Mock()
        self.orchestrator.workflow_executor.process_archives_by_category.assert_not_called()
    
    def test_update_configuration(self):
        """Test configuration update after successful processing."""
        self.orchestrator.state_manager.get_successful_archives = Mock(
            return_value=['archive1', 'archive2']
        )
        self.orchestrator.state_manager.remove_successful_urls = Mock(return_value=True)
        
        self.orchestrator._update_configuration()
        
        self.orchestrator.state_manager.remove_successful_urls.assert_called_once_with(
            ['archive1', 'archive2']
        )
    
    def test_update_readme_files(self):
        """Test README files update."""
        self.orchestrator.archives = {
            'old-newspaper': [{'folder': 'test1'}],
            'newspaper': [{'folder': 'test2'}]
        }
        self.orchestrator.readme_generator.generate_main_readme = Mock()
        
        self.orchestrator._update_readme_files()
        
        # Should generate both Persian and English READMEs
        calls = self.orchestrator.readme_generator.generate_main_readme.call_args_list
        self.assertEqual(len(calls), 2)
        
        # Check Persian README call
        self.assertEqual(calls[0][0][0], 'fa')
        self.assertEqual(calls[0][0][2], 'README.md')
        
        # Check English README call
        self.assertEqual(calls[1][0][0], 'en')
        self.assertEqual(calls[1][0][2], 'README.en.md')
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_commit_changes_success(self, mock_exists, mock_subprocess):
        """Test successful git commit."""
        mock_exists.return_value = True  # .git directory exists
        self.orchestrator.state_manager.generate_commit_message = Mock(
            return_value="feat: add new files"
        )
        
        # Mock git commands
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # git add
            Mock(returncode=1),  # git diff --cached --quiet (changes exist)
            Mock(returncode=0)   # git commit
        ]
        
        self.orchestrator._commit_changes()
        
        # Verify git commands were called
        expected_calls = [
            call(['git', 'add', '.'], check=True, capture_output=True),
            call(['git', 'diff', '--cached', '--quiet'], capture_output=True),
            call(['git', 'commit', '-m', 'feat: add new files'], check=True, capture_output=True)
        ]
        mock_subprocess.assert_has_calls(expected_calls)
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_commit_changes_no_git_repo(self, mock_exists, mock_subprocess):
        """Test commit when not in git repository."""
        mock_exists.return_value = False  # No .git directory
        
        self.orchestrator._commit_changes()
        
        # Should not call any git commands
        mock_subprocess.assert_not_called()
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_commit_changes_no_changes(self, mock_exists, mock_subprocess):
        """Test commit when no changes to commit."""
        mock_exists.return_value = True
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # git add
            Mock(returncode=0)   # git diff --cached --quiet (no changes)
        ]
        
        self.orchestrator._commit_changes()
        
        # Should not call git commit
        self.assertEqual(mock_subprocess.call_count, 2)
    
    def test_cleanup(self):
        """Test cleanup operations."""
        self.orchestrator.state_manager.export_summary_to_file = Mock()
        
        self.orchestrator._cleanup()
        
        # Should export summary
        self.orchestrator.state_manager.export_summary_to_file.assert_called_once()
        
        # Check that filename contains timestamp
        call_args = self.orchestrator.state_manager.export_summary_to_file.call_args[0][0]
        self.assertIn('workflow_summary_', call_args)
        self.assertIn('.md', call_args)
    
    @patch.object(WorkflowOrchestrator, '_load_configuration')
    @patch.object(WorkflowOrchestrator, '_filter_archives_for_processing')
    @patch.object(WorkflowOrchestrator, '_process_archives')
    @patch.object(WorkflowOrchestrator, '_update_configuration')
    @patch.object(WorkflowOrchestrator, '_update_readme_files')
    @patch.object(WorkflowOrchestrator, '_commit_changes')
    @patch.object(WorkflowOrchestrator, '_cleanup')
    def test_execute_workflow_success(self, mock_cleanup, mock_commit, mock_readme,
                                    mock_update_config, mock_process, mock_filter,
                                    mock_load):
        """Test successful workflow execution."""
        # Mock successful operations
        mock_load.return_value = True
        mock_filter.return_value = {'newspaper': [{'folder': 'test'}]}
        
        # Mock state manager with proper attributes
        mock_summary = Mock()
        mock_summary.total_archives = 1
        mock_summary.successful_archives = 1
        mock_summary.failed_archives = 0
        mock_summary.total_files_downloaded = 5
        mock_summary.total_files_failed = 0
        mock_summary.execution_time = 10.5
        self.orchestrator.state_manager.generate_processing_summary = Mock(return_value=mock_summary)
        
        result = self.orchestrator.execute_workflow(
            is_scheduled_run=True, dry_run=False, verbose=True
        )
        
        self.assertTrue(result)
        
        # Verify all steps were called
        mock_load.assert_called_once()
        mock_filter.assert_called_once()
        mock_process.assert_called_once()
        mock_update_config.assert_called_once()
        mock_readme.assert_called_once()
        mock_commit.assert_called_once()
        mock_cleanup.assert_called_once()
        
        # Verify workflow state was set
        self.assertTrue(self.orchestrator.is_scheduled_run)
        self.assertFalse(self.orchestrator.dry_run)
        self.assertTrue(self.orchestrator.verbose)
    
    @patch.object(WorkflowOrchestrator, '_load_configuration')
    def test_execute_workflow_config_failure(self, mock_load):
        """Test workflow execution when configuration loading fails."""
        mock_load.return_value = False
        
        result = self.orchestrator.execute_workflow()
        
        self.assertFalse(result)
        mock_load.assert_called_once()
    
    @patch.object(WorkflowOrchestrator, '_load_configuration')
    @patch.object(WorkflowOrchestrator, '_filter_archives_for_processing')
    def test_execute_workflow_no_archives(self, mock_filter, mock_load):
        """Test workflow execution when no archives to process."""
        mock_load.return_value = True
        mock_filter.return_value = {}
        
        result = self.orchestrator.execute_workflow()
        
        self.assertTrue(result)  # Should succeed with no work to do
    
    @patch.object(WorkflowOrchestrator, '_load_configuration')
    def test_execute_workflow_exception(self, mock_load):
        """Test workflow execution when exception occurs."""
        mock_load.side_effect = Exception("Test error")
        
        result = self.orchestrator.execute_workflow()
        
        self.assertFalse(result)
    
    def test_log_verbose_filtering(self):
        """Test that verbose messages are filtered correctly."""
        self.orchestrator.verbose = False
        
        with patch('builtins.print') as mock_print:
            self.orchestrator._log("Normal message")
            self.orchestrator._log("Verbose message", verbose=True)
        
        # Should only print normal message
        mock_print.assert_called_once()
        self.assertIn("Normal message", mock_print.call_args[0][0])
    
    def test_performance_monitoring_start_stop(self):
        """Test performance monitoring start and stop."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True)
        
        # Test starting monitoring
        orchestrator._start_monitoring()
        self.assertTrue(orchestrator.monitoring_active)
        self.assertIsNotNone(orchestrator.monitoring_thread)
        
        # Test stopping monitoring
        orchestrator._stop_monitoring()
        self.assertFalse(orchestrator.monitoring_active)
        self.assertIsNotNone(orchestrator.performance_metrics.end_time)
    
    def test_debug_info_collection(self):
        """Test debug information collection."""
        orchestrator = WorkflowOrchestrator(enable_debugging=True, enable_monitoring=True)
        
        # Add debug info
        orchestrator._add_debug_info("test_phase", "Test message", {"key": "value"})
        
        self.assertEqual(len(orchestrator.debug_info), 1)
        debug_info = orchestrator.debug_info[0]
        self.assertEqual(debug_info.phase, "test_phase")
        self.assertEqual(debug_info.message, "Test message")
        self.assertEqual(debug_info.details["key"], "value")
    
    def test_debug_info_disabled(self):
        """Test that debug info is not collected when disabled."""
        orchestrator = WorkflowOrchestrator(enable_debugging=False)
        
        orchestrator._add_debug_info("test_phase", "Test message")
        
        self.assertEqual(len(orchestrator.debug_info), 0)
    
    def test_memory_optimization(self):
        """Test memory optimization functionality."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True)
        
        # Should not raise any exceptions
        orchestrator._optimize_memory_usage()
        
        # Test with monitoring disabled
        orchestrator.enable_monitoring = False
        orchestrator._optimize_memory_usage()  # Should do nothing
    
    def test_performance_report_generation(self):
        """Test performance report generation."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True, enable_debugging=True)
        
        # Set some test metrics
        orchestrator.performance_metrics.files_processed = 10
        orchestrator.performance_metrics.directories_created = 5
        orchestrator.performance_metrics.peak_memory_mb = 100.0
        orchestrator.performance_metrics.initial_memory_mb = 80.0
        
        # Add debug info
        orchestrator._add_debug_info("test", "Test debug message")
        
        report = orchestrator._generate_performance_report()
        
        self.assertIn("Workflow Performance Report", report)
        self.assertIn("Files Processed: 10", report)
        self.assertIn("Directories Created: 5", report)
        self.assertIn("Delta: 20.0 MB", report)
        self.assertIn("Debug Information", report)
    
    @patch('builtins.open', create=True)
    @patch('json.dump')
    def test_performance_data_export(self, mock_json_dump, mock_open):
        """Test performance data export."""
        orchestrator = WorkflowOrchestrator(enable_monitoring=True, enable_debugging=True)
        
        # Set test data
        orchestrator.performance_metrics.files_processed = 5
        orchestrator._add_debug_info("test", "Export test")
        
        orchestrator._export_performance_data()
        
        # Should have called open for both metrics and debug files
        self.assertEqual(mock_open.call_count, 2)
        self.assertEqual(mock_json_dump.call_count, 2)


class TestArgumentParser(unittest.TestCase):
    """Test cases for command line argument parsing."""
    
    def test_create_argument_parser(self):
        """Test argument parser creation."""
        parser = create_argument_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)
    
    def test_parse_default_arguments(self):
        """Test parsing with default arguments."""
        parser = create_argument_parser()
        args = parser.parse_args([])
        
        self.assertFalse(args.scheduled)
        self.assertFalse(args.dry_run)
        self.assertFalse(args.verbose)
        self.assertEqual(args.config, 'urls.yml')
        self.assertEqual(args.log_file, 'workflow.log')
    
    def test_parse_all_arguments(self):
        """Test parsing with all arguments."""
        parser = create_argument_parser()
        args = parser.parse_args([
            '--scheduled',
            '--dry-run',
            '--verbose',
            '--config', 'custom.yml',
            '--log-file', 'custom.log'
        ])
        
        self.assertTrue(args.scheduled)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.verbose)
        self.assertEqual(args.config, 'custom.yml')
        self.assertEqual(args.log_file, 'custom.log')
    
    def test_parse_short_arguments(self):
        """Test parsing with short argument forms."""
        parser = create_argument_parser()
        args = parser.parse_args(['-v', '-c', 'test.yml', '-l', 'test.log'])
        
        self.assertTrue(args.verbose)
        self.assertEqual(args.config, 'test.yml')
        self.assertEqual(args.log_file, 'test.log')


class TestMainFunction(unittest.TestCase):
    """Test cases for main function."""
    
    @patch('workflow_orchestrator.WorkflowOrchestrator')
    @patch('sys.argv', ['workflow_orchestrator.py'])
    def test_main_success(self, mock_orchestrator_class):
        """Test successful main execution."""
        mock_orchestrator = Mock()
        mock_orchestrator.execute_workflow.return_value = True
        mock_orchestrator_class.return_value = mock_orchestrator
        
        result = main()
        
        self.assertEqual(result, 0)
        mock_orchestrator.execute_workflow.assert_called_once_with(
            is_scheduled_run=False,
            dry_run=False,
            verbose=False
        )
    
    @patch('workflow_orchestrator.WorkflowOrchestrator')
    @patch('sys.argv', ['workflow_orchestrator.py', '--scheduled', '--dry-run', '--verbose'])
    def test_main_with_arguments(self, mock_orchestrator_class):
        """Test main execution with arguments."""
        mock_orchestrator = Mock()
        mock_orchestrator.execute_workflow.return_value = True
        mock_orchestrator_class.return_value = mock_orchestrator
        
        result = main()
        
        self.assertEqual(result, 0)
        mock_orchestrator.execute_workflow.assert_called_once_with(
            is_scheduled_run=True,
            dry_run=True,
            verbose=True
        )
    
    @patch('workflow_orchestrator.WorkflowOrchestrator')
    @patch('sys.argv', ['workflow_orchestrator.py'])
    def test_main_workflow_failure(self, mock_orchestrator_class):
        """Test main execution when workflow fails."""
        mock_orchestrator = Mock()
        mock_orchestrator.execute_workflow.return_value = False
        mock_orchestrator_class.return_value = mock_orchestrator
        
        result = main()
        
        self.assertEqual(result, 1)
    
    @patch('workflow_orchestrator.WorkflowOrchestrator')
    @patch('sys.argv', ['workflow_orchestrator.py'])
    def test_main_keyboard_interrupt(self, mock_orchestrator_class):
        """Test main execution with keyboard interrupt."""
        mock_orchestrator_class.side_effect = KeyboardInterrupt()
        
        with patch('builtins.print') as mock_print:
            result = main()
        
        self.assertEqual(result, 130)
        mock_print.assert_called_with("\nWorkflow interrupted by user")
    
    @patch('workflow_orchestrator.WorkflowOrchestrator')
    @patch('sys.argv', ['workflow_orchestrator.py'])
    def test_main_exception(self, mock_orchestrator_class):
        """Test main execution with exception."""
        mock_orchestrator_class.side_effect = Exception("Test error")
        
        with patch('builtins.print') as mock_print:
            result = main()
        
        self.assertEqual(result, 1)
        mock_print.assert_called_with("Fatal error: Test error")


class TestIntegrationScenarios(unittest.TestCase):
    """Integration test scenarios for workflow orchestrator."""
    
    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test configuration
        with open('urls.yml', 'w', encoding='utf-8') as f:
            f.write("""
archives:
  - title_fa: روزنامه کیهان
    folder: kayhan-newspaper
    category: old-newspaper
    description: Historical Iranian newspaper
    years:
      2020: ['file1.pdf', 'file2.pdf']
    urls: ['http://example.com/kayhan1.pdf', 'http://example.com/kayhan2.pdf']
  - title_fa: تهران تایمز
    folder: tehran-times
    category: newspaper
    description: English language newspaper
    years:
      2023: ['file1.pdf']
    urls: ['http://example.com/tehran1.pdf']
""")
    
    def tearDown(self):
        """Clean up integration test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    @patch('workflow_orchestrator.FileManager')
    @patch('workflow_orchestrator.subprocess.run')
    @patch('os.path.exists')
    def test_complete_workflow_manual_run(self, mock_exists, mock_subprocess, mock_file_manager):
        """Test complete workflow execution in manual mode."""
        # Mock file manager for successful downloads
        mock_file_manager_instance = Mock()
        mock_file_manager_instance.download_file.return_value = True
        mock_file_manager.return_value = mock_file_manager_instance
        
        # Mock git operations
        mock_exists.return_value = True
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # git add
            Mock(returncode=1),  # git diff (changes exist)
            Mock(returncode=0)   # git commit
        ]
        
        orchestrator = WorkflowOrchestrator()
        
        result = orchestrator.execute_workflow(
            is_scheduled_run=False,
            dry_run=False,
            verbose=True
        )
        
        self.assertTrue(result)
        
        # Verify directories were created
        self.assertTrue(os.path.exists('old-newspaper'))
        self.assertTrue(os.path.exists('newspaper'))
    
    @patch('workflow_orchestrator.FileManager')
    def test_complete_workflow_scheduled_run(self, mock_file_manager):
        """Test complete workflow execution in scheduled mode."""
        # Mock file manager
        mock_file_manager_instance = Mock()
        mock_file_manager_instance.download_file.return_value = True
        mock_file_manager.return_value = mock_file_manager_instance
        
        orchestrator = WorkflowOrchestrator()
        
        result = orchestrator.execute_workflow(
            is_scheduled_run=True,
            dry_run=False,
            verbose=True
        )
        
        self.assertTrue(result)
        
        # In scheduled mode, only newspaper category should be processed
        # old-newspaper directory should not be created
        self.assertTrue(os.path.exists('newspaper'))
    
    def test_complete_workflow_dry_run(self):
        """Test complete workflow execution in dry run mode."""
        orchestrator = WorkflowOrchestrator()
        
        result = orchestrator.execute_workflow(
            is_scheduled_run=False,
            dry_run=True,
            verbose=True
        )
        
        self.assertTrue(result)
        
        # In dry run, no actual directories should be created
        # (except by the orchestrator setup itself)
        # But the workflow should complete successfully


if __name__ == '__main__':
    unittest.main()