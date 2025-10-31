"""
LiveKit-based Voice Agent for EV Charging Chatbot
Handles STT -> LLM -> TTS pipeline with FAISS vector search
Uses latest LiveKit Agents API with turn detection, preemptive generation, and metrics
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
    inference,
    metrics,
    llm,
)
from livekit.agents.voice import events as voice_events
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

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

SYSTEM_PROMPT_HI = """आप भारत में EV बैटरी चार्जिंग और स्वैपिंग सेवा के लिए एक सहायक ग्राहक सेवा एजेंट हैं।
आप हाइपरमार्केट डिलीवरी कर्मियों (HDP) को चार्जिंग स्टेशन, बैटरी स्वैपिंग, खाता प्रबंधन और तकनीकी समस्याओं के बारे में प्रश्नों में सहायता करते हैं।

उपयोगकर्ता आपसे वॉइस के माध्यम से बातचीत कर रहा है, भले ही आप बातचीत को टेक्स्ट के रूप में देखें।

मुख्य दिशानिर्देश:
1. विनम्र, पेशेवर और सहानुभूतिपूर्ण रहें
2. स्वाभाविक बातचीत के स्वर में स्पष्ट और संक्षिप्त उत्तर प्रदान करें
3. प्रश्नों का सटीक उत्तर देने के लिए FAQ डेटाबेस से संदर्भ का उपयोग करें
4. यदि आपको उत्तर नहीं पता है, तो विनम्रता से कहें और उन्हें मानव एजेंट से जोड़ने की पेशकश करें
5. तकनीकी समस्याओं से निपटते समय हमेशा समझ की पुष्टि करें
6. फोन वार्तालाप की तरह स्वाभाविक रूप से बोलें
7. प्रतिक्रियाओं को संक्षिप्त रखें (अधिकतम 2-3 वाक्य) जब तक कि विशेष रूप से अधिक विवरण का अनुरोध न किया गया हो
8. आपकी प्रतिक्रियाएं संक्षिप्त, सटीक हैं और बिना किसी जटिल फॉर्मेटिंग या विराम चिह्न जैसे इमोजी, तारांकन, या अन्य प्रतीकों के

