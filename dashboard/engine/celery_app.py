from celery import Celery
from ..core.config import settings

celery_app = Celery(
    "antigravity_prospector",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "antigravity_prospector.engine.workflow_bootstrap",
        "antigravity_prospector.engine.workflow_search",
        "antigravity_prospector.engine.workflow_enrichment"
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "antigravity_prospector.engine.workflow_bootstrap.*": {"queue": "q_bootstrap"},
        "antigravity_prospector.engine.workflow_search.places_search_task": {"queue": "q_places_collect"},
        "antigravity_prospector.engine.workflow_search.places_details_task": {"queue": "q_place_details"},
        "antigravity_prospector.engine.workflow_enrichment.*": {"queue": "q_enrich_provider"}
    },
    task_queues={
        "q_bootstrap": {"exchange": "q_bootstrap", "routing_key": "q_bootstrap"},
        "q_places_collect": {"exchange": "q_places_collect", "routing_key": "q_places_collect"},
        "q_place_details": {"exchange": "q_place_details", "routing_key": "q_place_details"},
        "q_enrich_provider": {"exchange": "q_enrich_provider", "routing_key": "q_enrich_provider"}
    }
)
