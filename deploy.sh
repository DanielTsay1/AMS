#!/bin/bash

echo "🚀 PDF Search & Storage Deployment Script"
echo "=========================================="

# Check if Docker is installed
if command -v docker &> /dev/null; then
    echo "✅ Docker found"
else
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose found"
else
    echo "❌ Docker Compose not found. Please install Docker Compose first."
    exit 1
fi

echo ""
echo "Choose deployment option:"
echo "1) Local Docker (localhost:5000)"
echo "2) Build Docker image for cloud deployment"
echo "3) Deploy to Heroku (requires Heroku CLI)"
echo "4) Deploy to Railway (requires Railway CLI)"
echo "5) Deploy to Render (requires Render account)"

read -p "Enter your choice (1-5): " choice

case $choice in
    1)
        echo "🐳 Starting local Docker deployment..."
        docker-compose up --build -d
        echo "✅ Application running at http://localhost:5000"
        echo "📱 Share this link with users: http://localhost:5000"
        ;;
    2)
        echo "🏗️ Building Docker image..."
        docker build -t pdf-search-app .
        echo "✅ Docker image built successfully!"
        echo "📦 Image name: pdf-search-app"
        echo "🚀 Deploy to any cloud platform that supports Docker"
        ;;
    3)
        echo "☁️ Deploying to Heroku..."
        if command -v heroku &> /dev/null; then
            heroku create pdf-search-app-$(date +%s)
            git add .
            git commit -m "Deploy to Heroku"
            git push heroku main
            echo "✅ Deployed to Heroku!"
            echo "🔗 Your app URL: $(heroku info -s | grep web_url | cut -d= -f2)"
        else
            echo "❌ Heroku CLI not found. Please install it first:"
            echo "   https://devcenter.heroku.com/articles/heroku-cli"
        fi
        ;;
    4)
        echo "🚂 Deploying to Railway..."
        if command -v railway &> /dev/null; then
            railway login
            railway init
            railway up
            echo "✅ Deployed to Railway!"
        else
            echo "❌ Railway CLI not found. Please install it first:"
            echo "   npm install -g @railway/cli"
        fi
        ;;
    5)
        echo "🎨 Deploying to Render..."
        echo "📝 Please follow these steps:"
        echo "   1. Go to https://render.com"
        echo "   2. Connect your GitHub repository"
        echo "   3. Create a new Web Service"
        echo "   4. Select your repository"
        echo "   5. Build Command: pip install -r requirements.txt"
        echo "   6. Start Command: gunicorn app:app"
        echo "   7. Deploy!"
        ;;
    *)
        echo "❌ Invalid choice. Please run the script again."
        exit 1
        ;;
esac

echo ""
echo "🎉 Deployment complete!"
echo "📚 Users can now access your PDF Search & Storage system via the provided URL"
