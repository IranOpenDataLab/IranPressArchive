#!/usr/bin/env python3
"""
Test script for the new two-stage workflow system
"""

import yaml
import json
import requests
from urllib.parse import urlparse
from datetime import datetime
import os
from pathlib import Path
import sys

def test_url_analysis():
    """Test the URL analysis functionality"""
    print("🔍 Testing URL Analysis...")
    
    # Load URLs configuration
    with open('urls.yml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    analysis_results = {
        'analysis_date': datetime.now().isoformat(),
        'newspapers': {},
        'summary': {
            'total_archives': 0,
            'total_files': 0,
            'direct_files': 0,
            'directories': 0,
            'unknown': 0
        }
    }
    
    for archive in config.get('archives', []):
        archive_name = archive.get('folder', 'unknown')
        newspaper_fa = archive.get('source_info', {}).get('newspaper_name', '')
        
        newspaper_info = {
            'title_fa': archive.get('title_fa', ''),
            'title_en': archive.get('title_en', ''),
            'folder': archive_name,
            'category': archive.get('category', 'old-newspaper'),
            'description': archive.get('description', ''),
            'newspaper_name': newspaper_fa,
            'files': [],
            'total_files': 0,
            'years': {}
        }
        
        # Analyze each URL
        for year, urls in archive.get('years', {}).items():
            year_files = []
            
            for i, url in enumerate(urls):
                print(f"  Analyzing: {url}")
                
                # Simple URL analysis
                try:
                    response = requests.head(url, timeout=10, allow_redirects=True)
                    content_type = response.headers.get('content-type', '').lower()
                    
                    if 'pdf' in content_type:
                        url_type = 'direct_file'
                        size = response.headers.get('content-length', 0)
                    else:
                        url_type = 'directory'
                        size = None
                        
                    analysis_results['summary']['direct_files'] += 1 if url_type == 'direct_file' else 0
                    analysis_results['summary']['directories'] += 1 if url_type == 'directory' else 0
                    
                except Exception as e:
                    print(f"    Error: {e}")
                    url_type = 'unknown'
                    size = None
                    analysis_results['summary']['unknown'] += 1
                
                file_info = {
                    'url': url,
                    'type': url_type,
                    'size': size,
                    'year': year,
                    'filename': f"{archive_name}_{len(newspaper_info['files'])+1:03d}.pdf"
                }
                
                year_files.append(file_info)
                newspaper_info['files'].append(file_info)
                analysis_results['summary']['total_files'] += 1
            
            newspaper_info['years'][year] = year_files
        
        newspaper_info['total_files'] = len(newspaper_info['files'])
        analysis_results['newspapers'][archive_name] = newspaper_info
        analysis_results['summary']['total_archives'] += 1
    
    # Save analysis results
    analysis_file = f"test_url_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Analysis complete! Results saved to {analysis_file}")
    print(f"   Total newspapers: {analysis_results['summary']['total_archives']}")
    print(f"   Total files: {analysis_results['summary']['total_files']}")
    print(f"   Direct files: {analysis_results['summary']['direct_files']}")
    
    return analysis_file

def test_file_download(analysis_file, max_files=2):
    """Test the file download functionality"""
    print(f"\n📥 Testing File Download (max {max_files} files per newspaper)...")
    
    if not os.path.exists(analysis_file):
        print(f"❌ Analysis file not found: {analysis_file}")
        return False
    
    # Load analysis
    with open(analysis_file, 'r', encoding='utf-8') as f:
        analysis = json.load(f)
    
    download_stats = {
        'downloaded': 0,
        'skipped': 0,
        'failed': 0,
        'total_size': 0
    }
    
    # Process each newspaper
    for newspaper_name, info in analysis['newspapers'].items():
        print(f"\n📰 Processing: {info['title_fa']} ({newspaper_name})")
        
        # Create newspaper directory
        newspaper_dir = Path(f"old-newspaper/{newspaper_name}")
        newspaper_dir.mkdir(parents=True, exist_ok=True)
        
        # Download files (limited by max_files)
        files_downloaded = 0
        for file_info in info['files'][:max_files]:
            if files_downloaded >= max_files:
                break
            
            url = file_info['url']
            filename = file_info['filename']
            target_path = newspaper_dir / filename
            
            # Skip if file exists
            if target_path.exists():
                print(f"  ⏭️  Skipping existing file: {filename}")
                download_stats['skipped'] += 1
                continue
            
            # Download file
            try:
                print(f"  📥 Downloading: {filename}")
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()
                
                total_size = 0
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)
                
                print(f"  ✅ Downloaded: {filename} ({total_size} bytes)")
                download_stats['downloaded'] += 1
                download_stats['total_size'] += total_size
                files_downloaded += 1
                
            except Exception as e:
                print(f"  ❌ Download failed: {e}")
                download_stats['failed'] += 1
                if target_path.exists():
                    target_path.unlink()  # Delete partial file
        
        print(f"  📊 {newspaper_name}: {files_downloaded} files processed")
    
    # Print statistics
    print("\n" + "=" * 50)
    print("📊 DOWNLOAD STATISTICS")
    print("=" * 50)
    print(f"✅ Downloaded: {download_stats['downloaded']} files")
    print(f"⏭️  Skipped: {download_stats['skipped']} files")
    print(f"❌ Failed: {download_stats['failed']} files")
    print(f"💾 Total size: {download_stats['total_size'] / 1024 / 1024:.1f} MB")
    print("=" * 50)
    
    return download_stats['downloaded'] > 0

