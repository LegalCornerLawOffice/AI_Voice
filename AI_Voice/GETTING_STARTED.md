# AI Voice Intake System - Getting Started

## Quick Start (5 minutes)

### 1. Setup Environment

```bash
cd AI_Voice

# Run setup script
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit with your keys
nano .env
```

**Required variables:**
- `DEEPGRAM_API_KEY` - Get from https://deepgram.com
- `AWS_ACCESS_KEY_ID` - Your AWS credentials
- `AWS_SECRET_ACCESS_KEY` - Your AWS credentials
- `AWS_REGION` - e.g., us-east-1

**Optional (for development):**
- `REDIS_URL` - Default: redis://localhost:6379
- `DATABASE_URL` - PostgreSQL URL (not required for MVP)

### 3. Get API Keys

#### Deepgram (STT & TTS)
1. Sign up at https://deepgram.com
2. Get $200 free credits
3. Create API key from dashboard
4. Add to `.env` as `DEEPGRAM_API_KEY`

#### AWS Bedrock (LLM)
1. Log into AWS Console
2. Go to Bedrock service
3. Request access to Claude 3.5 Sonnet (instant approval usually)
4. Create IAM user with Bedrock permissions
5. Add credentials to `.env`

### 4. Start Redis (Local Development)

**Option A: Docker (easiest)**
```bash
docker run -d -p 6379:6379 redis:alpine
```

**Option B: Homebrew (macOS)**
```bash
brew install redis
redis-server
```

**Option C: Use cloud Redis**
- Upstash (free tier): https://upstash.com
- Update `REDIS_URL` in .env

### 5. Run the Server

```bash
source venv/bin/activate  # If not already activated
python main.py
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application started successfully
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 6. Open Web Interface

Open your browser to: **http://localhost:8000**

Click "Start Call" and allow microphone access. The AI will greet you!

---

## Project Structure

```
AI_Voice/
├── main.py              # FastAPI application
├── config.py            # Configuration management
├── requirements.txt     # Python dependencies
├── .env                 # Your environment variables (create this)
│
├── handlers/            # Audio input/output handlers
│   ├── base.py         # Abstract base class
│   ├── webrtc.py       # Web browser handler
│   └── twilio.py       # Phone call handler (future)
│
├── services/            # External API integrations
│   ├── deepgram_stt.py # Speech-to-text
│   ├── deepgram_tts.py # Text-to-speech
│   ├── bedrock_llm.py  # LLM processing
│   └── state_manager.py # Redis state management
│
├── conversation/        # Conversation logic
│   ├── flow.py         # Section progression
│   └── prompts.py      # LLM prompts
│
├── pipeline/            # Core audio pipeline
│   └── audio_pipeline.py # STT → LLM → TTS
│
└── web/                 # Web client
    ├── index.html      # UI
    └── client.js       # WebRTC + WebSocket
```

---

## Testing

### Test the Web Interface

1. Start the server: `python main.py`
2. Open http://localhost:8000
3. Click "Start Call"
4. Allow microphone access
5. Wait for AI greeting
6. Respond to questions naturally

### Test Individual Components

```python
# Test Deepgram STT
python -c "from services.deepgram_stt import DeepgramSTTService; print('STT OK')"

# Test Bedrock LLM
python -c "from services.bedrock_llm import BedrockLLMService; print('LLM OK')"

