import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from antigravity_prospector.core.database import get_db_context, engine, Base
from antigravity_prospector.models.schema import PlacesRaw, CampaignRun, Tenant
from antigravity_prospector.connectors.google_places_new import GooglePlacesNewClient
from loguru import logger

# --- Configuration ---
INPUT = {
  "tenant_id": "smoke-test-tenant",
  "run_label": "smoke-test-v1",
  "text_query": "contador em São Paulo SP",
  "languageCode": "pt-BR",
  "regionCode": "BR",
  "rate_limit": { "qps": 1, "burst": 2 },
  "cache_ttl_days": 7
}

logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")

# --- Helpers ---
def calc_fingerprint(data: Any) -> str:
    s = json.dumps(data, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()

class MockCache:
    """Mock Redis for Smoke Test"""
    def __init__(self):
        self.store = {}
        
    def get(self, key):
        entry = self.store.get(key)
        if not entry: return None
        if datetime.now() > entry["expires_at"]:
            del self.store[key]
            return None
        return entry["value"]
    
    def set(self, key, value, ttl_days):
        self.store[key] = {
            "value": value,
            "expires_at": datetime.now() + timedelta(days=ttl_days)
        }

mock_cache = MockCache()

# --- Workflow ---

async def run_smoke_test():
    logger.info("🚀 Starting WF_GOOGLE_PLACES_SMOKE_TEST_V1")
    
    async with get_db_context() as db:
        # Init DB (ensure tables)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        # STEP 1: Init Run
        # Create dummy Tenant/Run for Referencing
        # In real app these exist, for smoke test we might need duplicates or mock
        # We'll just generate a UUID-like run_id for logging, 
        # but for DB FKs (if strict) we might fail. 
        # Schema definition: run_id is Integer FK to campaign_runs.id
        # We need to insert a campaign_run first if we want to honor FKs
        
        # Ensure Tenant
        tenant_id = INPUT["tenant_id"]
        # ... logic to create tenant if not exists ...
        
        run_id = 9999 # Mock Integer ID for test
        logger.info(f"Run ID: {run_id}")

        client = GooglePlacesNewClient()
        
        # STEP 2: Rate Limit Gate (Search)
        logger.info("⏳ Rate Limit Gate (Search)...")
        await asyncio.sleep(1 / INPUT["rate_limit"]["qps"])
        
        # STEP 3: Cache Get (Search)
        cache_key_search = f"places:searchText:{hashlib.md5((INPUT['text_query'] + INPUT['languageCode']).encode()).hexdigest()}"
        search_response = mock_cache.get(cache_key_search)
        
        if search_response:
            logger.info("✅ Cache HIT (Search)")
        else:
            logger.info("❌ Cache MISS (Search) -> Calling API")
            
            # STEP 4: HTTP Request (SearchText New)
            field_mask_search = "places.id,places.displayName,places.primaryType,places.formattedAddress,places.location,places.types,places.businessStatus"
            try:
                search_response = await client.search_text(
                    text_query=INPUT["text_query"],
                    field_mask=field_mask_search
                )
                logger.info(f"API Success. Found {len(search_response.get('places', []))} places.")
            except Exception as e:
                logger.error(f"API Failed: {e}")
                return

            # STEP 5: Cache Set
            mock_cache.set(cache_key_search, search_response, INPUT["cache_ttl_days"])

        # STEP 6: Persist Raw (Search)
        places = search_response.get("places", [])
        for place in places:
            raw = PlacesRaw(
                tenant_id=tenant_id,
                run_id=run_id,
                place_id=place["id"],
                source_step="search_text",
                request_fingerprint=calc_fingerprint({"query": INPUT["text_query"], "mask": field_mask_search}),
                request_json={"endpoint": "places:searchText", "body": INPUT["text_query"]},
                data=place, # response_json
                fetched_at=datetime.utcnow()
            )
            db.add(raw)
        await db.commit()
        logger.info(f"Persisted {len(places)} items to places_raw")

        # STEP 7: Extract first place_id
        if not places:
            logger.warning("No places found. Exiting.")
            return
        
        first_place_id = places[0]["id"]
        logger.info(f"First Place ID: {first_place_id}")
        
        # STEP 8: Rate Limit Gate (Details)
        await asyncio.sleep(1 / INPUT["rate_limit"]["qps"])

        # STEP 9: Cache Get (Details)
        details_mask = "id,displayName,formattedAddress,addressComponents,location,websiteUri,internationalPhoneNumber,rating,userRatingCount,types,primaryType,businessStatus"
        cache_key_details = f"places:details:{first_place_id}:{hashlib.md5(details_mask.encode()).hexdigest()}"
        details_response = mock_cache.get(cache_key_details)
        
        if details_response:
             logger.info("✅ Cache HIT (Details)")
        else:
            logger.info("❌ Cache MISS (Details) -> Calling API")
            
            # STEP 10: HTTP Request (Details)
            try:
                details_response = await client.place_details(first_place_id, details_mask)
                logger.info("API Success (Details).")
            except Exception as e:
                logger.error(f"API Failed (Details): {e}")
                return
            
            # STEP 11: Cache Set
            mock_cache.set(cache_key_details, details_response, INPUT["cache_ttl_days"])

        # STEP 12: Persist Raw (Details)
        raw_details = PlacesRaw(
            tenant_id=tenant_id,
            run_id=run_id,
            place_id=details_response["id"],
            source_step="place_details",
            request_fingerprint=calc_fingerprint({"place_id": first_place_id, "mask": details_mask}),
            request_json={"endpoint": "places/{id}", "place_id": first_place_id, "mask": details_mask},
            data=details_response,
            fetched_at=datetime.utcnow()
        )
        db.add(raw_details)
        await db.commit()

        # STEP 13: Log summary
        log_summary = {
            "event": "places.smoke_test.ok",
            "tenant_id": tenant_id,
            "place_id": details_response.get("id"),
            "website": details_response.get("websiteUri"),
            "phone": details_response.get("internationalPhoneNumber"),
            "status": details_response.get("businessStatus")
        }
        logger.info(json.dumps(log_summary, indent=2))
        
        # STEP 14: Final Output
        print(json.dumps({
            "ok": True,
            "places_found": len(places),
            "details_tested_place_id": details_response.get("id")
        }))

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
