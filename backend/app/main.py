from fastapi import FastAPI

from app.api.agent import router as agent_router
from app.api.buildings import router as buildings_router
from app.api.health import router as health_router
from app.api.roads import router as roads_router
from app.api.routes import router as routes_router
from app.api.safety import router as safety_router


app = FastAPI(
    title="SafeAlley API",
    version="0.2.0",
    description="SafeAlley MVP backend",
)

app.include_router(health_router)
app.include_router(agent_router)
app.include_router(buildings_router)
app.include_router(roads_router)
app.include_router(routes_router)
app.include_router(safety_router)
