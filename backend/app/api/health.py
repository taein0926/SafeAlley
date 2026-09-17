from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.connection import DatabaseConnectionError, check_database


router = APIRouter(tags=["health"])


@router.get("/health", response_model=None)
def health() -> dict[str, object] | JSONResponse:
    """Check the API process, database connection, and PostGIS extension."""
    try:
        database = check_database()
    except DatabaseConnectionError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "service": "backend",
                "database": {
                    "status": "unavailable",
                    "message": str(exc),
                },
            },
        )

    return {
        "status": "ok",
        "service": "backend",
        "database": database,
    }
