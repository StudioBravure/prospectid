from .celery_app import celery_app
from ..core.database import get_db_context
from ..models.schema import Campaign, CampaignRun, Task
from sqlalchemy import select
from loguru import logger
from datetime import datetime
import asyncio

@celery_app.task(bind=True, name="antigravity_prospector.engine.workflow_bootstrap.start_campaign_run")
def start_campaign_run(self, campaign_id: int, tenant_id: str):
    """
    Workflow A: Bootstrap
    1. Load Campaign Config
    2. Create Run Record
    3. Fan-out Search Tasks (Region x Keyword)
    """
    # Celery tasks are sync by default, but we use async DB. 
    # We need a bridge or just run_until_complete for this lightweight bootstrap step.
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(_async_start_campaign_run(campaign_id, tenant_id))

async def _async_start_campaign_run(campaign_id: int, tenant_id: str):
    async with get_db_context() as db:
        # 1. Load Campaign
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        result = await db.execute(stmt)
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found for tenant {tenant_id}")
            return {"status": "error", "message": "Campaign not found"}

        # 2. Create Run
        run = CampaignRun(
            campaign_id=campaign.id,
            status="running",
            started_at=datetime.utcnow(),
            stats={"tasks_enqueued": 0}
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        
        logger.info(f"Started Run ID: {run.id} for Campaign: {campaign.name}")

        # 3. Fan-out Tasks
        config = campaign.config
        tasks_enqueued = 0
        
        from .workflow_search import places_search_task
        
        # Iterate Regions
        for region in config.get("regions", []):
            # Iterate Keywords
            keywords = config.get("keywords", [])
            categories = config.get("google_categories", {}).get("include", [])
            
            # Mix keywords + categories as search queries
            search_terms = keywords + categories
            
            for term in search_terms:
                # Create Task Record
                task_input = {
                    "query": f"{term} in {region['city']}, {region['state']}",
                    "location": region,
                    "term": term
                }
                
                db_task = Task(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    type="places_search",
                    status="pending",
                    input_data=task_input
                )
                db.add(db_task)
                await db.commit() # Commit each task to get ID
                await db.refresh(db_task)
                
                # Enqueue in Celery
                places_search_task.delay(
                    task_id=db_task.id, 
                    tenant_id=tenant_id, 
                    query=task_input["query"],
                    location=region
                )
                tasks_enqueued += 1

        # Update Run Stats
        run.stats = {"tasks_enqueued": tasks_enqueued}
        await db.commit()
        
        return {"run_id": run.id, "tasks_enqueued": tasks_enqueued}
