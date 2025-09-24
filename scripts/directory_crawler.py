#!/usr/bin/env python3
"""
Directory Crawler for Iranian Archive Workflow

This module crawls directory-like URLs to discover downloadable files
following a hierarchical structure like:
example.com/neshat-1377/1.pdf, 2.pdf/1378/1.pdf, x.pdf, y.pdf/2/...

Features:
- Automatic directory structure discovery
- Pattern-based file detection
- Recursive crawling with depth limits
- Support for various archive structures
- Integration with existing workflow
"""

import re
import time
import requests
from urllib.parse import urljoin, urlparse, unquote
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import logging
from bs4 import BeautifulSoup

from error_handler import ErrorHandler


@dataclass
class CrawlResult:
    """Result of directory crawling operation."""
    base_url: str
    discovered_files: List[str]
    discovered_directories: List[str]
    total_files: int
    crawl_depth: int
    errors: List[str]
    processing_time: float


@dataclass
class CrawlConfig:
    """Configuration for directory crawling."""
    max_depth: int = 5
    max_files_per_directory: int = 1000
    max_total_files: int = 10000
    timeout: int = 30
    delay_between_requests: float = 1.0
    follow_redirects: bool = True
    allowed_extensions: Set[str] = None
    blocked_patterns: Set[str] = None
    user_agent: str = "Iranian Archive Crawler 1.0"
    
    def __post_init__(self):
        if self.allowed_extensions is None:
            self.allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.html'}
        if self.blocked_patterns is None:
            self.blocked_patterns = {'admin', 'login', 'auth', 'private', 'secure'}


