"""
LiveKit Voice Agent - CORRECTED VERSION
Features:
- Fixed RunContext issues
- Latency optimizations (preemptive generation, faster turn detection)
- Proper streaming transcriptions using LiveKit's built-in transcription forwarding
- Working thinking sounds during tool calls
"""
import asyncio
import json
import os
import logging
import time
from typing import Optional
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RoomOutputOptions,
    WorkerOptions,
    cli,
    metrics,
    llm,
    function_tool,
    RunContext,
    get_job_context,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    AudioConfig
)
from livekit.agents.voice import events as voice_events
from livekit.plugins import noise_cancellation, silero, openai as oai, cartesia
from livekit import rtc

from vector_search import VectorSearch

# Load environment variables
load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "ev-charging-assistant")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ev-charging-agent")

# System prompts - UPDATED with tool calling instructions
SYSTEM_PROMPT_EN = """You are a helpful customer service agent for an EV battery charging and swapping service in India.
You assist hypermarket delivery personnel (HDP) with queries about charging stations, battery swapping, account management, and technical issues.

IMPORTANT INSTRUCTIONS:
1. For general conversation (greetings, casual chat, simple questions), respond directly without using tools.
2. ONLY use the 'search_knowledge_base' tool when you need specific information about:
   - Charging station locations, availability, or details
   - Battery swapping procedures or policies
   - Account management or billing
   - Technical issues or troubleshooting
   - Company policies or services

3. DO NOT use the tool for:
   - Greetings (hi, hello, how are you)
   - General conversation
   - Questions you can answer with common knowledge
   - Simple acknowledgments

CONVERSATION STYLE:
- Be polite, professional, and empathetic
- Speak naturally as if in a phone conversation
- Keep responses brief (2-3 sentences) unless more detail is requested
- Your responses should be conversational without complex formatting, emojis, asterisks, or other symbols

Service areas: Delhi NCR, Mumbai, Bangalore, Hyderabad, and Pune
Support: 24x7 helpline available at 1800-XXX-XXXX
"""

SYSTEM_PROMPT_HI = """आप भारत में EV बैटरी चार्जिंग और स्वैपिंग सेवा के लिए एक सहायक ग्राहक सेवा एजेंट हैं।

महत्वपूर्ण निर्देश:
1. सामान्य बातचीत के लिए सीधे उत्तर दें, tools का उपयोग न करें।
2. केवल 'search_knowledge_base' tool का उपयोग करें जब आपको विशिष्ट जानकारी की आवश्यकता हो।

बातचीत की शैली:
- विनम्र और पेशेवर रहें
- स्वाभाविक रूप से बोलें
- संक्षिप्त उत्तर दें (2-3 वाक्य)
"""


