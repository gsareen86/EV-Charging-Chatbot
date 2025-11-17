"""
LiveKit Voice Agent - OPTIMIZED VERSION with LiveKit Best Practices
Features:
- on_user_turn_completed for efficient RAG (no extra LLM round trips)
- Verbal status updates during RAG lookups
- Thinking sounds during processing
- UI status notifications
- Improved response times
"""
import asyncio
import json
import os
import logging
import random
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
    function_tool,
    RunContext,
    BackgroundAudioPlayer,
    AudioConfig,
    BuiltinAudioClip,
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

# Default thinking messages for verbal status updates
DEFAULT_THINKING_MESSAGES = [
    "Let me look that up for you...",
    "One moment while I check our knowledge base...",
    "I'll find that information for you...",
    "Just a second while I search...",
    "Looking into that now...",
    "Checking our database for you...",
    "Let me get that information...",
]

# System prompts - UPDATED to work with on_user_turn_completed
SYSTEM_PROMPT_EN = """You are a helpful customer service agent for an EV battery charging and swapping service in India.
You assist hypermarket delivery personnel (HDP) with queries about charging stations, battery swapping, account management, and technical issues.

IMPORTANT: When you receive additional context in the conversation, use it to answer the user's question accurately.
If the context says "No relevant information found", respond EXACTLY with:
"I'm sorry, I don't have information about that in my knowledge base. Would you like me to transfer your call to a human agent who can better assist you?"

CONVERSATION STYLE:
- Be polite, professional, and empathetic
- Speak naturally as if in a phone conversation
- Keep responses brief (2-3 sentences) unless more detail is requested
- Your responses should be conversational without complex formatting, emojis, asterisks, or other symbols

Service areas: Delhi NCR, Mumbai, Bangalore, Hyderabad, and Pune
Support: 24x7 helpline available at 1800-XXX-XXXX
"""

SYSTEM_PROMPT_HI = """आप भारत में EV बैटरी चार्जिंग और स्वैपिंग सेवा के लिए एक सहायक ग्राहक सेवा एजेंट हैं।

महत्वपूर्ण: जब आपको conversation में additional context मिले, तो उसका उपयोग करके उत्तर दें।
यदि context में "No relevant information found" है, तो कहें:
"मुझे खेद है, मेरे पास इसके बारे में जानकारी नहीं है। क्या आप चाहेंगे कि मैं आपका कॉल किसी मानव एजेंट को transfer कर दूं?"

बातचीत की शैली:
- विनम्र और पेशेवर रहें
- स्वाभाविक रूप से बोलें
- संक्षिप्त उत्तर दें (2-3 वाक्य)
"""


