#!/usr/bin/env python3
"""
Session Archive Tool — LLM-driven topic grouping.

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
        "将会话话题归档到 ~/.hermes/archive/ 持久化存储。"
        "分析会话内容，按话题分组后使用此工具。\n\n"
        "操作:\n"
        "  archive([topicData, ...]) — 写入话题组。\n"
        "  topicData = {merge_into?: gid, title, description, summary, source_message_indices?: [int], message_ids?: [int], project?: string}\n"
        "    新建话题：传 title/description/summary + source_message_indices（当前会话）或 message_ids（历史会话）\n"
        "    合并已有话题：加 merge_into=<gid>，新的 title/description/summary 会覆盖原值\n"
        "  ls        — 列出所有已归档话题（gid + 描述）\n"
        "  show      — 查看话题详情（title/description/summary），按 gid 或 title\n"
        "  delete    — 删除话题，按 gid 或 title\n"
        "  load_session — 读取历史会话全量消息（按 session_id，支持跨 profile）。\n"
        "               一次调用获取全部消息，替代多次 session_search scroll。\n\n"
        "最佳实践:\n"
        "  \u2022 归档前：archive(show, gid=[gid1, gid2, ...]) 一次拉所有待合并话题的当前摘要\n"
        "  \u2022 归档时：archive([topicData, ...]) 一次写入所有新老话题\n"
        "  \u2022 同一话题经过 30+ 轮问答且已有结论时，主动归档。\n"
        "    用户明确说 archive 时也要响应。\n"
        "  \u2022 当会话覆盖 3+ 个不同技术话题（各 \u22655 轮且有结论），主动归档。\n"
        "  \u2022 合并时产生合并新旧内容的学术风格摘要。\n"
        "  \u2022 关于配置/扩展/排障 Hermes Agent 本身的话题设 project=\"hermes-agent\"，\n"
        "    其他话题留空 project。\n"
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
                                "Academic-style summary (目标+关键步骤+结论, "
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
                                "\"hermes-agent\" if the topic is about "
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

def _indices_to_message_ids(session_id: str, indices: list[int]) -> list[int]:
    """Map 0-based messages[] array indices to state.db message IDs.

    messages[0] = system prompt (NOT in state.db).
    messages[1] = first stored message → first row (ORDER BY id).
    So: state_db_position = index - 1.
    """
    if not STATE_DB.exists():
        return []
    conn = sqlite3.connect(str(STATE_DB))
    try:
        rows = conn.execute(
            "SELECT id FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
        ids = [row[0] for row in rows]
        resolved = []
        for idx in indices:
            pos = idx - 1  # skip system prompt
            if 0 <= pos < len(ids):
                resolved.append(ids[pos])
        return resolved
    finally:
        conn.close()


# ── Load session (internal — no session_search needed) ──────────────────────

def _load_session(session_id: str, profile: str | None = None) -> str:
    """Load all messages from a session, optionally from another profile's DB.

    Returns the same structure as session_search(dump_all=True) but without
    touching any Hermes internal code — reads state.db directly via SQLite.
    """
    db_path = STATE_DB
    if profile and str(profile).strip():
        try:
            from hermes_cli import profiles as profiles_mod
            canon = profiles_mod.normalize_profile_name(profile)
            profiles_mod.validate_profile_name(canon)
            if not profiles_mod.profile_exists(canon):
                return json.dumps({
                    "success": False,
                    "error": f"profile '{profile}' does not exist",
                })
            db_path = profiles_mod.get_profile_dir(canon) / "state.db"
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    if not db_path.exists():
        return json.dumps({"success": False, "error": "session DB not found"})

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
        messages = [{"id": r[0], "role": r[1], "content": r[2]} for r in rows]

        # Also get session meta
        meta = conn.execute(
            "SELECT title, source, model, started_at FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        session_meta = {}
        if meta:
            session_meta = {
                "title": meta[0],
                "source": meta[1],
                "model": meta[2],
                "when": meta[3],
            }

        return json.dumps({
            "success": True,
            "messages": messages,
            "message_count": len(messages),
            "session_meta": session_meta,
            "truncated": False,
        }, ensure_ascii=False)
    finally:
        conn.close()


# ── Subcommand dispatch ──────────────────────────────────────────────────────

def _resolve_gids(args: list[str]) -> tuple[list[int] | None, str | None]:
    """Parse args for --title or gid list. Returns (gids, title_query)."""
    title_query = None
    if args and args[0] == "--title" and len(args) >= 2:
        title_query = args[1]
        return None, title_query

    gids = []
    for a in args:
        try:
            gids.append(int(a))
        except ValueError:
            return None, None
    return gids, None


def _run_archive_subcommand(action: str, args: dict) -> str:
    """Execute archive subcommand via archive.py."""
    script = ARCHIVE_DIR / "src/archive.py"
    if not script.exists():
        return json.dumps({
            "success": False,
            "error": f"Archive script not found at {script}",
        })

    cmd = [sys.executable, str(script)]

    # load_session is handled internally, not delegated to archive.py
    if action == "load_session":
        return _load_session(
            args.get("session_id", ""),
            args.get("profile"),
        )

    if action == "archive":
        groups_input = args.get("groups", [])
        session_id = args.get("session_id", "")

        converted_groups = []
        for g in groups_input:
            direct_ids = g.get("message_ids")
            if direct_ids is not None:
                message_ids = direct_ids
            else:
                indices = g.get("source_message_indices", [])
                message_ids = _indices_to_message_ids(session_id, indices)
            converted_groups.append({
                "title": g.get("title", ""),
                "description": g.get("description", ""),
                "summary": g.get("summary", ""),
                "message_ids": message_ids,
                "merge_into": g.get("merge_into"),
                "project": g.get("project"),
            })

        analysis = {
            "session_id": session_id,
            "groups": converted_groups,
        }
        try:
            result = subprocess.run(
                cmd,
                input=json.dumps(analysis, ensure_ascii=False),
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"success": False, "error": "archive.py timed out"})

        if result.returncode != 0:
            return json.dumps({
                "success": False,
                "error": result.stderr.strip() or f"archive.py exited {result.returncode}",
            })
        return result.stdout.strip()

    elif action == "ls":
        try:
            result = subprocess.run(
                cmd + ["ls"], capture_output=True, text=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"success": False, "error": "archive.py ls timed out"})
        return result.stdout.strip()

    elif action == "show":
        gid = args.get("gid")
        title_query = args.get("title")
        if gid is None and title_query is None:
            return json.dumps({
                "success": False,
                "error": "gid or title is required",
            })

        if title_query is not None:
            try:
                result = subprocess.run(
                    cmd + ["show", "--title", title_query],
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired:
                return json.dumps({
                    "success": False, "error": "archive.py show timed out",
                })
        else:
            gids = gid if isinstance(gid, list) else [gid]
            try:
                result = subprocess.run(
                    cmd + ["show"] + [str(g) for g in gids],
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired:
                return json.dumps({
                    "success": False, "error": "archive.py show timed out",
                })
        return result.stdout.strip()

    elif action == "delete":
        gid = args.get("gid")
        title_query = args.get("title")
        if gid is None and title_query is None:
            return json.dumps({
                "success": False,
                "error": "gid or title is required",
            })

        if title_query is not None:
            try:
                result = subprocess.run(
                    cmd + ["delete", "--title", title_query],
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired:
                return json.dumps({
                    "success": False, "error": "archive.py delete timed out",
                })
        else:
            gids = gid if isinstance(gid, list) else [gid]
            try:
                result = subprocess.run(
                    cmd + ["delete"] + [str(g) for g in gids],
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired:
                return json.dumps({
                    "success": False, "error": "archive.py delete timed out",
                })
        return result.stdout.strip()

    else:
        return json.dumps({"success": False, "error": f"Unknown action: {action}"})


# ── Handler ──────────────────────────────────────────────────────────────────

def archive(
    action: str = "archive",
    session_id: str = "",
    groups: list | None = None,
    gid: int | list[int] | None = None,
    title: str | None = None,
    profile: str | None = None,
    task_id: str | None = None,
) -> str:
    """Archive session topics. Called by the registry handler."""
    if not check_archive_requirements():
        return json.dumps({
            "success": False,
            "error": f"Archive system not found at {ARCHIVE_DIR}",
        })

    tool_args = {
        "session_id": session_id,
        "groups": groups or [],
        "gid": gid,
        "title": title,
        "profile": profile,
    }

    try:
        return _run_archive_subcommand(action, tool_args)
    except Exception as e:
        logger.exception("archive tool failed action=%s", action)
        return json.dumps({"success": False, "error": str(e)})


# ── Registry ──────────────────────────────────────────────────────────────────

from tools.registry import registry

registry.register(
    name="archive",
    toolset="session_search",
    schema=ARCHIVE_SCHEMA,
    handler=lambda args, **kw: archive(
        action=args.get("action", "archive"),
        session_id=args.get("session_id", ""),
        groups=args.get("groups"),
        gid=args.get("gid"),
        title=args.get("title"),
        profile=args.get("profile"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_archive_requirements,
    description="Persist session topics with array-index message references",
    emoji="🗄️",
)
