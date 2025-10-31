"""
LiveKit-based Voice Agent for EV Charging Chatbot - ENHANCED DEBUG VERSION
Handles STT -> LLM -> TTS pipeline with FAISS vector search
Includes comprehensive logging to diagnose audio subscription issues
"""
import asyncio
import json
import os
import logging
from typing import Optional
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    llm,
)
from livekit.agents.voice import events as voice_events
from livekit.plugins import noise_cancellation, silero, openai as oai
from livekit import rtc

from vector_search import VectorSearch

# Load environment variables
load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "ev-charging-assistant")

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ev-charging-agent")

# System prompts for the agent
SYSTEM_PROMPT_EN = """You are a helpful customer service agent for an EV battery charging and swapping service in India.
You assist hypermarket delivery personnel (HDP) with queries about charging stations, battery swapping, account management, and technical issues.

The user is interacting with you via voice, even if you perceive the conversation as text.

Key guidelines:
1. Be polite, professional, and empathetic
2. Provide clear and concise answers in natural conversational tone
3. Use the context from the FAQ database to answer questions accurately
4. If you don't know the answer, politely say so and offer to connect them with a human agent
5. Always confirm understanding when dealing with technical issues
6. Speak naturally as if in a phone conversation
7. Keep responses brief (2-3 sentences max) unless more detail is specifically requested
8. Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols

Service areas: Delhi NCR, Mumbai, Bangalore, Hyderabad, and Pune
Support: 24x7 helpline available at 1800-XXX-XXXX
Battery swap time: 2-3 minutes
All stations support QR code authentication
"""


class EVChargingAssistant(Agent):
    """EV Charging Voice Assistant with FAISS-backed context retrieval"""

    def __init__(self):
        """Initialize the assistant with vector search capability"""
        super().__init__(instructions=SYSTEM_PROMPT_EN)

        try:
            self.vector_search = VectorSearch()
            self.current_language = 'en'
            logger.info("Vector search initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize vector search: {e}")
            logger.warning("Agent will run without vector search context")
            self.vector_search = None

    def detect_language(self, text: str) -> str:
        """Detect language from text"""
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return 'hi'
        return 'en'

    async def get_context(self, user_message: str) -> str:
        """Get relevant context from FAISS vector database"""
        if not self.vector_search:
            return ""

        try:
            self.current_language = self.detect_language(user_message)
            logger.info(f"Detected language: {self.current_language}")

            context = self.vector_search.get_context_for_llm(
                query=user_message,
                language=self.current_language,
                top_k=3
            )

            return f"\n\nRELEVANT CONTEXT FROM FAQ DATABASE:\n{context}\n\nUse the above context to answer the user's question accurately."

        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return ""

    def get_system_prompt(self) -> str:
        """Get system prompt based on current language"""
        return SYSTEM_PROMPT_EN


