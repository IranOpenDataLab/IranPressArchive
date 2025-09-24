"""
Unit tests for file_manager.py

Tests cover:
- File download functionality with error handling and retries
- Directory structure creation
- File existence checking
- Sequential file numbering
- URL validation and sanitization
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import requests
from file_manager import FileManager


class TestFileManager(unittest.TestCase):
    """Test cases for FileManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = FileManager(max_file_size_mb=1, max_retries=2, timeout=10)
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_create_directory_structure(self):
        """Test directory structure creation."""
        # Test actual directory creation in temp directory
        result = self.file_manager.create_directory_structure("newspaper", "daily-news", "2024")
        
        # Verify the path was created correctly
        self.assertTrue(result.exists())
        self.assertTrue(result.is_dir())
        self.assertEqual(result.name, "2024")
        self.assertEqual(result.parent.name, "daily-news")
        self.assertEqual(result.parent.parent.name, "newspaper")
    
    def test_create_directory_structure_real(self):
        """Test directory creation with real filesystem."""
        # Change to temp directory for testing
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(self.temp_dir)
            
            result = self.file_manager.create_directory_structure("newspaper", "daily-news", "2024")
            
            expected_path = self.temp_dir / "newspaper" / "daily-news" / "2024"
            self.assertTrue(expected_path.exists())
            self.assertTrue(expected_path.is_dir())
            
        finally:
            os.chdir(original_cwd)
    
    def test_sanitize_folder_name(self):
        """Test folder name sanitization."""
        # Test various problematic characters
        test_cases = [
            ("normal_name", "normal_name"),
            ("name with spaces", "name with spaces"),
            ("name<>:\"/\\|?*", "name_________"),
            ("  .leading_trailing.  ", "leading_trailing"),
            ("", "unnamed_folder"),
            ("a" * 150, "a" * 100),  # Test length limit
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = self.file_manager._sanitize_folder_name(input_name)
                self.assertEqual(result, expected)
    
    def test_file_exists(self):
        """Test file existence checking."""
        # Create a test file
        test_file = self.temp_dir / "test.pdf"
        test_file.touch()
        
        # Test existing file
        self.assertTrue(self.file_manager.file_exists(test_file))
        
        # Test non-existing file
        non_existing = self.temp_dir / "nonexistent.pdf"
        self.assertFalse(self.file_manager.file_exists(non_existing))
        
        # Test directory (should return False)
        test_dir = self.temp_dir / "testdir"
        test_dir.mkdir()
        self.assertFalse(self.file_manager.file_exists(test_dir))
    
    def test_get_next_file_number(self):
        """Test sequential file numbering."""
        test_dir = self.temp_dir / "test_numbering"
        test_dir.mkdir()
        
        # Test empty directory
        self.assertEqual(self.file_manager.get_next_file_number(test_dir), 1)
        
        # Create some numbered files
        (test_dir / "1.pdf").touch()
        (test_dir / "3.pdf").touch()
        (test_dir / "5.pdf").touch()
        (test_dir / "non_numeric.pdf").touch()  # Should be ignored
        
        # Should return 6 (next after highest number)
        self.assertEqual(self.file_manager.get_next_file_number(test_dir), 6)
        
        # Test non-existing directory
        non_existing_dir = self.temp_dir / "nonexistent"
        self.assertEqual(self.file_manager.get_next_file_number(non_existing_dir), 1) 
   
    def test_is_valid_url(self):
        """Test URL validation."""
        valid_urls = [
            "https://example.com/file.pdf",
            "http://test.org/document.pdf",
            "https://subdomain.example.com/path/to/file.pdf"
        ]
        
        invalid_urls = [
            "not_a_url",
            "ftp://example.com/file.pdf",  # Wrong scheme
            "https://",  # No netloc
            "",  # Empty string
            "file:///local/path.pdf"  # Local file
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(self.file_manager._is_valid_url(url))
        
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(self.file_manager._is_valid_url(url))
    
    @patch('file_manager.requests.get')
    def test_download_file_success(self, mock_get):
        """Test successful file download."""
        # Mock successful response
        mock_response = Mock()
        mock_response.headers = {'content-type': 'application/pdf', 'content-length': '1000'}
        mock_response.iter_content.return_value = [b'fake pdf content']
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        target_path = self.temp_dir / "test.pdf"
        success, error = self.file_manager.download_file("https://example.com/test.pdf", target_path)
        
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(target_path.exists())
        mock_get.assert_called_once()
    
    @patch('file_manager.requests.get')
    def test_download_file_already_exists(self, mock_get):
        """Test download when file already exists."""
        # Create existing file
        target_path = self.temp_dir / "existing.pdf"
        target_path.touch()
        
        success, error = self.file_manager.download_file("https://example.com/test.pdf", target_path)
        
        self.assertTrue(success)
        self.assertIsNone(error)
        mock_get.assert_not_called()  # Should not attempt download
    
    def test_download_file_invalid_url(self):
        """Test download with invalid URL."""
        target_path = self.temp_dir / "test.pdf"
        success, error = self.file_manager.download_file("invalid_url", target_path)
        
        self.assertFalse(success)
        self.assertIn("Invalid URL format", error)
    
    @patch('file_manager.requests.get')
    def test_download_file_too_large(self, mock_get):
        """Test download with file too large."""
        # Mock response with large content-length
        mock_response = Mock()
        mock_response.headers = {'content-length': str(self.file_manager.max_file_size_bytes + 1)}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        target_path = self.temp_dir / "large.pdf"
        success, error = self.file_manager.download_file("https://example.com/large.pdf", target_path)
        
        self.assertFalse(success)
        self.assertIn("File too large", error)
    
    @patch('file_manager.requests.get')
    @patch('file_manager.time.sleep')  # Mock sleep to speed up tests
    def test_download_file_retry_mechanism(self, mock_sleep, mock_get):
        """Test retry mechanism on network errors."""
        # Mock network error on first two attempts, success on third
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Network error"),
            requests.exceptions.Timeout("Timeout error"),
            Mock(headers={'content-type': 'application/pdf'}, 
                 iter_content=lambda chunk_size: [b'content'],
                 raise_for_status=lambda: None)
        ]
        
        target_path = self.temp_dir / "retry_test.pdf"
        success, error = self.file_manager.download_file("https://example.com/test.pdf", target_path)
        
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(mock_get.call_count, 3)  # Should retry twice then succeed
        self.assertEqual(mock_sleep.call_count, 2)  # Should sleep between retries
    
    @patch('file_manager.requests.get')
    @patch('file_manager.time.sleep')
    def test_download_file_max_retries_exceeded(self, mock_sleep, mock_get):
        """Test behavior when max retries are exceeded."""
        # Mock persistent network error
        mock_get.side_effect = requests.exceptions.ConnectionError("Persistent error")
        
        target_path = self.temp_dir / "fail_test.pdf"
        success, error = self.file_manager.download_file("https://example.com/test.pdf", target_path)
        
        self.assertFalse(success)
        self.assertIn("Network error", error)
        self.assertEqual(mock_get.call_count, self.file_manager.max_retries + 1)
    
    @patch('file_manager.requests.get')
    def test_download_file_size_exceeded_during_download(self, mock_get):
        """Test handling when file size exceeds limit during download."""
        # Mock response that returns too much data
        mock_response = Mock()
        mock_response.headers = {'content-type': 'application/pdf'}
        # Return chunks that exceed size limit
        large_chunk = b'x' * (self.file_manager.max_file_size_bytes + 1)
        mock_response.iter_content.return_value = [large_chunk]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        target_path = self.temp_dir / "oversized.pdf"
        success, error = self.file_manager.download_file("https://example.com/test.pdf", target_path)
        
        self.assertFalse(success)
        self.assertIn("exceeded size limit during download", error)
        self.assertFalse(target_path.exists())  # Partial file should be deleted
    
    def test_url_security_validation(self):
        """Test URL security validation."""
        # Test malicious URLs are blocked
        malicious_urls = [
            "javascript:alert('xss')",
            "https://localhost/file.pdf",
            "http://127.0.0.1/file.pdf",
            "https://example.com/../../../etc/passwd"
        ]
        
        for url in malicious_urls:
            with self.subTest(url=url):
                target_path = self.temp_dir / "test.pdf"
                success, error = self.file_manager.download_file(url, target_path)
                self.assertFalse(success, f"Malicious URL not blocked: {url}")
                self.assertIsNotNone(error)
    
    def test_pdf_content_validation(self):
        """Test PDF content validation."""
        # Create a file with invalid PDF signature
        invalid_pdf = self.temp_dir / "invalid.pdf"
        with open(invalid_pdf, 'wb') as f:
            f.write(b'<html>Not a PDF</html>')
        
        is_valid, error = self.file_manager._validate_pdf_content(invalid_pdf)
        self.assertFalse(is_valid)
        self.assertIn("PDF signature", error)
        
        # Create a file with valid PDF signature
        valid_pdf = self.temp_dir / "valid.pdf"
        with open(valid_pdf, 'wb') as f:
            f.write(b'%PDF-1.4\nfake content')
        
        is_valid, error = self.file_manager._validate_pdf_content(valid_pdf)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_content_type_validation(self):
        """Test content type validation."""
        # Valid PDF content types
        valid_types = ["application/pdf", "application/x-pdf"]
        for content_type in valid_types:
            with self.subTest(content_type=content_type):
                is_valid, error = self.file_manager._validate_content_type(
                    content_type, "https://example.com/test.pdf"
                )
                self.assertTrue(is_valid, f"Valid PDF type rejected: {content_type}")
        
        # Invalid content types
        invalid_types = ["text/html", "application/javascript", "image/jpeg"]
        for content_type in invalid_types:
            with self.subTest(content_type=content_type):
                is_valid, error = self.file_manager._validate_content_type(
                    content_type, "https://example.com/test.pdf"
                )
                self.assertFalse(is_valid, f"Invalid type not rejected: {content_type}")


if __name__ == '__main__':
    unittest.main()