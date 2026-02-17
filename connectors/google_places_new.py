import httpx
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..core.config import settings
from loguru import logger

class GooglePlacesNewClient:
    """
    Client for Google Places API (New) - v1
    Docs: https://developers.google.com/maps/documentation/places/web-service/op-overview
    """
    BASE_URL = "https://places.googleapis.com/v1/places"

    def __init__(self, api_key: str = settings.GOOGLE_PLACES_API_KEY, http_timeout_s: int = 30):
        self.api_key = api_key
        self.timeout = http_timeout_s
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "User-Agent": settings.USER_AGENT_LABEL
        }

    def _get_field_mask_header(self, mask: str) -> Dict[str, str]:
        return {**self.headers, "X-Goog-FieldMask": mask}

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def search_text(
        self, 
        text_query: str, 
        field_mask: str = "places.id,places.displayName,places.formattedAddress",
        page_size: int = 20, 
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        
        url = f"{self.BASE_URL}:searchText"
        headers = self._get_field_mask_header(field_mask)
        
        payload = {
            "textQuery": text_query,
            "pageSize": page_size,
            "languageCode": settings.GOOGLE_LANGUAGE_CODE
        }
        if page_token:
            payload["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def search_nearby(
        self, 
        center_lat: float, 
        center_lng: float, 
        radius_m: int,
        field_mask: str = "places.id,places.displayName,places.formattedAddress",
        included_types: Optional[List[str]] = None,
        excluded_types: Optional[List[str]] = None,
        max_result_count: int = 20,
        rank_preference: str = "POPULARITY"
    ) -> Dict[str, Any]:
        
        url = f"{self.BASE_URL}:searchNearby"
        headers = self._get_field_mask_header(field_mask)
        
        payload = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": center_lat, "longitude": center_lng},
                    "radius": float(radius_m)
                }
            },
            "maxResultCount": max_result_count,
            "rankPreference": rank_preference,
            "languageCode": settings.GOOGLE_LANGUAGE_CODE
        }
        
        if included_types:
            payload["includedTypes"] = included_types
        if excluded_types:
            payload["excludedTypes"] = excluded_types

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def place_details(self, place_id: str, field_mask: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{place_id}"
        headers = self._get_field_mask_header(field_mask)
        params = {
            "languageCode": settings.GOOGLE_LANGUAGE_CODE,
            "regionCode": settings.GOOGLE_REGION_CODE
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
