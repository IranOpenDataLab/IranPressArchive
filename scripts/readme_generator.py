"""
README Generator Module

This module handles the generation and updating of bilingual README files
for the Iranian Archive Workflow system.
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime


class ReadmeGenerator:
    """Handles generation of main and publication-specific README files."""
    
    def __init__(self):
        self.persian_template = self._get_persian_template()
        self.english_template = self._get_english_template()
        self.publication_template = self._get_publication_template()
    
    def generate_main_readme(self, language: str, archives: List[Dict[str, Any]], 
                           output_path: str) -> None:
        """
        Generate main README file in specified language.
        
        Args:
            language: 'fa' for Persian, 'en' for English
            archives: List of archive configurations
            output_path: Path where README should be written
        """
        if language == 'fa':
            content = self._generate_persian_readme(archives)
        elif language == 'en':
            content = self._generate_english_readme(archives)
        else:
            raise ValueError(f"Unsupported language: {language}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def update_readme_section(self, readme_path: str, archive: Dict[str, Any], 
                            language: str) -> None:
        """
        Update existing README file with new archive section.
        
        Args:
            readme_path: Path to existing README file
            archive: Archive configuration to add
            language: 'fa' for Persian, 'en' for English
        """
        if not os.path.exists(readme_path):
            # If README doesn't exist, create it with just this archive
            self.generate_main_readme(language, [archive], readme_path)
            return
        
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Generate section for this archive
        section = self._generate_archive_section(archive, language)
        
        # Find insertion point (before the last line or at the end)
        lines = content.split('\n')
        
        # Insert the new section before any existing footer
        if lines and lines[-1].strip() == '':
            lines.insert(-1, section)
        else:
            lines.append('\n' + section)
        
        updated_content = '\n'.join(lines)
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(updated_content) 
   
    def _generate_persian_readme(self, archives: List[Dict[str, Any]]) -> str:
        """Generate Persian README content."""
        language_toggle = self._get_language_toggle('fa')
        archive_sections = []
        
        for archive in archives:
            section = self._generate_archive_section(archive, 'fa')
            archive_sections.append(section)
        
        content = self.persian_template.format(
            language_toggle=language_toggle,
            archive_sections='\n\n'.join(archive_sections),
            last_updated=datetime.now().strftime('%Y/%m/%d')
        )
        
        return content
    
    def _generate_english_readme(self, archives: List[Dict[str, Any]]) -> str:
        """Generate English README content."""
        language_toggle = self._get_language_toggle('en')
        archive_sections = []
        
        for archive in archives:
            section = self._generate_archive_section(archive, 'en')
            archive_sections.append(section)
        
        content = self.english_template.format(
            language_toggle=language_toggle,
            archive_sections='\n\n'.join(archive_sections),
            last_updated=datetime.now().strftime('%Y/%m/%d')
        )
        
        return content
    
    def _generate_archive_section(self, archive: Dict[str, Any], language: str) -> str:
        """Generate archive section with H3 header and year links."""
        if language == 'fa':
            title = archive.get('title_fa', archive['folder'])
            section_header = f"### {title}"
            years_text = "سال‌های موجود:"
        else:
            title = archive['folder'].replace('-', ' ').title()
            section_header = f"### {title}"
            years_text = "Available years:"
        
        # Generate year links
        year_links = []
        if 'years' in archive:
            for year in sorted(archive['years'].keys()):
                category = archive.get('category', 'old-newspaper')
                folder = archive['folder']
                link_path = f"{category}/{folder}/{year}"
                year_links.append(f"[{year}]({link_path})")
        
        if year_links:
            years_line = f"{years_text} {' | '.join(year_links)}"
        else:
            years_line = f"{years_text} Coming soon..."
        
        return f"{section_header}\n\n{years_line}"
    
    def _get_language_toggle(self, current_language: str) -> str:
        """Generate language toggle buttons."""
        if current_language == 'fa':
            return """[🇺🇸 English](README.en.md) | 🇮🇷 فارسی"""
        else:
            return """🇺🇸 English | [🇮🇷 فارسی](README.md)"""   
 
    def _get_persian_template(self) -> str:
        """Get Persian README template."""
        return """{language_toggle}

# آرشیو اسناد عمومی ایران

این مخزن شامل مجموعه‌ای از اسناد عمومی ایران شامل روزنامه‌ها، مجلات و نشریات است که به صورت خودکار جمع‌آوری و سازماندهی شده‌اند.

## محتویات آرشیو

{archive_sections}

## درباره این پروژه

این آرشیو با استفاده از GitHub Actions به صورت خودکار به‌روزرسانی می‌شود. هدف از این پروژه حفظ و دسترسی آسان به اسناد تاریخی و معاصر ایران است.

