"""
Unit tests for Category Processor module.
"""

import unittest
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from category_processor import (
    OldNewspaperProcessor, NewspaperProcessor, CategoryProcessorFactory,
    WorkflowExecutor
)
from file_manager import FileManager
from error_handler import ErrorHandler
from state_manager import StateManager
from readme_generator import ReadmeGenerator


class TestOldNewspaperProcessor(unittest.TestCase):
    """Test cases for OldNewspaperProcessor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create mock dependencies
        self.file_manager = Mock(spec=FileManager)
        self.error_handler = Mock(spec=ErrorHandler)
        self.state_manager = Mock(spec=StateManager)
        self.readme_generator = Mock(spec=ReadmeGenerator)
        
        self.processor = OldNewspaperProcessor(
            self.file_manager, self.error_handler, 
            self.state_manager, self.readme_generator
        )
        
        self.sample_archive = {
            'folder': 'kayhan-newspaper',
            'title_fa': 'روزنامه کیهان',
            'urls': [
                'http://example.com/file1.pdf',
                'http://example.com/file2.pdf'
            ]
        }
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_create_directory_structure(self):
        """Test directory structure creation for old newspaper."""
        base_dir = self.processor.create_directory_structure(self.sample_archive)
        
        expected_dir = os.path.join('old-newspaper', 'kayhan-newspaper')
        self.assertEqual(base_dir, expected_dir)
        self.assertTrue(os.path.exists(expected_dir))
    
    def test_should_process_in_scheduled_run(self):
        """Test that old newspapers are not processed in scheduled runs."""
        result = self.processor.should_process_in_scheduled_run(self.sample_archive)
        self.assertFalse(result)
    
    def test_process_archive_success(self):
        """Test successful processing of old newspaper archive."""
        # Mock successful downloads
        self.file_manager.download_file.return_value = True
        
        success, files_downloaded, files_failed, errors = self.processor.process_archive(self.sample_archive)
        
        self.assertTrue(success)
        self.assertEqual(files_downloaded, 2)
        self.assertEqual(files_failed, 0)
        self.assertEqual(len(errors), 0)
        
        # Verify download calls
        self.assertEqual(self.file_manager.download_file.call_count, 2)
        
        # Verify README generation was called
        self.readme_generator.update_publication_readme.assert_called_once()
    
    def test_process_archive_partial_failure(self):
        """Test processing with some failed downloads."""
        # Mock mixed success/failure
        self.file_manager.download_file.side_effect = [True, False]
        
        success, files_downloaded, files_failed, errors = self.processor.process_archive(self.sample_archive)
        
        self.assertFalse(success)  # Not fully successful
        self.assertEqual(files_downloaded, 1)
        self.assertEqual(files_failed, 1)
        self.assertEqual(len(errors), 1)
        
        # Verify error logging
        self.error_handler.log_error.assert_called()
    
    def test_process_archive_no_urls(self):
        """Test processing archive with no URLs."""
        archive_no_urls = {'folder': 'test-archive', 'urls': []}
        
        success, files_downloaded, files_failed, errors = self.processor.process_archive(archive_no_urls)
        
        self.assertFalse(success)
        self.assertEqual(files_downloaded, 0)
        self.assertEqual(files_failed, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn('No URLs found', errors[0])
    
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_process_archive_skip_existing_files(self, mock_makedirs, mock_exists):
        """Test that existing files are skipped."""
        # Mock that files already exist
        mock_exists.return_value = True
        
        success, files_downloaded, files_failed, errors = self.processor.process_archive(self.sample_archive)
        
        # No downloads should occur
        self.file_manager.download_file.assert_not_called()
        self.assertEqual(files_downloaded, 0)
        self.assertEqual(files_failed, 0)


class TestNewspaperProcessor(unittest.TestCase):
    """Test cases for NewspaperProcessor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create mock dependencies
        self.file_manager = Mock(spec=FileManager)
        self.error_handler = Mock(spec=ErrorHandler)
        self.state_manager = Mock(spec=StateManager)
        self.readme_generator = Mock(spec=ReadmeGenerator)
        
        self.processor = NewspaperProcessor(
            self.file_manager, self.error_handler, 
            self.state_manager, self.readme_generator
        )
        
        self.sample_archive = {
            'folder': 'tehran-times',
            'urls': [
                'http://example.com/today1.pdf',
                'http://example.com/today2.pdf'
            ]
        }
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)
    
    def test_create_directory_structure(self):
        """Test directory structure creation for newspaper."""
        base_dir = self.processor.create_directory_structure(self.sample_archive)
        
        expected_dir = os.path.join('newspaper', 'tehran-times')
        self.assertEqual(base_dir, expected_dir)
        self.assertTrue(os.path.exists(expected_dir))
    
    def test_should_process_in_scheduled_run(self):
        """Test that newspapers are processed in scheduled runs."""
        result = self.processor.should_process_in_scheduled_run(self.sample_archive)
        self.assertTrue(result)
    
    @patch('category_processor.datetime')
    def test_process_archive_creates_year_directory(self, mock_datetime):
        """Test that year-specific directory is created."""
        # Mock current year
        mock_datetime.now.return_value.year = 2023
        mock_datetime.now.return_value.strftime.return_value = '20231201'
        
        self.file_manager.download_file.return_value = True
        
        success, files_downloaded, files_failed, errors = self.processor.process_archive(self.sample_archive)
        
        # Check that year directory was created
        year_dir = os.path.join('newspaper', 'tehran-times', '2023')
        self.assertTrue(os.path.exists(year_dir))
    
    @patch('category_processor.datetime')
    def test_process_archive_filename_format(self, mock_datetime):
        """Test that filenames include date and sequential numbering."""
        mock_datetime.now.return_value.year = 2023
        mock_datetime.now.return_value.strftime.return_value = '20231201'
        
        self.file_manager.download_file.return_value = True
        
        self.processor.process_archive(self.sample_archive)
        
        # Check download calls for correct filenames
        calls = self.file_manager.download_file.call_args_list
        self.assertEqual(len(calls), 2)
        
        # First file should be tehran-times_20231201_001.pdf
        first_call_path = calls[0][0][1]  # Second argument (file_path)
        self.assertIn('tehran-times_20231201_001.pdf', first_call_path)
        
        # Second file should be tehran-times_20231201_002.pdf
        second_call_path = calls[1][0][1]
        self.assertIn('tehran-times_20231201_002.pdf', second_call_path)
    
    def test_update_archive_years(self):
        """Test updating archive with year information."""
        archive = {'folder': 'test-paper'}
        
        self.processor._update_archive_years(archive, 2023, 2)
        
        self.assertIn('years', archive)
        self.assertIn('2023', archive['years'])
        self.assertEqual(len(archive['years']['2023']), 2)


