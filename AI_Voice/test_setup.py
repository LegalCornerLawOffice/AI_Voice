"""
Simple test to verify core components are working.
Run with: python test_setup.py
"""

import asyncio
import sys


async def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing imports...")
    
    try:
        from config import settings
        print("✅ Config loaded")
        
        from handlers.base import AudioHandler
        from handlers.webrtc import WebRTCAudioHandler
        print("✅ Handlers OK")
        
        from services.deepgram_stt import DeepgramSTTService
        from services.deepgram_tts import DeepgramTTSService
        from services.bedrock_llm import BedrockLLMService
        from services.state_manager_inmemory import InMemoryStateManager
        print("✅ Services OK")
        
        from conversation.flow import ConversationFlow
        from conversation.prompts import SYSTEM_PROMPT
        print("✅ Conversation OK")
        
        from pipeline.audio_pipeline import AudioPipeline
        print("✅ Pipeline OK")
        
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


async def test_config():
    """Test configuration."""
    print("\n🧪 Testing configuration...")
    
    try:
        from config import settings
        
        # Check required settings
        required = [
            'deepgram_api_key',
            'aws_region',
            'aws_bedrock_model_id',
        ]
        
        missing = []
        for key in required:
            value = getattr(settings, key, None)
            if not value or value == f'your_{key}_here':
                missing.append(key)
        
        if missing:
            print(f"⚠️  Missing configuration: {', '.join(missing)}")
            print("   Please update your .env file")
            return False
        
        print(f"✅ Environment: {settings.environment}")
        print(f"✅ AWS Region: {settings.aws_region}")
        print(f"✅ Bedrock Model: {settings.aws_bedrock_model_id}")
        print(f"✅ Database URL: {settings.database_url}")
        
        return True
    except Exception as e:
        print(f"❌ Config error: {e}")
        return False


async def test_deepgram():
    """Test Deepgram API key."""
    print("\n🧪 Testing Deepgram connection...")
    
    try:
        from services.deepgram_tts import DeepgramTTSService
        
        tts = DeepgramTTSService()
        
        # Try to synthesize a short test phrase
        audio = await tts.synthesize("Test")
        
        if audio:
            print(f"✅ Deepgram TTS OK ({len(audio)} bytes)")
            await tts.close()
            return True
        else:
            print("❌ Deepgram TTS returned empty audio")
            return False
            
    except Exception as e:
        print(f"❌ Deepgram error: {e}")
        print("   Check your DEEPGRAM_API_KEY in .env")
        return False


async def test_bedrock():
    """Test AWS Bedrock connection."""
    print("\n🧪 Testing AWS Bedrock connection...")
    
    try:
        from services.bedrock_llm import BedrockLLMService
        
        llm = BedrockLLMService()
        
        # Try a simple generation
        response = await llm.generate(
            messages=[{"role": "user", "content": "Say 'test successful'"}],
            max_tokens=50
        )
        
        if response and response.get('content'):
            print(f"✅ Bedrock LLM OK")
            print(f"   Response: {response['content'][:100]}...")
            return True
        else:
            print("❌ Bedrock returned empty response")
            return False
            
    except Exception as e:
        print(f"❌ Bedrock error: {e}")
        print("   Check your AWS credentials and Bedrock access in .env")
        print("   Make sure you've requested access to Claude in the Bedrock console")
        return False


async def test_state_manager():
    """Test in-memory state manager."""
    print("\n🧪 Testing state manager...")
    
    try:
        from services.state_manager_inmemory import InMemoryStateManager
        
        manager = InMemoryStateManager()
        await manager.initialize()
        
        # Try to set and get a value
        test_session = "test-session-123"
        await manager.initialize_session(test_session, {"test": True})
        
        state = await manager.get_state(test_session)
        
        if state and state.get('session_id') == test_session:
            print("✅ State manager OK (in-memory)")
            await manager.close()
            return True
        else:
            print("❌ State not saved correctly")
            return False
            
    except Exception as e:
        print(f"❌ State manager error: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("AI Voice Intake System - Setup Verification")
    print("=" * 60)
    
    results = {
        'imports': await test_imports(),
        'config': await test_config(),
    }
    
    # Only test APIs if config is OK
    if results['config']:
        results['deepgram'] = await test_deepgram()
        results['bedrock'] = await test_bedrock()
        results['state_manager'] = await test_state_manager()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {name.title()}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 All tests passed! You're ready to start the server.")
        print("\nNext steps:")
        print("1. Run: python main.py")
        print("2. Open: http://localhost:8000")
        print("3. Click 'Start Call' and test the system")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("- Copy .env.example to .env and add your API keys")
        print("- Start Redis: redis-server")
        print("- Request Bedrock access in AWS Console")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
