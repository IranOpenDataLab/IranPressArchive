"""
Performance Monitoring Utility

Standalone utility for monitoring and analyzing workflow performance,
providing detailed insights into system resource usage and optimization
opportunities.
"""

import os
import sys
import json
import time
import argparse
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None


class PerformanceMonitor:
    """Standalone performance monitoring utility with enhanced optimization features."""
    
    def __init__(self, output_dir: str = "performance_data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        self.performance_data: List[Dict[str, Any]] = []
        
        # System monitoring
        if PSUTIL_AVAILABLE:
            self.process = psutil.Process()
        else:
            self.process = None
        self.start_time = time.time()
        
        # Enhanced monitoring features
        self.execution_phases: List[Dict[str, Any]] = []
        self.memory_checkpoints: List[Dict[str, Any]] = []
        self.optimization_suggestions: List[str] = []
        self.performance_thresholds = {
            'max_memory_mb': 1000,
            'max_cpu_percent': 80,
            'max_execution_time': 300,
            'max_io_rate_mb_s': 100
        }
    
    def start_monitoring(self, interval: float = 0.5) -> None:
        """Start continuous performance monitoring."""
        if self.monitoring_active or not PSUTIL_AVAILABLE:
            if not PSUTIL_AVAILABLE:
                print("psutil not available - monitoring disabled")
            return
        
        self.monitoring_active = True
        self.performance_data.clear()
        self.start_time = time.time()
        
        def monitor_loop():
            """Main monitoring loop."""
            while self.monitoring_active:
                try:
                    timestamp = time.time()
                    
                    # System metrics
                    cpu_percent = self.process.cpu_percent()
                    memory_info = self.process.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024
                    
                    # I/O metrics
                    io_counters = self.process.io_counters()
                    
                    # System-wide metrics
                    system_cpu = psutil.cpu_percent()
                    system_memory = psutil.virtual_memory()
                    disk_usage = psutil.disk_usage('.')
                    
                    # Network metrics (if available)
                    network_io = psutil.net_io_counters()
                    
                    data_point = {
                        'timestamp': timestamp,
                        'elapsed_time': timestamp - self.start_time,
                        'process_cpu_percent': cpu_percent,
                        'process_memory_mb': memory_mb,
                        'process_memory_percent': self.process.memory_percent(),
                        'process_threads': self.process.num_threads(),
                        'process_open_files': len(self.process.open_files()),
                        'process_io_read_mb': io_counters.read_bytes / 1024 / 1024,
                        'process_io_write_mb': io_counters.write_bytes / 1024 / 1024,
                        'system_cpu_percent': system_cpu,
                        'system_memory_percent': system_memory.percent,
                        'system_memory_available_mb': system_memory.available / 1024 / 1024,
                        'disk_usage_percent': disk_usage.percent,
                        'network_bytes_sent': network_io.bytes_sent if network_io else 0,
                        'network_bytes_recv': network_io.bytes_recv if network_io else 0,
                    }
                    
                    self.performance_data.append(data_point)
                    
                    time.sleep(interval)
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                except Exception as e:
                    print(f"Monitoring error: {e}")
                    time.sleep(interval)
        
        self.monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitoring_thread.start()
        print(f"Performance monitoring started (interval: {interval}s)")
    
    def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=2.0)
        
        print(f"Performance monitoring stopped. Collected {len(self.performance_data)} data points.")
    
    def export_data(self, filename: Optional[str] = None) -> str:
        """Export performance data to JSON file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"performance_data_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(self.performance_data, f, indent=2)
        
        print(f"Performance data exported to {filepath}")
        return str(filepath)
    
    def add_execution_phase(self, phase_name: str, start_time: float, end_time: float, 
                           details: Dict[str, Any] = None) -> None:
        """Add execution phase timing information."""
        phase_info = {
            'phase': phase_name,
            'start_time': start_time,
            'end_time': end_time,
            'duration': end_time - start_time,
            'details': details or {}
        }
        self.execution_phases.append(phase_info)
    
    def add_memory_checkpoint(self, checkpoint_name: str, memory_mb: float, 
                             details: Dict[str, Any] = None) -> None:
        """Add memory usage checkpoint."""
        checkpoint = {
            'checkpoint': checkpoint_name,
            'timestamp': time.time(),
            'memory_mb': memory_mb,
            'details': details or {}
        }
        self.memory_checkpoints.append(checkpoint)
    
    def analyze_performance_bottlenecks(self) -> List[str]:
        """Analyze performance data to identify bottlenecks."""
        bottlenecks = []
        
        if not self.performance_data:
            return bottlenecks
        
        # Analyze execution phases
        if self.execution_phases:
            slowest_phase = max(self.execution_phases, key=lambda x: x.get('duration', 0))
            if slowest_phase.get('duration', 0) > 30:  # More than 30 seconds
                bottlenecks.append(f"Slow execution phase: {slowest_phase['phase']} "
                                 f"took {slowest_phase['duration']:.1f}s")
        
        # Analyze memory usage patterns
        if self.memory_checkpoints:
            memory_values = [cp['memory_mb'] for cp in self.memory_checkpoints]
            if memory_values:
                max_memory = max(memory_values)
                min_memory = min(memory_values)
                if max_memory - min_memory > 500:  # More than 500MB variation
                    bottlenecks.append(f"High memory variation: {max_memory - min_memory:.1f}MB")
        
        # Analyze performance data trends
        if len(self.performance_data) > 10:
            recent_data = self.performance_data[-10:]
            avg_recent_cpu = sum(d.get('process_cpu_percent', 0) for d in recent_data) / len(recent_data)
            avg_recent_memory = sum(d.get('process_memory_mb', 0) for d in recent_data) / len(recent_data)
            
            if avg_recent_cpu > self.performance_thresholds['max_cpu_percent']:
                bottlenecks.append(f"Sustained high CPU usage: {avg_recent_cpu:.1f}%")
            
            if avg_recent_memory > self.performance_thresholds['max_memory_mb']:
                bottlenecks.append(f"High memory usage: {avg_recent_memory:.1f}MB")
        
        return bottlenecks
    
    def generate_optimization_suggestions(self) -> List[str]:
        """Generate optimization suggestions based on performance analysis."""
        suggestions = []
        
        bottlenecks = self.analyze_performance_bottlenecks()
        
        for bottleneck in bottlenecks:
            if "Slow execution phase" in bottleneck:
                suggestions.append("Consider parallelizing slow operations or optimizing algorithms")
            elif "High memory variation" in bottleneck:
                suggestions.append("Implement memory pooling or reduce object creation/destruction")
            elif "Sustained high CPU usage" in bottleneck:
                suggestions.append("Add processing delays or implement rate limiting")
            elif "High memory usage" in bottleneck:
                suggestions.append("Implement memory cleanup or process data in smaller chunks")
        
        # General suggestions based on data patterns
        if self.performance_data:
            total_time = max(d.get('elapsed_time', 0) for d in self.performance_data)
            if total_time > self.performance_thresholds['max_execution_time']:
                suggestions.append("Consider breaking large operations into smaller batches")
        
        return suggestions
    
    def generate_report(self) -> str:
        """Generate comprehensive performance report with optimization insights."""
        if not self.performance_data:
            return "No performance data available."
        
        if not PANDAS_AVAILABLE:
            return self._generate_enhanced_basic_report()
        
        df = pd.DataFrame(self.performance_data)
        
        # Calculate statistics
        total_time = df['elapsed_time'].max()
        avg_cpu = df['process_cpu_percent'].mean()
        peak_cpu = df['process_cpu_percent'].max()
        avg_memory = df['process_memory_mb'].mean()
        peak_memory = df['process_memory_mb'].max()
        memory_delta = peak_memory - df['process_memory_mb'].iloc[0]
        
        # I/O statistics
        total_io_read = df['process_io_read_mb'].iloc[-1] - df['process_io_read_mb'].iloc[0]
        total_io_write = df['process_io_write_mb'].iloc[-1] - df['process_io_write_mb'].iloc[0]
        
        # System resource usage
        avg_system_cpu = df['system_cpu_percent'].mean()
        avg_system_memory = df['system_memory_percent'].mean()
        
        report = f"""