class DirectoryCrawler:
    """Crawls directory-like URLs to discover downloadable files."""
    
    def __init__(self, config: CrawlConfig = None, error_handler: ErrorHandler = None):
        """Initialize the directory crawler."""
        self.config = config or CrawlConfig()
        self.error_handler = error_handler or ErrorHandler()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        # Tracking
        self.visited_urls: Set[str] = set()
        self.discovered_files: List[str] = []
        self.discovered_directories: List[str] = []
        self.errors: List[str] = []
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def crawl_directory(self, base_url: str, max_depth: int = None) -> CrawlResult:
        """
        Crawl a directory URL to discover all downloadable files.
        
        Args:
            base_url: The base URL to start crawling from
            max_depth: Maximum depth to crawl (overrides config)
            
        Returns:
            CrawlResult with discovered files and metadata
        """
        start_time = time.time()
        
        # Reset state
        self.visited_urls.clear()
        self.discovered_files.clear()
        self.discovered_directories.clear()
        self.errors.clear()
        
        # Use provided max_depth or config default
        crawl_depth = max_depth or self.config.max_depth
        
        self.logger.info(f"Starting directory crawl: {base_url}")
        self.logger.info(f"Max depth: {crawl_depth}, Max files: {self.config.max_total_files}")
        
        try:
            # Start recursive crawling
            self._crawl_recursive(base_url, 0, crawl_depth)
            
        except Exception as e:
            error_msg = f"Critical crawling error: {str(e)}"
            self.errors.append(error_msg)
            self.error_handler.log_error(error_msg, 'crawler')
        
        processing_time = time.time() - start_time
        
        # Create result
        result = CrawlResult(
            base_url=base_url,
            discovered_files=self.discovered_files.copy(),
            discovered_directories=self.discovered_directories.copy(),
            total_files=len(self.discovered_files),
            crawl_depth=crawl_depth,
            errors=self.errors.copy(),
            processing_time=processing_time
        )
        
        self.logger.info(f"Crawl completed: {result.total_files} files, {len(result.discovered_directories)} directories")
        return result
    
    def _crawl_recursive(self, url: str, current_depth: int, max_depth: int) -> None:
        """Recursively crawl directories."""
        # Check limits
        if current_depth >= max_depth:
            return
        
        if len(self.discovered_files) >= self.config.max_total_files:
            self.logger.warning(f"Reached maximum file limit: {self.config.max_total_files}")
            return
        
        if url in self.visited_urls:
            return
        
        # Check for blocked patterns
        if self._is_blocked_url(url):
            self.logger.debug(f"Skipping blocked URL: {url}")
            return
        
        self.visited_urls.add(url)
        
        try:
            # Add delay between requests
            if self.config.delay_between_requests > 0:
                time.sleep(self.config.delay_between_requests)
            
            # Fetch the page
            response = self.session.get(
                url, 
                timeout=self.config.timeout,
                allow_redirects=self.config.follow_redirects
            )
            response.raise_for_status()
            
            # Parse content
            content_type = response.headers.get('content-type', '').lower()
            
            if 'text/html' in content_type:
                # Parse HTML directory listing
                self._parse_html_directory(url, response.text, current_depth, max_depth)
            elif 'application/json' in content_type:
                # Parse JSON directory listing
                self._parse_json_directory(url, response.json(), current_depth, max_depth)
            else:
                # Check if it's a direct file
                if self._is_downloadable_file(url):
                    self.discovered_files.append(url)
                    self.logger.debug(f"Found direct file: {url}")
        
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to crawl {url}: {str(e)}"
            self.errors.append(error_msg)
            self.logger.warning(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error crawling {url}: {str(e)}"
            self.errors.append(error_msg)
            self.logger.error(error_msg)
    
    def _parse_html_directory(self, base_url: str, html_content: str, current_depth: int, max_depth: int) -> None:
        """Parse HTML directory listing to find files and subdirectories."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all links
            links = soup.find_all('a', href=True)
            
            files_in_directory = 0
            
            for link in links:
                if files_in_directory >= self.config.max_files_per_directory:
                    self.logger.warning(f"Reached max files per directory limit in {base_url}")
                    break
                
                href = link.get('href')
                if not href or href.startswith('#') or href.startswith('mailto:'):
                    continue
                
                # Resolve relative URLs
                full_url = urljoin(base_url, href)
                
                # Skip parent directory links
                if href in ['..', '../', './']:
                    continue
                
                # Check if it's a file or directory
                if self._is_downloadable_file(full_url):
                    if full_url not in self.discovered_files:
                        self.discovered_files.append(full_url)
                        files_in_directory += 1
                        self.logger.debug(f"Found file: {full_url}")
                
                elif self._looks_like_directory(href, link.text):
                    if full_url not in self.discovered_directories:
                        self.discovered_directories.append(full_url)
                        self.logger.debug(f"Found directory: {full_url}")
                        
                        # Recursively crawl subdirectory
                        self._crawl_recursive(full_url, current_depth + 1, max_depth)
        
        except Exception as e:
            error_msg = f"Error parsing HTML directory {base_url}: {str(e)}"
            self.errors.append(error_msg)
            self.logger.error(error_msg)
    
    def _parse_json_directory(self, base_url: str, json_data: dict, current_depth: int, max_depth: int) -> None:
        """Parse JSON directory listing (for APIs that return JSON)."""
        try:
            # Handle different JSON structures
            items = []
            
            if 'files' in json_data:
                items = json_data['files']
            elif 'items' in json_data:
                items = json_data['items']
            elif 'contents' in json_data:
                items = json_data['contents']
            elif isinstance(json_data, list):
                items = json_data
            
            for item in items:
                if isinstance(item, str):
                    # Simple string list
                    full_url = urljoin(base_url, item)
                    if self._is_downloadable_file(full_url):
                        self.discovered_files.append(full_url)
                
                elif isinstance(item, dict):
                    # Object with metadata
                    name = item.get('name') or item.get('filename') or item.get('path')
                    if not name:
                        continue
                    
                    full_url = urljoin(base_url, name)
                    item_type = item.get('type', '').lower()
                    
                    if item_type == 'file' or self._is_downloadable_file(full_url):
                        self.discovered_files.append(full_url)
                    elif item_type == 'directory' or item_type == 'folder':
                        self.discovered_directories.append(full_url)
                        self._crawl_recursive(full_url, current_depth + 1, max_depth)
        
        except Exception as e:
            error_msg = f"Error parsing JSON directory {base_url}: {str(e)}"
            self.errors.append(error_msg)
            self.logger.error(error_msg)
    
    def _is_downloadable_file(self, url: str) -> bool:
        """Check if URL points to a downloadable file."""
        parsed = urlparse(url)
        path = unquote(parsed.path).lower()
        query = unquote(parsed.query).lower()
        
        # Check file extension in path
        for ext in self.config.allowed_extensions:
            if path.endswith(ext):
                return True
        
        # Check file extension in query parameters (for URLs like ?file=document.pdf)
        if 'file=' in query:
            for ext in self.config.allowed_extensions:
                if ext in query:
                    return True
        
        # Check for common file patterns in path
        file_patterns = [
            r'\.pdf$',
            r'\.docx?$',
            r'\.txt$',
            r'\.html?$',
            r'\.rtf$',
            r'\.odt$',
        ]
        
        for pattern in file_patterns:
            if re.search(pattern, path):
                return True
        
        # Check for file patterns in query parameters
        for pattern in file_patterns:
            if re.search(pattern, query):
                return True
        
        return False
    
    def _looks_like_directory(self, href: str, link_text: str) -> bool:
        """Check if a link looks like a directory."""
        # Ends with slash
        if href.endswith('/'):
            return True
        
        # No file extension
        if '.' not in href.split('/')[-1]:
            return True
        
        # Link text suggests directory
        directory_indicators = ['folder', 'dir', 'directory', '[DIR]', '📁']
        for indicator in directory_indicators:
            if indicator.lower() in link_text.lower():
                return True
        
        # Common directory patterns
        directory_patterns = [
            r'^\d{4}/?$',  # Year directories like "1377", "1378/"
            r'^[a-zA-Z]+-\d{4}/?$',  # Archive-year like "neshat-1377/"
            r'^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # Month names
            r'^(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)',  # Persian months
        ]
        
        for pattern in directory_patterns:
            if re.search(pattern, href, re.IGNORECASE):
                return True
        
        return False
    
    def _is_blocked_url(self, url: str) -> bool:
        """Check if URL should be blocked from crawling."""
        url_lower = url.lower()
        
        for pattern in self.config.blocked_patterns:
            if pattern in url_lower:
                return True
        
        return False
    
    def generate_urls_config(self, crawl_result: CrawlResult, archive_info: Dict[str, str]) -> Dict[str, any]:
        """
        Generate URLs configuration from crawl results.
        
        Args:
            crawl_result: Result from directory crawling
            archive_info: Archive metadata (title, folder, category, etc.)
            
        Returns:
            Dictionary in urls.yml format
        """
        # Group files by year if possible
        files_by_year = {}
        ungrouped_files = []
        
        for file_url in crawl_result.discovered_files:
            year = self._extract_year_from_url(file_url)
            if year:
                if year not in files_by_year:
                    files_by_year[year] = []
                files_by_year[year].append(file_url)
            else:
                ungrouped_files.append(file_url)
        
        # Create years dictionary
        years_dict = {}
        
        # Add grouped files
        for year, files in sorted(files_by_year.items()):
            years_dict[str(year)] = files
        
        # Add ungrouped files to a default year or current year
        if ungrouped_files:
            default_year = str(max(files_by_year.keys())) if files_by_year else "2024"
            if default_year not in years_dict:
                years_dict[default_year] = []
            years_dict[default_year].extend(ungrouped_files)
        
        # Create archive configuration
        archive_config = {
            'title_fa': archive_info.get('title_fa', 'آرشیو کراول شده'),
            'title_en': archive_info.get('title_en', 'Crawled Archive'),
            'folder': archive_info.get('folder', 'crawled-archive'),
            'category': archive_info.get('category', 'newspaper'),
            'description': archive_info.get('description', f'Archive crawled from {crawl_result.base_url}'),
            'years': years_dict,
            'crawl_info': {
                'base_url': crawl_result.base_url,
                'crawl_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_files': crawl_result.total_files,
                'crawl_depth': crawl_result.crawl_depth,
                'processing_time': crawl_result.processing_time
            }
        }
        
        return archive_config
    
    def _extract_year_from_url(self, url: str) -> Optional[int]:
        """Extract year from URL path."""
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


def crawl_directory_url(url: str, config: CrawlConfig = None) -> CrawlResult:
    """
    Convenience function to crawl a directory URL.
    
    Args:
        url: The directory URL to crawl
        config: Crawling configuration
        
    Returns:
        CrawlResult with discovered files
    """
    crawler = DirectoryCrawler(config)
    return crawler.crawl_directory(url)


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Crawl directory URLs to discover files')
    parser.add_argument('url', help='Base URL to crawl')
    parser.add_argument('--max-depth', type=int, default=5, help='Maximum crawl depth')
    parser.add_argument('--max-files', type=int, default=10000, help='Maximum total files')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests (seconds)')
    parser.add_argument('--output', '-o', help='Output file for discovered URLs')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Create config
    config = CrawlConfig(
        max_depth=args.max_depth,
        max_total_files=args.max_files,
        delay_between_requests=args.delay
    )
    
    # Crawl directory
    print(f"🕷️  Crawling directory: {args.url}")
    result = crawl_directory_url(args.url, config)
    
    # Display results
    print(f"\n📊 Crawl Results:")
    print(f"   Base URL: {result.base_url}")
    print(f"   Files found: {result.total_files}")
    print(f"   Directories found: {len(result.discovered_directories)}")
    print(f"   Processing time: {result.processing_time:.2f}s")
    print(f"   Errors: {len(result.errors)}")
    
    if result.errors:
        print(f"\n❌ Errors:")
        for error in result.errors[:5]:  # Show first 5 errors
            print(f"   {error}")
        if len(result.errors) > 5:
            print(f"   ... and {len(result.errors) - 5} more errors")
    
    # Show sample files
    if result.discovered_files:
        print(f"\n📄 Sample files:")
        for file_url in result.discovered_files[:10]:  # Show first 10 files
            print(f"   {file_url}")
        if len(result.discovered_files) > 10:
            print(f"   ... and {len(result.discovered_files) - 10} more files")
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            for file_url in result.discovered_files:
                f.write(f"{file_url}\n")
        print(f"\n💾 URLs saved to: {args.output}")


if __name__ == '__main__':
    main()