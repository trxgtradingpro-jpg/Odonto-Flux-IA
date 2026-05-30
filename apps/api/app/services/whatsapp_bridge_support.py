from __future__ import annotations

from app.core.config import settings

OFFICIAL_API_TRANSPORT = "official_api"
WHATSAPP_WEB_BRIDGE_TRANSPORT = "whatsapp_web_bridge"


def resolve_sales_outreach_transport() -> str:
    raw_value = str(settings.sales_outreach_transport or OFFICIAL_API_TRANSPORT).strip().lower()
    if raw_value in {"whatsapp_web", WHATSAPP_WEB_BRIDGE_TRANSPORT}:
        return WHATSAPP_WEB_BRIDGE_TRANSPORT
    return OFFICIAL_API_TRANSPORT


def payload_metadata(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def payload_uses_whatsapp_web_bridge(payload: dict | None) -> bool:
    metadata = payload_metadata(payload)
    return str(metadata.get("transport") or "").strip().lower() == WHATSAPP_WEB_BRIDGE_TRANSPORT
