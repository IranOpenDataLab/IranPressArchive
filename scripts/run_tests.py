#!/usr/bin/env python3
"""
Comprehensive test runner for the Iranian Archive Workflow.

This script provides a unified interface for running all test suites
with proper configuration, reporting, and performance monitoring.
"""

import unittest
import sys
import os
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any
import json
from datetime import datetime

# Try to import psutil for memory monitoring, but make it optional
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Add scripts directory to Python path
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))


class TestRunner:
    """Comprehensive test runner with reporting and monitoring."""
    
    def __init__(self, verbose: bool = False, buffer: bool = True):
        """Initialize test runner."""
        self.verbose = verbose
        self.buffer = buffer
        self.results = {}
        self.start_time = None
        self.process = psutil.Process() if HAS_PSUTIL else None
        self.initial_memory = None
        
    def setup_environment(self):
        """Set up test environment."""
        # Ensure we're in the correct directory
        os.chdir(scripts_dir.parent)
        
        # Record initial metrics
        self.start_time = time.time()
        self.initial_memory = (self.process.memory_info().rss / 1024 / 1024 
                              if HAS_PSUTIL and self.process else 0.0)  # MB
        
        print("=" * 70)
        print("Iranian Archive Workflow - Test Suite")
        print("=" * 70)
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Python version: {sys.version}")
        print(f"Working directory: {os.getcwd()}")
        if HAS_PSUTIL:
            print(f"Initial memory: {self.initial_memory:.2f} MB")
        else:
            print("Memory monitoring unavailable (psutil not installed)")
        print()
    
    def run_test_suite(self, test_module: str, suite_name: str) -> Dict[str, Any]:
        """Run a specific test suite and return results."""
        print(f"Running {suite_name}...")
        print("-" * 50)
        
        suite_start_time = time.time()
        suite_start_memory = (self.process.memory_info().rss / 1024 / 1024 
                             if HAS_PSUTIL and self.process else 0.0)
        
        try:
            # Discover and run tests
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromName(test_module)
            
            runner = unittest.TextTestRunner(
                verbosity=2 if self.verbose else 1,
                buffer=self.buffer,
                stream=sys.stdout
            )
            
            result = runner.run(suite)
            
            suite_end_time = time.time()
            suite_end_memory = (self.process.memory_info().rss / 1024 / 1024 
                               if HAS_PSUTIL and self.process else 0.0)
            
            # Calculate metrics
            execution_time = suite_end_time - suite_start_time
            memory_delta = suite_end_memory - suite_start_memory
            
            suite_results = {
                'name': suite_name,
                'module': test_module,
                'tests_run': result.testsRun,
                'failures': len(result.failures),
                'errors': len(result.errors),
                'skipped': len(getattr(result, 'skipped', [])),
                'success_rate': ((result.testsRun - len(result.failures) - len(result.errors)) / 
                               max(result.testsRun, 1)) * 100,
                'execution_time': execution_time,
                'memory_delta': memory_delta,
                'failure_details': [
                    {'test': str(test), 'traceback': traceback}
                    for test, traceback in result.failures
                ],
                'error_details': [
                    {'test': str(test), 'traceback': traceback}
                    for test, traceback in result.errors
                ]
            }
            
            # Print summary
            print(f"\n{suite_name} Results:")
            print(f"  Tests run: {result.testsRun}")
            print(f"  Failures: {len(result.failures)}")
            print(f"  Errors: {len(result.errors)}")
            print(f"  Success rate: {suite_results['success_rate']:.1f}%")
            print(f"  Execution time: {execution_time:.2f}s")
            if HAS_PSUTIL:
                print(f"  Memory delta: {memory_delta:+.2f}MB")
            
            if result.failures:
                print(f"  ❌ {len(result.failures)} test(s) failed")
            if result.errors:
                print(f"  💥 {len(result.errors)} test(s) had errors")
            if result.testsRun > 0 and not result.failures and not result.errors:
                print(f"  ✅ All tests passed!")
            
            print()
            
            return suite_results
            
        except Exception as e:
            print(f"❌ Failed to run {suite_name}: {e}")
            return {
                'name': suite_name,
                'module': test_module,
                'tests_run': 0,
                'failures': 0,
                'errors': 1,
                'skipped': 0,
                'success_rate': 0.0,
                'execution_time': 0.0,
                'memory_delta': 0.0,
                'failure_details': [],
                'error_details': [{'test': 'Suite execution', 'traceback': str(e)}]
            }
    
    def run_all_tests(self, test_categories: List[str] = None) -> Dict[str, Any]:
        """Run all test suites."""
        self.setup_environment()
        
        # Define test suites
        test_suites = {
            'unit': [
                ('test_config_parser', 'Configuration Parser Tests'),
                ('test_file_manager', 'File Manager Tests'),
                ('test_error_handler', 'Error Handler Tests'),
                ('test_state_manager', 'State Manager Tests'),
                ('test_readme_generator', 'README Generator Tests'),
                ('test_category_processor', 'Category Processor Tests'),
                ('test_workflow_orchestrator', 'Workflow Orchestrator Tests'),
                ('test_security_validation', 'Security Validation Tests'),
            ],
            'integration': [
                ('test_integration', 'Integration Tests'),
            ],
            'performance': [
                ('test_performance', 'Performance Tests'),
            ],
            'error_simulation': [
                ('test_error_simulation', 'Error Simulation Tests'),
            ]
        }
        
        # Filter test categories if specified
        if test_categories:
            filtered_suites = {}
            for category in test_categories:
                if category in test_suites:
                    filtered_suites[category] = test_suites[category]
                else:
                    print(f"Warning: Unknown test category '{category}'")
            test_suites = filtered_suites
        
        # Run test suites
        all_results = {}
        
        for category, suites in test_suites.items():
            print(f"\n{'=' * 20} {category.upper()} TESTS {'=' * 20}")
            category_results = []
            
            for test_module, suite_name in suites:
                try:
                    result = self.run_test_suite(test_module, suite_name)
                    category_results.append(result)
                except KeyboardInterrupt:
                    print("\n⚠️  Test execution interrupted by user")
                    break
                except Exception as e:
                    print(f"❌ Unexpected error running {suite_name}: {e}")
                    continue
            
            all_results[category] = category_results
        
        # Generate final report
        return self.generate_final_report(all_results)
    
    def generate_final_report(self, all_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Generate comprehensive final report."""
        end_time = time.time()
        final_memory = (self.process.memory_info().rss / 1024 / 1024 
                       if HAS_PSUTIL and self.process else 0.0)
        
        total_execution_time = end_time - self.start_time
        total_memory_delta = final_memory - self.initial_memory
        
        # Aggregate statistics
        total_tests = 0
        total_failures = 0
        total_errors = 0
        total_skipped = 0
        
        for category_results in all_results.values():
            for result in category_results:
                total_tests += result['tests_run']
                total_failures += result['failures']
                total_errors += result['errors']
                total_skipped += result['skipped']
        
        overall_success_rate = ((total_tests - total_failures - total_errors) / 
                              max(total_tests, 1)) * 100
        
        # Create final report
        final_report = {
            'timestamp': datetime.now().isoformat(),
            'execution_time': total_execution_time,
            'memory_delta': total_memory_delta,
            'summary': {
                'total_tests': total_tests,
                'total_failures': total_failures,
                'total_errors': total_errors,
                'total_skipped': total_skipped,
                'success_rate': overall_success_rate
            },
            'categories': all_results,
            'system_info': {
                'python_version': sys.version,
                'platform': sys.platform,
                'initial_memory_mb': self.initial_memory,
                'final_memory_mb': final_memory
            }
        }
        
        # Print final summary
        print("\n" + "=" * 70)
        print("FINAL TEST SUMMARY")
        print("=" * 70)
        print(f"Total execution time: {total_execution_time:.2f}s")
        if HAS_PSUTIL:
            print(f"Total memory delta: {total_memory_delta:+.2f}MB")
        print()
        print(f"Tests run: {total_tests}")
        print(f"Failures: {total_failures}")
        print(f"Errors: {total_errors}")
        print(f"Skipped: {total_skipped}")
        print(f"Overall success rate: {overall_success_rate:.1f}%")
        print()
        
        # Category breakdown
        for category, results in all_results.items():
            category_tests = sum(r['tests_run'] for r in results)
            category_failures = sum(r['failures'] for r in results)
            category_errors = sum(r['errors'] for r in results)
            category_success_rate = ((category_tests - category_failures - category_errors) / 
                                   max(category_tests, 1)) * 100
            
            status_icon = "✅" if category_success_rate == 100 else "⚠️" if category_success_rate >= 80 else "❌"
            print(f"{status_icon} {category.upper()}: {category_tests} tests, "
                  f"{category_success_rate:.1f}% success rate")
        
        print()
        
        # Overall status
        if overall_success_rate == 100:
            print("🎉 ALL TESTS PASSED!")
        elif overall_success_rate >= 90:
            print("✅ Tests mostly successful")
        elif overall_success_rate >= 70:
            print("⚠️  Some tests failed - review needed")
        else:
            print("❌ Many tests failed - immediate attention required")
        
        print("=" * 70)
        
        return final_report
    
    def save_report(self, report: Dict[str, Any], filename: str = None):
        """Save test report to file."""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'test_report_{timestamp}.json'
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Test report saved to: {filename}")
    
    def print_failure_details(self, report: Dict[str, Any]):
        """Print detailed failure information."""
        has_failures = False
        
        for category, results in report['categories'].items():
            for result in results:
                if result['failures'] or result['errors']:
                    if not has_failures:
                        print("\n" + "=" * 70)
                        print("FAILURE DETAILS")
                        print("=" * 70)
                        has_failures = True
                    
                    print(f"\n{result['name']}:")
                    
                    for failure in result['failure_details']:
                        print(f"  ❌ FAILURE: {failure['test']}")
                        if self.verbose:
                            print(f"     {failure['traceback']}")
                    
                    for error in result['error_details']:
                        print(f"  💥 ERROR: {error['test']}")
                        if self.verbose:
                            print(f"     {error['traceback']}")


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(
        description='Run Iranian Archive Workflow test suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                           # Run all tests
  python run_tests.py --categories unit         # Run only unit tests
  python run_tests.py --categories unit integration  # Run unit and integration tests
  python run_tests.py --verbose --save-report  # Verbose output with saved report
  python run_tests.py --quick                   # Run only fast tests
        """
    )
    
    parser.add_argument(
        '--categories',
        nargs='+',
        choices=['unit', 'integration', 'performance', 'error_simulation'],
        help='Test categories to run (default: all)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output with detailed failure information'
    )
    
    parser.add_argument(
        '--save-report',
        action='store_true',
        help='Save test report to JSON file'
    )
    
    parser.add_argument(
        '--report-file',
        help='Custom filename for test report'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run only quick tests (unit tests only)'
    )
    
    parser.add_argument(
        '--no-buffer',
        action='store_true',
        help='Disable output buffering (show output immediately)'
    )
    
    args = parser.parse_args()
    
    # Handle quick mode
    if args.quick:
        args.categories = ['unit']
    
    # Create test runner
    runner = TestRunner(
        verbose=args.verbose,
        buffer=not args.no_buffer
    )
    
    try:
        # Run tests
        report = runner.run_all_tests(args.categories)
        
        # Print failure details if verbose
        if args.verbose:
            runner.print_failure_details(report)
        
        # Save report if requested
        if args.save_report:
            runner.save_report(report, args.report_file)
        
        # Exit with appropriate code
        success_rate = report['summary']['success_rate']
        if success_rate == 100:
            sys.exit(0)  # All tests passed
        elif success_rate >= 80:
            sys.exit(1)  # Some failures but mostly working
        else:
            sys.exit(2)  # Many failures
            
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()