# Test Deepgram TTS
python -c "from services.deepgram_tts import DeepgramTTSService; print('TTS OK')"
```

---

## Troubleshooting

### "WebSocket connection failed"
- ✅ Check server is running
- ✅ Check port 8000 is not in use: `lsof -i :8000`
- ✅ Check browser console for errors

### "Error accessing microphone"
- ✅ Grant microphone permissions in browser
- ✅ Use Chrome or Edge (best WebRTC support)
- ✅ Check System Preferences > Privacy > Microphone (macOS)

### "Deepgram authentication failed"
- ✅ Check `DEEPGRAM_API_KEY` in .env
- ✅ Verify API key is active in Deepgram dashboard
- ✅ Check you have credits remaining

### "Bedrock access denied"
- ✅ Verify AWS credentials in .env
- ✅ Check IAM user has `bedrock:InvokeModel` permission
- ✅ Confirm model access is granted in Bedrock console
- ✅ Verify region supports Bedrock (us-east-1 recommended)

### "Redis connection refused"
- ✅ Start Redis: `redis-server`
- ✅ Or update `REDIS_URL` to point to cloud Redis
- ✅ Test connection: `redis-cli ping` (should return PONG)

### "No audio playing"
- ✅ Check browser audio isn't muted
- ✅ Check system volume
- ✅ Look for TTS errors in server logs

---

## Development Tips

### Watch Logs in Real-Time

```bash
# Terminal 1: Run server with debug logging
DEBUG=true LOG_LEVEL=DEBUG python main.py

# Terminal 2: Watch Redis
redis-cli monitor

# Browser: Open DevTools > Console
```

### Modify Conversation Flow

Edit `conversation/prompts.py` to change AI behavior:
```python
GREETING_PROMPT = """Your custom greeting here"""
```

Edit `conversation/flow.py` to change section progression.

### Test with Mock Audio

Instead of speaking, you can send mock transcripts:
```javascript
// In browser console
websocket.send(JSON.stringify({
    type: 'transcript',
    text: 'My name is John Doe',
    is_final: true
}));
```

---

## Next Steps

### Phase 1: Current (Web MVP) ✅
- [x] WebSocket server
- [x] Deepgram STT
- [x] Bedrock LLM
- [x] Deepgram TTS
- [x] Basic conversation flow
- [ ] **TODO: Add database persistence**
- [ ] **TODO: Add field extraction**

### Phase 2: Enhanced Conversation
- [ ] Map all 300+ intake fields
- [ ] Implement full branching logic
- [ ] Add conversation checkpoints
- [ ] Field validation
- [ ] Admin dashboard for QA

### Phase 3: Phone Support
- [ ] Twilio integration
- [ ] Audio format conversion
- [ ] Phone number setup

### Phase 4: Production
- [ ] Deploy to AWS
- [ ] HIPAA compliance
- [ ] Salesforce integration
- [ ] Monitoring & alerts

---

## Cost Tracking

**Development (testing with 10 calls @ 10 min each):**
- Deepgram: ~$1
- AWS Bedrock: ~$2
- Total: **~$3/day**

**Production (25 calls/day @ 60 min each):**
- Deepgram STT: $6.50/day
- Deepgram TTS: $6.50/day
- AWS Bedrock: $16/day
- Total: **~$29/day** or **$870/month**

Still 97% cheaper than human intake!

---

## Getting Help

**Check logs first:**
```bash
# Server logs show everything
tail -f logs/ai_voice.log
```

**Test components individually:**
```bash
# Test STT
python -c "from services.deepgram_stt import DeepgramSTTService; import asyncio; asyncio.run(DeepgramSTTService().start_stream(lambda t, f: print(t)))"
```

**Common issues:**
1. API key problems → Check .env file
2. Network errors → Check firewall/VPN
3. Audio issues → Test in different browser
4. Redis errors → Restart Redis server

---

## Architecture Overview

```
Browser Microphone
       ↓
   WebSocket
       ↓
  WebRTCAudioHandler (handlers/webrtc.py)
       ↓
  AudioPipeline (pipeline/audio_pipeline.py)
       ↓
   ┌──────┴──────┐
   ↓             ↓
Deepgram STT   (records audio)
   ↓
Bedrock LLM (processes intent)
   ↓
Deepgram TTS (synthesizes response)
   ↓
Back to Browser
```

---

Happy building! 🚀

For questions or issues, check the main README.md or server logs.
