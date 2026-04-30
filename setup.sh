#!/bin/bash
# One-time setup script

echo "=== CoinSwitch Futures Bot Setup ==="

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Copy env template
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "Created .env — edit it with your API keys before running!"
fi

echo ""
echo "Setup complete. Next steps:"
echo "  1. Edit .env and add your CoinSwitch API keys"
echo "  2. Test in paper mode: python main.py --paper"
echo "  3. Run backtest:       python main.py --backtest"
echo "  4. Go live:            python main.py --live  (REAL MONEY)"