class EVChargingAssistant(Agent):
    """
    EV Charging Voice Assistant with OPTIMIZED RAG using on_user_turn_completed
    This approach is faster than function tools as it:
    1. Doesn't require extra LLM round trips
    2. Injects context directly before LLM generation
    3. Provides verbal status updates during processing
    """

    def __init__(self, session: AgentSession, job_context: JobContext):
        """Initialize the assistant with vector search capability"""
        super().__init__(instructions=SYSTEM_PROMPT_EN)

        self.session = session
        self.job_context = job_context
        self.current_language = 'en'
        
        try:
            self.vector_search = VectorSearch()
            logger.info("✓ Vector search initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize vector search: {e}")
            logger.warning("⚠️  Agent will run without vector search - RAG disabled!")
            self.vector_search = None

        # Add human handoff tool
        self._tools = [
            self.transfer_to_human_agent,
        ]

    def detect_language(self, text: str) -> str:
        """Detect language from text"""
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return 'hi'
        return 'en'

    async def _send_status_to_ui(self, status: str, status_type: str = "searching"):
        """Send status update to the frontend UI"""
        try:
            await self.job_context.room.local_participant.publish_data(
                json.dumps({
                    "type": "status_update",
                    "status": status,
                    "status_type": status_type,
                    "timestamp": asyncio.get_event_loop().time(),
                }).encode("utf-8"),
                reliable=True,
            )
            logger.info(f"📤 Status sent to UI: {status}")
        except Exception as e:
            logger.warning(f"❌ Failed to send status to UI: {e}")

    async def on_user_turn_completed(
        self, 
        turn_ctx: llm.ChatContext, 
        new_message: llm.ChatMessage
    ) -> None:
        """
        OPTIMIZED RAG IMPLEMENTATION using on_user_turn_completed
        This is called BEFORE the LLM generates a response, allowing us to:
        1. Perform RAG lookup efficiently
        2. Inject context directly into the chat
        3. Provide status updates during processing
        
        Key advantages over function tools:
        - No extra LLM round trips
        - Faster response times
        - Direct context injection
        """
        
        if not self.vector_search:
            return
        
        user_text = new_message.text_content() or ""
        if not user_text.strip():
            return
            
        logger.info(f"🔍 RAG LOOKUP: Processing query: '{user_text[:100]}...'")
        
        # Detect language
        self.current_language = self.detect_language(user_text)
        
        # Create async tasks for:
        # 1. Verbal status update (after 500ms delay)
        # 2. UI status notification (immediate)
        # 3. RAG lookup
        
        # Send immediate UI status
        await self._send_status_to_ui("Searching knowledge base...", "searching")
        
        # Create verbal status update task with delay
        async def _speak_status_update():
            await asyncio.sleep(0.5)  # Wait 500ms before speaking
            
            # Choose a random thinking message
            thinking_msg = random.choice(DEFAULT_THINKING_MESSAGES)
            
            logger.info(f"🗣️  Speaking status update: {thinking_msg}")
            await self._send_status_to_ui(thinking_msg, "speaking")
            
            # Generate brief verbal update
            await self.session.generate_reply(
                instructions=f"""Say this exact message briefly: "{thinking_msg}" 
                Be very brief and natural.""",
                allow_interruptions=False,
            )
        
        status_task = asyncio.create_task(_speak_status_update())
        
        try:
            # Perform the RAG lookup
            results = self.vector_search.get_context_for_llm(
                query=user_text,
                language=self.current_language,
                top_k=3
            )
            
            # Cancel status update if search completed quickly
            if not status_task.done():
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass
            
            # Send completion status to UI
            await self._send_status_to_ui("Search complete", "complete")
            
            if results and len(results.strip()) > 0:
                logger.info(f"✅ RAG SUCCESS: Found context ({len(results)} chars)")
                
                # Inject context DIRECTLY into the chat context
                # This message is used by the LLM but not spoken to the user
                turn_ctx.add_message(
                    role="assistant",
                    content=f"""RELEVANT INFORMATION FROM KNOWLEDGE BASE:
{results}

Use this information to answer the user's question accurately."""
                )
                
                logger.info("✓ Context injected into chat for LLM generation")
            else:
                logger.info("⚠️  No relevant information found")
                
                # Inform the LLM that no context was found
                turn_ctx.add_message(
                    role="assistant",
                    content="No relevant information found in the knowledge base for this query. Offer to transfer to human agent."
                )
                
        except Exception as e:
            logger.error(f"❌ Error in RAG lookup: {e}")
            
            # Cancel status update if there was an error
            if not status_task.done():
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass
            
            await self._send_status_to_ui("Search failed", "error")

    @function_tool
    async def transfer_to_human_agent(
        self,
        context: RunContext,
        reason: str = "User requested human assistance"
    ) -> str:
        """
        Transfer the call to a human agent.
        
        Args:
            reason: Reason for the transfer
            
        Returns:
            Confirmation message
        """
        logger.info(f"📞 Transferring to human agent. Reason: {reason}")
        
        # Publish transfer event to frontend
        try:
            await context.room.local_participant.publish_data(
                json.dumps({
                    "type": "transfer_request",
                    "reason": reason,
                    "timestamp": str(asyncio.get_event_loop().time())
                }).encode("utf-8"),
                reliable=True,
            )
        except Exception as e:
            logger.warning(f"Failed to publish transfer event: {e}")
        
        return "I'm transferring your call to a human agent now. Please hold for a moment. They will be with you shortly."


