"""
File download and management system for Iranian Archive Workflow.

This module provides functionality for:
- Downloading PDF files with error handling and retries
- Creating directory structures
- Managing sequential file numbering
- Checking file existence to prevent duplicates
"""

import os
import time
import requests
from pathlib import Path
from typing import Optional, Tuple, Set
from urllib.parse import urlparse, urljoin
import logging
import mimetypes
import re

from error_handler import (
    WorkflowLogger, RetryHandler, ErrorCategory, 
    create_workflow_logger, create_retry_handler
)

class FileManager:
    """Handles file downloads and directory management for archive workflow."""
    
    # Security configuration
    ALLOWED_SCHEMES = {'http', 'https'}
    ALLOWED_CONTENT_TYPES = {
        'application/pdf',
        'application/x-pdf',
        'application/acrobat',
        'applications/vnd.pdf',
        'text/pdf',
        'text/x-pdf'
    }
    BLOCKED_DOMAINS = {
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        '::1'
    }
    BLOCKED_IP_RANGES = [
        '10.0.0.0/8',      # Private network
        '172.16.0.0/12',   # Private network
        '192.168.0.0/16',  # Private network
        '169.254.0.0/16',  # Link-local
        '224.0.0.0/4',     # Multicast
        '240.0.0.0/4'      # Reserved
    ]
    
    def __init__(self, max_file_size_mb: int = 100, max_retries: int = 3, timeout: int = 300,
                 logger: Optional[WorkflowLogger] = None, max_redirects: int = 5):
        """
        Initialize FileManager with configuration.
        
        Args:
            max_file_size_mb: Maximum file size in MB
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
            logger: Optional WorkflowLogger instance for error handling
            max_redirects: Maximum number of redirects to follow
        """
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.logger = logger or create_workflow_logger("file_manager")
        self.retry_handler = create_retry_handler(max_retries=max_retries)
        
    def create_directory_structure(self, category: str, folder: str, year: str) -> Path:
        """
        Create nested directory structure for archive organization.
        
        Args:
            category: Archive category (old-newspaper or newspaper)
            folder: Publication folder name
            year: Year folder (YYYY format)
            
        Returns:
            Path object for the created directory
            
        Raises:
            OSError: If directory creation fails
        """
        try:
            # Sanitize folder name for filesystem compatibility
            sanitized_folder = self._sanitize_folder_name(folder)
            
            # Create directory path: {category}/{folder}/{year}
            dir_path = Path(category) / sanitized_folder / year
            dir_path.mkdir(parents=True, exist_ok=True)
            
            self.logger.log_success(
                f"Created directory structure: {dir_path}",
                context={"category": category, "folder": folder, "year": year}
            )
            return dir_path
            
        except OSError as e:
            self.logger.log_error(
                e, ErrorCategory.FILESYSTEM,
                context={"category": category, "folder": folder, "year": year}
            )
            raise
    
    def file_exists(self, file_path: Path) -> bool:
        """
        Check if file already exists to prevent duplicate downloads.
        
        Args:
            file_path: Path to check for existence
            
        Returns:
            True if file exists, False otherwise
        """
        exists = file_path.exists() and file_path.is_file()
        if exists:
            self.logger.log_success(
                f"File already exists, skipping: {file_path}",
                file_path=str(file_path)
            )
        return exists
    
    def get_next_file_number(self, directory: Path) -> int:
        """
        Determine the next sequential file number in directory.
        
        Args:
            directory: Directory to scan for existing files
            
        Returns:
            Next available file number (starting from 1)
        """
        if not directory.exists():
            return 1
            
        # Find all PDF files with numeric names
        existing_numbers = []
        for file_path in directory.glob("*.pdf"):
            try:
                # Extract number from filename (e.g., "5.pdf" -> 5)
                number = int(file_path.stem)
                existing_numbers.append(number)
            except ValueError:
                # Skip files with non-numeric names
                continue
        
        # Return next sequential number
        next_number = max(existing_numbers, default=0) + 1
        self.logger.logger.debug(f"Next file number for {directory}: {next_number}")
        return next_number
    
    def download_file(self, url: str, target_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Download PDF file with comprehensive security validation and error handling.
        
        Args:
            url: URL to download from
            target_path: Local path to save the file
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        # Comprehensive URL security validation
        is_safe, safety_error = self._is_safe_url(url)
        if not is_safe:
            error = ValueError(f"URL security validation failed: {safety_error}")
            error_details = self.logger.log_error(
                error, ErrorCategory.VALIDATION,
                url=url, file_path=str(target_path)
            )
            return False, error_details.message
        
        # Check if file already exists
        if self.file_exists(target_path):
            return True, None
        
        # Ensure target directory exists
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            error_details = self.logger.log_error(
                e, ErrorCategory.FILESYSTEM,
                url=url, file_path=str(target_path)
            )
            return False, error_details.message
        
        # Use retry handler for download operation
        def _download_operation():
            return self._perform_download(url, target_path)
        
        success, result, error_details = self.retry_handler.execute_with_retry(
            _download_operation,
            error_categories=[ErrorCategory.NETWORK],
            logger=self.logger,
            context={"url": url, "target_path": str(target_path)}
        )
        
        if success:
            # Validate downloaded file is actually a PDF
            is_valid_pdf, pdf_error = self._validate_pdf_content(target_path)
            if not is_valid_pdf:
                # Remove invalid file
                target_path.unlink(missing_ok=True)
                error = ValueError(f"Downloaded file is not a valid PDF: {pdf_error}")
                error_details = self.logger.log_error(
                    error, ErrorCategory.VALIDATION,
                    url=url, file_path=str(target_path)
                )
                return False, error_details.message
            
            self.logger.log_success(
                f"Successfully downloaded and validated PDF file",
                url=url,
                file_path=str(target_path),
                context={"file_size_bytes": result}
            )
            return True, None
        else:
            return False, error_details.message if error_details else "Download failed"
    
    def _perform_download(self, url: str, target_path: Path) -> int:
        """
        Perform the actual file download operation with security validations.
        
        Args:
            url: URL to download from
            target_path: Local path to save the file
            
        Returns:
            File size in bytes
            
        Raises:
            Various exceptions for different error conditions
        """
        try:
            # Make request with timeout and limited redirects
            session = requests.Session()
            session.max_redirects = self.max_redirects
            
            response = session.get(url, timeout=self.timeout, stream=True, allow_redirects=True)
            response.raise_for_status()
            
            # Validate final URL after redirects
            final_url = response.url
            if final_url != url:
                is_safe, safety_error = self._is_safe_url(final_url)
                if not is_safe:
                    raise ValueError(f"Redirect to unsafe URL: {final_url} - {safety_error}")
                
                self.logger.logger.info(f"Followed redirect from {url} to {final_url}")
            
            # Validate content type
            content_type = response.headers.get('content-type', '')
            is_valid_type, type_error = self._validate_content_type(content_type, final_url)
            if not is_valid_type:
                raise ValueError(f"Invalid content type: {type_error}")
            
            # Check file size from headers
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.max_file_size_bytes:
                size_mb = int(content_length) / (1024 * 1024)
                max_mb = self.max_file_size_bytes / (1024 * 1024)
                raise ValueError(f"File too large: {size_mb:.1f}MB (max: {max_mb:.0f}MB)")
            
            # Download file with size monitoring
            total_size = 0
            with open(target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
                        
                        # Check size during download
                        if total_size > self.max_file_size_bytes:
                            f.close()
                            target_path.unlink(missing_ok=True)  # Delete partial file
                            size_mb = total_size / (1024 * 1024)
                            max_mb = self.max_file_size_bytes / (1024 * 1024)
                            raise ValueError(f"File exceeded size limit during download: {size_mb:.1f}MB (max: {max_mb:.0f}MB)")
            
            return total_size
            
        except requests.exceptions.RequestException as e:
            # Network-related errors that should trigger retries
            raise ConnectionError(f"Network error downloading {url}: {e}")
        except OSError as e:
            # Filesystem errors
            raise OSError(f"File system error saving {url}: {e}")
        except Exception as e:
            # Other unexpected errors
            raise RuntimeError(f"Unexpected error downloading {url}: {e}")
    
    def _is_valid_url(self, url: str) -> bool:
        """
        Validate URL format and scheme.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL is valid, False otherwise
        """
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc and parsed.scheme in self.ALLOWED_SCHEMES)
        except Exception:
            return False
    
    def _is_safe_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive URL security validation to prevent malicious requests.
        
        Args:
            url: URL to validate for security
            
        Returns:
            Tuple of (is_safe: bool, error_message: Optional[str])
        """
        try:
            # Basic format validation
            if not self._is_valid_url(url):
                return False, "Invalid URL format or unsupported scheme"
            
            parsed = urlparse(url)
            
            # Check for blocked domains
            hostname = parsed.hostname
            if not hostname:
                return False, "URL must have a valid hostname"
            
            hostname_lower = hostname.lower()
            if hostname_lower in self.BLOCKED_DOMAINS:
                return False, f"Access to domain '{hostname}' is not allowed"
            
            # Check for private IP ranges
            if self._is_private_ip(hostname_lower):
                return False, f"Access to private IP address '{hostname}' is not allowed"
            
            # Validate file extension in URL path
            if not self._has_pdf_extension(parsed.path):
                self.logger.logger.warning(f"URL does not have .pdf extension: {url}")
                # Don't block, but log warning as some servers serve PDFs without extension
            
            # Check for suspicious URL patterns
            if self._has_suspicious_patterns(url):
                return False, "URL contains suspicious patterns"
            
            return True, None
            
        except Exception as e:
            return False, f"URL validation error: {e}"
    
    def _is_private_ip(self, hostname: str) -> bool:
        """
        Check if hostname is a private IP address.
        
        Args:
            hostname: Hostname to check
            
        Returns:
            True if hostname is a private IP, False otherwise
        """
        import ipaddress
        
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        except ValueError:
            # Not an IP address, check if it resolves to private IP
            return False
    
    def _has_pdf_extension(self, path: str) -> bool:
        """
        Check if URL path has PDF extension.
        
        Args:
            path: URL path to check
            
        Returns:
            True if path ends with .pdf, False otherwise
        """
        return path.lower().endswith('.pdf')
    
    def _has_suspicious_patterns(self, url: str) -> bool:
        """
        Check for suspicious URL patterns that might indicate malicious intent.
        
        Args:
            url: URL to check
            
        Returns:
            True if suspicious patterns found, False otherwise
        """
        suspicious_patterns = [
            r'\.\./',           # Directory traversal
            r'%2e%2e%2f',      # URL encoded directory traversal
            r'javascript:',     # JavaScript protocol
            r'data:',          # Data protocol
            r'file:',          # File protocol
            r'ftp:',           # FTP protocol
            r'@',              # Potential credential injection
            r'[<>"\']',        # HTML/script injection characters
        ]
        
        url_lower = url.lower()
        for pattern in suspicious_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False
    
    def _validate_content_type(self, content_type: str, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that content type is an allowed PDF type.
        
        Args:
            content_type: Content-Type header value
            url: URL being downloaded (for logging)
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not content_type:
            # Some servers don't set content-type, check URL extension
            if self._has_pdf_extension(urlparse(url).path):
                self.logger.logger.warning(f"No content-type header, but URL has .pdf extension: {url}")
                return True, None
            else:
                return False, "No content-type header and URL doesn't end with .pdf"
        
        # Normalize content type (remove charset, etc.)
        content_type_main = content_type.split(';')[0].strip().lower()
        
        if content_type_main in self.ALLOWED_CONTENT_TYPES:
            return True, None
        
        # Check if it's a generic binary type that might be PDF
        if content_type_main in ['application/octet-stream', 'binary/octet-stream']:
            if self._has_pdf_extension(urlparse(url).path):
                self.logger.logger.warning(f"Generic binary content-type but .pdf extension: {url}")
                return True, None
        
        return False, f"Content type '{content_type_main}' is not allowed (expected PDF)"
    
    def _validate_pdf_content(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate that downloaded file is actually a PDF by checking file signature.
        
        Args:
            file_path: Path to downloaded file
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        try:
            with open(file_path, 'rb') as f:
                # Read first few bytes to check PDF signature
                header = f.read(8)
                
                # PDF files start with %PDF-
                if header.startswith(b'%PDF-'):
                    return True, None
                else:
                    return False, f"File does not have valid PDF signature (starts with: {header[:8]})"
                    
        except Exception as e:
            return False, f"Error validating PDF content: {e}"
    
    def _sanitize_folder_name(self, folder_name: str) -> str:
        """
        Sanitize folder name for filesystem compatibility.
        
        Args:
            folder_name: Original folder name
            
        Returns:
            Sanitized folder name safe for filesystem use
        """
        # Replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = folder_name
        
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip(' .')
        
        # Ensure not empty
        if not sanitized:
            sanitized = "unnamed_folder"
        
        # Limit length to prevent path issues
        if len(sanitized) > 100:
            sanitized = sanitized[:100].rstrip()
        
        return sanitized
    
    def check_file_size_before_download(self, url: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Check file size and security before downloading to avoid large files and security issues.
        
        Args:
            url: URL to check
            
        Returns:
            Tuple of (can_download: bool, file_size_bytes: Optional[int], error_message: Optional[str])
        """
        # Security validation first
        is_safe, safety_error = self._is_safe_url(url)
        if not is_safe:
            error = ValueError(f"URL security validation failed: {safety_error}")
            error_details = self.logger.log_error(error, ErrorCategory.VALIDATION, url=url)
            return False, None, error_details.message
        
        try:
            # Make HEAD request to get file info without downloading
            session = requests.Session()
            session.max_redirects = self.max_redirects
            
            response = session.head(url, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()
            
            # Validate final URL after redirects
            final_url = response.url
            if final_url != url:
                is_safe, safety_error = self._is_safe_url(final_url)
                if not is_safe:
                    error_msg = f"Redirect to unsafe URL: {final_url} - {safety_error}"
                    error = ValueError(error_msg)
                    error_details = self.logger.log_error(error, ErrorCategory.VALIDATION, url=url)
                    return False, None, error_details.message
            
            # Validate content type
            content_type = response.headers.get('content-type', '')
            is_valid_type, type_error = self._validate_content_type(content_type, final_url)
            if not is_valid_type:
                error = ValueError(f"Invalid content type: {type_error}")
                error_details = self.logger.log_error(error, ErrorCategory.VALIDATION, url=url)
                return False, None, error_details.message
            
            # Check file size
            content_length = response.headers.get('content-length')
            if content_length:
                file_size = int(content_length)
                if file_size > self.max_file_size_bytes:
                    size_mb = file_size / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    error_msg = f"File too large: {size_mb:.1f}MB (max: {max_mb:.0f}MB)"
                    
                    error = ValueError(error_msg)
                    self.logger.log_error(
                        error, ErrorCategory.VALIDATION,
                        url=url,
                        context={"file_size_bytes": file_size, "max_size_bytes": self.max_file_size_bytes}
                    )
                    return False, file_size, error_msg
                else:
                    self.logger.log_success(
                        f"File size and security checks passed: {file_size:,} bytes ({file_size/1024/1024:.1f}MB)",
                        url=url,
                        context={"file_size_bytes": file_size}
                    )
                    return True, file_size, None
            else:
                # If no content-length header, we can't determine size beforehand
                self.logger.logger.warning(f"Cannot determine file size for: {url}")
                return True, None, None
                
        except requests.exceptions.RequestException as e:
            error_details = self.logger.log_error(e, ErrorCategory.NETWORK, url=url)
            return False, None, error_details.message
        except Exception as e:
            error_details = self.logger.log_error(e, ErrorCategory.UNKNOWN, url=url)
            return False, None, error_details.message
    
    def download_with_size_check(self, url: str, target_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Download file with pre-download size check for GitHub compatibility.
        
        Args:
            url: URL to download from
            target_path: Local path to save the file
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        # First check file size
        can_download, file_size, size_error = self.check_file_size_before_download(url)
        
        if not can_download:
            return False, size_error
        
        # If size check passed, proceed with normal download
        return self.download_file(url, target_path)