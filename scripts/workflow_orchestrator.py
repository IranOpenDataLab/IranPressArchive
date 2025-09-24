"""
Workflow Orchestration and Main Execution Logic

This module coordinates all components of the Iranian Archive Workflow system,
handling both manual and scheduled execution modes with comprehensive monitoring
and optimization features.
"""

import os
import sys
import argparse
import time
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import subprocess
from dataclasses import dataclass, field

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

from config_parser import ConfigParser
from file_manager import FileManager
from error_handler import ErrorHandler
from state_manager import StateManager
from readme_generator import ReadmeGenerator
from category_processor import WorkflowExecutor


@dataclass
class PerformanceMetrics:
    """Performance metrics for workflow execution monitoring."""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    peak_memory_mb: float = 0.0
    initial_memory_mb: float = 0.0
    cpu_percent: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_requests: int = 0
    files_processed: int = 0
    directories_created: int = 0
    
    @property
    def execution_time(self) -> float:
        """Calculate total execution time."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time
    
    @property
    def memory_delta_mb(self) -> float:
        """Calculate memory usage delta."""
        return self.peak_memory_mb - self.initial_memory_mb
    
    @property
    def files_per_second(self) -> float:
        """Calculate files processed per second."""
        exec_time = self.execution_time
        return self.files_processed / exec_time if exec_time > 0 else 0.0


@dataclass
class WorkflowDebugInfo:
    """Debug information for troubleshooting workflow issues."""
    phase: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    active_threads: int = 0
    open_files: int = 0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class WorkflowOrchestrator:
    """Main orchestrator for the Iranian Archive Workflow system with monitoring."""
    
    def __init__(self, config_path: str = 'urls.yml', 
                 log_file: str = 'workflow.log',
                 enable_monitoring: bool = True,
                 enable_debugging: bool = False):
        """
        Initialize the workflow orchestrator.
        
        Args:
            config_path: Path to the configuration file
            log_file: Path to the log file
            enable_monitoring: Enable performance monitoring
            enable_debugging: Enable detailed debugging output
        """
        self.config_path = config_path
        self.log_file = log_file
        self.enable_monitoring = enable_monitoring
        self.enable_debugging = enable_debugging
        
        # Initialize components
        self.config_parser = ConfigParser(config_path)
        self.file_manager = FileManager()
        self.error_handler = ErrorHandler(log_file)
        self.state_manager = StateManager(config_path)
        self.readme_generator = ReadmeGenerator()
        self.workflow_executor = WorkflowExecutor(
            self.file_manager, self.error_handler,
            self.state_manager, self.readme_generator
        )
        
        # Workflow state
        self.is_scheduled_run = False
        self.dry_run = False
        self.verbose = False
        
        # Monitoring and debugging
        self.performance_metrics = PerformanceMetrics()
        self.debug_info: List[WorkflowDebugInfo] = []
        self.monitoring_thread: Optional[threading.Thread] = None
        self.monitoring_active = False
        
        # System process for monitoring
        self.process = psutil.Process() if (enable_monitoring and PSUTIL_AVAILABLE) else None
    
    def _start_monitoring(self) -> None:
        """Start enhanced performance monitoring in background thread."""
        if not self.enable_monitoring or not self.process or not PSUTIL_AVAILABLE:
            if self.enable_monitoring and not PSUTIL_AVAILABLE:
                self._log("psutil not available - monitoring disabled", verbose=True)
            return
        
        self.monitoring_active = True
        self.performance_metrics.initial_memory_mb = self.process.memory_info().rss / 1024 / 1024
        
        # Initialize performance monitor for detailed tracking
        try:
            from performance_monitor import PerformanceMonitor
            self.detailed_monitor = PerformanceMonitor("workflow_performance_data")
            self.detailed_monitor.start_monitoring(interval=0.5)
        except ImportError:
            self.detailed_monitor = None
        
        def monitor_performance():
            """Monitor system performance metrics with enhanced tracking."""
            sample_count = 0
            while self.monitoring_active:
                try:
                    # Memory monitoring with leak detection
                    memory_mb = self.process.memory_info().rss / 1024 / 1024
                    self.performance_metrics.peak_memory_mb = max(
                        self.performance_metrics.peak_memory_mb, memory_mb
                    )
                    
                    # Track memory growth rate
                    if sample_count > 0 and sample_count % 10 == 0:  # Every 5 seconds
                        memory_growth = memory_mb - self.performance_metrics.initial_memory_mb
                        if memory_growth > 100:  # More than 100MB growth
                            self._add_debug_info("memory_warning", 
                                               f"High memory growth detected: {memory_growth:.1f}MB",
                                               {"current_memory": memory_mb, "growth": memory_growth})
                    
                    # CPU monitoring with sustained usage detection
                    cpu_percent = self.process.cpu_percent()
                    self.performance_metrics.cpu_percent = max(
                        self.performance_metrics.cpu_percent, cpu_percent
                    )
                    
                    # Detect sustained high CPU usage
                    if cpu_percent > 80 and sample_count % 20 == 0:  # Every 10 seconds
                        self._add_debug_info("cpu_warning",
                                           f"Sustained high CPU usage: {cpu_percent:.1f}%",
                                           {"cpu_percent": cpu_percent})
                    
                    # I/O monitoring with rate calculation
                    io_counters = self.process.io_counters()
                    current_read_mb = io_counters.read_bytes / 1024 / 1024
                    current_write_mb = io_counters.write_bytes / 1024 / 1024
                    
                    # Calculate I/O rates
                    if hasattr(self, '_last_io_sample'):
                        time_delta = time.time() - self._last_io_sample['time']
                        if time_delta > 0:
                            read_rate = (current_read_mb - self._last_io_sample['read']) / time_delta
                            write_rate = (current_write_mb - self._last_io_sample['write']) / time_delta
                            
                            # Detect high I/O rates
                            if read_rate + write_rate > 50:  # More than 50MB/s
                                self._add_debug_info("io_warning",
                                                   f"High I/O rate: {read_rate + write_rate:.1f}MB/s",
                                                   {"read_rate": read_rate, "write_rate": write_rate})
                    
                    self._last_io_sample = {
                        'time': time.time(),
                        'read': current_read_mb,
                        'write': current_write_mb
                    }
                    
                    self.performance_metrics.disk_io_read_mb = current_read_mb
                    self.performance_metrics.disk_io_write_mb = current_write_mb
                    
                    sample_count += 1
                    time.sleep(0.5)  # Monitor every 500ms
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                except Exception as e:
                    if self.verbose:
                        self._log(f"Monitoring error: {e}", verbose=True)
        
        self.monitoring_thread = threading.Thread(target=monitor_performance, daemon=True)
        self.monitoring_thread.start()
    
    def _stop_monitoring(self) -> None:
        """Stop enhanced performance monitoring."""
        if self.monitoring_active:
            self.monitoring_active = False
            self.performance_metrics.end_time = time.time()
            
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=1.0)
            
            # Stop detailed monitoring if available
            if hasattr(self, 'detailed_monitor') and self.detailed_monitor:
                try:
                    self.detailed_monitor.stop_monitoring()
                except Exception as e:
                    self._log(f"Error stopping detailed monitor: {e}", verbose=True)
    
    def _add_debug_info(self, phase: str, message: str, details: Dict[str, Any] = None) -> None:
        """Add debug information for troubleshooting."""
        if not self.enable_debugging:
            return
        
        debug_info = WorkflowDebugInfo(
            phase=phase,
            message=message,
            details=details or {}
        )
        
        if self.process:
            try:
                debug_info.memory_mb = self.process.memory_info().rss / 1024 / 1024
                debug_info.cpu_percent = self.process.cpu_percent()
                debug_info.active_threads = threading.active_count()
                debug_info.open_files = len(self.process.open_files())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        self.debug_info.append(debug_info)
        
        if self.verbose:
            self._log(f"DEBUG [{phase}] {message}", verbose=True)
            if details:
                for key, value in details.items():
                    self._log(f"  {key}: {value}", verbose=True)
    
    def _add_memory_checkpoint(self, checkpoint_name: str) -> None:
        """Add memory usage checkpoint for tracking."""
        if not self.enable_monitoring or not self.process:
            return
        
        try:
            current_memory = self.process.memory_info().rss / 1024 / 1024
            
            # Add to detailed monitor if available
            if hasattr(self, 'detailed_monitor') and self.detailed_monitor:
                self.detailed_monitor.add_memory_checkpoint(
                    checkpoint_name, 
                    current_memory,
                    {'timestamp': datetime.now().isoformat()}
                )
            
            # Log significant memory changes
            if hasattr(self, '_last_checkpoint_memory'):
                memory_delta = current_memory - self._last_checkpoint_memory
                if abs(memory_delta) > 10:  # More than 10MB change
                    self._add_debug_info("memory_checkpoint", 
                                       f"Memory checkpoint '{checkpoint_name}': {current_memory:.1f}MB "
                                       f"(Δ{memory_delta:+.1f}MB)",
                                       {"checkpoint": checkpoint_name, "memory_mb": current_memory, "delta_mb": memory_delta})
            else:
                self._add_debug_info("memory_checkpoint", 
                                   f"Memory checkpoint '{checkpoint_name}': {current_memory:.1f}MB",
                                   {"checkpoint": checkpoint_name, "memory_mb": current_memory})
            
            self._last_checkpoint_memory = current_memory
            
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    def _optimize_memory_usage(self) -> None:
        """Optimize memory usage during workflow execution."""
        if not self.enable_monitoring:
            return
        
        try:
            import gc
            
            # Force garbage collection
            collected = gc.collect()
            
            if self.verbose and collected > 0:
                self._log(f"Garbage collected {collected} objects", verbose=True)
            
            # Check memory usage and warn if high
            if self.process:
                current_memory = self.process.memory_info().rss / 1024 / 1024
                if current_memory > 500:  # Warn if using more than 500MB
                    self._log(f"WARNING: High memory usage detected: {current_memory:.1f}MB")
                
        except Exception as e:
            self._log(f"Memory optimization failed: {e}", verbose=True)
    
    def _generate_performance_report(self) -> str:
        """Generate comprehensive workflow performance report."""
        metrics = self.performance_metrics
        
        # Calculate performance scores
        cpu_efficiency = max(0, 100 - metrics.cpu_percent)
        memory_efficiency = max(0, 100 - (metrics.memory_delta_mb / 10)) if metrics.memory_delta_mb > 0 else 100
        time_efficiency = max(0, 100 - (metrics.execution_time / 10)) if metrics.execution_time > 0 else 100
        overall_score = (cpu_efficiency + memory_efficiency + time_efficiency) / 3
        
        report = f"""
