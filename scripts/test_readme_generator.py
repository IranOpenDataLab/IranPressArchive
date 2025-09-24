"""
Unit tests for README Generator module.
"""

import unittest
import tempfile
import os
from unittest.mock import patch, mock_open
from datetime import datetime

from readme_generator import ReadmeGenerator


class TestReadmeGenerator(unittest.TestCase):
    """Test cases for ReadmeGenerator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.generator = ReadmeGenerator()
        self.sample_archive = {
            'title_fa': 'روزنامه کیهان',
            'folder': 'kayhan-newspaper',
            'category': 'old-newspaper',
            'description': 'Historical Iranian newspaper',
            'years': {
                '2020': ['issue1.pdf', 'issue2.pdf'],
                '2021': ['issue3.pdf']
            }
        }
        
        self.sample_archives = [
            self.sample_archive,
            {
                'title_fa': 'مجله آرمان',
                'folder': 'arman-magazine',
                'category': 'newspaper',
                'description': 'Contemporary Iranian magazine',
                'years': {
                    '2023': ['vol1.pdf', 'vol2.pdf']
                }
            }
        ]
    
    def test_language_toggle_persian(self):
        """Test Persian language toggle generation."""
        toggle = self.generator._get_language_toggle('fa')
        self.assertIn('English](README.en.md)', toggle)
        self.assertIn('🇮🇷 فارسی', toggle)
        self.assertNotIn('[🇮🇷 فارسی]', toggle)  # Should not be a link
    
    def test_language_toggle_english(self):
        """Test English language toggle generation."""
        toggle = self.generator._get_language_toggle('en')
        self.assertIn('فارسی](README.md)', toggle)
        self.assertIn('🇺🇸 English', toggle)
        self.assertNotIn('[🇺🇸 English]', toggle)  # Should not be a link
    
    def test_archive_section_persian(self):
        """Test Persian archive section generation."""
        section = self.generator._generate_archive_section(self.sample_archive, 'fa')
        
        self.assertIn('### روزنامه کیهان', section)
        self.assertIn('سال‌های موجود:', section)
        self.assertIn('[2020](old-newspaper/kayhan-newspaper/2020)', section)
        self.assertIn('[2021](old-newspaper/kayhan-newspaper/2021)', section)
        self.assertIn('|', section)  # Year separator
    
    def test_archive_section_english(self):
        """Test English archive section generation."""
        section = self.generator._generate_archive_section(self.sample_archive, 'en')
        
        self.assertIn('### Kayhan Newspaper', section)
        self.assertIn('Available years:', section)
        self.assertIn('[2020](old-newspaper/kayhan-newspaper/2020)', section)
        self.assertIn('[2021](old-newspaper/kayhan-newspaper/2021)', section)
    
    def test_archive_section_no_years(self):
        """Test archive section generation when no years are available."""
        archive_no_years = {
            'title_fa': 'تست',
            'folder': 'test-publication',
            'category': 'newspaper'
        }
        
        section = self.generator._generate_archive_section(archive_no_years, 'en')
        self.assertIn('Coming soon...', section)
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('readme_generator.datetime')
    def test_generate_persian_readme(self, mock_datetime, mock_file):
        """Test Persian README generation."""
        mock_datetime.now.return_value.strftime.return_value = '2023/12/01'
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            self.generator.generate_main_readme('fa', self.sample_archives, tmp_path)
            
            # Verify file was opened for writing
            mock_file.assert_called_once_with(tmp_path, 'w', encoding='utf-8')
            
            # Get the written content
            written_content = ''.join(call.args[0] for call in mock_file().write.call_args_list)
            
            self.assertIn('# آرشیو اسناد عمومی ایران', written_content)
            self.assertIn('روزنامه کیهان', written_content)
            self.assertIn('مجله آرمان', written_content)
            self.assertIn('2023/12/01', written_content)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('readme_generator.datetime')
    def test_generate_english_readme(self, mock_datetime, mock_file):
        """Test English README generation."""
        mock_datetime.now.return_value.strftime.return_value = '2023/12/01'
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            self.generator.generate_main_readme('en', self.sample_archives, tmp_path)
            
            # Verify file was opened for writing
            mock_file.assert_called_once_with(tmp_path, 'w', encoding='utf-8')
            
            # Get the written content
            written_content = ''.join(call.args[0] for call in mock_file().write.call_args_list)
            
            self.assertIn('# Iranian Public Archives', written_content)
            self.assertIn('Kayhan Newspaper', written_content)
            self.assertIn('Arman Magazine', written_content)
            self.assertIn('2023/12/01', written_content)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_generate_readme_invalid_language(self):
        """Test README generation with invalid language."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            with self.assertRaises(ValueError) as context:
                self.generator.generate_main_readme('invalid', self.sample_archives, tmp_path)
            
            self.assertIn('Unsupported language: invalid', str(context.exception))
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    @patch('builtins.open', new_callable=mock_open, read_data='# Existing README\n\nSome content\n')
    @patch('os.path.exists', return_value=True)
    def test_update_readme_section_existing_file(self, mock_exists, mock_file):
        """Test updating existing README file with new section."""
        readme_path = 'README.md'
        
        self.generator.update_readme_section(readme_path, self.sample_archive, 'en')
        
        # Verify file was read and written
        mock_file.assert_any_call(readme_path, 'r', encoding='utf-8')
        mock_file.assert_any_call(readme_path, 'w', encoding='utf-8')
        
        # Get the written content
        write_calls = [call for call in mock_file().write.call_args_list]
        written_content = ''.join(call.args[0] for call in write_calls)
        
        self.assertIn('# Existing README', written_content)
        self.assertIn('### Kayhan Newspaper', written_content)
        self.assertIn('Available years:', written_content)
    
    @patch('readme_generator.ReadmeGenerator.generate_main_readme')
    @patch('os.path.exists', return_value=False)
    def test_update_readme_section_new_file(self, mock_exists, mock_generate):
        """Test updating README when file doesn't exist."""
        readme_path = 'README.md'
        
        self.generator.update_readme_section(readme_path, self.sample_archive, 'en')
        
        # Should call generate_main_readme instead
        mock_generate.assert_called_once_with('en', [self.sample_archive], readme_path)


