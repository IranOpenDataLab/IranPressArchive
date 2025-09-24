#!/usr/bin/env python3
"""
URL Pattern Detector for Iranian Archive Workflow

This module detects if a URL is a directory that should be crawled
versus a direct file URL. It handles various patterns commonly found
in Iranian archive websites.
"""

import re
import requests
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum


class URLType(Enum):
    """Types of URLs that can be detected."""
    DIRECT_FILE = "direct_file"
    DIRECTORY_LISTING = "directory_listing"
    ARCHIVE_ROOT = "archive_root"
    YEAR_DIRECTORY = "year_directory"
    MONTH_DIRECTORY = "month_directory"
    UNKNOWN = "unknown"


@dataclass
class URLAnalysis:
    """Analysis result for a URL."""
    url: str
    url_type: URLType
    confidence: float  # 0.0 to 1.0
    suggested_crawl_depth: int
    patterns_found: List[str]
    metadata: Dict[str, any]


class URLPatternDetector:
    """Detects URL patterns to determine crawling strategy."""
    
    def __init__(self):
        """Initialize the URL pattern detector."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Iranian Archive Pattern Detector 1.0'
        })
        
        # Define pattern rules
        self.file_patterns = [
            r'\.pdf$',
            r'\.docx?$',
            r'\.txt$',
            r'\.html?$',
            r'\.rtf$',
            r'\.odt$',
        ]
        
        self.directory_patterns = [
            r'/$',  # Ends with slash
            r'/index\.html?$',  # Index pages
            r'/default\.html?$',  # Default pages
        ]
        
        self.archive_patterns = [
            r'/neshat[-_]?\d{4}/?$',  # neshat-1377, neshat_1378
            r'/[a-zA-Z]+[-_]?\d{4}/?$',  # publication-year
            r'/\d{4}/?$',  # Just year
            r'/archive/?$',  # Archive directory
            r'/files/?$',  # Files directory
        ]
        
        self.year_patterns = [
            r'1[3-4]\d{2}',  # Persian years 1300-1499
            r'(19|20|21)\d{2}',  # Gregorian years 1900-2199
        ]
        
        self.month_patterns = [
            # Persian months
            r'(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)',
            # English months
            r'(january|february|march|april|may|june|july|august|september|october|november|december)',
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            # Month numbers
            r'(0?[1-9]|1[0-2])',
        ]
    
    def analyze_url(self, url: str, check_content: bool = True) -> URLAnalysis:
        """
        Analyze a URL to determine its type and crawling strategy.
        
        Args:
            url: The URL to analyze
            check_content: Whether to fetch and analyze content
            
        Returns:
            URLAnalysis with detected patterns and recommendations
        """
        patterns_found = []
        metadata = {}
        confidence = 0.0
        url_type = URLType.UNKNOWN
        suggested_depth = 3
        
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Check for direct file patterns
        for pattern in self.file_patterns:
            if re.search(pattern, path):
                patterns_found.append(f"file_pattern: {pattern}")
                url_type = URLType.DIRECT_FILE
                confidence = 0.9
                suggested_depth = 0
                break
        
        # If not a direct file, check directory patterns
        if url_type == URLType.UNKNOWN:
            # Check for directory indicators
            for pattern in self.directory_patterns:
                if re.search(pattern, path):
                    patterns_found.append(f"directory_pattern: {pattern}")
                    url_type = URLType.DIRECTORY_LISTING
                    confidence = 0.7
                    suggested_depth = 2
                    break
            
            # Check for archive patterns
            for pattern in self.archive_patterns:
                if re.search(pattern, path):
                    patterns_found.append(f"archive_pattern: {pattern}")
                    url_type = URLType.ARCHIVE_ROOT
                    confidence = 0.8
                    suggested_depth = 4
                    break
            
            # Check for year patterns
            year_matches = []
            for pattern in self.year_patterns:
                matches = re.findall(pattern, path)
                year_matches.extend(matches)
            
            if year_matches:
                patterns_found.append(f"year_pattern: {year_matches}")
                url_type = URLType.YEAR_DIRECTORY
                confidence = 0.6
                suggested_depth = 2
                metadata['years'] = year_matches
            
            # Check for month patterns
            month_matches = []
            for pattern in self.month_patterns:
                matches = re.findall(pattern, path, re.IGNORECASE)
                month_matches.extend(matches)
            
            if month_matches:
                patterns_found.append(f"month_pattern: {month_matches}")
                if url_type == URLType.UNKNOWN:
                    url_type = URLType.MONTH_DIRECTORY
                    confidence = 0.5
                    suggested_depth = 1
                metadata['months'] = month_matches
        
        # Content-based analysis
        if check_content and url_type in [URLType.UNKNOWN, URLType.DIRECTORY_LISTING]:
            content_analysis = self._analyze_content(url)
            if content_analysis:
                patterns_found.extend(content_analysis['patterns'])
                if content_analysis['type'] != URLType.UNKNOWN:
                    url_type = content_analysis['type']
                    confidence = max(confidence, content_analysis['confidence'])
                metadata.update(content_analysis['metadata'])
        
        # Default fallback
        if url_type == URLType.UNKNOWN:
            # If URL doesn't end with a file extension, assume it's a directory
            if not re.search(r'\.[a-zA-Z0-9]{2,4}$', path):
                url_type = URLType.DIRECTORY_LISTING
                confidence = 0.3
                suggested_depth = 2
                patterns_found.append("fallback: no_file_extension")
        
        return URLAnalysis(
            url=url,
            url_type=url_type,
            confidence=confidence,
            suggested_crawl_depth=suggested_depth,
            patterns_found=patterns_found,
            metadata=metadata
        )
    
    def _analyze_content(self, url: str) -> Optional[Dict]:
        """Analyze URL content to determine type."""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            content = response.text.lower()
            
            patterns = []
            metadata = {}
            url_type = URLType.UNKNOWN
            confidence = 0.0
            
            # Check content type
            if 'text/html' in content_type:
                # HTML content - likely a directory listing
                patterns.append("content_type: text/html")
                
                # Look for directory listing indicators
                directory_indicators = [
                    'index of',
                    'directory listing',
                    'parent directory',
                    '[dir]',
                    'folder',
                    '<a href="',  # Links present
                ]
                
                indicator_count = 0
                for indicator in directory_indicators:
                    if indicator in content:
                        patterns.append(f"html_indicator: {indicator}")
                        indicator_count += 1
                
                if indicator_count >= 2:
                    url_type = URLType.DIRECTORY_LISTING
                    confidence = 0.7
                
                # Count links to files
                file_links = 0
                for pattern in self.file_patterns:
                    file_links += len(re.findall(pattern, content))
                
                if file_links > 0:
                    metadata['file_links_found'] = file_links
                    patterns.append(f"file_links: {file_links}")
                    if file_links > 5:
                        url_type = URLType.DIRECTORY_LISTING
                        confidence = 0.8
                
                # Look for year/date patterns in content
                year_links = len(re.findall(r'href="[^"]*1[3-4]\d{2}[^"]*"', content))
                if year_links > 0:
                    metadata['year_links'] = year_links
                    patterns.append(f"year_links: {year_links}")
                    url_type = URLType.ARCHIVE_ROOT
                    confidence = 0.8
            
            elif 'application/json' in content_type:
                # JSON content - API directory listing
                patterns.append("content_type: application/json")
                url_type = URLType.DIRECTORY_LISTING
                confidence = 0.9
                
                try:
                    import json
                    json_data = json.loads(response.text)
                    if isinstance(json_data, list) or 'files' in json_data or 'items' in json_data:
                        patterns.append("json_structure: directory_listing")
                        confidence = 0.95
                except:
                    pass
            
            elif 'application/pdf' in content_type:
                # Direct PDF file
                patterns.append("content_type: application/pdf")
                url_type = URLType.DIRECT_FILE
                confidence = 1.0
            
            return {
                'type': url_type,
                'confidence': confidence,
                'patterns': patterns,
                'metadata': metadata
            }
        
        except Exception as e:
            # Content analysis failed, return None
            return None
    
    def suggest_crawl_config(self, analysis: URLAnalysis) -> Dict[str, any]:
        """
        Suggest crawling configuration based on URL analysis.
        
        Args:
            analysis: URL analysis result
            
        Returns:
            Dictionary with suggested crawl configuration
        """
        config = {
            'max_depth': analysis.suggested_crawl_depth,
            'max_files_per_directory': 1000,
            'max_total_files': 10000,
            'delay_between_requests': 1.0,
        }
        
        # Adjust based on URL type
        if analysis.url_type == URLType.DIRECT_FILE:
            config.update({
                'max_depth': 0,
                'max_files_per_directory': 1,
                'max_total_files': 1,
            })
        
        elif analysis.url_type == URLType.ARCHIVE_ROOT:
            config.update({
                'max_depth': 5,
                'max_files_per_directory': 2000,
                'max_total_files': 50000,
                'delay_between_requests': 0.5,
            })
        
        elif analysis.url_type == URLType.YEAR_DIRECTORY:
            config.update({
                'max_depth': 3,
                'max_files_per_directory': 500,
                'max_total_files': 5000,
            })
        
        elif analysis.url_type == URLType.MONTH_DIRECTORY:
            config.update({
                'max_depth': 2,
                'max_files_per_directory': 100,
                'max_total_files': 1000,
            })
        
        # Adjust based on confidence
        if analysis.confidence < 0.5:
            # Low confidence - be more conservative
            config['max_depth'] = min(config['max_depth'], 2)
            config['max_total_files'] = min(config['max_total_files'], 1000)
            config['delay_between_requests'] = max(config['delay_between_requests'], 1.0)
        
        return config
    
    def batch_analyze_urls(self, urls: List[str], check_content: bool = False) -> List[URLAnalysis]:
        """
        Analyze multiple URLs in batch.
        
        Args:
            urls: List of URLs to analyze
            check_content: Whether to check content for each URL
            
        Returns:
            List of URLAnalysis results
        """
        results = []
        
        for url in urls:
            try:
                analysis = self.analyze_url(url, check_content)
                results.append(analysis)
            except Exception as e:
                # Create error analysis
                error_analysis = URLAnalysis(
                    url=url,
                    url_type=URLType.UNKNOWN,
                    confidence=0.0,
                    suggested_crawl_depth=1,
                    patterns_found=[f"error: {str(e)}"],
                    metadata={'error': str(e)}
                )
                results.append(error_analysis)
        
        return results


def detect_url_pattern(url: str, check_content: bool = True) -> URLAnalysis:
    """
    Convenience function to detect URL pattern.
    
    Args:
        url: URL to analyze
        check_content: Whether to check content
        
    Returns:
        URLAnalysis result
    """
    detector = URLPatternDetector()
    return detector.analyze_url(url, check_content)


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Detect URL patterns for crawling')
    parser.add_argument('urls', nargs='+', help='URLs to analyze')
    parser.add_argument('--check-content', action='store_true', help='Check URL content')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    detector = URLPatternDetector()
    
    for url in args.urls:
        print(f"\n🔍 Analyzing: {url}")
        
        analysis = detector.analyze_url(url, args.check_content)
        
        print(f"   Type: {analysis.url_type.value}")
        print(f"   Confidence: {analysis.confidence:.2f}")
        print(f"   Suggested depth: {analysis.suggested_crawl_depth}")
        
        if analysis.patterns_found:
            print(f"   Patterns found:")
            for pattern in analysis.patterns_found:
                print(f"     - {pattern}")
        
        if analysis.metadata:
            print(f"   Metadata:")
            for key, value in analysis.metadata.items():
                print(f"     {key}: {value}")
        
        if args.verbose:
            config = detector.suggest_crawl_config(analysis)
            print(f"   Suggested config:")
            for key, value in config.items():
                print(f"     {key}: {value}")


if __name__ == '__main__':
    main()