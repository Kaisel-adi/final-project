import os
from app import create_app
from app.config import Config
import time
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")

    # If the URL isn't set, just skip no crash, no fuss
    if not url:
        logger.info("KeepAlive: no URL found, skipping")
        return

    logger.info(f"KeepAlive: pinging {url} every 12 minutes...")

    while True:
        try:
            requests.get(url, timeout=10)
            logger.info("KeepAlive: ping sent ✓")
        except Exception as e:
            logger.error(f"KeepAlive: something went wrong — {e}")

        time.sleep(720)  # sleep for 12 minutes, then repeat


app = create_app(Config)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    keep_alive()  # Start the keep-alive function in the main thread
    app.run(host="0.0.0.0", port=port, debug=True)