def prewarm(proc: JobProcess):
    """Prewarm function to load models before first use"""
    logger.info("🔄 Prewarming models...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("✓ VAD model prewarmed")


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

    # Create the agent session
    logger.info("🎙️ Creating AgentSession...")
    session = AgentSession(
        stt=oai.STT(
            model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe"),
            language="en",
            use_realtime=True,
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
        preemptive_generation=False,  # Keep disabled for accurate RAG
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

    # Real-time transcription handling
    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(ev: voice_events.UserInputTranscribedEvent):
        """Send real-time transcriptions to frontend"""
        
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
                        "timestamp": asyncio.get_event_loop().time(),
                    }).encode("utf-8"),
                    reliable=ev.is_final,
                )
            except Exception as e:
                logger.warning(f"❌ Failed to publish user transcript: {e}")
       
        asyncio.create_task(publish_user_transcript())

    @session.on("user_speech_committed")
    def _on_user_speech_committed(speech_text: str):
        """Called when user finishes speaking"""
        logger.info(f"✓ User speech committed: '{speech_text[:100]}...'")

    @session.on("agent_speech_started")
    def _on_agent_speech_started():
        """Called when agent starts speaking"""
        logger.info("🗣️  Agent started speaking")

    @session.on("agent_speech_stopped") 
    def _on_agent_speech_stopped():
        """Called when agent stops speaking"""
        logger.info("🛑 Agent stopped speaking")

    # Handle assistant responses
    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: voice_events.ConversationItemAddedEvent):
        """Send assistant responses to frontend"""
        item = ev.item
        
        if not isinstance(item, llm.ChatMessage) or item.role != "assistant":
            return

        text = item.text_content or ""
        if not text or "RELEVANT INFORMATION FROM KNOWLEDGE BASE" in text:
            # Skip internal context messages
            return
            
        logger.info(f"🤖 ASSISTANT: '{text}'")
        
        async def publish_assistant_response():
            try:
                await ctx.room.local_participant.publish_data(
                    json.dumps({
                        "type": "transcription",
                        "role": "assistant",
                        "text": text,
                        "isFinal": True,
                        "language": "en",
                        "timestamp": asyncio.get_event_loop().time(),
                    }).encode("utf-8"),
                    reliable=True,
                )
            except Exception as e:
                logger.warning(f"❌ Failed to publish assistant response: {e}")
        
        asyncio.create_task(publish_assistant_response())

    # Track subscription for debugging
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"🎧 Audio track subscribed from {participant.identity}")

    # Initialize the assistant with session and context
    logger.info("🤖 Initializing EV Charging Assistant with OPTIMIZED RAG...")
    assistant = EVChargingAssistant(session=session, job_context=ctx)

    # Start the session
    logger.info("▶️  Starting AgentSession...")
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Add background audio for thinking sounds
    logger.info("🎵 Setting up background audio (thinking sounds)...")
    background_audio = BackgroundAudioPlayer(
        # Play subtle typing sound when agent is thinking/processing
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.3, probability=0.6),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.25, probability=0.4),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    logger.info("✓ Background audio started")

    logger.info("=" * 80)
    logger.info("✅ VOICE AGENT FULLY INITIALIZED - OPTIMIZED MODE")
    logger.info("=" * 80)
    logger.info("📋 Optimizations enabled:")
    logger.info("   ✓ on_user_turn_completed RAG (faster than function tools)")
    logger.info("   ✓ Verbal status updates (500ms delay)")
    logger.info("   ✓ Thinking sounds (subtle keyboard typing)")
    logger.info("   ✓ UI status notifications")
    logger.info("   ✓ Direct context injection (no extra LLM round trips)")
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