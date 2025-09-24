#!/usr/bin/env python3
"""
Wikipedia Information Fetcher for Iranian Archive Workflow

This module fetches information about Iranian newspapers and publications
from Wikipedia (both Persian and English) to enrich README files.
"""

import re
import time
import requests
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import quote
import logging

from error_handler import ErrorHandler


@dataclass
class WikipediaInfo:
    """Information retrieved from Wikipedia about a publication."""
    title: str
    summary: str
    full_text: str
    url: str
    language: str
    categories: List[str]
    infobox_data: Dict[str, str]
    images: List[str]


class WikipediaFetcher:
    """Fetches information about publications from Wikipedia."""
    
    def __init__(self, error_handler: ErrorHandler = None):
        """Initialize the Wikipedia fetcher."""
        self.error_handler = error_handler or ErrorHandler()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Iranian Archive Workflow/1.0 (https://github.com/user/IranPressArchive)'
        })
        
        # Wikipedia API endpoints
        self.fa_api_url = "https://fa.wikipedia.org/api/rest_v1"
        self.en_api_url = "https://en.wikipedia.org/api/rest_v1"
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Cache for avoiding repeated requests
        self.cache: Dict[str, WikipediaInfo] = {}
    
    def get_newspaper_info(self, newspaper_name: str) -> Optional[WikipediaInfo]:
        """
        Get information about a newspaper from Wikipedia.
        
        Args:
            newspaper_name: Name of the newspaper (Persian or English)
            
        Returns:
            WikipediaInfo object if found, None otherwise
        """
        # Check cache first
        cache_key = newspaper_name.lower().strip()
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Try different search variations for Persian Wikipedia
        search_terms = [
            newspaper_name,
            f"روزنامه {newspaper_name}",
            f"نشریه {newspaper_name}",
            f"{newspaper_name} (روزنامه)"
        ]
        
        info = None
        for term in search_terms:
            info = self._search_wikipedia(term, 'fa')
            if info:
                break
        
        # If not found, try English Wikipedia
        if not info:
            # Convert Persian name to possible English equivalents
            english_variants = self._get_english_variants(newspaper_name)
            for variant in english_variants:
                # Try different variations for English too
                english_terms = [
                    variant,
                    f"{variant} newspaper",
                    f"{variant} (newspaper)"
                ]
                
                for term in english_terms:
                    info = self._search_wikipedia(term, 'en')
                    if info:
                        break
                
                if info:
                    break
        
        # Cache the result (even if None)
        self.cache[cache_key] = info
        
        return info
    
    def _search_wikipedia(self, query: str, language: str) -> Optional[WikipediaInfo]:
        """Search for a page on Wikipedia."""
        try:
            # First, search for the page
            search_results = self._search_pages(query, language)
            
            if not search_results:
                return None
            
            # Get the best match
            best_match = self._find_best_match(query, search_results)
            
            if not best_match:
                return None
            
            # Get detailed page information
            page_info = self._get_page_info(best_match['title'], language)
            
            return page_info
            
        except Exception as e:
            self.logger.warning(f"Error searching Wikipedia for '{query}': {e}")
            return None
    
    def _search_pages(self, query: str, language: str) -> List[Dict]:
        """Search for pages using Wikipedia search API."""
        api_url = self.fa_api_url if language == 'fa' else self.en_api_url
        
        # Use opensearch API for initial search
        search_url = f"https://{language}.wikipedia.org/w/api.php"
        params = {
            'action': 'opensearch',
            'search': query,
            'limit': 10,
            'namespace': 0,
            'format': 'json'
        }
        
        response = self.session.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Parse opensearch results
        if len(data) >= 2 and data[1]:
            results = []
            titles = data[1]
            descriptions = data[2] if len(data) > 2 else []
            urls = data[3] if len(data) > 3 else []
            
            for i, title in enumerate(titles):
                results.append({
                    'title': title,
                    'description': descriptions[i] if i < len(descriptions) else '',
                    'url': urls[i] if i < len(urls) else ''
                })
            
            return results
        
        return []
    
    def _find_best_match(self, query: str, search_results: List[Dict]) -> Optional[Dict]:
        """Find the best matching page from search results."""
        query_lower = query.lower().strip()
        
        # Avoid disambiguation pages
        disambiguation_indicators = ['ابهام‌زدایی', 'disambiguation', 'ممکن است یکی از موارد زیر باشد']
        
        # Look for exact matches first (but not disambiguation)
        for result in search_results:
            title_lower = result['title'].lower()
            description_lower = result.get('description', '').lower()
            
            # Skip disambiguation pages
            is_disambiguation = any(indicator in title_lower or indicator in description_lower 
                                  for indicator in disambiguation_indicators)
            if is_disambiguation:
                continue
                
            if query_lower == title_lower:
                return result
        
        # Look for newspaper-specific matches
        newspaper_indicators = [
            'روزنامه', 'نشریه', 'مجله', 'هفته‌نامه', 'ماهنامه',
            'newspaper', 'publication', 'magazine', 'weekly', 'monthly'
        ]
        
        # Prioritize results with newspaper indicators
        newspaper_results = []
        other_results = []
        
        for result in search_results:
            title_lower = result['title'].lower()
            description_lower = result.get('description', '').lower()
            
            # Skip disambiguation pages
            is_disambiguation = any(indicator in title_lower or indicator in description_lower 
                                  for indicator in disambiguation_indicators)
            if is_disambiguation:
                continue
            
            # Check if it's likely a newspaper/publication
            is_newspaper = any(indicator in title_lower or indicator in description_lower 
                             for indicator in newspaper_indicators)
            
            if is_newspaper:
                newspaper_results.append(result)
            else:
                other_results.append(result)
        
        # Look for matches in newspaper results first
        for result in newspaper_results:
            title_lower = result['title'].lower()
            # Extract newspaper name from query
            query_name = query_lower.replace('روزنامه', '').replace('نشریه', '').strip()
            
            if query_name in title_lower:
                return result
        
        # If no newspaper match, look in other results
        for result in other_results:
            title_lower = result['title'].lower()
            query_name = query_lower.replace('روزنامه', '').replace('نشریه', '').strip()
            
            if query_name in title_lower:
                return result
        
        # Return first newspaper result if available
        if newspaper_results:
            return newspaper_results[0]
        
        # Return first non-disambiguation result
        if other_results:
            return other_results[0]
        
        return None
    
    def _get_page_info(self, title: str, language: str) -> Optional[WikipediaInfo]:
        """Get detailed information about a Wikipedia page."""
        try:
            api_url = self.fa_api_url if language == 'fa' else self.en_api_url
            
            # Get page summary
            summary_url = f"{api_url}/page/summary/{quote(title)}"
            summary_response = self.session.get(summary_url, timeout=10)
            summary_response.raise_for_status()
            summary_data = summary_response.json()
            
            # Check if this is a disambiguation page
            summary_text = summary_data.get('extract', '')
            disambiguation_indicators = [
                'ممکن است یکی از موارد زیر باشد',
                'may refer to',
                'disambiguation'
            ]
            
            is_disambiguation = any(indicator in summary_text.lower() 
                                  for indicator in disambiguation_indicators)
            
            if is_disambiguation:
                self.logger.debug(f"Skipping disambiguation page: {title}")
                return None
            
            # Get full page content
            content_url = f"https://{language}.wikipedia.org/w/api.php"
            content_params = {
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'extracts|categories|pageimages',
                'exintro': True,
                'explaintext': True,
                'exsectionformat': 'plain',
                'piprop': 'original'
            }
            
            content_response = self.session.get(content_url, params=content_params, timeout=10)
            content_response.raise_for_status()
            content_data = content_response.json()
            
            # Parse the response
            pages = content_data.get('query', {}).get('pages', {})
            if not pages:
                return None
            
            page_data = next(iter(pages.values()))
            
            # Extract information
            extract = page_data.get('extract', '')
            categories = [cat['title'].replace('رده:', '').replace('Category:', '') 
                         for cat in page_data.get('categories', [])]
            
            # Double-check for disambiguation in categories
            is_disambiguation_cat = any('ابهام‌زدایی' in cat or 'disambiguation' in cat.lower() 
                                      for cat in categories)
            
            if is_disambiguation_cat:
                self.logger.debug(f"Skipping disambiguation page (by category): {title}")
                return None
            
            # Get page images
            images = []
            if 'pageimage' in page_data:
                images.append(page_data['pageimage'])
            
            # Create WikipediaInfo object
            wiki_info = WikipediaInfo(
                title=summary_data.get('title', title),
                summary=summary_data.get('extract', ''),
                full_text=extract,
                url=summary_data.get('content_urls', {}).get('desktop', {}).get('page', ''),
                language=language,
                categories=categories,
                infobox_data={},  # Could be enhanced to parse infobox
                images=images
            )
            
            return wiki_info
            
        except Exception as e:
            self.logger.warning(f"Error getting page info for '{title}': {e}")
            return None
    
    def _get_english_variants(self, persian_name: str) -> List[str]:
        """Get possible English variants of a Persian newspaper name."""
        # Common Persian to English newspaper name mappings
        name_mappings = {
            'نشاط': ['Neshat', 'Neshaat'],
            'توس': ['Tous', 'Toos'],
            'جامعه': ['Jameh', 'Jaameh'],
            'عصر آزادگان': ['Asr-e Azadegan', 'Asr Azadegan'],
            'کیهان': ['Kayhan', 'Keyhan'],
            'اطلاعات': ['Ettelaat', 'Ettela\'at'],
            'جمهوری اسلامی': ['Jomhouri-ye Eslami', 'Islamic Republic'],
            'ایران': ['Iran'],
            'همشهری': ['Hamshahri'],
            'شرق': ['Shargh'],
            'اعتماد': ['Etemad'],
            'آرمان': ['Arman'],
            'ابرار': ['Abrar'],
            'رسالت': ['Resalat'],
            'وطن امروز': ['Vatan-e Emrooz'],
            'صبح امروز': ['Sobh-e Emrooz']
        }
        
        variants = []
        
        # Check direct mappings
        if persian_name in name_mappings:
            variants.extend(name_mappings[persian_name])
        
        # Add transliterated versions
        transliterated = self._transliterate_persian(persian_name)
        if transliterated:
            variants.append(transliterated)
        
        # Add the original name as well
        variants.append(persian_name)
        
        return list(set(variants))  # Remove duplicates
    
    def _transliterate_persian(self, persian_text: str) -> str:
        """Basic Persian to English transliteration."""
        # Simple character mapping for basic transliteration
        char_map = {
            'ا': 'a', 'آ': 'aa', 'ب': 'b', 'پ': 'p', 'ت': 't', 'ث': 's',
            'ج': 'j', 'چ': 'ch', 'ح': 'h', 'خ': 'kh', 'د': 'd', 'ذ': 'z',
            'ر': 'r', 'ز': 'z', 'ژ': 'zh', 'س': 's', 'ش': 'sh', 'ص': 's',
            'ض': 'z', 'ط': 't', 'ظ': 'z', 'ع': 'a', 'غ': 'gh', 'ف': 'f',
            'ق': 'gh', 'ک': 'k', 'گ': 'g', 'ل': 'l', 'م': 'm', 'ن': 'n',
            'و': 'o', 'ه': 'h', 'ی': 'i', 'ء': '', ' ': '-'
        }
        
        result = ''
        for char in persian_text:
            result += char_map.get(char, char)
        
        # Clean up the result
        result = re.sub(r'-+', '-', result)  # Multiple dashes to single
        result = result.strip('-')  # Remove leading/trailing dashes
        
        return result.title()  # Capitalize first letters
    
    def format_wikipedia_info_for_readme(self, wiki_info: WikipediaInfo, language: str = 'fa') -> str:
        """Format Wikipedia information for inclusion in README."""
        if not wiki_info:
            return ""
        
        if language == 'fa':
            content = f"\n## درباره نشریه / About the Publication\n\n"
            
            if wiki_info.summary:
                # Limit summary length
                summary = wiki_info.summary
                if len(summary) > 500:
                    summary = summary[:500] + "..."
                
                content += f"{summary}\n\n"
            
            if wiki_info.url:
                content += f"**منبع اطلاعات / Information Source:** [ویکی‌پدیا]({wiki_info.url})\n\n"
            
            # Add categories if relevant
            relevant_categories = [cat for cat in wiki_info.categories 
                                 if any(keyword in cat.lower() for keyword in 
                                       ['روزنامه', 'نشریه', 'مطبوعات', 'newspaper', 'publication', 'press'])]
            
            if relevant_categories:
                content += f"**دسته‌بندی / Categories:** {', '.join(relevant_categories[:3])}\n\n"
        
        else:  # English
            content = f"\n## About the Publication\n\n"
            
            if wiki_info.summary:
                summary = wiki_info.summary
                if len(summary) > 500:
                    summary = summary[:500] + "..."
                
                content += f"{summary}\n\n"
            
            if wiki_info.url:
                content += f"**Information Source:** [Wikipedia]({wiki_info.url})\n\n"
            
            relevant_categories = [cat for cat in wiki_info.categories 
                                 if any(keyword in cat.lower() for keyword in 
                                       ['newspaper', 'publication', 'press', 'media'])]
            
            if relevant_categories:
                content += f"**Categories:** {', '.join(relevant_categories[:3])}\n\n"
        
        return content


