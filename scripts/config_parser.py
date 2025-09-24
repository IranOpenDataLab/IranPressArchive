#!/usr/bin/env python3
"""
Configuration parser and validation for Iranian Archive Workflow.

This module handles parsing and validation of the urls.yml configuration file,
including folder name sanitization and data validation.
"""

import yaml
import re
import os
import html
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse

from error_handler import WorkflowLogger, ErrorCategory, create_workflow_logger

# Import crawler modules
try:
    from directory_crawler import DirectoryCrawler, CrawlConfig
    from url_pattern_detector import URLPatternDetector, URLType
    CRAWLER_AVAILABLE = True
except ImportError:
    CRAWLER_AVAILABLE = False


@dataclass
class Archive:
    """Data class representing an archive configuration."""
    title_fa: str
    folder: str
    category: str
    description: str
    years: Dict[str, List[str]]


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class ConfigParser:
    """Parser and validator for urls.yml configuration file."""
    
    VALID_CATEGORIES = {'old-newspaper', 'newspaper'}
    REQUIRED_FIELDS = {'title_fa', 'folder', 'category', 'description', 'years'}
    
    # Security constraints
    MAX_STRING_LENGTH = 1000
    MAX_DESCRIPTION_LENGTH = 5000
    MAX_URLS_PER_YEAR = 1000
    MAX_YEARS_PER_ARCHIVE = 100
    MAX_ARCHIVES = 100
    
    # Dangerous patterns to sanitize
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',                # JavaScript protocol
        r'data:',                     # Data protocol
        r'vbscript:',                 # VBScript protocol
        r'on\w+\s*=',                # Event handlers (onclick, onload, etc.)
        r'<iframe[^>]*>.*?</iframe>', # Iframe tags
        r'<object[^>]*>.*?</object>', # Object tags
        r'<embed[^>]*>.*?</embed>',   # Embed tags
    ]
    
    def __init__(self, config_path: str = 'urls.yml', logger: Optional[WorkflowLogger] = None):
        """Initialize the configuration parser.
        
        Args:
            config_path: Path to the urls.yml configuration file
            logger: Optional WorkflowLogger instance for error handling
        """
        self.config_path = config_path
        self.logger = logger or create_workflow_logger("config_parser")
    
    def parse_configuration(self) -> List[Archive]:
        """Parse and validate the urls.yml configuration file.
        
        Returns:
            List of Archive objects
            
        Raises:
            ConfigurationError: If configuration is invalid or file cannot be read
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                config_data = yaml.safe_load(file)
                
            self.logger.log_success(
                f"Successfully loaded configuration file",
                file_path=self.config_path
            )
            
        except FileNotFoundError as e:
            error = ConfigurationError(f"Configuration file not found: {self.config_path}")
            self.logger.log_error(error, ErrorCategory.CONFIGURATION, file_path=self.config_path)
            raise error
        except yaml.YAMLError as e:
            error = ConfigurationError(f"Invalid YAML syntax: {e}")
            self.logger.log_error(error, ErrorCategory.CONFIGURATION, file_path=self.config_path)
            raise error
        except Exception as e:
            error = ConfigurationError(f"Error reading configuration file: {e}")
            self.logger.log_error(error, ErrorCategory.CONFIGURATION, file_path=self.config_path)
            raise error
        
        if not isinstance(config_data, dict) or 'archives' not in config_data:
            error = ConfigurationError("Configuration must contain 'archives' key")
            self.logger.log_error(error, ErrorCategory.CONFIGURATION, file_path=self.config_path)
            raise error
        
        # Check overall limits
        if len(config_data['archives']) > self.MAX_ARCHIVES:
            error = ConfigurationError(f"Too many archives ({len(config_data['archives'])}), maximum allowed: {self.MAX_ARCHIVES}")
            self.logger.log_error(error, ErrorCategory.CONFIGURATION, file_path=self.config_path)
            raise error
        
        archives = []
        for i, archive_data in enumerate(config_data['archives']):
            try:
                archive = self.validate_archive_entry(archive_data, i)
                archives.append(archive)
                
                self.logger.log_success(
                    f"Validated archive entry: {archive.title_fa}",
                    context={"archive_index": i, "folder": archive.folder, "category": archive.category}
                )
                
            except ConfigurationError as e:
                error = ConfigurationError(f"Archive entry {i}: {e}")
                self.logger.log_error(
                    error, ErrorCategory.CONFIGURATION,
                    file_path=self.config_path,
                    context={"archive_index": i}
                )
                raise error
        
        self.logger.log_success(
            f"Successfully parsed {len(archives)} archive entries",
            file_path=self.config_path,
            context={"total_archives": len(archives)}
        )
        
        return archives
    
    def validate_archive_entry(self, archive_data: Dict[str, Any], index: int) -> Archive:
        """Validate a single archive entry with comprehensive security checks.
        
        Args:
            archive_data: Dictionary containing archive configuration
            index: Index of the archive entry for error reporting
            
        Returns:
            Archive object
            
        Raises:
            ConfigurationError: If archive entry is invalid
        """
        if not isinstance(archive_data, dict):
            raise ConfigurationError(f"Archive entry must be a dictionary")
        
        # Check required fields
        missing_fields = self.REQUIRED_FIELDS - set(archive_data.keys())
        if missing_fields:
            raise ConfigurationError(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Validate and sanitize title_fa
        title_fa = archive_data['title_fa']
        if not isinstance(title_fa, str) or not title_fa.strip():
            raise ConfigurationError("title_fa must be a non-empty string")
        sanitized_title = self._sanitize_string_input(title_fa, "title_fa")
        
        # Validate and sanitize folder
        folder = archive_data['folder']
        if not isinstance(folder, str) or not folder.strip():
            raise ConfigurationError("folder must be a non-empty string")
        
        # Validate category (no sanitization needed for enum)
        category = archive_data['category']
        if category not in self.VALID_CATEGORIES:
            raise ConfigurationError(f"category must be one of: {', '.join(self.VALID_CATEGORIES)}")
        
        # Validate and sanitize description
        description = archive_data['description']
        if not isinstance(description, str) or not description.strip():
            raise ConfigurationError("description must be a non-empty string")
        sanitized_description = self._sanitize_string_input(
            description, "description", self.MAX_DESCRIPTION_LENGTH
        )
        
        # Validate years structure
        years = archive_data['years']
        if not isinstance(years, dict):
            raise ConfigurationError("years must be a dictionary")
        
        # Check limits
        if len(years) > self.MAX_YEARS_PER_ARCHIVE:
            raise ConfigurationError(f"Too many years ({len(years)}), maximum allowed: {self.MAX_YEARS_PER_ARCHIVE}")
        
        validated_years = self._validate_years_structure(years)
        
        # Sanitize folder name (this includes additional filesystem-specific sanitization)
        sanitized_folder = self.sanitize_folder_name(folder)
        
        return Archive(
            title_fa=sanitized_title,
            folder=sanitized_folder,
            category=category,
            description=sanitized_description,
            years=validated_years
        )
    
    def _validate_years_structure(self, years: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate the years structure within an archive entry with security checks.
        
        Args:
            years: Dictionary mapping years to lists of URLs
            
        Returns:
            Validated years dictionary
            
        Raises:
            ConfigurationError: If years structure is invalid
        """
        validated_years = {}
        total_urls = 0
        
        for year, urls in years.items():
            # Validate year format
            if not self._is_valid_year(year):
                raise ConfigurationError(f"Invalid year format: {year}. Must be 4-digit year (YYYY)")
            
            # Validate URLs list
            if not isinstance(urls, list):
                raise ConfigurationError(f"URLs for year {year} must be a list")
            
            # Check URL count limits
            if len(urls) > self.MAX_URLS_PER_YEAR:
                raise ConfigurationError(f"Too many URLs in year {year} ({len(urls)}), maximum allowed: {self.MAX_URLS_PER_YEAR}")
            
            validated_urls = []
            for i, url in enumerate(urls):
                if not isinstance(url, str) or not url.strip():
                    raise ConfigurationError(f"URL {i+1} in year {year} must be a non-empty string")
                
                url_cleaned = url.strip()
                
                # Length check
                if len(url_cleaned) > self.MAX_STRING_LENGTH:
                    raise ConfigurationError(f"URL {i+1} in year {year} exceeds maximum length of {self.MAX_STRING_LENGTH} characters")
                
                # Basic URL format validation
                if not self._is_valid_url(url_cleaned):
                    raise ConfigurationError(f"Invalid URL format in year {year}: {url_cleaned}")
                
                # Security validation
                is_secure, security_error = self._validate_url_security(url_cleaned)
                if not is_secure:
                    raise ConfigurationError(f"URL security validation failed in year {year}: {security_error}")
                
                validated_urls.append(url_cleaned)
                total_urls += 1
            
            if validated_urls:  # Only include years with URLs
                validated_years[year] = validated_urls
        
        return validated_years
    
    def _is_valid_year(self, year: str) -> bool:
        """Check if year string is in valid YYYY format.
        
        Args:
            year: Year string to validate
            
        Returns:
            True if valid year format, False otherwise
        """
        return bool(re.match(r'^\d{4}$', year))
    
    def _is_valid_url(self, url: str) -> bool:
        """Basic URL validation.
        
        Args:
            url: URL string to validate
            
        Returns:
            True if URL appears valid, False otherwise
        """
        # Basic URL pattern matching
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        return bool(url_pattern.match(url))
    
    def _sanitize_string_input(self, input_str: str, field_name: str, max_length: int = None) -> str:
        """
        Sanitize string input to prevent injection attacks and ensure safety.
        
        Args:
            input_str: String to sanitize
            field_name: Name of the field for error reporting
            max_length: Maximum allowed length (uses MAX_STRING_LENGTH if None)
            
        Returns:
            Sanitized string
            
        Raises:
            ConfigurationError: If input is invalid after sanitization
        """
        if not isinstance(input_str, str):
            raise ConfigurationError(f"{field_name} must be a string")
        
        # Remove dangerous patterns
        sanitized = input_str
        for pattern in self.DANGEROUS_PATTERNS:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        # HTML escape to prevent HTML injection
        sanitized = html.escape(sanitized)
        
        # Remove control characters except newlines and tabs
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
        
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        # Check length
        max_len = max_length or self.MAX_STRING_LENGTH
        if len(sanitized) > max_len:
            raise ConfigurationError(f"{field_name} exceeds maximum length of {max_len} characters")
        
        # Ensure not empty after sanitization
        if not sanitized:
            raise ConfigurationError(f"{field_name} is empty after sanitization")
        
        return sanitized
    
    def _validate_url_security(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate URL for security issues.
        
        Args:
            url: URL to validate
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        try:
            # Basic format validation
            parsed = urlparse(url)
            
            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False, f"URL scheme '{parsed.scheme}' not allowed (only http/https)"
            
            # Check for dangerous patterns in URL
            url_lower = url.lower()
            dangerous_url_patterns = [
                'javascript:',
                'data:',
                'vbscript:',
                'file:',
                'ftp:',
                '<script',
                'onclick',
                'onload',
                'onerror',
            ]
            
            for pattern in dangerous_url_patterns:
                if pattern in url_lower:
                    return False, f"URL contains dangerous pattern: {pattern}"
            
            # Check for suspicious characters
            if re.search(r'[<>"\'\x00-\x1f\x7f]', url):
                return False, "URL contains suspicious characters"
            
            # Check hostname
            if not parsed.hostname:
                return False, "URL must have a valid hostname"
            
            # Check for private/local addresses
            hostname = parsed.hostname.lower()
            if hostname in ['localhost', '127.0.0.1', '0.0.0.0', '::1']:
                return False, f"Access to local address '{hostname}' not allowed"
            
            return True, None
            
        except Exception as e:
            return False, f"URL validation error: {e}"
    
    def sanitize_folder_name(self, folder_name: str) -> str:
        """Sanitize folder name for filesystem compatibility.
        
        Args:
            folder_name: Original folder name
            
        Returns:
            Sanitized folder name safe for filesystem use
        """
        # First apply general string sanitization
        try:
            sanitized = self._sanitize_string_input(folder_name, "folder name", 200)
        except ConfigurationError:
            # If general sanitization fails, try more aggressive cleaning
            sanitized = folder_name
        
        # Remove or replace filesystem-invalid characters
        # Keep alphanumeric, hyphens, underscores, and spaces
        sanitized = re.sub(r'[^\w\s-]', '', sanitized)
        
        # Replace spaces with hyphens
        sanitized = re.sub(r'\s+', '-', sanitized)
        
        # Remove multiple consecutive hyphens
        sanitized = re.sub(r'-+', '-', sanitized)
        
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip('-')
        
        # Ensure it's not empty
        if not sanitized:
            raise ConfigurationError(f"Folder name '{folder_name}' results in empty string after sanitization")
        
        # Limit length to reasonable filesystem limits
        if len(sanitized) > 100:
            sanitized = sanitized[:100].rstrip('-')
        
        return sanitized
    
    def update_configuration(self, archives: List[Archive]) -> None:
        """Update the urls.yml file with modified archive configurations.
        
        Args:
            archives: List of Archive objects to write back to file
            
        Raises:
            ConfigurationError: If file cannot be written
        """
        config_data = {
            'archives': [
                {
                    'title_fa': archive.title_fa,
                    'folder': archive.folder,
                    'category': archive.category,
                    'description': archive.description,
                    'years': archive.years
                }
                for archive in archives
            ]
        }
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as file:
                yaml.dump(config_data, file, default_flow_style=False, 
                         allow_unicode=True, sort_keys=False)
                         
            self.logger.log_success(
                f"Successfully updated configuration file",
                file_path=self.config_path,
                context={"total_archives": len(archives)}
            )
            
        except Exception as e:
            error = ConfigurationError(f"Error writing configuration file: {e}")
            self.logger.log_error(error, ErrorCategory.FILESYSTEM, file_path=self.config_path)
            raise error
    
    def remove_successful_urls(self, archive: Archive, successful_urls: List[str]) -> Archive:
        """Remove successfully downloaded URLs from an archive configuration.
        
        Args:
            archive: Archive object to modify
            successful_urls: List of URLs that were successfully downloaded
            
        Returns:
            Modified Archive object with successful URLs removed
        """
        updated_years = {}
        
        for year, urls in archive.years.items():
            remaining_urls = [url for url in urls if url not in successful_urls]
            if remaining_urls:  # Only keep years that still have URLs
                updated_years[year] = remaining_urls
        
        return Archive(
            title_fa=archive.title_fa,
            folder=archive.folder,
            category=archive.category,
            description=archive.description,
            years=updated_years
        )
    
    def expand_directory_urls(self, archive_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Expand directory URLs in archive configuration by crawling them.
        
        Args:
            archive_data: Archive configuration dictionary
            
        Returns:
            Archive configuration with expanded URLs
        """
        if not CRAWLER_AVAILABLE:
            self.logger.log_error("Directory crawling requested but crawler modules not available", ErrorCategory.CONFIGURATION)
            return archive_data
        
        years_data = archive_data.get('years', {})
        expanded_years = {}
        
        for year, urls in years_data.items():
            if isinstance(urls, list) and len(urls) == 1:
                url = urls[0]
                
                if self._should_crawl_url(url):
                    self.logger.log_success(f"Detected directory URL for crawling: {url}")
                    
                    # Crawl the directory
                    crawled_urls = self._crawl_directory_url(url, archive_data)
                    
                    if crawled_urls:
                        # Group crawled URLs by year if possible
                        year_grouped_urls = self._group_urls_by_year(crawled_urls)
                        
                        # Merge with expanded years
                        for detected_year, detected_urls in year_grouped_urls.items():
                            if detected_year in expanded_years:
                                expanded_years[detected_year].extend(detected_urls)
                            else:
                                expanded_years[detected_year] = detected_urls
                    else:
                        # No files found, keep original URL
                        expanded_years[year] = urls
                else:
                    # Not a directory URL, keep original
                    expanded_years[year] = urls
            else:
                # Multiple URLs or not a list, keep original
                expanded_years[year] = urls
        
        # Update archive data
        updated_archive_data = archive_data.copy()
        updated_archive_data['years'] = expanded_years
        
        return updated_archive_data
    
    def _should_crawl_url(self, url: str) -> bool:
        """
        Check if a URL should be crawled as a directory.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL should be crawled
        """
        if not CRAWLER_AVAILABLE:
            return False
        
        try:
            detector = URLPatternDetector()
            analysis = detector.analyze_url(url, check_content=False)
            
            return analysis.url_type in [
                URLType.DIRECTORY_LISTING,
                URLType.ARCHIVE_ROOT,
                URLType.YEAR_DIRECTORY,
                URLType.MONTH_DIRECTORY
            ]
        except Exception as e:
            self.logger.log_error(f"Error analyzing URL {url}: {str(e)}", ErrorCategory.NETWORK)
            return False
    
    def _crawl_directory_url(self, url: str, archive_data: Dict[str, Any]) -> List[str]:
        """
        Crawl a directory URL to discover files.
        
        Args:
            url: Directory URL to crawl
            archive_data: Archive configuration for context
            
        Returns:
            List of discovered file URLs
        """
        try:
            # Analyze URL to get optimal crawl config
            detector = URLPatternDetector()
            analysis = detector.analyze_url(url, check_content=True)
            
            # Create crawl config
            crawl_settings = detector.suggest_crawl_config(analysis)
            config = CrawlConfig(
                max_depth=crawl_settings['max_depth'],
                max_files_per_directory=crawl_settings['max_files_per_directory'],
                max_total_files=min(crawl_settings['max_total_files'], self.MAX_URLS_PER_ARCHIVE),
                delay_between_requests=crawl_settings['delay_between_requests']
            )
            
            # Perform crawling
            crawler = DirectoryCrawler(config, self.logger)
            result = crawler.crawl_directory(url)
            
            if result.discovered_files:
                self.logger.log_success(
                    f"Successfully crawled directory: {url}",
                    context={
                        'files_found': result.total_files,
                        'processing_time': result.processing_time,
                        'crawl_depth': result.crawl_depth
                    }
                )
                
                # Log any errors
                if result.errors:
                    for error in result.errors[:3]:  # Log first 3 errors
                        self.logger.log_error(f"Crawl warning: {error}", ErrorCategory.NETWORK)
                
                return result.discovered_files
            else:
                self.logger.log_error(f"No files found when crawling directory: {url}", ErrorCategory.NETWORK)
                return []
        
        except Exception as e:
            self.logger.log_error(f"Failed to crawl directory {url}: {str(e)}", ErrorCategory.NETWORK)
            return []
    
    def _group_urls_by_year(self, urls: List[str]) -> Dict[str, List[str]]:
        """
        Group URLs by detected year patterns.
        
        Args:
            urls: List of URLs to group
            
        Returns:
            Dictionary mapping years to URL lists
        """
        year_groups = {}
        ungrouped_urls = []
        
        for url in urls:
            year = self._extract_year_from_url(url)
            if year:
                year_str = str(year)
                if year_str not in year_groups:
                    year_groups[year_str] = []
                year_groups[year_str].append(url)
            else:
                ungrouped_urls.append(url)
        
        # Add ungrouped URLs to the most recent year or create a default year
        if ungrouped_urls:
            if year_groups:
                # Add to the most recent year
                latest_year = max(year_groups.keys())
                year_groups[latest_year].extend(ungrouped_urls)
            else:
                # Create default year
                import datetime
                current_year = str(datetime.datetime.now().year)
                year_groups[current_year] = ungrouped_urls
        
        return year_groups
    
    def _extract_year_from_url(self, url: str) -> Optional[int]:
        """
        Extract year from URL path.
        
        Args:
            url: URL to analyze
            
        Returns:
            Detected year or None
        """
        # Persian/Jalali years (1300-1450)
        persian_year_match = re.search(r'1[3-4]\d{2}', url)
        if persian_year_match:
            year = int(persian_year_match.group())
            if 1300 <= year <= 1450:
                return year
        
        # Gregorian years (1900-2100)
        gregorian_year_match = re.search(r'(19|20|21)\d{2}', url)
        if gregorian_year_match:
            year = int(gregorian_year_match.group())
            if 1900 <= year <= 2100:
                return year
        
        return None


def main():
    """Main function for testing the configuration parser."""
    import sys
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'urls.yml'
    parser = ConfigParser(config_file)
    try:
        archives = parser.parse_configuration()
        print(f"Successfully parsed {len(archives)} archives:")
        for archive in archives:
            print(f"  - {archive.title_fa} ({archive.folder})")
            print(f"    Category: {archive.category}")
            print(f"    Description: {archive.description}")
            print(f"    Years: {list(archive.years.keys())}")
            total_urls = sum(len(urls) for urls in archive.years.values())
            print(f"    Total URLs: {total_urls}")
            print()
    except ConfigurationError as e:
        print(f"Configuration error: {e}")
        return 1
    return 0


if __name__ == '__main__':
    exit(main())