=== Enhanced Performance Analysis Report ===
Generated: {datetime.now().isoformat()}
Monitoring Duration: {total_time:.2f} seconds
Data Points Collected: {len(self.performance_data)}

=== Process Performance ===
CPU Usage:
  - Average: {avg_cpu:.1f}%
  - Peak: {peak_cpu:.1f}%
  - Threshold: {self.performance_thresholds['max_cpu_percent']}%

Memory Usage:
  - Average: {avg_memory:.1f} MB
  - Peak: {peak_memory:.1f} MB
  - Delta: {memory_delta:.1f} MB
  - Threshold: {self.performance_thresholds['max_memory_mb']} MB

I/O Operations:
  - Total Read: {total_io_read:.1f} MB
  - Total Write: {total_io_write:.1f} MB
  - I/O Rate: {(total_io_read + total_io_write) / total_time:.1f} MB/s

=== System Performance ===
System CPU Average: {avg_system_cpu:.1f}%
System Memory Average: {avg_system_memory:.1f}%

=== Execution Phases ===
"""
        
        # Add execution phase analysis
        if self.execution_phases:
            for phase in self.execution_phases:
                report += f"  {phase['phase']}: {phase['duration']:.2f}s\n"
        else:
            report += "  No phase timing data available\n"
        
        report += "\n=== Memory Checkpoints ===\n"
        if self.memory_checkpoints:
            for checkpoint in self.memory_checkpoints:
                report += f"  {checkpoint['checkpoint']}: {checkpoint['memory_mb']:.1f} MB\n"
        else:
            report += "  No memory checkpoint data available\n"
        
        # Performance insights and bottlenecks
        bottlenecks = self.analyze_performance_bottlenecks()
        report += "\n=== Performance Bottlenecks ===\n"
        if bottlenecks:
            for bottleneck in bottlenecks:
                report += f"⚠️  {bottleneck}\n"
        else:
            report += "✅ No significant bottlenecks detected\n"
        
        # Optimization suggestions
        suggestions = self.generate_optimization_suggestions()
        report += "\n=== Optimization Suggestions ===\n"
        if suggestions:
            for i, suggestion in enumerate(suggestions, 1):
                report += f"{i}. {suggestion}\n"
        else:
            report += "✅ Performance appears optimal\n"
        
        # Performance efficiency metrics
        if total_time > 0:
            io_efficiency = (total_io_read + total_io_write) / total_time
            memory_efficiency = peak_memory / total_time
            
            report += f"\n=== Efficiency Metrics ===\n"
            report += f"I/O Throughput: {io_efficiency:.1f} MB/s\n"
            report += f"Memory Efficiency: {memory_efficiency:.1f} MB/s\n"
            
            # Performance score (0-100)
            cpu_score = max(0, 100 - avg_cpu)
            memory_score = max(0, 100 - (memory_delta / 10))  # Penalize high memory usage
            time_score = max(0, 100 - (total_time / 10))  # Penalize long execution
            overall_score = (cpu_score + memory_score + time_score) / 3
            
            report += f"Overall Performance Score: {overall_score:.1f}/100\n"
        
        return report
    
    def _generate_enhanced_basic_report(self) -> str:
        """Generate enhanced basic performance report without pandas."""
        if not self.performance_data:
            return "No performance data available."
        
        # Calculate basic statistics manually
        total_time = max(d['elapsed_time'] for d in self.performance_data)
        cpu_values = [d['process_cpu_percent'] for d in self.performance_data]
        memory_values = [d['process_memory_mb'] for d in self.performance_data]
        
        avg_cpu = sum(cpu_values) / len(cpu_values)
        peak_cpu = max(cpu_values)
        avg_memory = sum(memory_values) / len(memory_values)
        peak_memory = max(memory_values)
        memory_delta = peak_memory - memory_values[0]
        
        # I/O statistics
        io_read_values = [d.get('process_io_read_mb', 0) for d in self.performance_data]
        io_write_values = [d.get('process_io_write_mb', 0) for d in self.performance_data]
        total_io_read = max(io_read_values) - min(io_read_values) if io_read_values else 0
        total_io_write = max(io_write_values) - min(io_write_values) if io_write_values else 0
        
        report = f"""
