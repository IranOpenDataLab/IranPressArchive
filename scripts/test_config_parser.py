#!/usr/bin/env python3
"""
Unit tests for the configuration parser and validation module.

This module contains comprehensive tests for the ConfigParser class,
including validation functions, error handling, and edge cases.
"""

import unittest
import tempfile
import os
import yaml
from unittest.mock import patch, mock_open
from config_parser import ConfigParser, Archive, ConfigurationError


class TestConfigParser(unittest.TestCase):
    """Test cases for ConfigParser class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = ConfigParser()
        
        # Sample valid configuration data
        self.valid_config = {
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
                    'title_fa': 'مجله دانشجو',
                    'folder': 'student-magazine',
                    'category': 'newspaper',
                    'description': 'Student magazine archive',
                    'years': {
                        '2023': [
                            'https://example.com/student-2023-01.pdf'
                        ]
                    }
                }
            ]
        }
    
    def test_parse_valid_configuration(self):
        """Test parsing a valid configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            yaml.dump(self.valid_config, f, allow_unicode=True)
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            archives = parser.parse_configuration()
            
            self.assertEqual(len(archives), 2)
            
            # Check first archive
            archive1 = archives[0]
            self.assertEqual(archive1.title_fa, 'روزنامه کیهان')
            self.assertEqual(archive1.folder, 'kayhan-newspaper')
            self.assertEqual(archive1.category, 'old-newspaper')
            self.assertEqual(archive1.description, 'Historical Kayhan newspaper archive')
            self.assertEqual(len(archive1.years), 2)
            self.assertIn('2020', archive1.years)
            self.assertIn('2021', archive1.years)
            
            # Check second archive
            archive2 = archives[1]
            self.assertEqual(archive2.title_fa, 'مجله دانشجو')
            self.assertEqual(archive2.folder, 'student-magazine')
            self.assertEqual(archive2.category, 'newspaper')
            
        finally:
            os.unlink(temp_path)
    
    def test_parse_nonexistent_file(self):
        """Test parsing a non-existent configuration file."""
        parser = ConfigParser('nonexistent.yml')
        with self.assertRaises(ConfigurationError) as cm:
            parser.parse_configuration()
        self.assertIn('Configuration file not found', str(cm.exception))
    
    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML syntax."""
        invalid_yaml = "archives:\n  - title_fa: 'test\n    invalid: yaml"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            with self.assertRaises(ConfigurationError) as cm:
                parser.parse_configuration()
            self.assertIn('Invalid YAML syntax', str(cm.exception))
        finally:
            os.unlink(temp_path)
    
    def test_parse_missing_archives_key(self):
        """Test parsing configuration without 'archives' key."""
        config = {'other_key': 'value'}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            yaml.dump(config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            with self.assertRaises(ConfigurationError) as cm:
                parser.parse_configuration()
            self.assertIn("Configuration must contain 'archives' key", str(cm.exception))
        finally:
            os.unlink(temp_path)
    
    def test_validate_archive_entry_missing_fields(self):
        """Test validation with missing required fields."""
        incomplete_archive = {
            'title_fa': 'Test Title',
            'folder': 'test-folder'
            # Missing category, description, years
        }
        
        with self.assertRaises(ConfigurationError) as cm:
            self.parser.validate_archive_entry(incomplete_archive, 0)
        
        error_msg = str(cm.exception)
        self.assertIn('Missing required fields', error_msg)
        self.assertIn('category', error_msg)
        self.assertIn('description', error_msg)
        self.assertIn('years', error_msg)
    
    def test_validate_archive_entry_invalid_category(self):
        """Test validation with invalid category."""
        invalid_archive = {
            'title_fa': 'Test Title',
            'folder': 'test-folder',
            'category': 'invalid-category',
            'description': 'Test description',
            'years': {'2023': ['https://example.com/test.pdf']}
        }
        
        with self.assertRaises(ConfigurationError) as cm:
            self.parser.validate_archive_entry(invalid_archive, 0)
        
        self.assertIn('category must be one of', str(cm.exception))
    
    def test_validate_archive_entry_empty_strings(self):
        """Test validation with empty string values."""
        empty_archive = {
            'title_fa': '',
            'folder': '   ',
            'category': 'newspaper',
            'description': '',
            'years': {}
        }
        
        with self.assertRaises(ConfigurationError) as cm:
            self.parser.validate_archive_entry(empty_archive, 0)
        
        self.assertIn('title_fa must be a non-empty string', str(cm.exception))
    
    def test_validate_years_structure_invalid_year(self):
        """Test validation with invalid year format."""
        archive = {
            'title_fa': 'Test Title',
            'folder': 'test-folder',
            'category': 'newspaper',
            'description': 'Test description',
            'years': {
                '23': ['https://example.com/test.pdf'],  # Invalid year format
                '2023': ['https://example.com/test2.pdf']
            }
        }
        
        with self.assertRaises(ConfigurationError) as cm:
            self.parser.validate_archive_entry(archive, 0)
        
        self.assertIn('Invalid year format: 23', str(cm.exception))
    
    def test_validate_years_structure_invalid_urls(self):
        """Test validation with invalid URL formats."""
        archive = {
            'title_fa': 'Test Title',
            'folder': 'test-folder',
            'category': 'newspaper',
            'description': 'Test description',
            'years': {
                '2023': [
                    'https://example.com/valid.pdf',
                    'invalid-url',  # Invalid URL
                    ''  # Empty URL
                ]
            }
        }
        
        with self.assertRaises(ConfigurationError) as cm:
            self.parser.validate_archive_entry(archive, 0)
        
        error_msg = str(cm.exception)
        self.assertTrue('Invalid URL format' in error_msg or 'must be a non-empty string' in error_msg)
    
    def test_sanitize_folder_name_basic(self):
        """Test basic folder name sanitization."""
        test_cases = [
            ('Simple Folder', 'Simple-Folder'),
            ('folder with spaces', 'folder-with-spaces'),
            ('folder_with_underscores', 'folder_with_underscores'),
            ('folder-with-hyphens', 'folder-with-hyphens'),
            ('Folder123', 'Folder123'),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = self.parser.sanitize_folder_name(input_name)
                self.assertEqual(result, expected)
    
    def test_sanitize_folder_name_special_characters(self):
        """Test folder name sanitization with special characters."""
        test_cases = [
            ('folder/with\\slashes', 'folderwithslashes'),
            ('folder:with*special?chars', 'folderwithspecialchars'),
            ('folder<with>brackets', 'folderwithbrackets'),
            ('folder|with|pipes', 'folderwithpipes'),
            ('folder"with"quotes', 'folderwithquotes'),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = self.parser.sanitize_folder_name(input_name)
                self.assertEqual(result, expected)
    
    def test_sanitize_folder_name_multiple_spaces_hyphens(self):
        """Test folder name sanitization with multiple spaces and hyphens."""
        test_cases = [
            ('folder   with   spaces', 'folder-with-spaces'),
            ('folder---with---hyphens', 'folder-with-hyphens'),
            ('  folder  with  leading  trailing  ', 'folder-with-leading-trailing'),
            ('---folder---', 'folder'),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = self.parser.sanitize_folder_name(input_name)
                self.assertEqual(result, expected)
    
    def test_sanitize_folder_name_empty_result(self):
        """Test folder name sanitization that results in empty string."""
        with self.assertRaises(ConfigurationError) as cm:
            self.parser.sanitize_folder_name('!@#$%^&*()')
        
        self.assertIn('results in empty string after sanitization', str(cm.exception))
    
    def test_sanitize_folder_name_long_name(self):
        """Test folder name sanitization with very long names."""
        long_name = 'a' * 150  # 150 characters
        result = self.parser.sanitize_folder_name(long_name)
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.startswith('a'))
    
    def test_is_valid_year(self):
        """Test year validation function."""
        valid_years = ['2020', '2023', '1900', '2099']
        invalid_years = ['20', '202', '20200', 'abcd', '']
        
        for year in valid_years:
            with self.subTest(year=year):
                self.assertTrue(self.parser._is_valid_year(year))
        
        for year in invalid_years:
            with self.subTest(year=year):
                self.assertFalse(self.parser._is_valid_year(year))
    
    def test_is_valid_url(self):
        """Test URL validation function."""
        valid_urls = [
            'https://example.com/file.pdf',
            'http://example.com/path/file.pdf',
            'https://subdomain.example.com/file.pdf',
            'https://example.com:8080/file.pdf',
            'https://192.168.1.1/file.pdf',
        ]
        
        invalid_urls = [
            'ftp://example.com/file.pdf',
            'example.com/file.pdf',
            'https://',
            '',
            'not-a-url',
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(self.parser._is_valid_url(url))
        
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(self.parser._is_valid_url(url))
    
    def test_update_configuration(self):
        """Test updating configuration file."""
        archives = [
            Archive(
                title_fa='Test Archive',
                folder='test-archive',
                category='newspaper',
                description='Test description',
                years={'2023': ['https://example.com/test.pdf']}
            )
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            temp_path = f.name
        
        try:
            parser = ConfigParser(temp_path)
            parser.update_configuration(archives)
            
            # Read back and verify
            with open(temp_path, 'r', encoding='utf-8') as f:
                updated_config = yaml.safe_load(f)
            
            self.assertIn('archives', updated_config)
            self.assertEqual(len(updated_config['archives']), 1)
            
            archive_data = updated_config['archives'][0]
            self.assertEqual(archive_data['title_fa'], 'Test Archive')
            self.assertEqual(archive_data['folder'], 'test-archive')
            self.assertEqual(archive_data['category'], 'newspaper')
            
        finally:
            os.unlink(temp_path)
    
    def test_remove_successful_urls(self):
        """Test removing successful URLs from archive configuration."""
        archive = Archive(
            title_fa='Test Archive',
            folder='test-archive',
            category='newspaper',
            description='Test description',
            years={
                '2023': [
                    'https://example.com/file1.pdf',
                    'https://example.com/file2.pdf',
                    'https://example.com/file3.pdf'
                ],
                '2024': [
                    'https://example.com/file4.pdf'
                ]
            }
        )
        
        successful_urls = [
            'https://example.com/file1.pdf',
            'https://example.com/file3.pdf',
            'https://example.com/file4.pdf'
        ]
        
        updated_archive = self.parser.remove_successful_urls(archive, successful_urls)
        
        # Check that successful URLs were removed
        self.assertEqual(len(updated_archive.years), 1)  # 2024 should be removed entirely
        self.assertIn('2023', updated_archive.years)
        self.assertEqual(updated_archive.years['2023'], ['https://example.com/file2.pdf'])
        
        # Check that other fields remain unchanged
        self.assertEqual(updated_archive.title_fa, archive.title_fa)
        self.assertEqual(updated_archive.folder, archive.folder)
        self.assertEqual(updated_archive.category, archive.category)
        self.assertEqual(updated_archive.description, archive.description)
    
    def test_remove_successful_urls_all_removed(self):
        """Test removing all URLs from archive configuration."""
        archive = Archive(
            title_fa='Test Archive',
            folder='test-archive',
            category='newspaper',
            description='Test description',
            years={
                '2023': ['https://example.com/file1.pdf']
            }
        )
        
        successful_urls = ['https://example.com/file1.pdf']
        
        updated_archive = self.parser.remove_successful_urls(archive, successful_urls)
        
        # All URLs removed, so years should be empty
        self.assertEqual(len(updated_archive.years), 0)
    
    def test_input_sanitization(self):
        """Test input sanitization for security."""
        # Test dangerous input patterns
        dangerous_title = "<script>alert('xss')</script>Test Title"
        sanitized = self.parser._sanitize_string_input(dangerous_title, "title")
        self.assertNotIn("<script", sanitized)
        self.assertNotIn("alert", sanitized)
        
        # Test HTML escaping
        html_input = "Title with <tags> & \"quotes\""
        sanitized = self.parser._sanitize_string_input(html_input, "title")
        self.assertIn("&lt;", sanitized)
        self.assertIn("&gt;", sanitized)
    
    def test_url_security_validation(self):
        """Test URL security validation."""
        # Valid URLs should pass
        valid_url = "https://example.com/document.pdf"
        is_valid, error = self.parser._validate_url_security(valid_url)
        self.assertTrue(is_valid, f"Valid URL rejected: {error}")
        
        # Malicious URLs should be blocked
        malicious_urls = [
            "javascript:alert('xss')",
            "https://localhost/file.pdf",
            "data:text/html,<script>alert(1)</script>",
            "https://example.com/file<script>.pdf"
        ]
        
        for url in malicious_urls:
            with self.subTest(url=url):
                is_valid, error = self.parser._validate_url_security(url)
                self.assertFalse(is_valid, f"Malicious URL not blocked: {url}")
                self.assertIsNotNone(error)
    
    def test_configuration_limits(self):
        """Test configuration security limits."""
        # Test string length limits
        long_string = "a" * (self.parser.MAX_STRING_LENGTH + 1)
        with self.assertRaises(ConfigurationError):
            self.parser._sanitize_string_input(long_string, "test_field")
        
        # Test empty string after sanitization
        empty_input = "<script></script>"
        with self.assertRaises(ConfigurationError):
            self.parser._sanitize_string_input(empty_input, "test_field")


class TestArchiveDataClass(unittest.TestCase):
    """Test cases for Archive data class."""
    
    def test_archive_creation(self):
        """Test creating Archive instance."""
        archive = Archive(
            title_fa='Test Title',
            folder='test-folder',
            category='newspaper',
            description='Test description',
            years={'2023': ['https://example.com/test.pdf']}
        )
        
        self.assertEqual(archive.title_fa, 'Test Title')
        self.assertEqual(archive.folder, 'test-folder')
        self.assertEqual(archive.category, 'newspaper')
        self.assertEqual(archive.description, 'Test description')
        self.assertEqual(archive.years, {'2023': ['https://example.com/test.pdf']})


class TestConfigurationError(unittest.TestCase):
    """Test cases for ConfigurationError exception."""
    
    def test_configuration_error(self):
        """Test ConfigurationError exception."""
        error_msg = "Test error message"
        error = ConfigurationError(error_msg)
        
        self.assertEqual(str(error), error_msg)
        self.assertIsInstance(error, Exception)


if __name__ == '__main__':
    unittest.main()