import asyncio
import json
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from .celery_app import celery_app
from ..core.database import get_db_context
from ..models.schema import Task, Lead, PlacesRaw, Campaign
from ..connectors.google_places_new import GooglePlacesNewClient

# Initialize Connector
places_client = GooglePlacesNewClient()

@celery_app.task(bind=True, name="antigravity_prospector.engine.workflow_search.places_search_task")
def places_search_task(self, task_id: int, tenant_id: str, query: str, location: dict):
    """
    Workflow B: Search
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_async_places_search(task_id, tenant_id, query))

async def _async_places_search(task_id: int, tenant_id: str, query: str):
    async with get_db_context() as db:
        task = await db.get(Task, task_id)
        if not task: return
        task.status = "processing"
        await db.commit()

        try:
            # 2. Call API (Search) - V1 New
            # FieldMask: Basic info to identify and dedupe
            # places.id, places.displayName, places.formattedAddress
            field_mask = "places.id,places.displayName,places.formattedAddress"
            
            # Using search_text for now as it handles queries best through V1
            results = await places_client.search_text(text_query=query, field_mask=field_mask)
            
            places = results.get("places", [])
            new_leads_count = 0
            
            for place in places:
                pid = place["id"]
                
                # Dedupe
                stmt = select(Lead).where(Lead.tenant_id == tenant_id, Lead.place_id == pid)
                existing = await db.execute(stmt)
                if existing.scalar_one_or_none():
                    continue 

                # Save Raw
                stmt_raw = select(PlacesRaw).where(PlacesRaw.place_id == pid)
                existing_raw = await db.execute(stmt_raw)
                if not existing_raw.scalar_one_or_none():
                    db.add(PlacesRaw(place_id=pid, data=place, source_step="search"))
                
                # Skeleton
                name_text = place.get("displayName", {}).get("text", "Unknown")
                new_lead = Lead(
                    tenant_id=tenant_id,
                    run_id=task.run_id,
                    place_id=pid,
                    name=name_text,
                    address=place.get("formattedAddress"),
                    data={},
                    lead_status="new"
                )
                db.add(new_lead)
                await db.commit()
                
                # Audit
                from ..core.security import AuditLogger
                await AuditLogger.log(tenant_id, "lead_discovered", "lead", str(new_lead.id), {"place_id": pid})

                # Enqueue Details
                details_task = Task(
                    tenant_id=tenant_id,
                    run_id=task.run_id,
                    type="places_details",
                    status="pending",
                    input_data={"place_id": pid}
                )
                db.add(details_task)
                await db.commit()
                await db.refresh(details_task)
                
                places_details_task.delay(details_task.id, tenant_id, pid)
                new_leads_count += 1
            
            task.status = "completed"
            task.result_data = {"found": len(places), "new": new_leads_count}
            await db.commit()
            
        except Exception as e:
            logger.exception(f"Search Task Failed: {e}")
            task.status = "failed"
            task.error_log = str(e)
            await db.commit()

@celery_app.task(bind=True, name="antigravity_prospector.engine.workflow_search.places_details_task")
def places_details_task(self, task_id: int, tenant_id: str, place_id: str):
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_async_places_details(task_id, tenant_id, place_id))

async def _async_places_details(task_id: int, tenant_id: str, place_id: str):
    async with get_db_context() as db:
        task = await db.get(Task, task_id)
        if not task: return
        task.status = "processing"
        await db.commit()
        
        try:
            # 1. Fetch Details (V1 New)
            # Mask required
            mask = "id,displayName,formattedAddress,websiteUri,internationalPhoneNumber,rating,userRatingCount,types,addressComponents"
            details = await places_client.place_details(place_id, mask)
            
            # Update Lead... using standard logic (same as before but V1 keys)
            # websiteUri is top level in V1
            
            stmt_lead = select(Lead).where(Lead.tenant_id == tenant_id, Lead.place_id == place_id)
            lead = (await db.execute(stmt_lead)).scalar_one_or_none()
            
            if lead:
                lead.data = details
                lead.website = details.get("websiteUri")
                lead.lead_status = "enriched_details"
                
                # Check website for domain
                if lead.website:
                    from urllib.parse import urlparse
                    try:
                        lead.domain = urlparse(lead.website).netloc.replace("www.", "")
                        celery_app.send_task(
                            "antigravity_prospector.engine.workflow_enrichment.email_finder_task",
                            kwargs={"tenant_id": tenant_id, "lead_id": lead.id, "website": lead.website}
                        )
                    except: pass
                
                # Always enqueue provider enrichment (Workflow E) if valid lead
                celery_app.send_task(
                     "antigravity_prospector.engine.workflow_enrichment.provider_enrichment_task",
                     kwargs={"tenant_id": tenant_id, "lead_id": lead.id}
                )

            task.status = "completed"
            await db.commit()

        except Exception as e:
            logger.exception(f"Details Task Failed: {e}")
            task.status = "failed"
            task.error_log = str(e)
            await db.commit()