class EVChargingAssistant(Agent):
    """
    EV Charging Voice Assistant with INTELLIGENT RAG using tool calling
    The LLM decides when to search the knowledge base.
    """

    def __init__(self):
        """Initialize the assistant with vector search capability"""
        super().__init__(instructions=SYSTEM_PROMPT_EN)

        self.current_language = 'en'
        
        try:
            self.vector_search = VectorSearch()
            logger.info("✓ Vector search initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize vector search: {e}")
            logger.warning("⚠️  Agent will run without vector search - RAG disabled!")
            self.vector_search = None

        # Add tools - LLM will decide when to call them
        self._tools = [
            self.search_knowledge_base,
            self.transfer_to_human_agent,
        ]

    def detect_language(self, text: str) -> str:
        """Detect language from text"""
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return 'hi'
        return 'en'

    @function_tool
    async def search_knowledge_base(
        self,
        context: RunContext,
        query: str
    ) -> str:
        """
        Search the knowledge base for information about EV charging stations, 
        battery swapping, account management, or technical issues.
        
        Use this tool ONLY when you need specific information that you don't already know.
        DO NOT use this for general conversation or greetings.
        
        Args:
            query: The user's question or search query
            
        Returns:
            Relevant information from the knowledge base, or a message if nothing found
        """
        if not self.vector_search:
            return "Knowledge base is not available. Please use general knowledge to answer."
        
        logger.info(f"🔍 RAG TOOL CALLED: Searching for '{query[:100]}...'")
        
        # Get the room from JobContext instead of RunContext
        try:
            job_ctx = get_job_context()
            room = job_ctx.room
            
            # Send UI status notification
            await room.local_participant.publish_data(
                json.dumps({
                    "type": "status_update",
                    "status": "Searching knowledge base...",
                    "status_type": "searching",
                    "timestamp": time.time(),
                }).encode("utf-8"),
                reliable=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send search status: {e}")
        
        # Detect language
        self.current_language = self.detect_language(query)
        
        try:
            # Perform the RAG lookup
            results = self.vector_search.get_context_for_llm(
                query=query,
                language=self.current_language,
                top_k=3
            )
            
            # Send completion status
            try:
                await room.local_participant.publish_data(
                    json.dumps({
                        "type": "status_update",
                        "status": "Search complete",
                        "status_type": "complete",
                        "timestamp": time.time(),
                    }).encode("utf-8"),
                    reliable=True,
                )
            except Exception as e:
                logger.warning(f"Failed to send completion status: {e}")
            
            if results and len(results.strip()) > 0:
                logger.info(f"✅ RAG SUCCESS: Found context ({len(results)} chars)")
                return f"Here is relevant information from our knowledge base:\n\n{results}\n\nUse this information to answer the user's question accurately."
            else:
                logger.info("⚠️  No relevant information found")
                return "I couldn't find specific information about that in our knowledge base. I can either try to help with general knowledge, or transfer you to a human agent for more detailed assistance."
                
        except Exception as e:
            logger.error(f"❌ Error in RAG lookup: {e}")
            return f"I encountered an error while searching. Error: {str(e)}. I can transfer you to a human agent if you need assistance."

    @function_tool
    async def transfer_to_human_agent(
        self,
        context: RunContext,
        reason: str = "User requested human assistance"
    ) -> str:
        """Transfer the call to a human agent."""
        logger.info(f"📞 Transferring to human agent. Reason: {reason}")
        
        try:
            job_ctx = get_job_context()
            room = job_ctx.room
            
            await room.local_participant.publish_data(
                json.dumps({
                    "type": "transfer_request",
                    "reason": reason,
                    "timestamp": time.time(),
                }).encode("utf-8"),
                reliable=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send transfer request: {e}")
        
        return "I'm transferring you to a human agent now. Please hold for a moment."


# Prewarm function for faster cold starts - CORRECTED: Now synchronous
def prewarm(proc: JobProcess):
    """Prewarm VAD and other models for faster startup"""
    logger.info("🔥 Prewarming models...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("✓ VAD prewarmed")


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent - OPTIMIZED VERSION"""
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "service": "ev-charging-chatbot"
    }

    logger.info("=" * 80)
    logger.info("🚀 STARTING EV CHARGING VOICE AGENT - OPTIMIZED MODE")
    logger.info("=" * 80)

    # Connect to the room FIRST
    logger.info("🔗 Connecting to room...")
    await ctx.connect()
    logger.info(f"✓ Agent connected to room: {ctx.room.name}")
    
    # Wait for user participant
    logger.info("⏳ Waiting for user participant...")
    try:
        participant = await ctx.wait_for_participant()
        logger.info(f"✓ User participant joined: {participant.identity}")
    except Exception as e:
        logger.error(f"Error waiting for participant: {e}")

    # Initialize the assistant
    logger.info("🤖 Initializing EV Charging Assistant...")
    assistant = EVChargingAssistant()

    # Create the agent session with OPTIMIZED settings for low latency
    logger.info("🎙️ Creating AgentSession with optimizations...")
    session = AgentSession(
        stt=oai.STT(
            model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe"),
            language="en",
        ),
        llm=oai.LLM(
            model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
        ),
        tts=cartesia.TTS(
            voice="faf0731e-dfb9-4cfc-8119-259a79b27e12",
            model=os.getenv("CARTESIA_TTS_MODEL"),
            api_key=os.getenv("CARTESIA_API_KEY"),
            language=os.getenv("CARTESIA_LANGUAGE"),
        ),
        turn_detection="vad",
        vad=ctx.proc.userdata["vad"],
        # LATENCY OPTIMIZATIONS
        preemptive_generation=True,  # Start LLM before VAD confirms end of speech
        min_endpointing_delay=0.3,   # Faster turn detection (reduced from 0.5s)
        max_endpointing_delay=2.5,   # Reduced from 3.0s
    )

    # Set up metrics collection
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Session Usage Summary: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # Real-time transcription handling - USER INPUT STREAMING
    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(ev: voice_events.UserInputTranscribedEvent):
        """Send real-time user transcriptions to frontend - both partial and final"""
        
        if ev.is_final:
            logger.info(f"💬 USER (final): '{ev.transcript}'")
        else:
            logger.debug(f"💬 USER (partial): '{ev.transcript}'")
        
        async def publish_user_transcript():
            try:
                await ctx.room.local_participant.publish_data(
                    json.dumps({
                        "type": "transcription",
                        "role": "user",
                        "text": ev.transcript,
                        "isFinal": ev.is_final,
                        "language": ev.language or "en",
                        "timestamp": time.time(),
                    }).encode("utf-8"),
                    reliable=ev.is_final,  # Only guarantee delivery for final transcripts
                )
            except Exception as e:
                logger.warning(f"❌ Failed to publish user transcript: {e}")
       
        asyncio.create_task(publish_user_transcript())

    @session.on("user_speech_committed")
    def _on_user_speech_committed(speech_text: str):
        logger.info(f"✓ User speech committed: '{speech_text[:100]}...'")

    @session.on("agent_speech_started")
    def _on_agent_speech_started():
        logger.info("🗣️  Agent started speaking")

    @session.on("agent_speech_stopped") 
    def _on_agent_speech_stopped():
        logger.info("🛑 Agent stopped speaking")

    # STREAMING ASSISTANT RESPONSES via conversation_item_added
    # This fires when the LLM generates a response
    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: voice_events.ConversationItemAddedEvent):
        """Stream assistant responses to frontend"""
        item = ev.item
        
        if not isinstance(item, llm.ChatMessage) or item.role != "assistant":
            return

        text = item.text_content or ""
        if not text or "Here is relevant information from our knowledge base" in text:
            return
            
        logger.info(f"🤖 ASSISTANT: '{text}'")
        
        async def publish_assistant_response():
            try:
                # Send as final message
                await ctx.room.local_participant.publish_data(
                    json.dumps({
                        "type": "transcription",
                        "role": "assistant",
                        "text": text,
                        "isFinal": True,
                        "language": "en",
                        "timestamp": time.time(),
                    }).encode("utf-8"),
                    reliable=True,
                )
            except Exception as e:
                logger.warning(f"❌ Failed to publish assistant response: {e}")
        
        asyncio.create_task(publish_assistant_response())

    # Track subscription
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"🎧 Audio track subscribed from {participant.identity}")

    # Start the session with transcription enabled and unsynced for faster delivery
    logger.info("▶️  Starting AgentSession...")
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(
            transcription_enabled=True,      # Enable transcription forwarding
            sync_transcription=False,        # Don't sync to audio for faster delivery
        ),
    )

    # Initialize thinking sounds AFTER session starts
    logger.info("🎵 Initializing background audio with thinking sounds...")
    background_audio = BackgroundAudioPlayer(
        # No ambient sound - just thinking sounds during tool calls
        thinking_sound=AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.4)
    )
    
    # Start the background audio player
    await background_audio.start(room=ctx.room, agent_session=session)
    logger.info("✓ Background audio initialized - thinking sounds will play during tool calls")

    logger.info("=" * 80)
    logger.info("✅ VOICE AGENT FULLY INITIALIZED - OPTIMIZED MODE")
    logger.info("=" * 80)
    logger.info("📋 Optimizations enabled:")
    logger.info("   ✓ Preemptive generation (reduced latency)")
    logger.info("   ✓ Faster turn detection (0.3s min delay)")
    logger.info("   ✓ Unsynced transcriptions (faster delivery)")
    logger.info("   ✓ Thinking sounds (during tool calls)")
    logger.info("   ✓ Fixed RunContext issues")
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