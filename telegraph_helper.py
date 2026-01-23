#!/usr/bin/env python3
"""
Telegraph Helper for creating professional result pages
"""

from telegraph import Telegraph
import logging

logger = logging.getLogger(__name__)


class TelegraphHelper:
    def __init__(self, author_name="TamilMV Leech Bot", author_url="https://t.me/telegram"):
        self.telegraph = Telegraph()
        self.author_name = author_name
        self.author_url = author_url
        self.account_created = False
    
    def create_account(self):
        """Create Telegraph account"""
        try:
            if not self.account_created:
                self.telegraph.create_account(
                    short_name=self.author_name,
                    author_name=self.author_name,
                    author_url=self.author_url
                )
                self.account_created = True
                logger.info(f"Telegraph account created: {self.author_name}")
        except Exception as e:
            logger.error(f"Telegraph account creation failed: {e}")
    
    def create_page(self, title, content):
        """
        Create a Telegraph page
        
        Args:
            title: Page title
            content: HTML content
        
        Returns:
            Page URL or None
        """
        try:
            if not self.account_created:
                self.create_account()
            
            response = self.telegraph.create_page(
                title=title,
                html_content=content,
                author_name=self.author_name,
                author_url=self.author_url
            )
            
            return f"https://telegra.ph/{response['path']}"
        
        except Exception as e:
            logger.error(f"Telegraph page creation failed: {e}")
            return None
    
    def format_search_results(self, results, query, total_found):
        """
        Format search results as HTML for Telegraph
        
        Args:
            results: List of torrent dicts
            query: Search query
            total_found: Total number of results
        
        Returns:
            HTML string
        """
        html = f"<h3>🔍 Search Results for: {query}</h3>"
        html += f"<p><b>Found {total_found} torrents</b></p>"
        html += "<hr>"
        
        for idx, result in enumerate(results, 1):
            name = result.get('name', 'Unknown')
            size = result.get('size', 'Unknown')
            seeders = result.get('seeders', 0)
            leechers = result.get('leechers', 0)
            source = result.get('source', 'Unknown')
            magnet = result.get('magnet', '')
            
            html += f"<h4>{idx}. {name}</h4>"
            html += f"<p>"
            html += f"📦 <b>Size:</b> {size}<br>"
            html += f"🌱 <b>Seeders:</b> {seeders} | 🔴 <b>Leechers:</b> {leechers}<br>"
            html += f"🔗 <b>Source:</b> {source}<br>"
            
            if magnet:
                # Create Telegram share link for magnet
                from urllib.parse import quote
                share_url = f"https://t.me/share/url?url={quote(magnet)}"
                html += f'<a href="{share_url}">Share Magnet to Telegram</a>'
            
            html += f"</p><hr>"
        
        html += f"<p><i>Total: {len(results)} results displayed</i></p>"
        
        return html


# Global telegraph instance
telegraph_helper = TelegraphHelper()
