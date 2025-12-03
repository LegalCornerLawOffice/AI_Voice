#!/bin/bash

# AI Voice Intake System - Quick Start Script

echo "🚀 AI Voice Intake System - Quick Start"
echo "========================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env"
echo "   $ cp .env.example .env"
echo ""
echo "2. Edit .env with your API keys:"
echo "   - DEEPGRAM_API_KEY"
echo "   - AWS credentials for Bedrock"
echo ""
echo "3. Start Redis (if not using cloud):"
echo "   $ redis-server"
echo ""
echo "4. Run the server:"
echo "   $ python main.py"
echo ""
echo "5. Open browser to http://localhost:8000"
echo ""
echo "Happy building! 🎉"
