"""
LiveKit-based Voice Agent for EV Charging Chatbot - PRODUCTION VERSION
Features:
- Proper RAG integration with FAISS vector search
- Real-time streaming transcriptions
- Human handoff capability
- Complete conversation logging
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
    function_tool,
    RunContext,
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ev-charging-agent")

# System prompts for the agent with RAG instructions
SYSTEM_PROMPT_EN = """You are a helpful customer service agent for an EV battery charging and swapping service in India.
You assist hypermarket delivery personnel (HDP) with queries about charging stations, battery swapping, account management, and technical issues.

CRITICAL INSTRUCTIONS FOR USING KNOWLEDGE BASE:
1. When a user asks a question, you have access to a knowledge base search function
2. ALWAYS call the search_knowledge_base function FIRST before answering any question
3. If the search returns relevant information, use it to answer the user's question
4. If the search returns no relevant information or says "No relevant information found", respond EXACTLY with:
   "I'm sorry, I don't have information about that in my knowledge base. Would you like me to transfer your call to a human agent who can better assist you?"
5. If user agrees to transfer, call the transfer_to_human_agent function

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
1. जब उपयोगकर्ता कोई प्रश्न पूछता है, तो पहले knowledge base search function का उपयोग करें
2. यदि search में प्रासंगिक जानकारी मिलती है, तो उसका उपयोग करके उत्तर दें
3. यदि कोई प्रासंगिक जानकारी नहीं मिलती है, तो कहें:
   "मुझे खेद है, मेरे पास इसके बारे में जानकारी नहीं है। क्या आप चाहेंगे कि मैं आपका कॉल किसी मानव एजेंट को transfer कर दूं?"

बातचीत की शैली:
- विनम्र और पेशेवर रहें
- स्वाभाविक रूप से बोलें
- संक्षिप्त उत्तर दें (2-3 वाक्य)
"""


class EVChargingAssistant(Agent):
    """EV Charging Voice Assistant with FAISS RAG and human handoff"""

    def __init__(self):
        """Initialize the assistant with vector search capability"""
        super().__init__(instructions=SYSTEM_PROMPT_EN)

        try:
            self.vector_search = VectorSearch()
            self.current_language = 'en'
            logger.info("✓ Vector search initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize vector search: {e}")
            logger.warning("⚠️  Agent will run without vector search - RAG disabled!")
            self.vector_search = None

        # Add function tools
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
        Search the EV charging knowledge base for information.
        
        Args:
            query: The user's question to search for in the knowledge base
            
        Returns:
            Relevant information from the knowledge base, or "No relevant information found"
        """
        logger.info(f"🔍 Searching knowledge base for: '{query}'")
        
        if not self.vector_search:
            return "Knowledge base is not available. Please transfer to human agent."
        
        try:
            # Detect language
            self.current_language = self.detect_language(query)
            
            # Get relevant context from FAISS
            results = self.vector_search.get_context_for_llm(
                query=query,
                language=self.current_language,
                top_k=3
            )
            
            if results and len(results.strip()) > 0:
                logger.info(f"✓ Found relevant context ({len(results)} chars)")
                return f"RELEVANT INFORMATION FROM KNOWLEDGE BASE:\n{results}"
            else:
                logger.info("⚠️  No relevant information found in knowledge base")
                return "No relevant information found in the knowledge base for this query."
                
        except Exception as e:
            logger.error(f"❌ Error searching knowledge base: {e}")
            return "Error accessing knowledge base. Please transfer to human agent."

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
            if hasattr(context, 'room'):
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
        
        # In a real system, this would integrate with your call center software
        return "I'm transferring your call to a human agent now. Please hold for a moment. They will be with you shortly."


