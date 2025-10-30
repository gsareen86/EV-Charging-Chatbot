"""
LiveKit-based Voice Agent for EV Charging Chatbot
Handles STT -> LLM -> TTS pipeline with FAISS vector search
"""
import os
import logging
from typing import Annotated
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero

from vector_search import VectorSearch

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System prompts for the agent
SYSTEM_PROMPT_EN = """You are a helpful customer service agent for an EV battery charging and swapping service in India.
You assist hypermarket delivery personnel (HDP) with queries about charging stations, battery swapping, account management, and technical issues.

Key guidelines:
1. Be polite, professional, and empathetic
2. Provide clear and concise answers
3. Use the context from the FAQ database to answer questions accurately
4. If you don't know the answer, politely say so and offer to connect them with a human agent
5. Always confirm understanding when dealing with technical issues
6. Speak naturally as if in a phone conversation
7. Keep responses brief (2-3 sentences max) unless more detail is specifically requested

Service areas: Delhi NCR, Mumbai, Bangalore, Hyderabad, and Pune
Support: 24x7 helpline available
Battery swap time: 2-3 minutes
All stations support QR code authentication
"""

SYSTEM_PROMPT_HI = """आप भारत में EV बैटरी चार्जिंग और स्वैपिंग सेवा के लिए एक सहायक ग्राहक सेवा एजेंट हैं।
आप हाइपरमार्केट डिलीवरी कर्मियों (HDP) को चार्जिंग स्टेशन, बैटरी स्वैपिंग, खाता प्रबंधन और तकनीकी समस्याओं के बारे में प्रश्नों में सहायता करते हैं।

मुख्य दिशानिर्देश:
1. विनम्र, पेशेवर और सहानुभूतिपूर्ण रहें
2. स्पष्ट और संक्षिप्त उत्तर प्रदान करें
3. प्रश्नों का सटीक उत्तर देने के लिए FAQ डेटाबेस से संदर्भ का उपयोग करें
4. यदि आपको उत्तर नहीं पता है, तो विनम्रता से कहें और उन्हें मानव एजेंट से जोड़ने की पेशकश करें
5. तकनीकी समस्याओं से निपटते समय हमेशा समझ की पुष्टि करें
6. फोन वार्तालाप की तरह स्वाभाविक रूप से बोलें
7. प्रतिक्रियाओं को संक्षिप्त रखें (अधिकतम 2-3 वाक्य) जब तक कि विशेष रूप से अधिक विवरण का अनुरोध न किया गया हो

सेवा क्षेत्र: दिल्ली एनसीआर, मुंबई, बैंगलोर, हैदराबाद और पुणे
सहायता: 24x7 हेल्पलाइन उपलब्ध
बैटरी स्वैप समय: 2-3 मिनट
सभी स्टेशन QR कोड प्रमाणीकरण का समर्थन करते हैं
"""


class EVChargingAgent:
    """EV Charging Voice Agent with FAISS-backed context"""

    def __init__(self):
        """Initialize the agent with vector search capability"""
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


async def entrypoint(ctx: JobContext):
    """
    Main entrypoint for the voice agent

    This function is called when a new participant joins the room
    """
    logger.info("Starting EV Charging Voice Agent")

    # Initialize the EV Charging Agent
    ev_agent = EVChargingAgent()

    # Connect to the room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: {ctx.room.name}")

    # Initialize the LLM with function calling for context retrieval
    initial_ctx = llm.ChatContext()
    initial_ctx.messages.append(
        llm.ChatMessage(
            role="system",
            content=ev_agent.get_system_prompt()
        )
    )

    # Create function to be called before LLM processes message
    async def _enrich_context(agent: VoicePipelineAgent, chat_ctx: llm.ChatContext):
        """Enrich the chat context with FAISS vector search results"""
        # Get the last user message
        user_messages = [msg for msg in chat_ctx.messages if msg.role == "user"]
        if not user_messages:
            return

        last_message = user_messages[-1].content

        # Get relevant context from vector database
        context = await ev_agent.get_context(last_message)

        if context:
            # Update system prompt with language-specific version
            for i, msg in enumerate(chat_ctx.messages):
                if msg.role == "system":
                    chat_ctx.messages[i] = llm.ChatMessage(
                        role="system",
                        content=ev_agent.get_system_prompt() + context
                    )
                    break

    # Configure the voice pipeline agent
    assistant = VoicePipelineAgent(
        vad=silero.VAD.load(),  # Voice Activity Detection
        stt=openai.STT(
            model="whisper-1",  # Using OpenAI Whisper for STT
            language=None,  # Auto-detect language
        ),
        llm=openai.LLM(
            model="gpt-4o-mini",  # Using GPT-4o-mini as specified (gpt-5-nano not available yet)
            temperature=0.7,
        ),
        tts=openai.TTS(
            model="tts-1",  # Using OpenAI TTS
            voice="nova",  # Nova voice - clear and professional
        ),
        chat_ctx=initial_ctx,
        before_llm_cb=_enrich_context,  # Inject context before LLM processing
    )

    # Start the agent
    assistant.start(ctx.room)

    # Send initial greeting based on detected language
    greeting_en = "Hello! Welcome to EV Charging Support. I'm here to help you with charging stations, battery swapping, and any other queries. How can I assist you today?"
    greeting_hi = "नमस्ते! EV चार्जिंग सपोर्ट में आपका स्वागत है। मैं चार्जिंग स्टेशन, बैटरी स्वैपिंग और अन्य प्रश्नों में आपकी सहायता के लिए यहां हूं। आज मैं आपकी कैसे मदद कर सकता हूं?"

    # Send greeting
    await assistant.say(greeting_en, allow_interruptions=True)

    logger.info("Voice agent started successfully")


def main():
    """Main function to run the worker"""
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
            ws_url=os.getenv("LIVEKIT_URL"),
        )
    )


if __name__ == "__main__":
    main()
