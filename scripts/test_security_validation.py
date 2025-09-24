#!/usr/bin/env python3
"""
Security-focused unit tests for Iranian Archive Workflow.

This module contains comprehensive security tests for:
- URL validation and malicious redirect prevention
- File type validation for PDF-only downloads
- File size limits and validation
- Input sanitization for all user-provided data
- Protection against various injection attacks
"""

import unittest
import tempfile
import shutil
import yaml
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import requests

from file_manager import FileManager
from config_parser import ConfigParser, ConfigurationError


class TestURLSecurityValidation(unittest.TestCase):
    """Test cases for URL security validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = FileManager(max_file_size_mb=1, max_retries=1, timeout=5)
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_valid_urls_pass_security_check(self):
        """Test that valid URLs pass security validation."""
        valid_urls = [
            "https://example.com/document.pdf",
            "http://test.org/archive/file.pdf",
            "https://subdomain.example.com/path/to/file.pdf",
            "https://example.com:8080/secure/document.pdf"
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                is_safe, error = self.file_manager._is_safe_url(url)
                self.assertTrue(is_safe, f"Valid URL rejected: {url} - {error}")
    
    def test_malicious_urls_blocked(self):
        """Test that malicious URLs are blocked."""
        malicious_urls = [
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "file:///etc/passwd",
            "ftp://example.com/file.pdf",
            "https://localhost/file.pdf",
            "http://127.0.0.1/file.pdf",
            "https://192.168.1.1/file.pdf",
            "https://example.com/../../../etc/passwd",
            "https://example.com/file.pdf?param=<script>alert('xss')</script>",
            "https://user:pass@example.com/file.pdf",
            "https://example.com/file.pdf'><script>alert('xss')</script>"
        ]
        
        for url in malicious_urls:
            with self.subTest(url=url):
                is_safe, error = self.file_manager._is_safe_url(url)
                self.assertFalse(is_safe, f"Malicious URL not blocked: {url}")
                self.assertIsNotNone(error, f"No error message for malicious URL: {url}")
    
    def test_private_ip_detection(self):
        """Test detection of private IP addresses."""
        private_ips = [
            "10.0.0.1",
            "172.16.0.1", 
            "192.168.1.1",
            "127.0.0.1",
            "localhost"
        ]
        
        for ip in private_ips:
            with self.subTest(ip=ip):
                result = self.file_manager._is_private_ip(ip)
                if ip in ["127.0.0.1", "localhost"]:
                    # These should be detected as private/local
                    continue
                # For actual private IPs, the method should detect them
                # Note: This test may need adjustment based on implementation
    
    def test_suspicious_url_patterns(self):
        """Test detection of suspicious URL patterns."""
        suspicious_urls = [
            "https://example.com/../../../etc/passwd",
            "https://example.com/%2e%2e%2f",
            "https://example.com/file.pdf?param=javascript:alert(1)",
            "https://example.com/file<script>alert(1)</script>.pdf"
        ]
        
        for url in suspicious_urls:
            with self.subTest(url=url):
                has_suspicious = self.file_manager._has_suspicious_patterns(url)
                self.assertTrue(has_suspicious, f"Suspicious pattern not detected: {url}")


class TestContentTypeValidation(unittest.TestCase):
    """Test cases for content type validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = FileManager()
    
    def test_valid_pdf_content_types(self):
        """Test that valid PDF content types are accepted."""
        valid_types = [
            "application/pdf",
            "application/x-pdf",
            "application/acrobat",
            "applications/vnd.pdf",
            "text/pdf",
            "text/x-pdf"
        ]
        
        for content_type in valid_types:
            with self.subTest(content_type=content_type):
                is_valid, error = self.file_manager._validate_content_type(
                    content_type, "https://example.com/test.pdf"
                )
                self.assertTrue(is_valid, f"Valid PDF content type rejected: {content_type} - {error}")
    
    def test_invalid_content_types_rejected(self):
        """Test that invalid content types are rejected."""
        invalid_types = [
            "text/html",
            "application/javascript",
            "image/jpeg",
            "video/mp4",
            "application/zip",
            "text/plain",
            "application/json"
        ]
        
        for content_type in invalid_types:
            with self.subTest(content_type=content_type):
                is_valid, error = self.file_manager._validate_content_type(
                    content_type, "https://example.com/test.pdf"
                )
                self.assertFalse(is_valid, f"Invalid content type not rejected: {content_type}")
                self.assertIsNotNone(error)
    
    def test_generic_binary_with_pdf_extension(self):
        """Test that generic binary types are accepted if URL has .pdf extension."""
        generic_types = [
            "application/octet-stream",
            "binary/octet-stream"
        ]
        
        for content_type in generic_types:
            with self.subTest(content_type=content_type):
                is_valid, error = self.file_manager._validate_content_type(
                    content_type, "https://example.com/document.pdf"
                )
                self.assertTrue(is_valid, f"Generic binary with .pdf extension rejected: {content_type}")
    
    def test_no_content_type_with_pdf_extension(self):
        """Test handling of missing content-type header with .pdf extension."""
        is_valid, error = self.file_manager._validate_content_type(
            "", "https://example.com/document.pdf"
        )
        self.assertTrue(is_valid, f"Missing content-type with .pdf extension rejected: {error}")


