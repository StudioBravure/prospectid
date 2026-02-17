import csv
import json
import os
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from .celery_app import celery_app
from ..core.database import get_db_context
from ..models.schema import Export, Lead, LeadSource, CampaignRun
from ..core.config import settings

OUTPUT_DIR = "antigravity_prospector/ui/exports" # Expose via static files in UI?

@celery_app.task(bind=True, name="antigravity_prospector.engine.workflow_export.export_run_task")
def export_run_task(self, tenant_id: str, run_id: int, format: str):
    """
    Workflow H: Export
    1. Fetch Leads (Eligible)
    2. Format Data
    3. Write File
    4. Update Export Record
    """
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_async_export_run(tenant_id, run_id, format))

async def _async_export_run(tenant_id: str, run_id: int, format: str):
    async with get_db_context() as db:
        # Create Export Record
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filename = f"export_{tenant_id}_{run_id}_{int(datetime.utcnow().timestamp())}.{format}"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        export_rec = Export(tenant_id=tenant_id, run_id=run_id, format=format, status="processing")
        db.add(export_rec)
        await db.commit()
        await db.refresh(export_rec)

        try:
            stmt = select(Lead).where(Lead.tenant_id == tenant_id, Lead.run_id == run_id)
            result = await db.execute(stmt)
            leads = result.scalars().all()
            
            data_to_write = []
            if format == "csv":
                for lead in leads:
                    row = {
                        "Company": lead.name,
                        "Address": lead.address,
                        "City": lead.city,
                        "Phone": lead.data.get("internationalPhoneNumber"),
                        "Website": lead.website,
                        "Email": lead.email,
                        "Email Source": lead.email_source_url,
                        "CNPJ": lead.cnpj,
                        "Employees Min": lead.employees_min,
                        "Score": lead.score,
                        "Place ID": lead.place_id
                    }
                    data_to_write.append(row)
                
                with open(filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=data_to_write[0].keys())
                    writer.writeheader()
                    writer.writerows(data_to_write)
            
            elif format == "json":
                for lead in leads:
                    # Fetch Lineage
                    stmt_src = select(LeadSource).where(LeadSource.lead_id == lead.id)
                    sources = (await db.execute(stmt_src)).scalars().all()
                    
                    lead_dict = {
                        "id": lead.id,
                        "name": lead.name,
                        "fields": {
                            "email": {
                                "value": lead.email,
                                "source": next((s.evidence for s in sources if s.field_name == "email"), None)
                            }
                        }
                    }
                    data_to_write.append(lead_dict)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data_to_write, f, indent=2)

            export_rec.status = "completed"
            export_rec.file_path = filepath
            await db.commit()

        except Exception as e:
            logger.error(f"Export Failed: {e}")
            export_rec.status = "failed"
            await db.commit()
