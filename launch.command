#!/bin/bash
# Double-click this file to launch the All-in-One Business App locally.
# It will open your browser automatically.

cd "$(dirname "$0")"

echo ""
echo "============================================"
echo "  Launching All-in-One Business App..."
echo "============================================"
echo ""

# Use virtual environment if it exists, otherwise fall back to system Python
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "  Using virtual environment."
else
    echo "  Using system Python (no .venv found)."
fi

# Install/verify dependencies
echo "  Checking dependencies..."
python3 -m pip install -r requirements.txt -q 2>/dev/null

# Copy .env if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from example. Add your API keys inside."
fi

echo ""
echo "  Starting server on http://localhost:8000"
echo "  Press Ctrl+C to stop."
echo ""

# Kill any existing process on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Open browser after short delay
(sleep 3 && open http://localhost:8000) &

# Run the app
python3 app.py
