"""
Usage:
    python main.py --client "Riley Earthmoving"
    python main.py --client "Riley Earthmoving" --max-sessions 2
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from src.confluence_client import ConfluenceClient
from src.gong_client import GongClient
from src.snapshot_generator import SnapshotGenerator
from src.confluence_formatter import format_snapshot


def run(client_name: str, max_sessions: int | None = None) -> str:
    print(f"\nStarting snapshot generation for: {client_name}")

    confluence = ConfluenceClient()
    gong = GongClient()
    generator = SnapshotGenerator()

    print("\n[1/5] Reading Confluence page…")
    page = confluence.get_client_page(client_name)
    print(f"      Found page: {page['title']}")

    sessions = confluence.parse_gong_sessions(page)
    if not sessions:
        print("ERROR: No sessions found in the Confluence table.")
        sys.exit(1)

    if max_sessions:
        sessions = sessions[:max_sessions]

    print(f"      Processing {len(sessions)} session(s):")
    for s in sessions:
        print(f"        • {s['session_name']} ({s['date']})")

    print("\n[2/5] Fetching Gong transcripts…")
    for session in sessions:
        print(f"      → {session['session_name']} ({session['date']})")
        try:
            session["transcript"] = gong.get_transcript_for_session(
                session["gong_url"], session["date"], client_name, session["session_name"]
            )
            print(f"        ✓ {len(session['transcript'].split()):,} words")
        except Exception as exc:
            print(f"        ⚠  Could not fetch transcript: {exc}")
            session["transcript"] = f"[Transcript unavailable: {exc}]"

    print("\n[3/5] Generating snapshot with Claude AI…")
    snapshot = generator.generate(sessions, client_name=client_name, sleep_between=65)

    print("\n[4/5] Formatting for Confluence…")
    onboarding_start = sessions[0]["date"] if sessions else ""
    storage_content = format_snapshot(snapshot, client_name, onboarding_start)

    title = f"{client_name} [Snapshot]"
    print(f"\n[5/5] Creating Confluence page: '{title}'…")
    result = confluence.create_snapshot_page(title, storage_content)

    page_url = f"{os.environ['CONFLUENCE_BASE_URL']}/pages/{result['id']}"
    print(f"\nDone! Snapshot created: {page_url}\n")
    return page_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Auto-generate an onboarding snapshot from Gong recordings + Confluence."
    )
    parser.add_argument("--client", required=True, help='Client name as it appears in Confluence')
    parser.add_argument("--max-sessions", type=int, default=None, help="Limit number of sessions to process")
    args = parser.parse_args()
    run(args.client, max_sessions=args.max_sessions)
