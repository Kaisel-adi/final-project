"""
Standalone Digest Runner for GCIR.
Can be executed directly from cron, Windows Task Scheduler, or CLI to dispatch periodic civic issue digests.

Usage:
    python scripts/run_digest.py
    python scripts/run_digest.py --hours 48
"""

import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app
from app.jobs.digest import dispatch_digest


def main():
    parser = argparse.ArgumentParser(description="Run periodic GCIR neighborhood civic issue digest.")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours for unverified issues (default: 24)")
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("Running GCIR Civic Verification Digest Job")
        print(f"Lookback window: {args.hours} hours")
        print("=" * 60)

        result = dispatch_digest(lookback_hours=args.hours)

        print(f"Status:               {result.get('status')}")
        print(f"Candidates Evaluated: {result.get('candidates_evaluated', 0)}")
        print(f"Users Notified:       {result.get('users_notified', 0)}")
        print(f"Emails Dispatched:    {result.get('emails_dispatched', 0)}")
        if "message" in result:
            print(f"Note:                 {result.get('message')}")
        print("=" * 60)


if __name__ == "__main__":
    main()
