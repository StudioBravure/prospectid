import asyncio
from loguru import logger
from sqlalchemy import select
from .celery_app import celery_app
from ..core.database import get_db_context
from ..models.schema import Task, Lead, LeadSource, OptOutRegistry
from ..connectors.crawler import OfficialWebCrawler

crawler = OfficialWebCrawler()

@celery_app.task(bind=True, name="antigravity_prospector.engine.workflow_enrichment.email_finder_task")
def email_finder_task(self, tenant_id: str, lead_id: int, website: str):
    """
    Workflow D: Email Finder
    1. Check Opt-out
    2. Crawl
    3. Save Result + Lineage
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_async_email_finder(tenant_id, lead_id, website))

async def _async_email_finder(tenant_id: str, lead_id: int, website: str):
    async with get_db_context() as db:
        # 1. Opt-out Check
        from urllib.parse import urlparse
        domain = urlparse(website).netloc.replace("www.", "")
        
        stmt_opt = select(OptOutRegistry).where(
            OptOutRegistry.tenant_id == tenant_id,
            OptOutRegistry.scope_type == "domain",
            OptOutRegistry.scope_value == domain
        )
        if (await db.execute(stmt_opt)).scalar_one_or_none():
            logger.info(f"Skipping email find for opted-out domain: {domain}")
            return

        # 2. Crawl
        try:
            emails = await crawler.extract_emails(website)
            
            if emails:
                best_email = emails[0] # Take first for now
                
                # 3. Update Lead
                stmt_lead = select(Lead).where(Lead.id == lead_id)
                lead = (await db.execute(stmt_lead)).scalar_one_or_none()
                
                if lead:
                    lead.email = best_email["value"]
                    lead.email_source_url = best_email["evidence"]["url"]
                    
                    # 4. Add Source Lineage
                    source = LeadSource(
                        lead_id=lead.id,
                        field_name="email",
                        source_type="official_website",
                        value=best_email["value"],
                        evidence=best_email["evidence"]
                    )
                    db.add(source)
                    await db.commit()
                    logger.info(f"Email found for lead {lead_id}: {lead.email}")
            
        except Exception as e:
            logger.error(f"Email Finder Failed for {website}: {e}")

@celery_app.task(bind=True, name="antigravity_prospector.engine.workflow_enrichment.provider_enrichment_task")
def provider_enrichment_task(self, tenant_id: str, lead_id: int):
    """
    Workflow E: Provider Enrichment
    """
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_async_provider_enrichment(tenant_id, lead_id))

async def _async_provider_enrichment(tenant_id: str, lead_id: int):
    from ..connectors.corporate_provider import get_corporate_provider
    from ..core.security import AuditLogger
    
    provider = get_corporate_provider()
    
    async with get_db_context() as db:
        stmt = select(Lead).where(Lead.id == lead_id)
        lead = (await db.execute(stmt)).scalar_one_or_none()
        if not lead: return

        # 1. Lookup (if missing CNPJ)
        if not lead.cnpj:
            candidates = await provider.lookup_by_name(lead.name, lead.city, "SP") # TODO: Parse state from address
            
            if candidates:
                best = candidates[0]
                if best.confidence >= 0.75:
                    lead.cnpj = best.cnpj
                    # Log source for extraction
                    db.add(LeadSource(
                        lead_id=lead.id, field_name="cnpj_candidate", source_type="provider_lookup",
                        value=best.cnpj, evidence=best.evidence
                    ))
                    await db.commit()
        
        # 2. Enrich (if CNPJ exists)
        if lead.cnpj:
            data = await provider.enrich_by_cnpj(lead.cnpj)
            if data:
                lead.cnpj = data.cnpj # Normalized
                lead.employees_min = data.employees_estimated.get("min")
                lead.employees_max = data.employees_estimated.get("max")
                
                # Lineage for key fields
                db.add(LeadSource(
                    lead_id=lead.id, field_name="employees_est", source_type="official_provider",
                    value=f"{lead.employees_min}-{lead.employees_max}", evidence=data.evidence
                ))
                
                await AuditLogger.log(tenant_id, "enrich_provider_completed", "lead", str(lead.id), 
                                      {"provider": "CorporateProvider", "cnpj": lead.cnpj})
                
                logger.info(f"Enriched Lead {lead.id} with CNPJ {lead.cnpj}")
            
        await db.commit()
