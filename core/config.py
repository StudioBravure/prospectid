from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, HttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Campaign Input Contract Models ---

class Region(BaseModel):
    country: str = "BR"
    state: str
    city: str
    radius_km: int = 10

class GoogleCategories(BaseModel):
    include: List[str]
    exclude: List[str] = []

class Limits(BaseModel):
    max_leads_total: Optional[int] = None  # None = Unbounded
    max_per_region: Optional[int] = None
    max_per_keyword: Optional[int] = None
    max_pages_per_domain_for_email: int = 3

class FilterConfig(BaseModel):
    require_found: bool = False
    include_list: List[str] = []
    exclude_list: List[str] = []

class RangeFilter(BaseModel):
    min: Optional[int] = None
    max: Optional[int] = None
    policy_unknown: Literal["include", "exclude", "score_zero"] = "include"

class ContactsFilter(BaseModel):
    require_phone: bool = True
    require_email: bool = False
    require_website: bool = False

class Filters(BaseModel):
    cnpj: FilterConfig = Field(default_factory=FilterConfig)
    employees: RangeFilter = Field(default_factory=RangeFilter)
    contacts: ContactsFilter = Field(default_factory=ContactsFilter)

class EnrichmentSources(BaseModel):
    cnpj: List[str] = ["PUBLIC_OR_LICENSED_PROVIDER"]
    employees: List[str] = ["PUBLIC_OR_LICENSED_PROVIDER"]
    email: List[str] = ["OFFICIAL_WEBSITE_ONLY"]

class ScoringWeights(BaseModel):
    has_phone: int = 10
    has_email: int = 20
    has_website: int = 10
    employees_in_range: int = 15
    rating: int = 5
    reviews: int = 5

class CrmSync(BaseModel):
    enabled: bool = False
    provider: Literal["hubspot", "pipedrive", "salesforce", "none"] = "none"
    dedupe_key: str = "place_id"

class CampaignConfig(BaseModel):
    name: str
    goal: str
    regions: List[Region]
    keywords: List[str]
    google_categories: GoogleCategories
    limits: Limits = Field(default_factory=Limits)
    filters: Filters = Field(default_factory=Filters)
    enrichment_sources_allowed: EnrichmentSources = Field(default_factory=EnrichmentSources)
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    exports: Dict[str, bool] = {"csv": True, "json": True}
    crm_sync: CrmSync = Field(default_factory=CrmSync)

# --- Runtime Settings ---

class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "Antigravity Prospector"
    VERSION: str = "0.1.0"
    USER_AGENT_LABEL: str = "AntigravityProspector"
    SECRET_KEY: str = "replace_this_in_prod"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://antigravity:password@localhost:5432/prospector"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Google
    GOOGLE_PLACES_API_KEY: str = Field(..., description="Required for Places API")
    GOOGLE_LANGUAGE_CODE: str = "pt-BR"
    GOOGLE_REGION_CODE: str = "BR"

    # Enrichment Providers
    # Allowed: CNPJ_WS, BIG_DATA_CORP
    DEFAULT_PROVIDER: Literal["CNPJ_WS", "BIG_DATA_CORP"] = "CNPJ_WS"
    
    # CNPJ.ws
    CNPJ_WS_TOKEN: Optional[str] = None
    
    # BigDataCorp
    BIG_DATA_CORP_TOKEN: Optional[str] = None
    BIG_DATA_CORP_USER: Optional[str] = None
    BIG_DATA_CORP_PASS: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
