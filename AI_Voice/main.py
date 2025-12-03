"""
Main FastAPI application for AI Voice Intake System.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from handlers.webrtc import WebRTCAudioHandler
from services.state_manager_inmemory import InMemoryStateManager
from pipeline.audio_pipeline import AudioPipeline

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state manager
state_manager: InMemoryStateManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup/shutdown."""
    global state_manager
    
    # Startup
    logger.info("Starting AI Voice Intake System...")
    state_manager = InMemoryStateManager()
    await state_manager.initialize()
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if state_manager:
        await state_manager.close()
    logger.info("Application shut down")


# Create FastAPI app
app = FastAPI(
    title="AI Voice Intake System",
    description="Legal intake call automation with speech recognition and LLM processing",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Serve web client."""
    return FileResponse("web/index.html")


@app.get("/web/client.js")
async def serve_client_js():
    """Serve client JavaScript."""
    return FileResponse("web/client.js", media_type="application/javascript")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "0.1.0"
    }


@app.get("/metrics")
async def metrics():
    """Basic metrics endpoint."""
    # TODO: Add Prometheus metrics
    return {
        "active_calls": 0,  # TODO: Track this
        "total_calls": 0,  # TODO: Track this
    }


@app.websocket("/ws/call")
async def websocket_call(websocket: WebSocket):
    """
    WebSocket endpoint for voice calls.
    Handles both web (WebRTC) and phone (Twilio) calls.
    """
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    logger.info(f"New WebSocket connection: {session_id}")
    
    # Accept connection
    await websocket.accept()
    
    try:
        # Determine handler type based on first message
        # For now, default to WebRTC (web)
        audio_handler = WebRTCAudioHandler(websocket, session_id)
        
        # Create and start pipeline
        pipeline = AudioPipeline(
            session_id=session_id,
            audio_handler=audio_handler,
            state_manager=state_manager
        )
        
        logger.info(f"Starting pipeline for session {session_id}")
        await pipeline.start()
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info(f"Cleaning up session: {session_id}")
        if audio_handler:
            await audio_handler.close()


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