class TestPublicationReadmeGenerator(unittest.TestCase):
    """Test cases for publication-specific README generation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.generator = ReadmeGenerator()
        self.sample_archive = {
            'title_fa': 'روزنامه کیهان',
            'folder': 'kayhan-newspaper',
            'category': 'old-newspaper',
            'description': 'Historical Iranian newspaper founded in 1943',
            'years': {
                '2020': ['issue1.pdf', 'issue2.pdf', 'issue3.pdf'],
                '2021': ['issue4.pdf', 'issue5.pdf']
            }
        }
        
        self.english_only_archive = {
            'folder': 'tehran-times',
            'category': 'newspaper',
            'description': 'English language Iranian newspaper',
            'years': {
                '2023': ['vol1.pdf', 'vol2.pdf']
            }
        }
        
        self.sample_errors = [
            'Failed to download issue1.pdf: Network timeout',
            'Failed to download issue3.pdf: File not found (404)'
        ]
    
    def test_generate_publication_readme_bilingual(self):
        """Test bilingual publication README generation."""
        content = self.generator.generate_publication_readme(self.sample_archive)
        
        # Check bilingual elements
        self.assertIn('روزنامه کیهان / Kayhan Newspaper', content)
        self.assertIn('شماره‌های موجود / Available Issues', content)
        self.assertIn('Historical Iranian newspaper founded in 1943', content)
        
        # Check years section
        self.assertIn('**2020**: 3 issues', content)
        self.assertIn('**2021**: 2 issues', content)
        self.assertIn('[View folder](2020/)', content)
        
        # Check language toggle
        self.assertIn('English](README.en.md)', content)
    
    def test_generate_publication_readme_english_only(self):
        """Test English-only publication README generation."""
        content = self.generator.generate_publication_readme(self.english_only_archive)
        
        # Check English elements
        self.assertIn('# Tehran Times', content)
        self.assertIn('## Available Issues', content)
        self.assertIn('English language Iranian newspaper', content)
        
        # Should not have Persian elements
        self.assertNotIn('شماره‌های موجود', content)
        
        # Check years section
        self.assertIn('**2023**: 2 issues', content)
    
    def test_generate_publication_readme_with_errors(self):
        """Test publication README generation with error reporting."""
        content = self.generator.generate_publication_readme(
            self.sample_archive, 
            self.sample_errors
        )
        
        # Check error section
        self.assertIn('خطاهای دانلود / Download Errors', content)
        self.assertIn('Failed to download issue1.pdf: Network timeout', content)
        self.assertIn('Failed to download issue3.pdf: File not found (404)', content)
    
    def test_generate_publication_readme_no_years(self):
        """Test publication README generation with no years data."""
        archive_no_years = {
            'folder': 'new-publication',
            'description': 'A new publication with no issues yet'
        }
        
        content = self.generator.generate_publication_readme(archive_no_years)
        
        self.assertIn('No issues available yet.', content)
    
    @patch('builtins.open', new_callable=mock_open)
    def test_generate_publication_readme_with_output_path(self, mock_file):
        """Test publication README generation with file output."""
        output_path = 'test_publication_readme.md'
        
        content = self.generator.generate_publication_readme(
            self.sample_archive, 
            output_path=output_path
        )
        
        # Verify file was written
        mock_file.assert_called_once_with(output_path, 'w', encoding='utf-8')
        
        # Verify content was written
        written_content = ''.join(call.args[0] for call in mock_file().write.call_args_list)
        self.assertIn('روزنامه کیهان / Kayhan Newspaper', written_content)
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('readme_generator.ReadmeGenerator.generate_publication_readme')
    @patch('os.path.exists', return_value=False)
    def test_update_publication_readme_new_file(self, mock_exists, mock_generate, mock_file):
        """Test updating publication README when file doesn't exist."""
        readme_path = 'publication/README.md'
        
        self.generator.update_publication_readme(readme_path, self.sample_archive, self.sample_errors)
        
        # Should call generate_publication_readme
        mock_generate.assert_called_once_with(self.sample_archive, self.sample_errors, readme_path)
    
    @patch('builtins.open', new_callable=mock_open, read_data='# Old README\n\nOld content\n')
    @patch('os.path.exists', return_value=True)
    def test_update_publication_readme_existing_file(self, mock_exists, mock_file):
        """Test updating existing publication README file."""
        readme_path = 'publication/README.md'
        
        self.generator.update_publication_readme(readme_path, self.sample_archive)
        
        # Verify file was read and written
        mock_file.assert_any_call(readme_path, 'r', encoding='utf-8')
        mock_file.assert_any_call(readme_path, 'w', encoding='utf-8')
        
        # Get the written content
        write_calls = [call for call in mock_file().write.call_args_list]
        written_content = ''.join(call.args[0] for call in write_calls)
        
        # Should contain new content, not old content
        self.assertIn('روزنامه کیهان / Kayhan Newspaper', written_content)
        self.assertNotIn('Old content', written_content)
    
    def test_years_section_generation(self):
        """Test years section generation."""
        years_section = self.generator._generate_years_section(self.sample_archive)
        
        self.assertIn('**2020**: 3 issues', years_section)
        self.assertIn('**2021**: 2 issues', years_section)
        self.assertIn('[View folder](2020/)', years_section)
        self.assertIn('[View folder](2021/)', years_section)
    
    def test_error_section_generation_persian(self):
        """Test error section generation in Persian."""
        error_section = self.generator._generate_error_section(self.sample_errors, 'fa')
        
        self.assertIn('خطاهای دانلود / Download Errors', error_section)
        self.assertIn('خطاهای زیر در هنگام دانلود', error_section)
        self.assertIn('Failed to download issue1.pdf', error_section)
    
    def test_error_section_generation_english(self):
        """Test error section generation in English."""
        error_section = self.generator._generate_error_section(self.sample_errors, 'en')
        
        self.assertIn('## Download Errors', error_section)
        self.assertIn('The following errors occurred', error_section)
        self.assertIn('Failed to download issue1.pdf', error_section)
    
    def test_error_section_no_errors(self):
        """Test error section generation with no errors."""
        error_section = self.generator._generate_error_section(None, 'en')
        self.assertEqual(error_section, "")
        
        error_section = self.generator._generate_error_section([], 'fa')
        self.assertEqual(error_section, "")


if __name__ == '__main__':
    unittest.main()