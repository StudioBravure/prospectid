from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint, Index, JSON, Text, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

class Base(DeclarativeBase):
    pass

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB)  # Stores the full CampaignConfig JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tenant_campaign_name"),)

class CampaignRun(Base):
    __tablename__ = "campaign_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"))
    status: Mapped[str] = mapped_column(String, default="running")  # running, paused, completed, error
    stats: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={})
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaign_runs.id"))
    place_id: Mapped[str] = mapped_column(String, index=True)
    
    # Core Fields
    name: Mapped[str] = mapped_column(String)
    address: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[Optional[str]] = mapped_column(String)
    domain: Mapped[Optional[str]] = mapped_column(String, index=True)
    
    # Enriched Fields (Nullable)
    cnpj: Mapped[Optional[str]] = mapped_column(String, index=True)
    employees_min: Mapped[Optional[int]] = mapped_column(Integer)
    employees_max: Mapped[Optional[int]] = mapped_column(Integer)
    email: Mapped[Optional[str]] = mapped_column(String)
    # Evidence for email is stored in lead_sources, but we keep source URL here for easy export
    email_source_url: Mapped[Optional[str]] = mapped_column(String)
    
    # Metrics
    score: Mapped[float] = mapped_column(Float, default=0.0)
    lead_status: Mapped[str] = mapped_column(String, default="new") # new, eligible, discarded, exported
    
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB) # Full raw data dump
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "place_id", name="uq_lead_run_place"),
        Index("idx_lead_tenant_domain", "tenant_id", "domain"),
    )

class LeadSource(Base):
    __tablename__ = "lead_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"))
    field_name: Mapped[str] = mapped_column(String) # email, cnpj, employees
    source_type: Mapped[str] = mapped_column(String) # official_website, public_provider, google
    value: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSONB) # {url, snippet, date}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class OptOutRegistry(Base):
    __tablename__ = "opt_out_registry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"))
    scope_type: Mapped[str] = mapped_column(String) # domain, email, phone
    scope_value: Mapped[str] = mapped_column(String)
    reason: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scope_type", "scope_value", name="uq_opt_out"),
    )

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaign_runs.id"), index=True)
    type: Mapped[str] = mapped_column(String) # places_search, places_details, email_finder
    status: Mapped[str] = mapped_column(String, default="pending") # pending, processing, completed, failed
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    result_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    error_log: Mapped[Optional[str]] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_task_status", "tenant_id", "run_id", "type", "status"),
    )

class PlacesRaw(Base):
    __tablename__ = "places_raw"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, index=True) # Compliance
    run_id: Mapped[Optional[int]] = mapped_column(Integer, index=True) # Compliance
    place_id: Mapped[str] = mapped_column(String, index=True) # NON-UNIQUE to allow history tracking per run
    
    # Audit / Lineage
    source_step: Mapped[str] = mapped_column(String) # search, details
    request_fingerprint: Mapped[Optional[str]] = mapped_column(String)
    request_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB) # response_json
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    target_type: Mapped[str] = mapped_column(String) # campaign, lead, export
    target_id: Mapped[str] = mapped_column(String)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Export(Base):
    __tablename__ = "exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"))
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaign_runs.id"))
    format: Mapped[str] = mapped_column(String) # csv, json
    status: Mapped[str] = mapped_column(String, default="pending")
    file_path: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
