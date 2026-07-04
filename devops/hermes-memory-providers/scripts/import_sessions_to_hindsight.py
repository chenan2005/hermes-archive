#!/usr/bin/env python3
"""Import historical Hermes sessions into Hindsight memory bank.

Reads from Hermes state.db (SQLite), constructs conversation texts for each
session, and imports via hindsight_client.retain_batch().

Usage:
    python3 ~/.hermes/skills/devops/hermes-memory-providers/scripts/import_sessions_to_hindsight.py

Edit the SESSION_FILTER at the bottom to change which sessions to import.
"""

import sqlite3
import os
import time
from datetime import datetime, timezone

# ─── Config ───────────────────────────────────────────────────────────────
STATE_DB = os.path.expanduser("~/.hermes/state.db")
HINDSIGHT_URL = os.environ.get("HINDSIGHT_URL", "http://localhost:8888")
BANK_ID = os.environ.get("HINDSIGHT_BANK", "main")

# ─── Helper: Format conversation ──────────────────────────────────────────

def format_conversation(messages):
    """Format messages into a readable conversation text."""
    lines = []
    for role, content, tool_call_id, tool_name, ts in messages:
        if role == "user":
            if content and content.strip():
                lines.append(f"**User**: {content.strip()}")
        elif role == "assistant":
            if content and content.strip():
                lines.append(f"**Assistant**: {content.strip()}")
            elif tool_call_id:
                lines.append(f"**Assistant** [tool call: {tool_name}]")
        elif role == "tool":
            if content and content.strip():
                text = content.strip()
                if len(text) > 500:
                    text = text[:500] + f"\n... [truncated, total {len(content)} chars]"
                lines.append(f"**Tool** ({tool_name or tool_call_id}): {text}")
        elif role == "system":
            if content and content.strip():
                lines.append(f"*System: {content.strip()[:200]}*")
    return "\n\n".join(lines)


# ─── Main import logic ────────────────────────────────────────────────────

def import_sessions(session_filter=lambda r: True):
    """Import sessions matching `session_filter` into Hindsight.

    Args:
        session_filter: A function that receives a sqlite3.Row (with keys:
            id, title, message_count, input_tokens, output_tokens, started_cst)
            and returns True if the session should be imported.
    """
    if not os.path.exists(STATE_DB):
        print(f"ERROR: state.db not found at {STATE_DB}")
        return

    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get sessions
    cursor.execute("""
        SELECT id, title, message_count, input_tokens, output_tokens,
               datetime(started_at, 'unixepoch', '+8 hours') as started_cst
        FROM sessions
        WHERE message_count > 0
        ORDER BY started_at
    """)
    all_sessions = cursor.fetchall()

    # Filter
    sessions = [r for r in all_sessions if session_filter(r)]
    print(f"Found {len(sessions)} sessions to import (of {len(all_sessions)} total)")

    from hindsight_client import Hindsight
    client = Hindsight(base_url=HINDSIGHT_URL)

    imported = 0
    failed = 0

    for session_row in sessions:
        sid = session_row["id"]
        title = session_row.get("title") or "(no title)"
        started = session_row.get("started_cst") or ""

        # Fetch messages
        cursor.execute("""
            SELECT role, content, tool_call_id, tool_name, timestamp
            FROM messages
            WHERE session_id = ? AND active = 1
            ORDER BY id
        """, (sid,))
        messages = cursor.fetchall()

        if not messages:
            print(f"  ⏭  [{sid}] {title} — no messages, skipping")
            continue

        # Format conversation
        conversation = format_conversation(messages)
        if not conversation.strip():
            print(f"  ⏭  [{sid}] {title} — empty after formatting, skipping")
            continue

        # Build context label
        inp_tok = session_row.get("input_tokens") or 0
        out_tok = session_row.get("output_tokens") or 0
        total_tok = inp_tok + out_tok
        context = (f"Hermes conversation: {title}"
                   f" | {len(messages)} messages, {total_tok:,} tokens"
                   f" | Session: {sid}")

        tags = ["historical", "batch-import"]

        try:
            result = client.retain_batch(
                bank_id=BANK_ID,
                items=[{
                    "content": conversation,
                    "context": context,
                    "metadata": {
                        "source": "batch-import",
                        "session_id": sid,
                        "title": title,
                        "started_cst": str(started),
                        "message_count": str(len(messages)),
                    },
                    "tags": tags,
                }],
                retain_async=True,
            )
            imported += 1
            print(f"  ✅  [{sid}] {title} ({len(messages)} msgs) — {result}")
        except Exception as e:
            failed += 1
            print(f"  ❌  [{sid}] {title} — {e}")

        time.sleep(0.5)

    conn.close()

    print(f"\nDone! Imported: {imported}, Failed: {failed}")
    print("NOTE: Extraction is async — imported content won't be immediately")
    print("searchable. Hindsight runs Iris Extract in the background.")


# ─── CLI entrypoint ───────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── EDIT THIS FILTER to change which sessions to import ──
    # Examples:
    #   Import all sessions from a specific date:
    #     lambda r: r["id"].startswith("20260621")
    #
    #   Import all sessions except current:
    #     lambda r: r["id"] != "20260622_085011_38b0c13e"
    #
    #   Import everything:
    #     lambda r: True
    # ──────────────────────────────────────────────────────────

    SESSION_FILTER = lambda r: r["id"].startswith("20260621") or r["id"] == "20260622_002108_ad6f95"

    print(f"Target bank: {BANK_ID}")
    print(f"Hindsight API: {HINDSIGHT_URL}")
    print("=" * 60)
    import_sessions(SESSION_FILTER)
