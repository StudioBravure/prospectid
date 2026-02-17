import re
import asyncio
from typing import Set, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed
from ..models.schema import LeadSource

class OfficialWebCrawler:
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    CONTACT_PATHS = ["/contact", "/contato", "/fale-conosco", "/sobre", "/about"]
    BLACKLIST_DOMAINS = ["facebook.com", "instagram.com", "linkedin.com", "google.com"]

    def __init__(self, user_agent: str = "AntigravityProspector/1.0"):
        self.headers = {"User-Agent": user_agent}

    def _is_valid_email(self, email: str) -> bool:
        if any(x in email.lower() for x in ["example.com", "yourdomain", "email.com", ".png", ".jpg", ".js"]):
            return False
        return True

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        try:
            response = await client.get(url, headers=self.headers, timeout=10.0, follow_redirects=True)
            if response.status_code == 200:
                return response.text
        except Exception:
            return None
        return None

    async def extract_emails(self, website_url: str, max_pages: int = 3) -> List[Dict[str, Any]]:
        found_emails: List[Dict[str, Any]] = []
        visited: Set[str] = set()
        queue: List[str] = [website_url]
        
        # Add heuristic contact pages
        base_domain = urlparse(website_url).netloc
        if any(d in base_domain for d in self.BLACKLIST_DOMAINS):
            return [] # Skip social media profiles

        for path in self.CONTACT_PATHS:
            queue.append(urljoin(website_url, path))

        async with httpx.AsyncClient(verify=False) as client:
            while queue and len(visited) < max_pages:
                url = queue.pop(0)
                if url in visited:
                    continue
                
                visited.add(url)
                html = await self._fetch(client, url)
                if not html:
                    continue

                # Extract Emails
                emails = set(self.EMAIL_REGEX.findall(html))
                for email in emails:
                    if self._is_valid_email(email):
                        found_emails.append({
                            "value": email,
                            "source_type": "official_website",
                            "evidence": {"url": url, "snippet": "Found on page"}
                        })
                
                # Simple link extraction for next hop (bfs)
                if len(visited) < max_pages:
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        full_url = urljoin(url, href)
                        if urlparse(full_url).netloc == base_domain and full_url not in visited:
                            queue.append(full_url)

        return found_emails[:1] # Return best match (or all if needed)
