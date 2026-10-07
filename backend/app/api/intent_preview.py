from fastapi import APIRouter, HTTPException

from app.schemas.intent_preview import IntentPreviewRequest, IntentPreviewResponse, IntentPreviewStatus
from app.services.jev_preview_service import PreviewLimited, PreviewUnavailable, analyze_preview, preview_status

router = APIRouter(prefix="/api/agent/intent-preview", tags=["intent-preview"])


@router.get("/status", response_model=IntentPreviewStatus)
def status():
    return preview_status()


@router.post("", response_model=IntentPreviewResponse)
def preview(request: IntentPreviewRequest):
    try:
        return analyze_preview(request.query)
    except PreviewLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except PreviewUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
