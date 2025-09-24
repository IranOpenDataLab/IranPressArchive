"""
Category-Specific Processing Logic

This module handles different processing logic for old-newspaper and newspaper categories,
including directory structure creation and scheduled execution logic.
"""

import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from file_manager import FileManager
from error_handler import ErrorHandler
from state_manager import StateManager
from readme_generator import ReadmeGenerator


class CategoryProcessor(ABC):
    """Abstract base class for category-specific processors."""
    
    def __init__(self, file_manager: FileManager, error_handler: ErrorHandler,
                 state_manager: StateManager, readme_generator: ReadmeGenerator):
        self.file_manager = file_manager
        self.error_handler = error_handler
        self.state_manager = state_manager
        self.readme_generator = readme_generator
    
    @abstractmethod
    def process_archive(self, archive: Dict[str, Any]) -> Tuple[bool, int, int, List[str]]:
        """Process a single archive according to category-specific logic."""
        pass
    
    @abstractmethod
    def create_directory_structure(self, archive: Dict[str, Any]) -> str:
        """Create directory structure for the archive."""
        pass
    
    @abstractmethod
    def should_process_in_scheduled_run(self, archive: Dict[str, Any]) -> bool:
        """Determine if archive should be processed in scheduled runs."""
        pass


class OldNewspaperProcessor(CategoryProcessor):
    """Processor for old-newspaper category archives."""
    
    def process_archive(self, archive: Dict[str, Any]) -> Tuple[bool, int, int, List[str]]:
        """Process old newspaper archive with static directory structure."""
        archive_name = archive.get('folder', 'unknown')
        urls = archive.get('urls', [])
        
        if not urls:
            error_msg = f"No URLs found for archive: {archive_name}"
            self.error_handler.log_error(error_msg, 'configuration')
            return False, 0, 0, [error_msg]
        
        # Create directory structure
        base_dir = self.create_directory_structure(archive)
        
        files_downloaded = 0
        files_failed = 0
        errors = []
        
        # Process each URL
        for i, url in enumerate(urls, 1):
            try:
                # Generate filename with sequential numbering
                filename = f"{archive_name}_{i:03d}.pdf"
                file_path = os.path.join(base_dir, filename)
                
                # Skip if file already exists
                if os.path.exists(file_path):
                    continue
                
                # Download file (convert string path to Path object)
                from pathlib import Path
                success, download_error = self.file_manager.download_file(url, Path(file_path))
                
                if success:
                    files_downloaded += 1
                else:
                    files_failed += 1
                    error_message = download_error or f"Failed to download {url}"
                    errors.append(error_message)
                    self.error_handler.log_error(error_message, 'network')
                    
            except Exception as e:
                files_failed += 1
                error_msg = f"Error processing {url}: {str(e)}"
                errors.append(error_msg)
                self.error_handler.log_error(error_msg, 'filesystem')
        
        # Generate publication README
        try:
            readme_path = os.path.join(base_dir, 'README.md')
            self.readme_generator.update_publication_readme(
                readme_path, archive, errors if errors else None
            )
        except Exception as e:
            error_msg = f"Failed to generate README for {archive_name}: {str(e)}"
            errors.append(error_msg)
            self.error_handler.log_error(error_msg, 'filesystem')
        
        # Determine overall success
        success = files_downloaded > 0 and files_failed == 0
        
        return success, files_downloaded, files_failed, errors
    
    def create_directory_structure(self, archive: Dict[str, Any]) -> str:
        """Create static directory structure for old newspaper."""
        folder_name = archive.get('folder', 'unknown')
        base_dir = os.path.join('old-newspaper', folder_name)
        
        # Create directory if it doesn't exist
        os.makedirs(base_dir, exist_ok=True)
        
        return base_dir
    
    def should_process_in_scheduled_run(self, archive: Dict[str, Any]) -> bool:
        """Old newspapers are not processed in scheduled runs (static archives)."""
        return False