=== Enhanced Performance Analysis Report (Basic Mode) ===
Generated: {datetime.now().isoformat()}
Monitoring Duration: {total_time:.2f} seconds
Data Points Collected: {len(self.performance_data)}

=== Process Performance ===
CPU Usage:
  - Average: {avg_cpu:.1f}%
  - Peak: {peak_cpu:.1f}%
  - Threshold: {self.performance_thresholds['max_cpu_percent']}%

Memory Usage:
  - Average: {avg_memory:.1f} MB
  - Peak: {peak_memory:.1f} MB
  - Delta: {memory_delta:.1f} MB
  - Threshold: {self.performance_thresholds['max_memory_mb']} MB

I/O Operations:
  - Total Read: {total_io_read:.1f} MB
  - Total Write: {total_io_write:.1f} MB
  - I/O Rate: {(total_io_read + total_io_write) / total_time:.1f} MB/s

=== Execution Phases ===
"""
        
        # Add execution phase analysis
        if self.execution_phases:
            for phase in self.execution_phases:
                report += f"  {phase['phase']}: {phase['duration']:.2f}s\n"
        else:
            report += "  No phase timing data available\n"
        
        report += "\n=== Memory Checkpoints ===\n"
        if self.memory_checkpoints:
            for checkpoint in self.memory_checkpoints:
                report += f"  {checkpoint['checkpoint']}: {checkpoint['memory_mb']:.1f} MB\n"
        else:
            report += "  No memory checkpoint data available\n"
        
        # Performance insights and bottlenecks
        bottlenecks = self.analyze_performance_bottlenecks()
        report += "\n=== Performance Bottlenecks ===\n"
        if bottlenecks:
            for bottleneck in bottlenecks:
                report += f"⚠️  {bottleneck}\n"
        else:
            report += "✅ No significant bottlenecks detected\n"
        
        # Optimization suggestions
        suggestions = self.generate_optimization_suggestions()
        report += "\n=== Optimization Suggestions ===\n"
        if suggestions:
            for i, suggestion in enumerate(suggestions, 1):
                report += f"{i}. {suggestion}\n"
        else:
            report += "✅ Performance appears optimal\n"
        
        # Performance score
        cpu_score = max(0, 100 - avg_cpu)
        memory_score = max(0, 100 - (memory_delta / 10))
        time_score = max(0, 100 - (total_time / 10))
        overall_score = (cpu_score + memory_score + time_score) / 3
        
        report += f"\n=== Performance Score ===\n"
        report += f"Overall Performance Score: {overall_score:.1f}/100\n"
        
        return report
    
    def create_visualizations(self) -> List[str]:
        """Create performance visualization charts."""
        if not self.performance_data:
            return []
        
        if not MATPLOTLIB_AVAILABLE or not PANDAS_AVAILABLE:
            print("Matplotlib or pandas not available - skipping chart generation")
            return []
        
        df = pd.DataFrame(self.performance_data)
        chart_files = []
        
        # CPU Usage Chart
        plt.figure(figsize=(12, 8))
        
        plt.subplot(2, 2, 1)
        plt.plot(df['elapsed_time'], df['process_cpu_percent'], label='Process CPU')
        plt.plot(df['elapsed_time'], df['system_cpu_percent'], label='System CPU', alpha=0.7)
        plt.xlabel('Time (seconds)')
        plt.ylabel('CPU Usage (%)')
        plt.title('CPU Usage Over Time')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Memory Usage Chart
        plt.subplot(2, 2, 2)
        plt.plot(df['elapsed_time'], df['process_memory_mb'], label='Process Memory')
        plt.xlabel('Time (seconds)')
        plt.ylabel('Memory Usage (MB)')
        plt.title('Memory Usage Over Time')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # I/O Operations Chart
        plt.subplot(2, 2, 3)
        plt.plot(df['elapsed_time'], df['process_io_read_mb'], label='Read')
        plt.plot(df['elapsed_time'], df['process_io_write_mb'], label='Write')
        plt.xlabel('Time (seconds)')
        plt.ylabel('I/O (MB)')
        plt.title('Disk I/O Over Time')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Resource Utilization Chart
        plt.subplot(2, 2, 4)
        plt.plot(df['elapsed_time'], df['process_threads'], label='Threads')
        plt.plot(df['elapsed_time'], df['process_open_files'], label='Open Files')
        plt.xlabel('Time (seconds)')
        plt.ylabel('Count')
        plt.title('Resource Utilization')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        chart_file = self.output_dir / f"performance_charts_{timestamp}.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        chart_files.append(str(chart_file))
        print(f"Performance charts saved to {chart_file}")
        
        return chart_files
    
    def analyze_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends and patterns."""
        if not self.performance_data:
            return {}
        
        if not PANDAS_AVAILABLE:
            return self._analyze_trends_basic()
        
        df = pd.DataFrame(self.performance_data)
        
        analysis = {
            'duration': df['elapsed_time'].max(),
            'cpu_trend': 'increasing' if df['process_cpu_percent'].iloc[-1] > df['process_cpu_percent'].iloc[0] else 'decreasing',
            'memory_trend': 'increasing' if df['process_memory_mb'].iloc[-1] > df['process_memory_mb'].iloc[0] else 'decreasing',
            'peak_periods': [],
            'efficiency_score': 0.0
        }
        
        # Identify peak usage periods
        cpu_threshold = df['process_cpu_percent'].quantile(0.9)
        memory_threshold = df['process_memory_mb'].quantile(0.9)
        
        high_cpu_periods = df[df['process_cpu_percent'] > cpu_threshold]
        high_memory_periods = df[df['process_memory_mb'] > memory_threshold]
        
        if not high_cpu_periods.empty:
            analysis['peak_periods'].append({
                'type': 'high_cpu',
                'start_time': high_cpu_periods['elapsed_time'].min(),
                'end_time': high_cpu_periods['elapsed_time'].max(),
                'peak_value': high_cpu_periods['process_cpu_percent'].max()
            })
        
        if not high_memory_periods.empty:
            analysis['peak_periods'].append({
                'type': 'high_memory',
                'start_time': high_memory_periods['elapsed_time'].min(),
                'end_time': high_memory_periods['elapsed_time'].max(),
                'peak_value': high_memory_periods['process_memory_mb'].max()
            })
        
        # Calculate efficiency score (0-100)
        cpu_efficiency = max(0, 100 - df['process_cpu_percent'].mean())
        memory_stability = max(0, 100 - (df['process_memory_mb'].std() / df['process_memory_mb'].mean() * 100))
        analysis['efficiency_score'] = (cpu_efficiency + memory_stability) / 2
        
        return analysis
    
    def _analyze_trends_basic(self) -> Dict[str, Any]:
        """Analyze performance trends without pandas."""
        if not self.performance_data:
            return {}
        
        cpu_values = [d['process_cpu_percent'] for d in self.performance_data]
        memory_values = [d['process_memory_mb'] for d in self.performance_data]
        
        analysis = {
            'duration': max(d['elapsed_time'] for d in self.performance_data),
            'cpu_trend': 'increasing' if cpu_values[-1] > cpu_values[0] else 'decreasing',
            'memory_trend': 'increasing' if memory_values[-1] > memory_values[0] else 'decreasing',
            'peak_periods': [],
            'efficiency_score': 0.0
        }
        
        # Calculate efficiency score
        avg_cpu = sum(cpu_values) / len(cpu_values)
        memory_std = (sum((x - sum(memory_values)/len(memory_values))**2 for x in memory_values) / len(memory_values))**0.5
        memory_mean = sum(memory_values) / len(memory_values)
        
        cpu_efficiency = max(0, 100 - avg_cpu)
        memory_stability = max(0, 100 - (memory_std / memory_mean * 100)) if memory_mean > 0 else 0
        analysis['efficiency_score'] = (cpu_efficiency + memory_stability) / 2
        
        return analysis


