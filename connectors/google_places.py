import httpx
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..core.config import settings
from loguru import logger

class GooglePlacesConnector:
    BASE_URL = "https://places.googleapis.com/v1"

    def __init__(self, api_key: str = settings.GOOGLE_PLACES_API_KEY):
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key
        }

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def search_text(self, query: str, field_mask: List[str], page_token: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/places:searchText"
        headers = {**self.headers, "X-Goog-FieldMask": ",".join(field_mask)}
        payload = {"textQuery": query, "languageCode": settings.GOOGLE_LANGUAGE_CODE}
        if page_token:
            payload["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def search_nearby(self, lat: float, lng: float, radius_meters: int, included_types: List[str], field_mask: List[str]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/places:searchNearby"
        headers = {**self.headers, "X-Goog-FieldMask": ",".join(field_mask)}
        payload = {
            "includedTypes": included_types,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_meters)
                }
            },
            "languageCode": settings.GOOGLE_LANGUAGE_CODE
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def get_place_details(self, place_id: str, field_mask: List[str]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/places/{place_id}"
        headers = {**self.headers, "X-Goog-FieldMask": ",".join(field_mask)}
        params = {"languageCode": settings.GOOGLE_LANGUAGE_CODE, "regionCode": settings.GOOGLE_REGION_CODE}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