---
*آخرین به‌روزرسانی: {last_updated}*
"""
    
    def _get_english_template(self) -> str:
        """Get English README template."""
        return """{language_toggle}

# Iranian Public Archives

This repository contains a collection of Iranian public documents including newspapers, magazines, and bulletins that are automatically collected and organized.

## Archive Contents

{archive_sections}

## About This Project

This archive is automatically updated using GitHub Actions. The goal of this project is to preserve and provide easy access to Iranian historical and contemporary documents.

---
*Last updated: {last_updated}*
"""
    
    def generate_publication_readme(self, archive: Dict[str, Any], 
                                  errors: Optional[List[str]] = None,
                                  output_path: str = None) -> str:
        """
        Generate publication-specific README file.
        
        Args:
            archive: Archive configuration
            errors: List of error messages from failed downloads
            output_path: Path where README should be written (optional)
            
        Returns:
            Generated README content
        """
        # Determine language based on title presence
        has_persian_title = 'title_fa' in archive and archive['title_fa']
        
        if has_persian_title:
            content = self._generate_publication_readme_bilingual(archive, errors)
        else:
            content = self._generate_publication_readme_english(archive, errors)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        return content
    
    def update_publication_readme(self, readme_path: str, archive: Dict[str, Any],
                                errors: Optional[List[str]] = None) -> None:
        """
        Update existing publication README file.
        
        Args:
            readme_path: Path to existing publication README
            archive: Archive configuration
            errors: List of error messages from failed downloads
        """
        if not os.path.exists(readme_path):
            # Create new README if it doesn't exist
            self.generate_publication_readme(archive, errors, readme_path)
            return
        
        # Read existing content
        with open(readme_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()
        
        # Generate new content
        new_content = self.generate_publication_readme(archive, errors)
        
        # For publication READMEs, we replace the entire content
        # since it's generated based on current archive state
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    
    def _generate_publication_readme_bilingual(self, archive: Dict[str, Any],
                                             errors: Optional[List[str]] = None) -> str:
        """Generate bilingual publication README."""
        persian_toggle = self._get_language_toggle('fa')
        
        title_fa = archive.get('title_fa', archive['folder'])
        title_en = archive['folder'].replace('-', ' ').title()
        description = archive.get('description', 'No description available.')
        
        years_section = self._generate_years_section(archive)
        error_section = self._generate_error_section(errors, 'fa')
        
        content = f"""{persian_toggle}

# {title_fa} / {title_en}

{description}

## شماره‌های موجود / Available Issues

{years_section}

{error_section}

---
*تولید شده به صورت خودکار توسط سیستم آرشیو ایران / Generated automatically by Iranian Archive Workflow*
"""
        return content
    
    def _generate_publication_readme_english(self, archive: Dict[str, Any],
                                           errors: Optional[List[str]] = None) -> str:
        """Generate English-only publication README."""
        english_toggle = self._get_language_toggle('en')
        
        title = archive['folder'].replace('-', ' ').title()
        description = archive.get('description', 'No description available.')
        
        years_section = self._generate_years_section(archive)
        error_section = self._generate_error_section(errors, 'en')
        
        content = f"""{english_toggle}

# {title}

{description}

## Available Issues

{years_section}

{error_section}

---
*Generated automatically by Iranian Archive Workflow*
"""
        return content
    
    def _generate_years_section(self, archive: Dict[str, Any]) -> str:
        """Generate years section for publication README."""
        if 'years' not in archive or not archive['years']:
            return "No issues available yet."
        
        years_info = []
        for year in sorted(archive['years'].keys()):
            issue_count = len(archive['years'][year])
            years_info.append(f"- **{year}**: {issue_count} issues ([View folder]({year}/))")
        
        return '\n'.join(years_info)
    
    def _generate_error_section(self, errors: Optional[List[str]], language: str) -> str:
        """Generate error section for publication README."""
        if not errors:
            return ""
        
        if language == 'fa':
            header = "## خطاهای دانلود / Download Errors"
            note = "خطاهای زیر در هنگام دانلود فایل‌ها رخ داده است:"
        else:
            header = "## Download Errors"
            note = "The following errors occurred during file downloads:"
        
        error_list = '\n'.join(f"- {error}" for error in errors)
        
        return f"""
{header}

{note}

{error_list}
"""
    
    def _get_publication_template(self) -> str:
        """Get publication-specific README template."""
        return """{language_toggle}

# {title}

{description}

## Available Issues

{years_section}

{error_section}

---
*Generated automatically by Iranian Archive Workflow*
"""