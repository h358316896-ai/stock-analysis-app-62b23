# StockAI Backend — Railway Procfile
# The Flask backend serving /api/* endpoints.
# When deploying to Railway, point to your Flask app entrypoint.

# Main backend (Flask app serving /api/* routes)
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120

# Optional: Backtest API as a separate service
# backtest: python backtest_api.py --port $PORT
