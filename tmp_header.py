#!/usr/bin/env python3
"""Session Archive Tool — LLM-driven topic grouping.

The LLM analyzes the conversation, groups messages by topic, and calls this
tool.  Message references use the 0-based array index from the messages array
the LLM sees (system prompt = index 0).  The handler maps indices to state.db
message IDs before delegating to archive.py.

All archive metadata lives in ~/.hermes/archive/ outside Hermes's own codebase.
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path(get_hermes_home()) / "archive"
DATA_DIR = ARCHIVE_DIR / "data"
ARCHIVE_INDEX = DATA_DIR / "index.json"
STATE_DB = Path(get_hermes_home()) / "state.db"

# ── Health check ──────────────────────────────────────────────────────────────


def check_archive_requirements() -> bool:
    """Check that the archive src and data directories exist."""
    return (ARCHIVE_DIR / "src/archive.py").exists() and DATA_DIR.exists()


# ── Schema ────────────────────────────────────────────────────────────────────

ARCHIVE_SCHEMA = {
    "name": "archive",
    "description": (
        'Archive conversation topics to persistent storage in ~/.hermes/archive/. '
        'Analyze the conversation, group messages by topic, and use this tool.\n\n'
        'ACTIONS:\n'
        '  archive([topicData, ...]) — Write topic groups.\n'
        '  topicData = {merge_into?: gid, title, description, summary,\n'
        '               source_message_indices?: [int], message_ids?: [int],\n'
        '               project?: string}\n'
        '    New topic: pass title/description/summary +\n'
        '               source_message_indices (current session) or\n'
        '               message_ids (past session via session_search)\n'
        '    Merge into existing: add merge_into=<gid>,\n'
        '               new title/description/summary overwrite old values\n'
        '  ls        — List all archived topics (gid + description)\n'
        '  show      — View topic meta (title/description/summary), by gid or title\n'
        '  delete    — Remove a topic, by gid or title\n'
        '  load_session — Load a full past session\'s messages (by session_id,\n'
        '               cross-profile supported). One call gets all messages —\n'
        '               replaces multiple session_search scrolls.\n\n'
        'BEST PRACTICE:\n'
        '  • Before archiving: archive(show, gid=[gid1, gid2, ...]) to fetch\n'
        '    existing topic summaries at once.\n'
        '  • When archiving: archive([topicData, ...]) to write all groups\n'
        '    (new and merge) in a single call.\n'
        '  • For merges, produce a consolidated academic-style summary.\n'
        '  • Set project="hermes-agent" for topics about configuring/extending/\n'
        '    troubleshooting Hermes Agent itself. Omit for general topics.\n'
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["archive", "ls", "show", "delete", "load_session"],
                "description": "Subcommand.",
            },
            "session_id": {
                "type": "string",
                "description": (
                    "Session ID (required for archive/load_session)."
                ),
            },
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Topic title (≤20 chars)",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "One-sentence topic description (≤120 chars). "
                                "Injected into system prompt for topic discovery."
                            ),
                        },
                        "summary": {
                            "type": "string",
                            "description": (
                                "Academic-style summary (goal + key steps + conclusion, "
                                "≤3000 chars). If all referenced messages total "
                                "<3K chars, store the raw messages."
                            ),
                        },
                        "source_message_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "0-based array indices in the messages array "
                                "you see. system prompt = index 0. "
                                "Include only user+assistant messages. "
                                "Mutually exclusive with 'message_ids'."
                            ),
                        },
                        "message_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "Direct state.db message IDs (not array indices). "
                                "Use for archiving a PAST session where you have "
                                "the actual message IDs from session_search. "
                                "Mutually exclusive with 'source_message_indices'."
                            ),
                        },
                        "merge_into": {
                            "type": "integer",
                            "description": (
                                "Existing topic gid to merge into. Set to "
                                "overwrite title/description/summary with your "
                                "consolidated rewrite. Omit or set null to "
                                "create a new topic."
                            ),
                        },
                        "project": {
                            "type": "string",
                            "description": (
                                "Optional project namespace. Set to "
                                '"hermes-agent" if the topic is about '
                                "configuring/extending/troubleshooting Hermes "
                                "Agent itself. Omit for general topics."
                            ),
                        },
                    },
                    "required": ["title", "description", "summary"],
                },
            },
            "gid": {
                "oneOf": [
                    {"type": "integer"},
                    {"type": "array", "items": {"type": "integer"}},
                ],
                "description": (
                    "Numeric group ID for show/delete actions. "
                    "Pass an array to target multiple topics in one call. "
                    "Mutually exclusive with 'title'."
                ),
            },
            "title": {
                "type": "string",
                "description": (
                    "Case-insensitive substring title match for show/delete. "
                    "Mutually exclusive with 'gid'."
                ),
            },
            "profile": {
                "type": "string",
                "description": (
                    "Optional profile name for cross-profile load_session."
                ),
            },
        },
        "required": ["action"],
    },
}


# ── Index → message_id conversion ────────────────────────────────────────────