class NewspaperProcessor(CategoryProcessor):
    """Processor for newspaper category archives (active publications)."""
    
    def process_archive(self, archive: Dict[str, Any]) -> Tuple[bool, int, int, List[str]]:
        """Process newspaper archive with dynamic year-based directory structure."""
        archive_name = archive.get('folder', 'unknown')
        urls = archive.get('urls', [])
        
        if not urls:
            error_msg = f"No URLs found for archive: {archive_name}"
            self.error_handler.log_error(error_msg, 'configuration')
            return False, 0, 0, [error_msg]
        
        # Create base directory structure
        base_dir = self.create_directory_structure(archive)
        
        # Create year-specific directory
        current_year = datetime.now().year
        year_dir = os.path.join(base_dir, str(current_year))
        os.makedirs(year_dir, exist_ok=True)
        
        files_downloaded = 0
        files_failed = 0
        errors = []
        
        # Process each URL
        for i, url in enumerate(urls, 1):
            try:
                # Generate filename with date and sequential numbering
                date_str = datetime.now().strftime('%Y%m%d')
                filename = f"{archive_name}_{date_str}_{i:03d}.pdf"
                file_path = os.path.join(year_dir, filename)
                
                # Skip if file already exists
                if os.path.exists(file_path):
                    continue
                
                # Download file (convert string path to Path object)
                from pathlib import Path
                success, download_error = self.file_manager.download_file(url, Path(file_path))
                
                if success:
                    files_downloaded += 1
                else:
                    files_failed += 1
                    error_message = download_error or f"Failed to download {url}"
                    errors.append(error_message)
                    self.error_handler.log_error(error_message, 'network')
                    
            except Exception as e:
                files_failed += 1
                error_msg = f"Error processing {url}: {str(e)}"
                errors.append(error_msg)
                self.error_handler.log_error(error_msg, 'filesystem')
        
        # Update archive configuration with year information
        self._update_archive_years(archive, current_year, files_downloaded)
        
        # Generate publication README
        try:
            readme_path = os.path.join(base_dir, 'README.md')
            self.readme_generator.update_publication_readme(
                readme_path, archive, errors if errors else None
            )
        except Exception as e:
            error_msg = f"Failed to generate README for {archive_name}: {str(e)}"
            errors.append(error_msg)
            self.error_handler.log_error(error_msg, 'filesystem')
        
        # Determine overall success
        success = files_downloaded > 0 and files_failed == 0
        
        return success, files_downloaded, files_failed, errors
    
    def create_directory_structure(self, archive: Dict[str, Any]) -> str:
        """Create dynamic directory structure for newspaper."""
        folder_name = archive.get('folder', 'unknown')
        base_dir = os.path.join('newspaper', folder_name)
        
        # Create base directory if it doesn't exist
        os.makedirs(base_dir, exist_ok=True)
        
        return base_dir
    
    def should_process_in_scheduled_run(self, archive: Dict[str, Any]) -> bool:
        """Newspapers are processed in scheduled runs (active publications)."""
        return True
    
    def _update_archive_years(self, archive: Dict[str, Any], year: int, files_count: int) -> None:
        """Update archive configuration with year information."""
        if 'years' not in archive:
            archive['years'] = {}
        
        year_str = str(year)
        if year_str not in archive['years']:
            archive['years'][year_str] = []
        
        # Add placeholder entries for downloaded files
        for i in range(files_count):
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"{archive.get('folder', 'unknown')}_{date_str}_{i+1:03d}.pdf"
            if filename not in archive['years'][year_str]:
                archive['years'][year_str].append(filename)


class CategoryProcessorFactory:
    """Factory class for creating category-specific processors."""
    
    @staticmethod
    def create_processor(category: str, file_manager: FileManager, 
                        error_handler: ErrorHandler, state_manager: StateManager,
                        readme_generator: ReadmeGenerator) -> CategoryProcessor:
        """Create appropriate processor for the given category."""
        if category == 'old-newspaper':
            return OldNewspaperProcessor(file_manager, error_handler, 
                                       state_manager, readme_generator)
        elif category == 'newspaper':
            return NewspaperProcessor(file_manager, error_handler, 
                                    state_manager, readme_generator)
        else:
            raise ValueError(f"Unsupported category: {category}")


class WorkflowExecutor:
    """Main executor for category-specific workflow processing."""
    
    def __init__(self, file_manager: FileManager, error_handler: ErrorHandler,
                 state_manager: StateManager, readme_generator: ReadmeGenerator):
        self.file_manager = file_manager
        self.error_handler = error_handler
        self.state_manager = state_manager
        self.readme_generator = readme_generator
        self.factory = CategoryProcessorFactory()
    
    def process_archives_by_category(self, archives: Dict[str, List[Dict[str, Any]]], 
                                   is_scheduled_run: bool = False) -> None:
        """Process archives grouped by category."""
        for category, archive_list in archives.items():
            if not archive_list:
                continue
            
            try:
                processor = self.factory.create_processor(
                    category, self.file_manager, self.error_handler,
                    self.state_manager, self.readme_generator
                )
                
                for archive in archive_list:
                    # Skip archives that shouldn't be processed in scheduled runs
                    if is_scheduled_run and not processor.should_process_in_scheduled_run(archive):
                        continue
                    
                    archive_name = archive.get('folder', 'unknown')
                    start_time = datetime.now()
                    
                    try:
                        success, files_downloaded, files_failed, errors = processor.process_archive(archive)
                        
                        processing_time = (datetime.now() - start_time).total_seconds()
                        
                        # Track result in state manager
                        self.state_manager.track_download_result(
                            archive_name=archive_name,
                            category=category,
                            success=success,
                            files_downloaded=files_downloaded,
                            files_failed=files_failed,
                            errors=errors,
                            processing_time=processing_time
                        )
                        
                    except Exception as e:
                        processing_time = (datetime.now() - start_time).total_seconds()
                        error_msg = f"Critical error processing {archive_name}: {str(e)}"
                        
                        self.error_handler.log_error(error_msg, 'unknown')
                        
                        self.state_manager.track_download_result(
                            archive_name=archive_name,
                            category=category,
                            success=False,
                            files_downloaded=0,
                            files_failed=1,
                            errors=[error_msg],
                            processing_time=processing_time
                        )
                        
            except ValueError as e:
                self.error_handler.log_error(f"Invalid category {category}: {str(e)}", 'configuration')
                continue
    
    def should_run_scheduled_processing(self) -> bool:
        """Determine if scheduled processing should run based on current time."""
        # Run scheduled processing daily (can be customized)
        return True
    
    def get_archives_for_processing(self, all_archives: Dict[str, List[Dict[str, Any]]], 
                                  is_scheduled_run: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """Filter archives based on processing type."""
        if not is_scheduled_run:
            # Manual runs process all archives
            return all_archives
        
        # Scheduled runs only process active publications (newspaper category)
        filtered_archives = {}
        
        for category, archive_list in all_archives.items():
            if category == 'newspaper':
                # Only include active newspapers in scheduled runs
                filtered_archives[category] = archive_list
            # old-newspaper category is excluded from scheduled runs
        
        return filtered_archives