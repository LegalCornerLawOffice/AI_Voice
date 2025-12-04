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
from services.redis_state_manager import RedisStateManager
from services.call_repository import CallRepository
from pipeline.audio_pipeline import AudioPipeline
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global services
state_manager: RedisStateManager = None
call_repository: CallRepository = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup/shutdown."""
    global state_manager, call_repository
    
    # Startup
    logger.info("Starting AI Voice Intake System...")
    
    # Initialize Redis state manager
    state_manager = RedisStateManager(redis_url=settings.redis_url)
    await state_manager.initialize()
    logger.info("Redis state manager initialized")
    
    # Initialize call repository
    call_repository = CallRepository(database_url=settings.database_url)
    await call_repository.initialize()
    logger.info("Call repository initialized")
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if state_manager:
        await state_manager.close()
    if call_repository:
        await call_repository.close()
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
    start_time = datetime.utcnow()
    
    logger.info(f"New WebSocket connection: {session_id}")
    
    # Accept connection
    await websocket.accept()
    
    audio_handler = None
    pipeline = None
    
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
        # Save call to database and JSON
        end_time = datetime.utcnow()
        try:
            # Get final state from Redis
            state = await state_manager.get_state(session_id)
            if state:
                conversation_history = state.get("conversation_history", [])
                collected_fields = state.get("collected_fields", {})
                
                # Save to PostgreSQL
                call_id = await call_repository.save_call(
                    session_id=session_id,
                    conversation_history=conversation_history,
                    collected_fields=collected_fields,
                    phone_number=None,  # TODO: Get from Twilio metadata
                    start_time=start_time,
                    end_time=end_time
                )
                logger.info(f"Saved call {session_id} to database (ID: {call_id})")
                
                # Also save to JSON for easy inspection
                json_path = await call_repository.save_call_as_json(
                    session_id=session_id,
                    conversation_history=conversation_history,
                    collected_fields=collected_fields
                )
                logger.info(f"Saved call to JSON: {json_path}")
                
        except Exception as e:
            logger.error(f"Error saving call {session_id}: {e}", exc_info=True)
        
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
