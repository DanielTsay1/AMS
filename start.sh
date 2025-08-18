#!/bin/bash

echo "🚀 Starting PDF Search & Storage System..."
echo "=================================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Check if uploads directory exists
if [ ! -d "uploads" ]; then
    echo "📁 Creating uploads directory..."
    mkdir -p uploads
fi

echo "=================================================="
echo "✅ Setup complete! Starting the application..."
echo "🌐 The app will be available at: http://localhost:5000"
echo "📱 Open your browser and navigate to the URL above"
echo "🛑 Press Ctrl+C to stop the server"
echo "=================================================="

# Start the Flask application
python app.py