सेवा क्षेत्र: दिल्ली एनसीआर, मुंबई, बैंगलोर, हैदराबाद और पुणे
सहायता: 24x7 हेल्पलाइन 1800-XXX-XXXX पर उपलब्ध
बैटरी स्वैप समय: 2-3 मिनट
सभी स्टेशन QR कोड प्रमाणीकरण का समर्थन करते हैं
"""


class EVChargingAssistant(Agent):
    """EV Charging Voice Assistant with FAISS-backed context retrieval"""

    def __init__(self):
        """Initialize the assistant with vector search capability"""
        # Default to English, will be detected dynamically
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
        """
        Detect language from text
        Simple heuristic: if text contains Hindi unicode characters, it's Hindi

        Args:
            text: Input text to analyze

        Returns:
            Language code ('en' or 'hi')
        """
        # Check for Devanagari script (Hindi)
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return 'hi'
        return 'en'

    async def get_context(self, user_message: str) -> str:
        """
        Get relevant context from FAISS vector database

        Args:
            user_message: User's query

        Returns:
            Context string to be added to LLM prompt
        """
        if not self.vector_search:
            return ""

        try:
            # Detect language
            self.current_language = self.detect_language(user_message)
            logger.info(f"Detected language: {self.current_language}")

            # Get relevant FAQs
            context = self.vector_search.get_context_for_llm(
                query=user_message,
                language=self.current_language,
                top_k=3
            )

            return f"\n\nRELEVANT CONTEXT FROM FAQ DATABASE:\n{context}\n\nUse the above context to answer the user's question accurately. If the context doesn't contain relevant information, use your general knowledge about EV charging services."

        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return ""

    def get_system_prompt(self) -> str:
        """Get system prompt based on current language"""
        return SYSTEM_PROMPT_HI if self.current_language == 'hi' else SYSTEM_PROMPT_EN

    # You can add function tools here if needed
    # Example:
    # @function_tool
    # async def check_battery_availability(self, context: RunContext, station_name: str):
    #     """Check battery availability at a specific station"""
    #     logger.info(f"Checking battery availability at {station_name}")
    #     # Implement actual logic here
    #     return f"Station {station_name} has 5 batteries available"


def prewarm(proc: JobProcess):
    """
    Prewarm function to load models before first use
    This improves initial response time
    """
    logger.info("Prewarming models...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD model prewarmed")


async def entrypoint(ctx: JobContext):
    """
    Main entrypoint for the voice agent
    This function is called when a new participant joins the room
    """
    # Logging setup - add context for better debugging
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "service": "ev-charging-chatbot"
    }

    logger.info("Starting EV Charging Voice Agent")

    # Initialize the EV Charging Assistant
    assistant = EVChargingAssistant()

    # Set up the agent session with the voice pipeline
    session = AgentSession(
        # Speech-to-text (STT) - the agent's ears
        # Using OpenAI Whisper with auto language detection
        stt=inference.STT(
            model="openai/whisper-1",
            language=None,  # Auto-detect between English and Hindi
        ),

        # Large Language Model (LLM) - the agent's brain
        # Using GPT-4o-mini for fast, cost-effective responses
        llm=inference.LLM(
            model="openai/gpt-4o-mini",
            temperature=0.7,  # Balanced between creativity and consistency
        ),

        # Text-to-speech (TTS) - the agent's voice
        # Using OpenAI TTS with a clear, professional voice
        tts=inference.TTS(
            model="openai/tts-1",
            voice="nova",  # Clear and professional voice
        ),

        # Voice Activity Detection and Turn Detection
        # MultilingualModel supports both English and Hindi
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],

        # Preemptive generation allows the LLM to start generating
        # a response while waiting for the end of the user's turn
        # This significantly reduces response latency
        preemptive_generation=True,
    )

    # For using OpenAI Realtime API instead (alternative approach):
    # Uncomment below and install livekit-agents[openai]
    # from livekit.plugins import openai
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="shimmer")
    # )

    # Set up metrics collection to measure pipeline performance
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        """Handle metrics collection events"""
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        """Log usage summary on shutdown"""
        summary = usage_collector.get_summary()
        logger.info(f"Session Usage Summary: {summary}")

    # Register shutdown callback
    ctx.add_shutdown_callback(log_usage)

    # Custom before_llm callback to inject FAISS context
    async def _handle_user_speech(speech_text: str) -> None:
        """Async helper to process committed user speech."""
        logger.info(f"User said: {speech_text}")

        # Get context from FAISS
        context = await assistant.get_context(speech_text)

        if context:
            # Update the agent's instructions with the retrieved context
            # and language-appropriate system prompt
            updated_instructions = assistant.get_system_prompt() + context
            assistant.instructions = updated_instructions
            logger.info("Context injected into agent instructions")

    @session.on("user_speech_committed")
    def _on_user_speech(speech_text: str) -> None:
        """Schedule async handling for committed user speech."""
        asyncio.create_task(_handle_user_speech(speech_text))

    def publish_transcript_message(
        *,
        role: str,
        text: str,
        is_final: bool,
        language: Optional[str] = None,
    ) -> None:
        """Publish transcription data to room participants via the data channel."""

        if not text:
            return

        if not language:
            language = assistant.detect_language(text)

        try:
            ctx.room.local_participant.publish_data(
                json.dumps(
                    {
                        "type": "transcription",
                        "role": role,
                        "text": text,
                        "isFinal": is_final,
                        "language": language,
                    }
                ).encode("utf-8"),
                reliable=is_final,
            )
        except Exception as publish_error:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to publish transcript data: %s", publish_error, exc_info=True
            )

    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(ev: voice_events.UserInputTranscribedEvent):
        publish_transcript_message(
            role="user",
            text=ev.transcript,
            is_final=ev.is_final,
            language=ev.language,
        )

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: voice_events.ConversationItemAddedEvent):
        item = ev.item
        if not isinstance(item, llm.ChatMessage):
            return

        if item.role != "assistant":
            return

        text = item.text_content or ""
        publish_transcript_message(role="assistant", text=text, is_final=True)

    # Start the session
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # Use BVC noise cancellation for clear audio
            # For telephony applications, use BVCTelephony instead
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Connect to the room
    await ctx.connect()

    logger.info(f"Agent connected to room: {ctx.room.name}")
    logger.info("Voice agent started successfully with turn detection and preemptive generation enabled")


if __name__ == "__main__":
    # Run the agent with prewarm function
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
