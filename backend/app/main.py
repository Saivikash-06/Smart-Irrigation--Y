import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import engine, Base, SessionLocal
from .services import initialize_default_data
from .websocket_manager import manager

from .api import devices, sensors, irrigation, dashboard, alerts, plants, demo

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("greenpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and default seed data
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        initialize_default_data(db)
        logger.info("Default device and configuration settings initialized.")
    finally:
        db.close()
    yield
    # Shutdown
    logger.info("Shutting down GreenPulse backend...")


app = FastAPI(
    title="GreenPulse – Smart Irrigation API",
    description="Backend API and WebSocket real-time server for GreenPulse Smart Irrigation and Garden Monitoring System.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend and simulator access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API Routers
app.include_router(devices.router)
app.include_router(sensors.router)
app.include_router(irrigation.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(plants.router)
app.include_router(demo.router)


# WebSocket endpoint for real-time dashboard telemetry
@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive and receive any client messages or pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client error: {e}")
        manager.disconnect(websocket)


# Mount frontend static directory if exists
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    def serve_frontend_index():
        index_file = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "GreenPulse API running. Frontend index not found."}