class TestCategoryProcessorFactory(unittest.TestCase):
    """Test cases for CategoryProcessorFactory class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = Mock(spec=FileManager)
        self.error_handler = Mock(spec=ErrorHandler)
        self.state_manager = Mock(spec=StateManager)
        self.readme_generator = Mock(spec=ReadmeGenerator)
    
    def test_create_old_newspaper_processor(self):
        """Test creating old newspaper processor."""
        processor = CategoryProcessorFactory.create_processor(
            'old-newspaper', self.file_manager, self.error_handler,
            self.state_manager, self.readme_generator
        )
        
        self.assertIsInstance(processor, OldNewspaperProcessor)
    
    def test_create_newspaper_processor(self):
        """Test creating newspaper processor."""
        processor = CategoryProcessorFactory.create_processor(
            'newspaper', self.file_manager, self.error_handler,
            self.state_manager, self.readme_generator
        )
        
        self.assertIsInstance(processor, NewspaperProcessor)
    
    def test_create_processor_invalid_category(self):
        """Test creating processor with invalid category."""
        with self.assertRaises(ValueError) as context:
            CategoryProcessorFactory.create_processor(
                'invalid-category', self.file_manager, self.error_handler,
                self.state_manager, self.readme_generator
            )
        
        self.assertIn('Unsupported category: invalid-category', str(context.exception))


class TestWorkflowExecutor(unittest.TestCase):
    """Test cases for WorkflowExecutor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = Mock(spec=FileManager)
        self.error_handler = Mock(spec=ErrorHandler)
        self.state_manager = Mock(spec=StateManager)
        self.readme_generator = Mock(spec=ReadmeGenerator)
        
        self.executor = WorkflowExecutor(
            self.file_manager, self.error_handler,
            self.state_manager, self.readme_generator
        )
        
        self.sample_archives = {
            'old-newspaper': [
                {
                    'folder': 'kayhan-newspaper',
                    'urls': ['http://example.com/kayhan1.pdf']
                }
            ],
            'newspaper': [
                {
                    'folder': 'tehran-times',
                    'urls': ['http://example.com/tehran1.pdf']
                }
            ]
        }
    
    @patch('category_processor.CategoryProcessorFactory.create_processor')
    def test_process_archives_by_category_manual_run(self, mock_create_processor):
        """Test processing archives in manual run (all categories)."""
        # Mock processor
        mock_processor = Mock()
        mock_processor.process_archive.return_value = (True, 1, 0, [])
        mock_processor.should_process_in_scheduled_run.return_value = True
        mock_create_processor.return_value = mock_processor
        
        self.executor.process_archives_by_category(self.sample_archives, is_scheduled_run=False)
        
        # Should create processors for both categories
        self.assertEqual(mock_create_processor.call_count, 2)
        
        # Should process both archives
        self.assertEqual(mock_processor.process_archive.call_count, 2)
        
        # Should track results for both archives
        self.assertEqual(self.state_manager.track_download_result.call_count, 2)
    
    @patch('category_processor.CategoryProcessorFactory.create_processor')
    def test_process_archives_by_category_scheduled_run(self, mock_create_processor):
        """Test processing archives in scheduled run (only active publications)."""
        # Mock processors
        old_processor = Mock()
        old_processor.should_process_in_scheduled_run.return_value = False
        
        new_processor = Mock()
        new_processor.should_process_in_scheduled_run.return_value = True
        new_processor.process_archive.return_value = (True, 1, 0, [])
        
        mock_create_processor.side_effect = [old_processor, new_processor]
        
        self.executor.process_archives_by_category(self.sample_archives, is_scheduled_run=True)
        
        # Should create processors for both categories
        self.assertEqual(mock_create_processor.call_count, 2)
        
        # Should only process newspaper archive (not old-newspaper)
        old_processor.process_archive.assert_not_called()
        new_processor.process_archive.assert_called_once()
        
        # Should track result for only one archive
        self.state_manager.track_download_result.assert_called_once()
    
    @patch('category_processor.CategoryProcessorFactory.create_processor')
    def test_process_archives_handles_processor_exception(self, mock_create_processor):
        """Test handling of processor exceptions."""
        # Mock processor that raises exception
        mock_processor = Mock()
        mock_processor.process_archive.side_effect = Exception("Test error")
        mock_processor.should_process_in_scheduled_run.return_value = True
        mock_create_processor.return_value = mock_processor
        
        self.executor.process_archives_by_category(self.sample_archives, is_scheduled_run=False)
        
        # Should log error and track failed result
        self.error_handler.log_error.assert_called()
        
        # Should track failure for both archives
        self.assertEqual(self.state_manager.track_download_result.call_count, 2)
        
        # Check that failures were tracked correctly
        calls = self.state_manager.track_download_result.call_args_list
        for call in calls:
            args, kwargs = call
            self.assertFalse(kwargs['success'])
            self.assertEqual(kwargs['files_downloaded'], 0)
            self.assertEqual(kwargs['files_failed'], 1)
    
    @patch('category_processor.CategoryProcessorFactory.create_processor')
    def test_process_archives_handles_invalid_category(self, mock_create_processor):
        """Test handling of invalid category."""
        mock_create_processor.side_effect = ValueError("Unsupported category")
        
        invalid_archives = {
            'invalid-category': [
                {'folder': 'test', 'urls': ['http://example.com/test.pdf']}
            ]
        }
        
        # Should not raise exception
        self.executor.process_archives_by_category(invalid_archives, is_scheduled_run=False)
        
        # Should log error
        self.error_handler.log_error.assert_called()
    
    def test_should_run_scheduled_processing(self):
        """Test scheduled processing decision logic."""
        # Currently always returns True (can be customized)
        result = self.executor.should_run_scheduled_processing()
        self.assertTrue(result)
    
    def test_get_archives_for_processing_manual_run(self):
        """Test getting archives for manual run (all archives)."""
        result = self.executor.get_archives_for_processing(
            self.sample_archives, is_scheduled_run=False
        )
        
        self.assertEqual(result, self.sample_archives)
        self.assertIn('old-newspaper', result)
        self.assertIn('newspaper', result)
    
    def test_get_archives_for_processing_scheduled_run(self):
        """Test getting archives for scheduled run (only newspapers)."""
        result = self.executor.get_archives_for_processing(
            self.sample_archives, is_scheduled_run=True
        )
        
        # Should only include newspaper category
        self.assertIn('newspaper', result)
        self.assertNotIn('old-newspaper', result)
        self.assertEqual(len(result['newspaper']), 1)
    
    def test_get_archives_for_processing_scheduled_run_empty_newspapers(self):
        """Test getting archives for scheduled run when no newspapers exist."""
        archives_no_newspapers = {
            'old-newspaper': [
                {'folder': 'kayhan', 'urls': ['http://example.com/kayhan.pdf']}
            ]
        }
        
        result = self.executor.get_archives_for_processing(
            archives_no_newspapers, is_scheduled_run=True
        )
        
        # Should return empty dictionary or only newspaper category
        self.assertNotIn('old-newspaper', result)
        # newspaper category might not exist or be empty
        if 'newspaper' in result:
            self.assertEqual(len(result['newspaper']), 0)


if __name__ == '__main__':
    unittest.main()