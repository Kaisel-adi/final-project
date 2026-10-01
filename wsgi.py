import os
import time
import threading
import logging
import requests
from app import create_app
from app.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _ping_loop(target_url: str, interval_seconds: int = 600, initial_delay_seconds: int = 30):
    """
    Background worker loop that sends lightweight HTTP GET requests
    to prevent cloud platform free tiers (e.g., Render) from spinning down.
    """
    logger.info(f"KeepAlive: registered for {target_url}. Waiting {initial_delay_seconds}s for server startup...")
    time.sleep(initial_delay_seconds)

    # Use /health endpoint if available, otherwise root
    ping_url = target_url if target_url.endswith("/health") else f"{target_url.rstrip('/')}/health"
    logger.info(f"KeepAlive: actively pinging {ping_url} every {interval_seconds}s...")

    while True:
        try:
            res = requests.get(ping_url, timeout=15)
            logger.info(f"KeepAlive: ping sent to {ping_url} [HTTP {res.status_code}] ✓")
        except Exception as e:
            logger.warning(f"KeepAlive: ping to {ping_url} encountered an error: {e}")

        time.sleep(interval_seconds)


def start_keep_alive():
    """
    Spawns the keep-alive ping loop in a background daemon thread.
    Automatically detects RENDER_EXTERNAL_URL or KEEP_ALIVE_URL.
    """
    # Skip during testing or if explicitly disabled
    if os.environ.get("TESTING") == "True" or os.environ.get("DISABLE_KEEP_ALIVE") == "true":
        logger.info("KeepAlive: disabled in test mode")
        return None

    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("KEEP_ALIVE_URL")
    if not url:
        logger.info("KeepAlive: no RENDER_EXTERNAL_URL or KEEP_ALIVE_URL found, skipping background ping.")
        return None

    try:
        # Default to 10 minutes (600s), well within Render's 15-minute idle spin-down window
        interval = int(os.environ.get("KEEP_ALIVE_INTERVAL", "600"))
    except ValueError:
        interval = 600

    thread = threading.Thread(
        target=_ping_loop,
        args=(url, interval),
        daemon=True,
        name="render_keep_alive_worker"
    )
    thread.start()
    logger.info(f"KeepAlive: background daemon thread started (interval={interval}s, target={url}).")
    return thread


app = create_app(Config)

# Start keep-alive daemon thread when loaded by Gunicorn in production
start_keep_alive()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