def get_newspaper_wikipedia_info(newspaper_name: str) -> Optional[WikipediaInfo]:
    """
    Convenience function to get Wikipedia information for a newspaper.
    
    Args:
        newspaper_name: Name of the newspaper
        
    Returns:
        WikipediaInfo object if found, None otherwise
    """
    fetcher = WikipediaFetcher()
    return fetcher.get_newspaper_info(newspaper_name)


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch Wikipedia information for newspapers')
    parser.add_argument('newspaper', help='Name of the newspaper')
    parser.add_argument('--language', '-l', choices=['fa', 'en'], default='fa', 
                       help='Language preference for Wikipedia')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Fetch information
    print(f"🔍 Searching Wikipedia for: {args.newspaper}")
    
    fetcher = WikipediaFetcher()
    info = fetcher.get_newspaper_info(args.newspaper)
    
    if info:
        print(f"\n✅ Found information:")
        print(f"   Title: {info.title}")
        print(f"   Language: {info.language}")
        print(f"   URL: {info.url}")
        print(f"   Categories: {', '.join(info.categories[:3])}")
        print(f"\n📄 Summary:")
        print(f"   {info.summary[:200]}...")
        
        # Format for README
        readme_content = fetcher.format_wikipedia_info_for_readme(info, args.language)
        print(f"\n📝 README Format:")
        print(readme_content)
    else:
        print(f"\n❌ No information found for: {args.newspaper}")


if __name__ == '__main__':
    main()