from datetime import datetime
from typing import Dict, Any, Optional
from ..core.database import AsyncSessionLocal
from ..models.schema import AuditLog

class AuditLogger:
    @staticmethod
    async def log(
        tenant_id: str,
        action: str,
        target_type: str,
        target_id: str,
        details: Dict[str, Any],
        user_id: Optional[str] = "system"
    ):
        async with AsyncSessionLocal() as db:
            audit = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details,
                timestamp=datetime.utcnow()
            )
            db.add(audit)
            await db.commit()
