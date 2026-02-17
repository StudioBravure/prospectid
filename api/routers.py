from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
from ..core.database import get_db
from ..core.config import CampaignConfig
from ..models.schema import Campaign, CampaignRun, Lead, Tenant, Export
from ..engine.workflow_bootstrap import start_campaign_run
from ..engine.workflow_export import export_run_task

router = APIRouter()

# --- Campaigns ---

@router.post("/campaigns")
async def create_campaign(
    campaign_config: CampaignConfig, 
    tenant_id: str = "default_tenant", # Mock auth
    db: AsyncSession = Depends(get_db)
):
    # Check if Tenant exists due to FK
    # For demo, assumes tenant exists or we create it
    # Ideally: get keys from auth token
    
    # Check unique
    stmt = select(Campaign).where(Campaign.name == campaign_config.name, Campaign.tenant_id == tenant_id)
    if (await db.execute(stmt)).scalar_one_or_none():
         raise HTTPException(status_code=400, detail="Campaign name exists")
         
    new_campaign = Campaign(
        tenant_id=tenant_id,
        name=campaign_config.name,
        config=campaign_config.model_dump()
    )
    db.add(new_campaign)
    await db.commit()
    await db.refresh(new_campaign)
    return {"id": new_campaign.id, "name": new_campaign.name}

@router.get("/campaigns")
async def list_campaigns(tenant_id: str = "default_tenant", db: AsyncSession = Depends(get_db)):
    stmt = select(Campaign).where(Campaign.tenant_id == tenant_id)
    result = await db.execute(stmt)
    return result.scalars().all()

# --- Runs ---

@router.post("/campaigns/{campaign_id}/run")
async def run_campaign(
    campaign_id: int, 
    tenant_id: str = "default_tenant", 
    db: AsyncSession = Depends(get_db)
):
    # Verify ownership
    stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(404, "Campaign not found")
        
    # Trigger Celery Task
    # start_campaign_run.delay(...)
    task = start_campaign_run.delay(campaign_id, tenant_id)
    
    return {"status": "enqueued", "task_id": task.id}

@router.get("/runs")
async def list_runs(tenant_id: str = "default_tenant", db: AsyncSession = Depends(get_db)):
    stmt = select(CampaignRun).order_by(CampaignRun.started_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

# --- Leads ---

@router.get("/leads")
async def list_leads(tenant_id: str = "default_tenant", skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(Lead).where(Lead.tenant_id == tenant_id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

# --- Exports ---

@router.post("/runs/{run_id}/export")
async def trigger_export(run_id: int, format: str = "csv", tenant_id: str = "default_tenant"):
    task = export_run_task.delay(tenant_id, run_id, format)
    return {"status": "enqueued", "task_id": task.id}

@router.get("/exports")
async def list_exports(tenant_id: str = "default_tenant", db: AsyncSession = Depends(get_db)):
    stmt = select(Export).where(Export.tenant_id == tenant_id).order_by(Export.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()