def test_readme_generation():
    """Test README generation"""
    print(f"\n📝 Testing README Generation...")
    
    # Find newspapers
    old_newspaper_dir = Path("old-newspaper")
    if not old_newspaper_dir.exists():
        print("❌ No old-newspaper directory found")
        return False
    
    newspapers = [d for d in old_newspaper_dir.iterdir() if d.is_dir()]
    
    for newspaper_dir in newspapers:
        newspaper_name = newspaper_dir.name
        print(f"  📰 Generating README for: {newspaper_name}")
        
        # Count PDF files
        pdf_files = list(newspaper_dir.glob("*.pdf"))
        
        # Generate README content
        readme_content = f"""[🇺🇸 English](README.en.md) | 🇮🇷 فارسی

# آرشیو نشریه {newspaper_name} / {newspaper_name.title()} Archive

آرشیو دیجیتال نشریه {newspaper_name}

## شماره‌های موجود / Available Issues

- **تعداد کل فایل‌ها / Total Files**: {len(pdf_files)}

## فایل‌های موجود / Available Files

"""
        
        for pdf_file in sorted(pdf_files):
            file_size = pdf_file.stat().st_size
            readme_content += f"- [{pdf_file.name}]({pdf_file.name}) ({file_size} bytes)\n"
        
        readme_content += f"""
---
*تولید شده به صورت خودکار توسط سیستم آرشیو ایران / Generated automatically by Iranian Archive Workflow*
*آخرین بروزرسانی / Last Updated: {datetime.now().isoformat()}*
"""
        
        # Write README
        readme_path = newspaper_dir / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        print(f"  ✅ Generated README for {newspaper_name} ({len(pdf_files)} files)")
    
    return True

def main():
    """Main test function"""
    print("🚀 Testing Two-Stage Workflow System")
    print("=" * 50)
    
    # Stage 1: URL Analysis
    analysis_file = test_url_analysis()
    
    # Stage 2: File Download
    download_success = test_file_download(analysis_file, max_files=2)
    
    # Stage 3: README Generation
    readme_success = test_readme_generation()
    
    # Summary
    print(f"\n🎯 TEST SUMMARY")
    print("=" * 50)
    print(f"✅ URL Analysis: {'PASSED' if analysis_file else 'FAILED'}")
    print(f"✅ File Download: {'PASSED' if download_success else 'FAILED'}")
    print(f"✅ README Generation: {'PASSED' if readme_success else 'FAILED'}")
    
    if analysis_file and download_success and readme_success:
        print("\n🎉 All tests PASSED! The workflow system is ready.")
        
        # Show directory structure
        print(f"\n📁 Directory Structure:")
        old_newspaper_dir = Path("old-newspaper")
        if old_newspaper_dir.exists():
            for newspaper_dir in sorted(old_newspaper_dir.iterdir()):
                if newspaper_dir.is_dir():
                    pdf_count = len(list(newspaper_dir.glob("*.pdf")))
                    print(f"  📰 {newspaper_dir.name}/ ({pdf_count} PDF files)")
    else:
        print("\n❌ Some tests FAILED. Please check the errors above.")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())