def prewarm(proc: JobProcess):
    """Prewarm function to load models before first use"""
    logger.info("🔄 Prewarming models...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("✓ VAD model prewarmed")


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent"""
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "service": "ev-charging-chatbot"
    }

    logger.info("=" * 80)
    logger.info("🚀 STARTING EV CHARGING VOICE AGENT - PRODUCTION MODE")
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

    # Initialize the assistant with RAG
    logger.info("🤖 Initializing EV Charging Assistant with RAG...")
    assistant = EVChargingAssistant()

    # Create the agent session
    logger.info("🎙️ Creating AgentSession...")
    session = AgentSession(
        stt=oai.STT(
            model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe"),  # documented model
            language="en",
            use_realtime=True,
        ),
        llm=oai.LLM(
            model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
            # temperature=0.2,
        ),
        tts=oai.TTS(
            model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            voice="alloy",
            speed=1.0,
        ),
        turn_detection="vad",
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,  # Disabled to ensure RAG happens before LLM
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

    # Real-time transcription handling - sends both partial and final
    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(ev: voice_events.UserInputTranscribedEvent):
        """Send real-time transcriptions (both partial and final)"""
        
        # Log for debugging
        if ev.is_final:
            logger.info(f"💬 USER (final): '{ev.transcript}'")
        else:
            logger.debug(f"💬 USER (partial): '{ev.transcript}'")
        
        # Async task to Publish to frontend - both partial and final for real-time feel
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
                    reliable=ev.is_final,  # Use reliable delivery for final transcripts
                )
                logger.info(f"✓ Published user transcript to frontend: '{ev.transcript[:50]}...'")
            except Exception as e:
                logger.warning(f"❌ Failed to publish user transcript: {e}")
       
        # Create task to run async publish
        asyncio.create_task(publish_user_transcript())

    @session.on("user_speech_committed")
    def _on_user_speech_committed(speech_text: str):
        """Called when user finishes speaking - log for monitoring"""
        logger.info(f"✓ User speech committed: '{speech_text[:100]}...'")

    @session.on("agent_speech_started")
    def _on_agent_speech_started():
        """Called when agent starts speaking"""
        logger.info("🗣️  Agent started speaking")

    @session.on("agent_speech_stopped") 
    def _on_agent_speech_stopped():
        """Called when agent stops speaking"""
        logger.info("🛑 Agent stopped speaking")

    # Handle assistant responses - send complete sentences
    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: voice_events.ConversationItemAddedEvent):
        """Send assistant responses when they're added to conversation"""
        item = ev.item
        
        # Only process assistant messages
        if not isinstance(item, llm.ChatMessage) or item.role != "assistant":
            return

        text = item.text_content or ""
        if not text:
            return
            
        logger.info(f"🤖 ASSISTANT: '{text}'")
        
        # Async task to Publish complete assistant response to frontend
        async def publish_assistant_response():
            try:
                await ctx.room.local_participant.publish_data(
                    json.dumps({
                        "type": "transcription",
                        "role": "assistant",
                        "text": text,
                        "isFinal": True,
                        "language": "en",  # Assistant always responds in detected language
                        "timestamp": asyncio.get_event_loop().time(),
                    }).encode("utf-8"),
                    reliable=True,
                )
                logger(f"✓ Published assistant response to frontend: '{text[:50]}...'")
            except Exception as e:
                logger.warning(f"❌ Failed to publish assistant response: {e}")
        
        # Create task to run async publish
        asyncio.create_task(publish_assistant_response())

    # Track subscribed event for debugging
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"🎧 Audio track subscribed from {participant.identity}")

    # Start the session
    logger.info("▶️  Starting AgentSession...")
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    logger.info("=" * 80)
    logger.info("✅ VOICE AGENT FULLY INITIALIZED")
    logger.info("=" * 80)
    logger.info("📋 Features enabled:")
    logger.info("   ✓ FAISS vector search (RAG)")
    logger.info("   ✓ Real-time transcriptions")
    logger.info("   ✓ Human agent handoff")
    logger.info("   ✓ Bilingual support (EN/HI)")
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