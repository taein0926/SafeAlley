from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings
from app.schemas.intent_preview import IntentPreviewRequest, IntentPreviewResponse, IntentPreviewStatus
from app.services.jev_preview_service import PreviewLimited, PreviewUnavailable, analyze_preview, preview_status

router = APIRouter(prefix="/api/agent/intent-preview", tags=["intent-preview"])


@router.get("/status", response_model=IntentPreviewStatus)
def status():
    if get_settings().intent_preview_provider == "laya":
        from app.services import laya_preview_service

        return laya_preview_service.preview_status()
    return preview_status()


@router.post("", response_model=IntentPreviewResponse)
def preview(
    request: IntentPreviewRequest,
    preview_session: str | None = Header(
        default=None,
        alias="X-Intent-Preview-Session",
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
):
    try:
        if get_settings().intent_preview_provider == "laya":
            from app.services import laya_preview_service

            return laya_preview_service.analyze_preview(request.query)
        return analyze_preview(request.query, session_id=preview_session)
    except PreviewLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except PreviewUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
