# EV Charging Voice Chatbot

An AI-powered voice chatbot for electric vehicle charging stations, designed to assist hypermarket delivery personnel (HDP) with queries about battery charging and swapping services across India.

## Features

- **Voice-Based Interaction**: Real-time voice conversations using LiveKit's optimized STT-LLM-TTS pipeline
- **Bilingual Support**: Handles queries in both Hindi and English with automatic language detection
- **Smart Context Retrieval**: Uses FAISS vector database for intelligent FAQ matching
- **Low Latency**: Optimized for fast response times using LiveKit framework
- **Professional UI**: Clean, responsive web interface with live transcriptions
- **Real-Time Transcription**: See live transcripts of conversations in both languages
- **Call Controls**: Easy-to-use connect, disconnect, mute/unmute controls

## Architecture

```
┌─────────────────┐
│   Web Browser   │
│   (Frontend)    │
└────────┬────────┘
         │
         │ WebSocket (LiveKit)
         │
┌────────▼────────┐
│  Flask Server   │
│ (Token Gen)     │
└────────┬────────┘
         │
    ┌────▼─────────────────────────────┐
    │      LiveKit Server              │
    │  (Voice Stream Management)       │
    └────┬─────────────────────────────┘
         │
┌────────▼────────────────────────────┐
│      Voice Agent (Python)           │
│  ┌──────────────────────────────┐  │
│  │  STT (OpenAI Whisper)        │  │
│  └──────────┬───────────────────┘  │
│             │                        │
│  ┌──────────▼───────────────────┐  │
│  │  FAISS Vector Search         │  │
│  │  (FAQ Context Retrieval)     │  │
│  └──────────┬───────────────────┘  │
│             │                        │
│  ┌──────────▼───────────────────┐  │
│  │  LLM (GPT-4o-mini)           │  │
│  └──────────┬───────────────────┘  │
│             │                        │
│  ┌──────────▼───────────────────┐  │
│  │  TTS (OpenAI TTS)            │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Technology Stack

### Backend
- **Python 3.8+**: Core backend language
- **LiveKit**: Real-time voice communication framework
- **OpenAI API**: Whisper (STT), GPT-4o-mini (LLM), TTS
- **FAISS**: Vector similarity search for FAQ retrieval
- **Flask**: Web server for frontend and API

### Frontend
- **HTML5/CSS3**: Structure and styling
- **JavaScript (ES6+)**: Interactive functionality
- **LiveKit Client SDK**: WebRTC communication

## Quick Start

### Prerequisites

1. Python 3.8+
2. LiveKit Server (or Docker)
3. OpenAI API Key

### Installation

```bash
# 1. Run setup
./scripts/setup.sh

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Build vector database
./scripts/build_db.sh

# 4. Start services (3 separate terminals)
./scripts/start_livekit.sh  # Terminal 1
./scripts/start_server.sh   # Terminal 2
./scripts/start_agent.sh    # Terminal 3

# 5. Open http://localhost:5000
```

## Project Structure

```
EV-Charging-Chatbot/
├── backend/
│   ├── voice_agent.py          # LiveKit voice agent
│   ├── vector_search.py        # FAISS search
│   ├── build_vector_db.py      # Build FAISS index
│   └── server.py               # Flask server
├── frontend/
│   ├── index.html              # Main UI
│   ├── styles.css              # Styling
│   └── app.js                  # Frontend logic
├── data/
│   └── faq_data.json           # FAQ data (EN/HI)
└── scripts/                    # Helper scripts
```

## Usage

1. Click "Connect" in the web interface
2. Enter room name and your name
3. Allow microphone access
4. Start speaking in English or Hindi
5. The assistant responds to queries about:
   - Charging station locations
   - Battery availability
   - Operational hours
   - Battery swapping issues
   - KYC and passwords
   - Payment and billing

## Adding FAQs

Edit `data/faq_data.json` and add entries:

```json
{
  "id": 21,
  "category": "category_name",
  "question_en": "Question in English?",
  "question_hi": "प्रश्न हिंदी में?",
  "answer_en": "Answer in English.",
  "answer_hi": "उत्तर हिंदी में।"
}
```

Then rebuild: `./scripts/build_db.sh`

## Troubleshooting

**Connection issues?**
- Ensure LiveKit is running: `curl http://localhost:7880`
- Check Flask server: `curl http://localhost:5000/api/health`

**No voice recognition?**
- Grant microphone permissions in browser
- Use localhost or HTTPS

**FAISS errors?**
- Run: `./scripts/build_db.sh`

## Customization

### Change TTS Voice
Edit `backend/voice_agent.py`:
```python
voice="nova"  # Options: alloy, echo, fable, onyx, nova, shimmer
```

### Adjust Response Style
Edit temperature in `backend/voice_agent.py`:
```python
temperature=0.7  # 0.0 = deterministic, 2.0 = creative
```

## Future Enhancements

- [ ] More Indian languages (Tamil, Telugu, Kannada, Bengali)
- [ ] Real charging station API integration
- [ ] Mobile apps (iOS/Android)
- [ ] Analytics dashboard
- [ ] Voice biometrics
- [ ] Offline mode

## Version

v1.0.0 - Initial release with English/Hindi support

---

Built for EV charging infrastructure in India