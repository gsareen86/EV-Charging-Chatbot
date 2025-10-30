"""
FastAPI server for EV Charging Chatbot
Handles token generation and serves the frontend
"""
import json
import logging
import os
from pathlib import Path
from typing import List, Set

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from livekit import api
from livekit.api import LiveKitAPI
from livekit.api.twirp_client import TwirpError, TwirpErrorCode
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# LiveKit configuration
LIVEKIT_DEPLOYMENT = os.getenv("LIVEKIT_DEPLOYMENT", "local").lower()
LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "ev-charging-assistant").strip()

logger = logging.getLogger("ev-charging-server")
logging.basicConfig(level=logging.INFO)

if LIVEKIT_DEPLOYMENT == "cloud":
    # Cloud deployment requires explicit credentials
    LIVEKIT_URL = os.getenv(
        "LIVEKIT_URL",
        "wss://voice-translator-52qz9ev9.livekit.cloud",
    )
    LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
    LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise RuntimeError(
            "LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set for cloud deployment"
        )
else:
    LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
    LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")


_dispatch_cache: Set[str] = set()


async def ensure_agent_dispatch(room_name: str) -> None:
    """Ensure the LiveKit voice agent is dispatched to the requested room."""

    if not LIVEKIT_AGENT_NAME:
        logger.debug("LIVEKIT_AGENT_NAME is empty, skipping dispatch request")
        return

    if room_name in _dispatch_cache:
        return

    try:
        async with LiveKitAPI(
            url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ) as lk_api:
            existing_dispatches = await lk_api.agent_dispatch.list_dispatch(room_name)
            for dispatch in existing_dispatches:
                if dispatch.agent_name == LIVEKIT_AGENT_NAME:
                    _dispatch_cache.add(room_name)
                    logger.debug(
                        "Found existing agent dispatch for %s in room %s",
                        LIVEKIT_AGENT_NAME,
                        room_name,
                    )
                    return

            await lk_api.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=LIVEKIT_AGENT_NAME,
                    room=room_name,
                    metadata=json.dumps({"service": "ev-charging-assistant"}),
                )
            )
            _dispatch_cache.add(room_name)
            logger.info(
                "Created LiveKit agent dispatch for %s in room %s",
                LIVEKIT_AGENT_NAME,
                room_name,
            )

    except TwirpError as error:
        if error.code == TwirpErrorCode.ALREADY_EXISTS:
            _dispatch_cache.add(room_name)
            logger.debug(
                "Agent dispatch already exists for %s in room %s",
                LIVEKIT_AGENT_NAME,
                room_name,
            )
            return

        logger.error(
            "LiveKit dispatch error (%s): %s", error.code, error.message, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to prepare voice agent")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Unable to ensure agent dispatch: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to prepare voice agent")

# Initialize FastAPI app
app = FastAPI(
    title="EV Charging Voice Chatbot API",
    description="API for EV charging voice assistant with LiveKit integration",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# Pydantic models for request/response validation
class TokenRequest(BaseModel):
    roomName: str
    participantName: str


class TokenResponse(BaseModel):
    token: str
    url: str
    deployment: str
    roomName: str
    participantName: str


class HealthResponse(BaseModel):
    status: str
    service: str
    livekit_url: str
    deployment: str


class ConfigResponse(BaseModel):
    livekit_url: str
    deployment: str
    supported_languages: List[str]


# API Endpoints
@app.post("/api/token", response_model=TokenResponse)
async def generate_token(request: TokenRequest):
    """
    Generate LiveKit access token for a participant

    - **roomName**: Name of the LiveKit room
    - **participantName**: Name of the participant joining
    """
    try:
        # Create access token
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
            .with_identity(request.participantName) \
            .with_name(request.participantName) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=request.roomName,
                can_publish=True,
                can_subscribe=True,
            ))

        await ensure_agent_dispatch(request.roomName)

        jwt_token = token.to_jwt()

        return TokenResponse(
            token=jwt_token,
            url=LIVEKIT_URL,
            deployment=LIVEKIT_DEPLOYMENT,
            roomName=request.roomName,
            participantName=request.participantName
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint to verify API status"""
    return HealthResponse(
        status="healthy",
        service="EV Charging Chatbot API",
        livekit_url=LIVEKIT_URL,
        deployment=LIVEKIT_DEPLOYMENT
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get public configuration information"""
    return ConfigResponse(
        livekit_url=LIVEKIT_URL,
        deployment=LIVEKIT_DEPLOYMENT,
        supported_languages=["en", "hi"]
    )


# Static file serving
@app.get("/")
async def read_index():
    """Serve the main HTML page"""
    return FileResponse(
        FRONTEND_DIR / "index.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/{file_path:path}")
async def serve_static(file_path: str):
    """Serve static files (CSS, JS, etc.)"""
    file_location = FRONTEND_DIR / file_path

    if file_location.exists() and file_location.is_file():
        return FileResponse(
            file_location,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    # If file not found, return 404
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn

    # Print startup information
    print("=" * 60)
    print("EV Charging Voice Chatbot - FastAPI Server")
    print("=" * 60)
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print(f"LiveKit Deployment: {LIVEKIT_DEPLOYMENT}")
    print(f"Server running on: http://localhost:5000")
    print(f"API documentation: http://localhost:5000/docs")
    print(f"Alternative API docs: http://localhost:5000/redoc")
    print("=" * 60)

    # Run the server with uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=5000,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )
