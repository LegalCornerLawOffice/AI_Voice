# AI Voice Intake System

Legal intake call automation system with speech recognition, LLM processing, and text-to-speech.

## Architecture Overview

### Core Design Principles
- **Web-first with phone compatibility**: Prioritize web interface, but architect for easy phone migration
- **Async everything**: Handle 20+ concurrent calls with single server
- **Provider abstraction**: Easy to swap STT/LLM/TTS providers
- **HIPAA-ready**: Architecture designed for healthcare/legal compliance

### Technology Stack

**Current (MVP):**
- **STT**: Deepgram (real-time streaming, low latency)
- **LLM**: AWS Bedrock (Claude 3.5 Sonnet - HIPAA compliant)
- **TTS**: Deepgram (real-time streaming, low latency)
- **Server**: FastAPI + Uvicorn (async WebSocket)
- **State**: Redis (conversation state management)
- **Database**: PostgreSQL (call records, extracted fields)
- **Hosting**: Railway/Render (dev) → AWS (production)

**Phone Support (Week 2):**
- **Telephony**: Twilio Media Streams
- **Audio**: mu-law ↔ PCM conversion layer

### Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│  Client (Browser or Phone)                          │
│  - WebRTC microphone access (web)                   │
│  - Twilio Media Streams (phone)                     │
└─────────────────┬───────────────────────────────────┘
                  │ WebSocket (PCM audio)
┌─────────────────▼───────────────────────────────────┐
│  FastAPI Server                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  Audio Handler Layer (abstracted)              │ │
│  │  - WebRTCAudioHandler (web)                    │ │
│  │  - TwilioAudioHandler (phone - future)         │ │
│  └─────────────┬──────────────────────────────────┘ │
│                │                                     │
│  ┌─────────────▼──────────────────────────────────┐ │
│  │  Audio Pipeline                                │ │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │ │
│  │  │ Deepgram │→ │  Bedrock │→ │  Deepgram   │ │ │
│  │  │   STT    │  │   LLM    │  │    TTS      │ │ │
│  │  └──────────┘  └──────────┘  └─────────────┘ │ │
│  └────────────────────────────────────────────────┘ │
│                │                                     │
│  ┌─────────────▼──────────────────────────────────┐ │
│  │  State Manager (Redis)                         │ │
│  │  - Conversation state                          │ │
│  │  - Collected fields                            │ │
│  │  - Branching logic tracking                    │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│  PostgreSQL Database                                 │
│  - Call records                                      │
│  - Full transcripts                                  │
│  - Extracted intake fields (300+ fields)            │
│  - QA review queue                                   │
└──────────────────────────────────────────────────────┘
```

### Concurrency Support

**Single Server Capacity (t3.medium):**
- 100+ concurrent calls
- Current need: 2-3 concurrent (25 calls/day)
- Headroom: 30-50x

**Async Design:**
- Non-blocking I/O throughout
- Connection pooling for external services
- Shared client instances
- Event-driven architecture

## Project Structure

```
AI_Voice/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── .env.example             # Environment template
├── config.py                # Configuration management
├── main.py                  # FastAPI application entry point
├── models/
│   ├── __init__.py
│   └── database.py          # SQLAlchemy models
├── services/
│   ├── __init__.py
│   ├── deepgram_stt.py     # Deepgram speech-to-text
│   ├── deepgram_tts.py     # Deepgram text-to-speech
│   ├── bedrock_llm.py      # AWS Bedrock LLM client
│   └── state_manager.py    # Redis conversation state
├── handlers/
│   ├── __init__.py
│   ├── base.py             # Abstract AudioHandler
│   ├── webrtc.py           # WebRTC handler (web)
│   └── twilio.py           # Twilio handler (phone - future)
├── conversation/
│   ├── __init__.py
│   ├── flow.py             # Conversation flow logic
│   ├── prompts.py          # LLM prompts
│   └── intake_fields.py    # Field mapping from Salesforce
├── pipeline/
│   ├── __init__.py
│   └── audio_pipeline.py   # Core STT→LLM→TTS pipeline
├── utils/
│   ├── __init__.py
│   ├── logging.py          # Structured logging
│   └── monitoring.py       # Health checks, metrics
├── web/
│   ├── index.html          # Web client interface
│   └── client.js           # WebSocket + WebRTC logic
└── tests/
    ├── __init__.py
    └── test_pipeline.py    # Unit tests
```

## Getting Started

### Prerequisites
- Python 3.10+
- Redis (local or cloud)
- PostgreSQL (local or cloud)
- AWS account (Bedrock access)
- Deepgram API key

### Installation

```bash
cd AI_Voice

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your API keys
nano .env
```

### Run Development Server

```bash
# Start Redis (or use cloud Redis)
# redis-server

# Run FastAPI server
python main.py

# Open browser to http://localhost:8000
```