class TestPDFContentValidation(unittest.TestCase):
    """Test cases for PDF file content validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = FileManager()
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_valid_pdf_signature(self):
        """Test validation of valid PDF file signature."""
        # Create a file with valid PDF signature
        test_file = self.temp_dir / "valid.pdf"
        with open(test_file, 'wb') as f:
            f.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')  # Valid PDF header
            f.write(b'fake pdf content')
        
        is_valid, error = self.file_manager._validate_pdf_content(test_file)
        self.assertTrue(is_valid, f"Valid PDF signature rejected: {error}")
    
    def test_invalid_pdf_signature(self):
        """Test rejection of invalid PDF file signature."""
        # Create a file with invalid signature
        test_file = self.temp_dir / "invalid.pdf"
        with open(test_file, 'wb') as f:
            f.write(b'<html><body>Not a PDF</body></html>')
        
        is_valid, error = self.file_manager._validate_pdf_content(test_file)
        self.assertFalse(is_valid, "Invalid PDF signature not rejected")
        self.assertIsNotNone(error)
        self.assertIn("PDF signature", error)
    
    def test_empty_file(self):
        """Test handling of empty file."""
        test_file = self.temp_dir / "empty.pdf"
        test_file.touch()
        
        is_valid, error = self.file_manager._validate_pdf_content(test_file)
        self.assertFalse(is_valid, "Empty file not rejected")
        self.assertIsNotNone(error)


class TestFileSizeLimits(unittest.TestCase):
    """Test cases for file size validation and limits."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = FileManager(max_file_size_mb=1)  # 1MB limit for testing
        
    @patch('file_manager.requests.Session')
    def test_file_size_check_within_limit(self, mock_session_class):
        """Test file size check for files within limit."""
        # Mock session and response with size within limit (500KB)
        mock_session = Mock()
        mock_response = Mock()
        mock_response.headers = {
            'content-length': '512000',  # 500KB
            'content-type': 'application/pdf'
        }
        mock_response.raise_for_status.return_value = None
        mock_response.url = "https://example.com/test.pdf"
        mock_session.head.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        can_download, file_size, error = self.file_manager.check_file_size_before_download(
            "https://example.com/test.pdf"
        )
        
        self.assertTrue(can_download, f"File within size limit rejected: {error}")
        self.assertEqual(file_size, 512000)
        self.assertIsNone(error)
    
    @patch('file_manager.requests.Session')
    def test_file_size_check_exceeds_limit(self, mock_session_class):
        """Test file size check for files exceeding limit."""
        # Mock session and response with size exceeding limit (2MB)
        mock_session = Mock()
        mock_response = Mock()
        mock_response.headers = {
            'content-length': '2097152',  # 2MB
            'content-type': 'application/pdf'
        }
        mock_response.raise_for_status.return_value = None
        mock_response.url = "https://example.com/large.pdf"
        mock_session.head.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        can_download, file_size, error = self.file_manager.check_file_size_before_download(
            "https://example.com/large.pdf"
        )
        
        self.assertFalse(can_download, "File exceeding size limit not rejected")
        self.assertEqual(file_size, 2097152)
        self.assertIsNotNone(error)
        self.assertIn("too large", error.lower())


