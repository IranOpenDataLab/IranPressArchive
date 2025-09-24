"""
State Management Module

This module handles tracking download status, updating configuration files,
and generating processing summaries for the Iranian Archive Workflow.
"""

import os
import yaml
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ProcessingResult:
    """Represents the result of processing a single archive."""
    archive_name: str
    category: str
    success: bool
    files_downloaded: int = 0
    files_failed: int = 0
    errors: List[str] = field(default_factory=list)
    processing_time: float = 0.0


@dataclass
class WorkflowSummary:
    """Represents the summary of an entire workflow execution."""
    total_archives: int = 0
    successful_archives: int = 0
    failed_archives: int = 0
    total_files_downloaded: int = 0
    total_files_failed: int = 0
    execution_time: float = 0.0
    results: List[ProcessingResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class StateManager:
    """Manages workflow state, configuration updates, and processing summaries."""
    
    def __init__(self, config_path: str = 'urls.yml'):
        self.config_path = config_path
        self.processing_results: List[ProcessingResult] = []
        self.workflow_start_time = datetime.now()
    
    def track_download_result(self, archive_name: str, category: str, 
                            success: bool, files_downloaded: int = 0,
                            files_failed: int = 0, errors: List[str] = None,
                            processing_time: float = 0.0) -> None:
        """Track the result of processing an archive."""
        result = ProcessingResult(
            archive_name=archive_name,
            category=category,
            success=success,
            files_downloaded=files_downloaded,
            files_failed=files_failed,
            errors=errors or [],
            processing_time=processing_time
        )
        self.processing_results.append(result)
    
    def remove_successful_urls(self, successful_archives: List[str]) -> bool:
        """Remove successfully processed archives from urls.yml configuration."""
        if not successful_archives or not os.path.exists(self.config_path):
            return False
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config:
                return False
            
            changes_made = False
            for category in ['old-newspaper', 'newspaper']:
                if category in config:
                    original_count = len(config[category])
                    config[category] = [
                        archive for archive in config[category]
                        if archive.get('folder', '') not in successful_archives
                    ]
                    if len(config[category]) < original_count:
                        changes_made = True
            
            if changes_made:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, 
                             allow_unicode=True, sort_keys=False)
                return True
            
        except Exception as e:
            print(f"Error updating configuration: {e}")
            return False
        
        return False
    
    def generate_processing_summary(self) -> WorkflowSummary:
        """Generate a comprehensive summary of the workflow execution."""
        execution_time = (datetime.now() - self.workflow_start_time).total_seconds()
        
        return WorkflowSummary(
            total_archives=len(self.processing_results),
            successful_archives=sum(1 for r in self.processing_results if r.success),
            failed_archives=sum(1 for r in self.processing_results if not r.success),
            total_files_downloaded=sum(r.files_downloaded for r in self.processing_results),
            total_files_failed=sum(r.files_failed for r in self.processing_results),
            execution_time=execution_time,
            results=self.processing_results.copy()
        )
    
    def generate_commit_message(self) -> str:
        """Generate a commit message based on processed archives."""
        if not self.processing_results:
            return "chore: workflow execution with no changes"
        
        successful_results = [r for r in self.processing_results if r.success]
        failed_results = [r for r in self.processing_results if not r.success]
        
        message_parts = []
        
        if successful_results:
            total_files = sum(r.files_downloaded for r in successful_results)
            archive_names = [r.archive_name for r in successful_results]
            
            if len(archive_names) == 1:
                message_parts.append(f"feat: add {total_files} files from {archive_names[0]}")
            else:
                message_parts.append(f"feat: add {total_files} files from {len(archive_names)} archives")
        
        if failed_results:
            failed_names = [r.archive_name for r in failed_results]
            if len(failed_names) == 1:
                message_parts.append(f"fix: processing failed for {failed_names[0]}")
            else:
                message_parts.append(f"fix: processing failed for {len(failed_names)} archives")
        
        main_message = "; ".join(message_parts) if message_parts else "chore: workflow execution with no changes"
        
        if len(self.processing_results) > 1:
            details = []
            for result in self.processing_results:
                status = "✅" if result.success else "❌"
                details.append(f"{status} {result.archive_name}: {result.files_downloaded} files")
            
            body = "\n".join(details)
            return f"{main_message}\n\n{body}"
        
        return main_message
    
    def get_successful_archives(self) -> List[str]:
        """Get list of successfully processed archive names."""
        return [r.archive_name for r in self.processing_results if r.success]
    
    def get_failed_archives(self) -> List[str]:
        """Get list of failed archive names."""
        return [r.archive_name for r in self.processing_results if not r.success]
    
    def export_summary_to_file(self, output_path: str) -> None:
        """Export processing summary to a file."""
        summary = self.generate_processing_summary()
        
        content = f"""# Workflow Execution Summary

**Execution Time:** {summary.timestamp}
**Total Duration:** {summary.execution_time:.2f} seconds

## Statistics
- **Total Archives:** {summary.total_archives}
- **Successful:** {summary.successful_archives}
- **Failed:** {summary.failed_archives}
- **Files Downloaded:** {summary.total_files_downloaded}
- **Files Failed:** {summary.total_files_failed}

## Detailed Results

"""
        
        for result in summary.results:
            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            content += f"### {result.archive_name} ({result.category}) - {status}\n"
            content += f"- Files Downloaded: {result.files_downloaded}\n"
            content += f"- Files Failed: {result.files_failed}\n"
            content += f"- Processing Time: {result.processing_time:.2f}s\n"
            
            if result.errors:
                content += "- Errors:\n"
                for error in result.errors:
                    content += f"  - {error}\n"
            
            content += "\n"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def reset_state(self) -> None:
        """Reset the state manager for a new workflow execution."""
        self.processing_results.clear()
        self.workflow_start_time = datetime.now()