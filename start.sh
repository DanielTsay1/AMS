#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Run the Flask application
echo "Starting AMS application on http://localhost:5001"
echo "Press Ctrl+C to stop the server"
python app.py 