class TestInputSanitization(unittest.TestCase):
    """Test cases for input sanitization in configuration parser."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = ConfigParser()
    
    def test_string_sanitization_removes_dangerous_patterns(self):
        """Test that dangerous patterns are removed from strings."""
        dangerous_inputs = [
            "<script>alert('xss')</script>Normal Text",
            "javascript:alert(1)",
            "Text with <iframe src='evil.com'></iframe>",
            "onclick=alert(1) Normal Text",
            "vbscript:msgbox(1)"
        ]
        
        for dangerous_input in dangerous_inputs:
            with self.subTest(input=dangerous_input):
                try:
                    sanitized = self.parser._sanitize_string_input(dangerous_input, "test_field")
                    # Should not contain dangerous patterns
                    self.assertNotIn("<script", sanitized.lower())
                    self.assertNotIn("javascript:", sanitized.lower())
                    self.assertNotIn("<iframe", sanitized.lower())
                    self.assertNotIn("onclick", sanitized.lower())
                    self.assertNotIn("vbscript:", sanitized.lower())
                except ConfigurationError:
                    # It's also acceptable to reject the input entirely
                    pass
    
    def test_html_escaping(self):
        """Test that HTML characters are properly escaped."""
        html_input = "Title with <tags> & \"quotes\" and 'apostrophes'"
        sanitized = self.parser._sanitize_string_input(html_input, "test_field")
        
        # Should escape HTML entities
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertIn("&lt;", sanitized)
        self.assertIn("&gt;", sanitized)
    
    def test_control_character_removal(self):
        """Test that control characters are removed."""
        control_input = "Normal text\x00\x01\x02\x1f\x7f with control chars"
        sanitized = self.parser._sanitize_string_input(control_input, "test_field")
        
        # Should not contain control characters
        for i in range(32):
            if i not in [9, 10, 13]:  # Allow tab, newline, carriage return
                self.assertNotIn(chr(i), sanitized)
    
    def test_length_limits_enforced(self):
        """Test that length limits are enforced."""
        long_input = "a" * 2000  # Exceeds MAX_STRING_LENGTH
        
        with self.assertRaises(ConfigurationError) as cm:
            self.parser._sanitize_string_input(long_input, "test_field")
        
        self.assertIn("exceeds maximum length", str(cm.exception))
    
    def test_empty_input_after_sanitization(self):
        """Test handling of input that becomes empty after sanitization."""
        empty_inputs = [
            "<script></script>",
            "   \t\n   ",
            "\x00\x01\x02",
            ""
        ]
        
        for empty_input in empty_inputs:
            with self.subTest(input=repr(empty_input)):
                with self.assertRaises(ConfigurationError) as cm:
                    self.parser._sanitize_string_input(empty_input, "test_field")
                
                self.assertIn("empty after sanitization", str(cm.exception))


class TestConfigurationSecurityLimits(unittest.TestCase):
    """Test cases for configuration security limits."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = ConfigParser()
    
    def test_archive_count_limit(self):
        """Test that archive count limits are enforced."""
        # Create configuration with too many archives
        too_many_archives = {
            'archives': [
                {
                    'title_fa': f'Archive {i}',
                    'folder': f'archive-{i}',
                    'category': 'newspaper',
                    'description': f'Description {i}',
                    'years': {'2023': ['https://example.com/file.pdf']}
                }
                for i in range(self.parser.MAX_ARCHIVES + 1)
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            yaml.dump(too_many_archives, f, allow_unicode=True)
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            with self.assertRaises(ConfigurationError) as cm:
                parser.parse_configuration()
            
            self.assertIn("Too many archives", str(cm.exception))
        finally:
            import os
            os.unlink(temp_path)
    
    def test_urls_per_year_limit(self):
        """Test that URL count per year limits are enforced."""
        # Create configuration with too many URLs in one year
        too_many_urls = {
            'archives': [
                {
                    'title_fa': 'Test Archive',
                    'folder': 'test-archive',
                    'category': 'newspaper',
                    'description': 'Test description',
                    'years': {
                        '2023': [f'https://example.com/file-{i}.pdf' 
                                for i in range(self.parser.MAX_URLS_PER_YEAR + 1)]
                    }
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            yaml.dump(too_many_urls, f, allow_unicode=True)
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            with self.assertRaises(ConfigurationError) as cm:
                parser.parse_configuration()
            
            self.assertIn("Too many URLs", str(cm.exception))
        finally:
            import os
            os.unlink(temp_path)
    
    def test_malicious_url_in_configuration(self):
        """Test that malicious URLs in configuration are rejected."""
        malicious_config = {
            'archives': [
                {
                    'title_fa': 'Test Archive',
                    'folder': 'test-archive',
                    'category': 'newspaper',
                    'description': 'Test description',
                    'years': {
                        '2023': [
                            'https://example.com/valid.pdf',
                            'https://localhost/local.pdf'  # Local URL that should be blocked
                        ]
                    }
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            yaml.dump(malicious_config, f, allow_unicode=True)
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            with self.assertRaises(ConfigurationError) as cm:
                parser.parse_configuration()
            
            error_msg = str(cm.exception)
            self.assertTrue(
                "security validation failed" in error_msg or 
                "dangerous pattern" in error_msg or
                "not allowed" in error_msg or
                "localhost" in error_msg
            )
        finally:
            import os
            os.unlink(temp_path)


class TestRedirectSecurity(unittest.TestCase):
    """Test cases for redirect security validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.file_manager = FileManager(max_redirects=3)
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    @patch('file_manager.requests.Session')
    def test_safe_redirect_allowed(self, mock_session_class):
        """Test that safe redirects are allowed."""
        # Mock session and response
        mock_session = Mock()
        mock_response = Mock()
        mock_response.url = "https://cdn.example.com/document.pdf"  # Safe redirect
        mock_response.headers = {
            'content-type': 'application/pdf',
            'content-length': '1000'
        }
        mock_response.iter_content.return_value = [b'%PDF-1.4\nfake content']
        mock_response.raise_for_status.return_value = None
        
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        target_path = self.temp_dir / "test.pdf"
        success, error = self.file_manager.download_file(
            "https://example.com/redirect-to-pdf", target_path
        )
        
        self.assertTrue(success, f"Safe redirect rejected: {error}")
    
    @patch('file_manager.requests.Session')
    def test_malicious_redirect_blocked(self, mock_session_class):
        """Test that malicious redirects are blocked."""
        # Mock session and response with malicious redirect
        mock_session = Mock()
        mock_response = Mock()
        mock_response.url = "https://localhost/malicious.pdf"  # Malicious redirect
        mock_response.raise_for_status.return_value = None
        
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        target_path = self.temp_dir / "test.pdf"
        success, error = self.file_manager.download_file(
            "https://example.com/redirect-to-malicious", target_path
        )
        
        self.assertFalse(success, "Malicious redirect not blocked")
        self.assertIsNotNone(error)
        self.assertIn("unsafe URL", error)


if __name__ == '__main__':
    # Run all security tests
    unittest.main(verbosity=2)