def prewarm(proc: JobProcess):
    """Prewarm function to load models before first use"""
    logger.info("Prewarming models...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD model prewarmed")


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent"""
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "service": "ev-charging-chatbot"
    }

    logger.info("=" * 80)
    logger.info("STARTING EV CHARGING VOICE AGENT - ENHANCED DEBUG MODE")
    logger.info("=" * 80)

    # STEP 1: Connect to the room FIRST
    logger.info("STEP 1: Connecting to room...")
    await ctx.connect()
    logger.info(f"✓ Agent connected to room: {ctx.room.name}")
    
    # Log room state
    logger.info(f"Room SID: {ctx.room.sid}")
    logger.info(f"Room participants: {len(ctx.room.remote_participants)}")
    logger.info(f"Local participant identity: {ctx.room.local_participant.identity}")
    
    # STEP 2: Wait for a participant to join
    logger.info("STEP 2: Waiting for user participant to join...")
    try:
        participant = await ctx.wait_for_participant()
        logger.info(f"✓ User participant joined: {participant.identity}")
        logger.info(f"  - SID: {participant.sid}")
        logger.info(f"  - Metadata: {participant.metadata}")
        
        # Log participant's tracks
        logger.info(f"  - Audio tracks: {len(list(participant.track_publications.values()))}")
        for pub_sid, pub in participant.track_publications.items():
            logger.info(f"    * Track: {pub.sid}, Kind: {pub.kind}, Subscribed: {pub.subscribed}")
            
    except Exception as e:
        logger.error(f"Error waiting for participant: {e}", exc_info=True)

    # STEP 3: Set up room event handlers for debugging
    @ctx.room.on("track_published")
    def on_track_published(publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        logger.info(f"🎵 TRACK PUBLISHED by {participant.identity}")
        logger.info(f"   - Track SID: {publication.sid}")
        logger.info(f"   - Track kind: {publication.kind}")
        logger.info(f"   - Track source: {publication.source}")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        logger.info(f"🎧 TRACK SUBSCRIBED from {participant.identity}")
        logger.info(f"   - Track SID: {track.sid}")
        logger.info(f"   - Track kind: {track.kind}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info("   - ✓ AUDIO TRACK SUBSCRIBED - Agent should now hear user!")

    @ctx.room.on("track_unsubscribed")
    def on_track_unsubscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        logger.info(f"🔇 TRACK UNSUBSCRIBED from {participant.identity}")

    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        logger.debug(f"Data received from {data.participant.identity if data.participant else 'unknown'}")

    # STEP 4: Initialize the assistant
    logger.info("STEP 3: Initializing EV Charging Assistant...")
    assistant = EVChargingAssistant()

    # STEP 5: Create the agent session
    logger.info("STEP 4: Creating AgentSession...")
    session = AgentSession(
        stt=oai.STT(
            model="gpt-4o-transcribe",
            language="en",
            use_realtime=True
        ),
        llm=oai.LLM(
            model="gpt-4o-mini",
            temperature=0.2,
        ),
        tts=oai.TTS(
            model="gpt-4o-mini-tts",
            voice="alloy",
            speed=1.0,
        ),
        turn_detection="vad",
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Set up metrics collection
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Session Usage Summary: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # Enhanced event handlers with detailed logging
    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(ev: voice_events.UserInputTranscribedEvent):
        logger.info(f"📝 USER TRANSCRIPTION: '{ev.transcript}' (final: {ev.is_final})")
        
        # Publish to frontend
        try:
            ctx.room.local_participant.publish_data(
                json.dumps({
                    "type": "transcription",
                    "role": "user",
                    "text": ev.transcript,
                    "isFinal": ev.is_final,
                    "language": ev.language,
                }).encode("utf-8"),
                reliable=ev.is_final,
            )
        except Exception as e:
            logger.warning(f"Failed to publish user transcript: {e}")

    @session.on("user_speech_committed")
    def _on_user_speech(speech_text: str) -> None:
        logger.info(f"💬 USER SPEECH COMMITTED: '{speech_text}'")
        
        async def _handle():
            context = await assistant.get_context(speech_text)
            if context:
                updated_instructions = assistant.get_system_prompt() + context
                await assistant.update_instructions(updated_instructions)
                logger.info("✓ Context injected into agent instructions")
        
        asyncio.create_task(_handle())

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: voice_events.ConversationItemAddedEvent):
        item = ev.item
        if isinstance(item, llm.ChatMessage) and item.role == "assistant":
            text = item.text_content or ""
            logger.info(f"🤖 ASSISTANT RESPONSE: '{text}'")
            
            # Publish to frontend
            try:
                ctx.room.local_participant.publish_data(
                    json.dumps({
                        "type": "transcription",
                        "role": "assistant",
                        "text": text,
                        "isFinal": True,
                        "language": "en",
                    }).encode("utf-8"),
                    reliable=True,
                )
            except Exception as e:
                logger.warning(f"Failed to publish assistant response: {e}")

    @session.on("agent_speech_started")
    def _on_agent_speech_started():
        logger.info("🗣️ AGENT STARTED SPEAKING")

    @session.on("agent_speech_stopped")
    def _on_agent_speech_stopped():
        logger.info("🛑 AGENT STOPPED SPEAKING")

    @session.on("user_started_speaking")
    def _on_user_started_speaking():
        logger.info("👂 USER STARTED SPEAKING (detected by VAD)")

    @session.on("user_stopped_speaking")
    def _on_user_stopped_speaking():
        logger.info("🔇 USER STOPPED SPEAKING (detected by VAD)")

    # STEP 6: Start the session
    logger.info("STEP 5: Starting AgentSession...")
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    logger.info("=" * 80)
    logger.info("✓ VOICE AGENT FULLY INITIALIZED AND LISTENING")
    logger.info("=" * 80)
    logger.info("Waiting for user audio input...")
    logger.info("If you speak now, you should see VAD and transcription events above")
    logger.info("=" * 80)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=LIVEKIT_AGENT_NAME,
            ws_url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
    )