def monitor_workflow_execution(config_path: str = 'urls.yml', 
                             monitoring_interval: float = 0.5,
                             output_dir: str = 'performance_data') -> None:
    """Monitor a workflow execution and generate performance report."""
    monitor = PerformanceMonitor(output_dir)
    
    try:
        # Start monitoring
        monitor.start_monitoring(monitoring_interval)
        
        # Import and run workflow
        from workflow_orchestrator import WorkflowOrchestrator
        
        orchestrator = WorkflowOrchestrator(
            config_path=config_path,
            enable_monitoring=True,
            enable_debugging=True
        )
        
        print("Starting monitored workflow execution...")
        success = orchestrator.execute_workflow(dry_run=True, verbose=True)
        
        print(f"Workflow completed: {'SUCCESS' if success else 'FAILED'}")
        
    finally:
        # Stop monitoring and generate reports
        monitor.stop_monitoring()
        
        if monitor.performance_data:
            # Export data
            data_file = monitor.export_data()
            
            # Generate report
            report = monitor.generate_report()
            report_file = monitor.output_dir / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            # Ensure output directory exists
            monitor.output_dir.mkdir(exist_ok=True)
            
            with open(report_file, 'w') as f:
                f.write(report)
            
            print(f"Performance report saved to {report_file}")
            print(report)
            
            # Create visualizations
            try:
                chart_files = monitor.create_visualizations()
                if chart_files:
                    print(f"Performance charts created: {', '.join(chart_files)}")
            except ImportError:
                print("Matplotlib not available - skipping chart generation")
            
            # Analyze trends
            trends = monitor.analyze_performance_trends()
            print(f"\nPerformance Analysis:")
            print(f"  Efficiency Score: {trends.get('efficiency_score', 0):.1f}/100")
            print(f"  CPU Trend: {trends.get('cpu_trend', 'unknown')}")
            print(f"  Memory Trend: {trends.get('memory_trend', 'unknown')}")


def main():
    """Main entry point for performance monitoring utility."""
    parser = argparse.ArgumentParser(
        description='Performance monitoring utility for Iranian Archive Workflow'
    )
    
    parser.add_argument(
        '--config', '-c',
        default='urls.yml',
        help='Path to workflow configuration file'
    )
    
    parser.add_argument(
        '--interval', '-i',
        type=float,
        default=0.5,
        help='Monitoring interval in seconds (default: 0.5)'
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        default='performance_data',
        help='Output directory for performance data (default: performance_data)'
    )
    
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only analyze existing performance data files'
    )
    
    args = parser.parse_args()
    
    if args.analyze_only:
        # Analyze existing data files
        output_dir = Path(args.output_dir)
        if not output_dir.exists():
            print(f"Output directory {output_dir} does not exist")
            return 1
        
        json_files = list(output_dir.glob('performance_data_*.json'))
        if not json_files:
            print(f"No performance data files found in {output_dir}")
            return 1
        
        # Analyze the most recent file
        latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
        print(f"Analyzing {latest_file}")
        
        monitor = PerformanceMonitor(args.output_dir)
        with open(latest_file, 'r') as f:
            monitor.performance_data = json.load(f)
        
        report = monitor.generate_report()
        print(report)
        
        try:
            monitor.create_visualizations()
        except ImportError:
            print("Matplotlib not available - skipping chart generation")
        
    else:
        # Monitor workflow execution
        monitor_workflow_execution(
            config_path=args.config,
            monitoring_interval=args.interval,
            output_dir=args.output_dir
        )
    
    return 0


if __name__ == '__main__':
    sys.exit(main())