=== Comprehensive Workflow Performance Report ===
Generated: {datetime.now().isoformat()}
Execution Mode: {'Scheduled' if self.is_scheduled_run else 'Manual'}
Dry Run: {'Yes' if self.dry_run else 'No'}

=== Execution Summary ===
Total Execution Time: {metrics.execution_time:.2f} seconds
Overall Performance Score: {overall_score:.1f}/100

=== Resource Usage ===
Memory Usage:
  - Initial: {metrics.initial_memory_mb:.1f} MB
  - Peak: {metrics.peak_memory_mb:.1f} MB
  - Delta: {metrics.memory_delta_mb:.1f} MB
  - Efficiency Score: {memory_efficiency:.1f}/100

CPU Usage:
  - Peak: {metrics.cpu_percent:.1f}%
  - Efficiency Score: {cpu_efficiency:.1f}/100

Disk I/O:
  - Read: {metrics.disk_io_read_mb:.1f} MB
  - Write: {metrics.disk_io_write_mb:.1f} MB
  - Total I/O: {metrics.disk_io_read_mb + metrics.disk_io_write_mb:.1f} MB

=== Processing Statistics ===
Files Processed: {metrics.files_processed}
Directories Created: {metrics.directories_created}
Network Requests: {metrics.network_requests}
Processing Rate: {metrics.files_per_second:.1f} files/second
"""
        
        # Add phase timing analysis
        if hasattr(self, 'detailed_monitor') and self.detailed_monitor and self.detailed_monitor.execution_phases:
            report += "\n=== Execution Phase Analysis ===\n"
            total_phase_time = sum(phase['duration'] for phase in self.detailed_monitor.execution_phases)
            for phase in self.detailed_monitor.execution_phases:
                percentage = (phase['duration'] / total_phase_time * 100) if total_phase_time > 0 else 0
                report += f"  {phase['phase']}: {phase['duration']:.2f}s ({percentage:.1f}%)\n"
        
        # Add memory checkpoint analysis
        memory_checkpoints = [d for d in self.debug_info if d.phase == "memory_checkpoint"]
        if memory_checkpoints:
            report += "\n=== Memory Usage Timeline ===\n"
            for checkpoint in memory_checkpoints[-5:]:  # Show last 5 checkpoints
                if 'checkpoint' in checkpoint.details:
                    checkpoint_name = checkpoint.details['checkpoint']
                    memory_mb = checkpoint.details.get('memory_mb', 0)
                    delta_mb = checkpoint.details.get('delta_mb', 0)
                    report += f"  {checkpoint_name}: {memory_mb:.1f} MB"
                    if delta_mb != 0:
                        report += f" (Δ{delta_mb:+.1f} MB)"
                    report += "\n"
        
        # Add performance warnings and recommendations
        warnings = []
        recommendations = []
        
        if metrics.cpu_percent > 80:
            warnings.append(f"High CPU usage detected: {metrics.cpu_percent:.1f}%")
            recommendations.append("Consider optimizing CPU-intensive operations or adding processing delays")
        
        if metrics.memory_delta_mb > 200:
            warnings.append(f"High memory usage: {metrics.memory_delta_mb:.1f} MB increase")
            recommendations.append("Consider processing data in smaller batches or implementing memory cleanup")
        
        if metrics.execution_time > 300:  # More than 5 minutes
            warnings.append(f"Long execution time: {metrics.execution_time:.1f} seconds")
            recommendations.append("Consider parallelizing operations or optimizing slow components")
        
        if metrics.files_per_second < 1 and metrics.files_processed > 0:
            warnings.append(f"Low processing rate: {metrics.files_per_second:.2f} files/second")
            recommendations.append("Consider optimizing file processing or network operations")
        
        if warnings:
            report += "\n=== Performance Warnings ===\n"
            for warning in warnings:
                report += f"⚠️  {warning}\n"
        
        if recommendations:
            report += "\n=== Optimization Recommendations ===\n"
            for i, recommendation in enumerate(recommendations, 1):
                report += f"{i}. {recommendation}\n"
        
        if not warnings:
            report += "\n✅ No performance issues detected\n"
        
        # Add debug information summary
        if self.debug_info:
            report += f"\n=== Debug Information Summary ===\n"
            report += f"Total Debug Entries: {len(self.debug_info)}\n"
            
            # Group debug entries by phase
            phase_counts = {}
            for debug in self.debug_info:
                phase_counts[debug.phase] = phase_counts.get(debug.phase, 0) + 1
            
            report += "Debug Entries by Phase:\n"
            for phase, count in sorted(phase_counts.items()):
                report += f"  {phase}: {count}\n"
            
            # Show recent critical debug entries
            critical_entries = [d for d in self.debug_info[-20:] 
                              if any(keyword in d.phase for keyword in ['warning', 'error', 'critical'])]
            if critical_entries:
                report += "\nRecent Critical Entries:\n"
                for debug in critical_entries[-5:]:
                    report += f"  [{debug.timestamp}] {debug.phase}: {debug.message}\n"
        
        return report
    
    def execute_workflow(self, is_scheduled_run: bool = False, 
                        dry_run: bool = False, verbose: bool = False) -> bool:
        """
        Execute the complete workflow with enhanced monitoring and optimization.
        
        Args:
            is_scheduled_run: Whether this is a scheduled execution
            dry_run: If True, don't make actual changes
            verbose: Enable verbose logging
            
        Returns:
            True if workflow completed successfully
        """
        self.is_scheduled_run = is_scheduled_run
        self.dry_run = dry_run
        self.verbose = verbose
        
        # Phase timing tracking
        phase_times = {}
        
        try:
            # Start performance monitoring
            self._start_monitoring()
            self._add_debug_info("initialization", "Workflow execution started")
            self._add_memory_checkpoint("workflow_start")
            
            self._log_workflow_start()
            
            # Step 1: Load and validate configuration
            phase_start = time.time()
            self._add_debug_info("configuration", "Loading configuration file")
            if not self._load_configuration():
                return False
            phase_times['configuration'] = time.time() - phase_start
            self._add_memory_checkpoint("configuration_loaded")
            
            # Step 2: Filter archives based on execution type
            phase_start = time.time()
            self._add_debug_info("filtering", "Filtering archives for processing")
            archives_to_process = self._filter_archives_for_processing()
            phase_times['filtering'] = time.time() - phase_start
            
            if not archives_to_process:
                self._log("No archives to process", verbose=True)
                self._add_debug_info("filtering", "No archives to process")
                return True
            
            # Update metrics with expected file count
            total_files = sum(len(archive.get('urls', [])) for archive_list in archives_to_process.values() 
                            for archive in archive_list)
            self.performance_metrics.files_processed = total_files
            self._add_debug_info("processing", f"Processing {total_files} files from {sum(len(archives) for archives in archives_to_process.values())} archives")
            
            # Step 3: Process archives by category
            phase_start = time.time()
            self._add_debug_info("processing", "Starting archive processing")
            self._add_memory_checkpoint("processing_start")
            self._process_archives(archives_to_process)
            phase_times['processing'] = time.time() - phase_start
            self._add_memory_checkpoint("processing_complete")
            
            # Optimize memory after processing
            self._optimize_memory_usage()
            self._add_memory_checkpoint("memory_optimized")
            
            # Step 4: Generate processing summary
            phase_start = time.time()
            self._add_debug_info("summary", "Generating processing summary")
            summary = self.state_manager.generate_processing_summary()
            self._log_processing_summary(summary)
            phase_times['summary'] = time.time() - phase_start
            
            # Step 5: Update configuration (remove successful URLs)
            if not dry_run:
                phase_start = time.time()
                self._add_debug_info("configuration", "Updating configuration file")
                self._update_configuration()
                phase_times['config_update'] = time.time() - phase_start
            
            # Step 6: Generate and update README files
            if not dry_run:
                phase_start = time.time()
                self._add_debug_info("documentation", "Updating README files")
                self._update_readme_files()
                phase_times['readme_generation'] = time.time() - phase_start
                self._add_memory_checkpoint("readme_generated")
            
            # Step 7: Commit changes to repository
            if not dry_run:
                phase_start = time.time()
                self._add_debug_info("git", "Committing changes")
                self._commit_changes()
                phase_times['git_commit'] = time.time() - phase_start
            
            # Step 8: Cleanup operations
            phase_start = time.time()
            self._add_debug_info("cleanup", "Performing cleanup operations")
            self._cleanup()
            phase_times['cleanup'] = time.time() - phase_start
            self._add_memory_checkpoint("workflow_complete")
            
            # Add phase timing to detailed monitor if available
            if hasattr(self, 'detailed_monitor') and self.detailed_monitor:
                for phase_name, duration in phase_times.items():
                    self.detailed_monitor.add_execution_phase(
                        phase_name, 
                        self.performance_metrics.start_time, 
                        self.performance_metrics.start_time + duration,
                        {'files_processed': total_files}
                    )
            
            self._log_workflow_completion(True)
            
            # Generate and log performance report
            if self.enable_monitoring:
                performance_report = self._generate_performance_report()
                self._log("Performance Report:" + performance_report)
                
                # Export detailed performance data
                self._export_performance_data()
                
                # Generate detailed monitoring report if available
                if hasattr(self, 'detailed_monitor') and self.detailed_monitor:
                    try:
                        detailed_report = self.detailed_monitor.generate_report()
                        self._log("Detailed Performance Analysis:" + detailed_report)
                        
                        # Export detailed data
                        self.detailed_monitor.export_data()
                    except Exception as e:
                        self._log(f"Error generating detailed report: {e}", verbose=True)
            
            return True
            
        except Exception as e:
            self.error_handler.log_error(f"Critical workflow error: {str(e)}", 'unknown')
            self._add_debug_info("error", f"Critical error: {str(e)}")
            self._log_workflow_completion(False)
            return False
        
        finally:
            # Always stop monitoring
            self._stop_monitoring()
    
    def _load_configuration(self) -> bool:
        """Load and validate configuration file."""
        try:
            if not os.path.exists(self.config_path):
                self.error_handler.log_error(f"Configuration file not found: {self.config_path}", 'configuration')
                return False
            
            archive_list = self.config_parser.parse_configuration()
            
            if not archive_list:
                self.error_handler.log_error("No valid archives found in configuration", 'configuration')
                return False
            
            # Convert Archive objects to dictionary format expected by workflow
            self.archives = self._convert_archives_to_dict(archive_list)
            
            self._log(f"Loaded {sum(len(archives) for archives in self.archives.values())} archives from configuration")
            return True
            
        except Exception as e:
            self.error_handler.log_error(f"Failed to load configuration: {str(e)}", 'configuration')
            return False
    
    def _filter_archives_for_processing(self) -> Dict[str, List[Dict[str, Any]]]:
        """Filter archives based on execution type."""
        return self.workflow_executor.get_archives_for_processing(
            self.archives, self.is_scheduled_run
        )
    
    def _process_archives(self, archives: Dict[str, List[Dict[str, Any]]]) -> None:
        """Process archives using the workflow executor."""
        total_archives = sum(len(archive_list) for archive_list in archives.values())
        self._log(f"Processing {total_archives} archives...")
        
        if self.dry_run:
            self._log("DRY RUN: Simulating archive processing", verbose=True)
            # In dry run, simulate processing without actual downloads
            for category, archive_list in archives.items():
                for archive in archive_list:
                    archive_name = archive.get('folder', 'unknown')
                    self.state_manager.track_download_result(
                        archive_name=archive_name,
                        category=category,
                        success=True,
                        files_downloaded=len(archive.get('urls', [])),
                        files_failed=0,
                        errors=[],
                        processing_time=0.1
                    )
        else:
            self.workflow_executor.process_archives_by_category(archives, self.is_scheduled_run)
    
    def _update_configuration(self) -> None:
        """Update configuration file by removing successful URLs."""
        successful_archives = self.state_manager.get_successful_archives()
        
        if successful_archives:
            self._log(f"Removing {len(successful_archives)} successful archives from configuration")
            
            updated = self.state_manager.remove_successful_urls(successful_archives)
            if updated:
                self._log("Configuration updated successfully")
            else:
                self._log("No configuration changes needed")
    
    def _update_readme_files(self) -> None:
        """Generate and update README files."""
        try:
            self._log("Updating README files...")
            
            # Generate main README files (Persian and English)
            if self.archives:
                # Persian README
                self.readme_generator.generate_main_readme(
                    'fa', list(self.archives.values())[0] if self.archives else [], 'README.md'
                )
                
                # English README
                self.readme_generator.generate_main_readme(
                    'en', list(self.archives.values())[0] if self.archives else [], 'README.en.md'
                )
                
                self._log("Main README files updated")
            
        except Exception as e:
            self.error_handler.log_error(f"Failed to update README files: {str(e)}", 'filesystem')
    
    def _commit_changes(self) -> None:
        """Commit changes to the repository."""
        try:
            # Check if we're in a git repository
            if not os.path.exists('.git'):
                self._log("Not in a git repository, skipping commit", verbose=True)
                return
            
            # Generate commit message
            commit_message = self.state_manager.generate_commit_message()
            
            # Stage changes
            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
            
            # Check if there are changes to commit
            result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
            if result.returncode == 0:
                self._log("No changes to commit", verbose=True)
                return
            
            # Commit changes
            subprocess.run(['git', 'commit', '-m', commit_message], check=True, capture_output=True)
            self._log(f"Changes committed: {commit_message}")
            
        except subprocess.CalledProcessError as e:
            self.error_handler.log_error(f"Git operation failed: {str(e)}", 'filesystem')
        except Exception as e:
            self.error_handler.log_error(f"Failed to commit changes: {str(e)}", 'filesystem')
    
    def _convert_archives_to_dict(self, archive_list) -> Dict[str, List[Dict[str, Any]]]:
        """Convert Archive objects to dictionary format."""
        archives_dict = {'old-newspaper': [], 'newspaper': []}
        
        for archive in archive_list:
            # Extract URLs from years data or use urls attribute if available
            urls = []
            if hasattr(archive, 'urls'):
                urls = archive.urls
            elif archive.years:
                # Extract URLs from years data (assuming they're stored there)
                for year_files in archive.years.values():
                    urls.extend(year_files)
            
            archive_dict = {
                'folder': archive.folder,
                'urls': urls,
                'description': archive.description,
                'title_fa': archive.title_fa,
                'category': archive.category,
                'years': archive.years
            }
            
            category = archive.category
            if category in archives_dict:
                archives_dict[category].append(archive_dict)
            else:
                archives_dict['old-newspaper'].append(archive_dict)
        
        return archives_dict
    
    def _export_performance_data(self) -> None:
        """Export comprehensive performance data and generate summary reports."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Export performance metrics as JSON
            import json
            metrics_data = {
                'workflow_info': {
                    'execution_mode': 'scheduled' if self.is_scheduled_run else 'manual',
                    'dry_run': self.dry_run,
                    'verbose': self.verbose,
                    'monitoring_enabled': self.enable_monitoring,
                    'debugging_enabled': self.enable_debugging
                },
                'performance_metrics': {
                    'execution_time': self.performance_metrics.execution_time,
                    'memory_initial_mb': self.performance_metrics.initial_memory_mb,
                    'memory_peak_mb': self.performance_metrics.peak_memory_mb,
                    'memory_delta_mb': self.performance_metrics.memory_delta_mb,
                    'cpu_peak_percent': self.performance_metrics.cpu_percent,
                    'disk_io_read_mb': self.performance_metrics.disk_io_read_mb,
                    'disk_io_write_mb': self.performance_metrics.disk_io_write_mb,
                    'files_processed': self.performance_metrics.files_processed,
                    'directories_created': self.performance_metrics.directories_created,
                    'network_requests': self.performance_metrics.network_requests,
                    'files_per_second': self.performance_metrics.files_per_second
                },
                'execution_phases': [],
                'memory_checkpoints': [],
                'performance_analysis': {
                    'cpu_efficiency': max(0, 100 - self.performance_metrics.cpu_percent),
                    'memory_efficiency': max(0, 100 - (self.performance_metrics.memory_delta_mb / 10)) if self.performance_metrics.memory_delta_mb > 0 else 100,
                    'time_efficiency': max(0, 100 - (self.performance_metrics.execution_time / 10)) if self.performance_metrics.execution_time > 0 else 100
                },
                'timestamp': datetime.now().isoformat()
            }
            
            # Add execution phases if available
            if hasattr(self, 'detailed_monitor') and self.detailed_monitor and self.detailed_monitor.execution_phases:
                metrics_data['execution_phases'] = self.detailed_monitor.execution_phases
            
            # Add memory checkpoints from debug info
            memory_checkpoints = [d for d in self.debug_info if d.phase == "memory_checkpoint"]
            for checkpoint in memory_checkpoints:
                if 'checkpoint' in checkpoint.details:
                    metrics_data['memory_checkpoints'].append({
                        'name': checkpoint.details['checkpoint'],
                        'timestamp': checkpoint.timestamp,
                        'memory_mb': checkpoint.details.get('memory_mb', 0),
                        'delta_mb': checkpoint.details.get('delta_mb', 0)
                    })
            
            # Calculate overall performance score
            analysis = metrics_data['performance_analysis']
            overall_score = (analysis['cpu_efficiency'] + analysis['memory_efficiency'] + analysis['time_efficiency']) / 3
            analysis['overall_score'] = overall_score
            
            metrics_path = f"workflow_performance_{timestamp}.json"
            with open(metrics_path, 'w', encoding='utf-8') as f:
                json.dump(metrics_data, f, indent=2, ensure_ascii=False)
            
            self._log(f"Performance metrics exported to {metrics_path}", verbose=True)
            
            # Export debug information if available
            if self.debug_info:
                debug_path = f"workflow_debug_{timestamp}.json"
                debug_data = {
                    'workflow_info': metrics_data['workflow_info'],
                    'debug_entries': [],
                    'summary': {
                        'total_entries': len(self.debug_info),
                        'phases': {},
                        'warnings': 0,
                        'errors': 0
                    }
                }
                
                # Process debug entries
                for debug in self.debug_info:
                    debug_entry = {
                        'phase': debug.phase,
                        'timestamp': debug.timestamp,
                        'memory_mb': debug.memory_mb,
                        'cpu_percent': debug.cpu_percent,
                        'active_threads': debug.active_threads,
                        'open_files': debug.open_files,
                        'message': debug.message,
                        'details': debug.details
                    }
                    debug_data['debug_entries'].append(debug_entry)
                    
                    # Update summary
                    phase = debug.phase
                    debug_data['summary']['phases'][phase] = debug_data['summary']['phases'].get(phase, 0) + 1
                    
                    if 'warning' in phase.lower():
                        debug_data['summary']['warnings'] += 1
                    elif 'error' in phase.lower():
                        debug_data['summary']['errors'] += 1
                
                with open(debug_path, 'w', encoding='utf-8') as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                
                self._log(f"Debug information exported to {debug_path}", verbose=True)
            
            # Generate human-readable summary report
            summary_path = f"workflow_summary_{timestamp}.md"
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("# Workflow Execution Summary\n\n")
                f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
                f.write(f"**Execution Mode:** {'Scheduled' if self.is_scheduled_run else 'Manual'}\n")
                f.write(f"**Dry Run:** {'Yes' if self.dry_run else 'No'}\n")
                f.write(f"**Performance Score:** {overall_score:.1f}/100\n\n")
                
                f.write("## Performance Metrics\n\n")
                f.write(f"- **Execution Time:** {self.performance_metrics.execution_time:.2f} seconds\n")
                f.write(f"- **Files Processed:** {self.performance_metrics.files_processed}\n")
                f.write(f"- **Processing Rate:** {self.performance_metrics.files_per_second:.1f} files/second\n")
                f.write(f"- **Peak Memory:** {self.performance_metrics.peak_memory_mb:.1f} MB\n")
                f.write(f"- **Memory Delta:** {self.performance_metrics.memory_delta_mb:.1f} MB\n")
                f.write(f"- **Peak CPU:** {self.performance_metrics.cpu_percent:.1f}%\n\n")
                
                if metrics_data['execution_phases']:
                    f.write("## Execution Phases\n\n")
                    for phase in metrics_data['execution_phases']:
                        f.write(f"- **{phase['phase']}:** {phase['duration']:.2f}s\n")
                    f.write("\n")
                
                if metrics_data['memory_checkpoints']:
                    f.write("## Memory Usage Timeline\n\n")
                    for checkpoint in metrics_data['memory_checkpoints']:
                        f.write(f"- **{checkpoint['name']}:** {checkpoint['memory_mb']:.1f} MB")
                        if checkpoint['delta_mb'] != 0:
                            f.write(f" (Δ{checkpoint['delta_mb']:+.1f} MB)")
                        f.write("\n")
                    f.write("\n")
                
                if self.debug_info:
                    warnings = [d for d in self.debug_info if 'warning' in d.phase.lower()]
                    errors = [d for d in self.debug_info if 'error' in d.phase.lower()]
                    
                    if warnings or errors:
                        f.write("## Issues Detected\n\n")
                        
                        if warnings:
                            f.write("### Warnings\n\n")
                            for warning in warnings[-5:]:  # Last 5 warnings
                                f.write(f"- **{warning.phase}:** {warning.message}\n")
                            f.write("\n")
                        
                        if errors:
                            f.write("### Errors\n\n")
                            for error in errors[-5:]:  # Last 5 errors
                                f.write(f"- **{error.phase}:** {error.message}\n")
                            f.write("\n")
            
            self._log(f"Workflow summary exported to {summary_path}", verbose=True)
                
        except Exception as e:
            self._log(f"Failed to export performance data: {e}", verbose=True)
    
    def _cleanup(self) -> None:
        """Perform cleanup operations."""
        try:
            # Export processing summary
            summary_path = f"workflow_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            self.state_manager.export_summary_to_file(summary_path)
            self._log(f"Processing summary exported to {summary_path}")
            
            # Perform final memory optimization
            self._optimize_memory_usage()
            
        except Exception as e:
            self.error_handler.log_error(f"Cleanup failed: {str(e)}", 'filesystem')
    
    def _log_workflow_start(self) -> None:
        """Log workflow start information."""
        execution_type = "scheduled" if self.is_scheduled_run else "manual"
        mode = "DRY RUN" if self.dry_run else "LIVE"
        
        self._log(f"=== Iranian Archive Workflow Started ===")
        self._log(f"Execution Type: {execution_type}")
        self._log(f"Mode: {mode}")
        self._log(f"Timestamp: {datetime.now().isoformat()}")
        self._log(f"Configuration: {self.config_path}")
    
    def _log_workflow_completion(self, success: bool) -> None:
        """Log workflow completion information."""
        status = "COMPLETED" if success else "FAILED"
        self._log(f"=== Iranian Archive Workflow {status} ===")
        self._log(f"Timestamp: {datetime.now().isoformat()}")
    
    def _log_processing_summary(self, summary) -> None:
        """Log processing summary."""
        self._log(f"=== Processing Summary ===")
        self._log(f"Total Archives: {summary.total_archives}")
        self._log(f"Successful: {summary.successful_archives}")
        self._log(f"Failed: {summary.failed_archives}")
        self._log(f"Files Downloaded: {summary.total_files_downloaded}")
        self._log(f"Files Failed: {summary.total_files_failed}")
        self._log(f"Execution Time: {summary.execution_time:.2f} seconds")
    
    def _log(self, message: str, verbose: bool = False) -> None:
        """Log a message."""
        if verbose and not self.verbose:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        
        print(log_message)
        
        # Also log to file if error handler is available
        if hasattr(self, 'error_handler'):
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(log_message + '\n')
            except Exception:
                pass  # Don't fail if logging fails


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Iranian Archive Workflow - Automated document archiving system with monitoring',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python workflow_orchestrator.py                    # Manual run
  python workflow_orchestrator.py --scheduled        # Scheduled run
  python workflow_orchestrator.py --dry-run          # Dry run (no changes)
  python workflow_orchestrator.py --verbose          # Verbose output
  python workflow_orchestrator.py --debug            # Enable debugging
  python workflow_orchestrator.py --no-monitoring    # Disable monitoring
  python workflow_orchestrator.py --config custom.yml # Custom config file
        """
    )
    
    parser.add_argument(
        '--scheduled',
        action='store_true',
        help='Run in scheduled mode (only process active publications)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making actual changes'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable detailed debugging output'
    )
    
    parser.add_argument(
        '--no-monitoring',
        action='store_true',
        help='Disable performance monitoring'
    )
    
    parser.add_argument(
        '--config', '-c',
        default='urls.yml',
        help='Path to configuration file (default: urls.yml)'
    )
    
    parser.add_argument(
        '--log-file', '-l',
        default='workflow.log',
        help='Path to log file (default: workflow.log)'
    )
    
    parser.add_argument(
        '--benchmark',
        action='store_true',
        help='Run in benchmark mode with detailed performance analysis'
    )
    
    return parser


def main() -> int:
    """Main entry point for the workflow."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    try:
        # Create orchestrator with monitoring options
        orchestrator = WorkflowOrchestrator(
            config_path=args.config,
            log_file=args.log_file,
            enable_monitoring=not args.no_monitoring,
            enable_debugging=args.debug or args.benchmark
        )
        
        # Set benchmark mode if requested
        if args.benchmark:
            orchestrator.verbose = True
            print("Running in benchmark mode with detailed performance analysis...")
        
        # Execute workflow
        success = orchestrator.execute_workflow(
            is_scheduled_run=args.scheduled,
            dry_run=args.dry_run,
            verbose=args.verbose or args.benchmark
        )
        
        # Print benchmark results if requested
        if args.benchmark and orchestrator.enable_monitoring:
            print("\n" + "="*60)
            print("BENCHMARK RESULTS")
            print("="*60)
            print(orchestrator._generate_performance_report())
            print("="*60)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nWorkflow interrupted by user")
        return 130
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())