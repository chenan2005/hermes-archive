#!/usr/bin/env python3
"""
Hermes Session Archive Tool — v4

Data model (LLM-driven topic grouping, no keyword matching):

  meta.json:
    gid (int)          — unique numeric ID (auto-increment)
    title (str ≤20)    — readable identifier
    description (str ≤120) — one-liner, injected into system prompt
    summary (str ≤3000) — condensed summary; raw messages if total <3K chars
    project (str|null) — optional namespace

  sources/{session_id}.json:
    {"session_id": "...", "message_ids": [1234, 1238, ...]}

  index.json:
    {"version": 4, "next_gid": N, "groups": [{gid, title, description, ...}]}

Usage:
  echo '<analysis_json>' | python3 src/archive.py         # archive (stdin)
  python3 src/archive.py ls [project <name>]              # list groups
  python3 src/archive.py show <gid> [<gid> ...]          # group detail by gid
  python3 src/archive.py show --title <query>            # group detail by title (fuzzy)
  python3 src/archive.py delete <gid>                    # delete group
  python3 src/archive.py delete --title <query>          # delete by title match
"""

import fcntl
import json
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ARCHIVE_DIR = Path(os.path.expanduser("~/.hermes/archive"))
DATA_DIR = ARCHIVE_DIR / "data"
INDEX_PATH = DATA_DIR / "index.json"
GROUPS_DIR = DATA_DIR / "groups"

SUMMARY_MAX_CHARS = 3000
TITLE_MAX_CHARS = 20
DESC_MAX_CHARS = 120


# ─── Init ────────────────────────────────────────────────────────────────────

def init():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    GROUPS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": 4, "next_gid": 1, "groups": []},
                      f, ensure_ascii=False, indent=2)


@contextmanager
def _locked_index():
    """Acquire exclusive lock on index.json, yield parsed dict, auto-save on exit."""
    init()
    with open(INDEX_PATH, "r+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            index = json.load(f)
            yield index
            f.seek(0)
            f.truncate()
            json.dump(index, f, ensure_ascii=False, indent=2)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def load_index():
    if not INDEX_PATH.exists():
        init()
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def next_gid():
    with _locked_index() as index:
        gid = index.get("next_gid", 1)
        index["next_gid"] = gid + 1
    return gid


def sanitize_name(name):
    if not name:
        return "unnamed"
    clean = "".join(c if c.isalnum() else "-" for c in name.lower())
    return "-".join(p for p in clean.split("-") if p)[:50].rstrip("-")


# ─── Write group ─────────────────────────────────────────────────────────────

def write_group(title, description, summary, message_ids, session_id,
                project=None, msg_count=0):
    """Write a new group: meta.json + sources/{session}.json. Returns gid."""

    gid = next_gid()
    group_dir = _group_dir(gid, project, create=True)
    now = datetime.now().isoformat()

    sources_dir = group_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    source_path = sources_dir / f"{session_id}.json"
    with open(source_path, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "message_ids": message_ids},
                  f, ensure_ascii=False, indent=2)

    meta = {
        "gid": gid,
        "title": title[:TITLE_MAX_CHARS],
        "description": description[:DESC_MAX_CHARS],
        "summary": summary[:SUMMARY_MAX_CHARS],
        "project": project,
        "created_at": now,
        "updated_at": now,
        "source_sessions": [session_id],
        "versions": [{"session": session_id, "merged_at": now}],
    }
    meta_path = group_dir / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    with _locked_index() as index:
        index["groups"].append({
            "gid": gid,
            "title": title[:TITLE_MAX_CHARS],
            "description": description[:DESC_MAX_CHARS],
            "project": project,
            "created_at": now,
            "updated_at": now,
            "source_sessions": [session_id],
            "message_count": len(message_ids),
        })
        _record_session_archive(index, session_id, msg_count, now)

    return gid


def merge_into_group(gid, title, description, summary, message_ids,
                     session_id, project=None, msg_count=0):
    """Merge new content into an existing group. Overwrites title/description/
    summary with the caller-provided values. Returns gid."""

    group_dir = _group_dir(gid, project, create=True)
    now = datetime.now().isoformat()

    # Check if this session was already archived to this topic
    sources_dir = group_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    source_path = sources_dir / f"{session_id}.json"
    old_count = 0
    session_exists = source_path.exists()
    if session_exists:
        with open(source_path, "r", encoding="utf-8") as f:
            old_src = json.load(f)
        old_count = len(old_src.get("message_ids", []))

    # Overwrite source file
    with open(source_path, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "message_ids": message_ids},
                  f, ensure_ascii=False, indent=2)

    meta_path = group_dir / "meta.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    meta["summary"] = summary[:SUMMARY_MAX_CHARS]
    if title:
        meta["title"] = title[:TITLE_MAX_CHARS]
    if description:
        meta["description"] = description[:DESC_MAX_CHARS]
    meta["updated_at"] = now
    if not session_exists:
        if session_id not in meta.get("source_sessions", []):
            meta.setdefault("source_sessions", []).append(session_id)
        meta.setdefault("versions", []).append({
            "session": session_id, "merged_at": now,
        })

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    with _locked_index() as index:
        for g in index["groups"]:
            if g.get("gid") == gid:
                if title:
                    g["title"] = title[:TITLE_MAX_CHARS]
                if description:
                    g["description"] = description[:DESC_MAX_CHARS]
                g["updated_at"] = now
                g["message_count"] = g.get("message_count", 0) - old_count + len(message_ids)
                if not session_exists:
                    if session_id not in g.get("source_sessions", []):
                        g.setdefault("source_sessions", []).append(session_id)
                break
        _record_session_archive(index, session_id, msg_count, now)

    return gid


def _record_session_archive(index, session_id, msg_count, timestamp):
    """Record session archive metadata in index.json."""
    if "session_archive_records" not in index:
        index["session_archive_records"] = []
    index["session_archive_records"] = [
        r for r in index["session_archive_records"]
        if r.get("session_id") != session_id
    ]
    index["session_archive_records"].append({
        "session_id": session_id,
        "msg_count": msg_count,
        "time": timestamp,
    })


def _delete_group(gid):
    """Remove group from index and disk. Returns True if deleted."""
    with _locked_index() as index:
        group = None
        for g in index.get("groups", []):
            if g.get("gid") == gid:
                group = g
                break
        if not group:
            return False

        group_dir = _group_dir(gid, group.get("project"))
        if group_dir.exists():
            shutil.rmtree(str(group_dir))

        index["groups"] = [g for g in index["groups"] if g.get("gid") != gid]

    return True


def _group_dir(gid, project=None, create=False):
    """Resolve a group directory by gid.

    If project is explicitly provided, use it directly (no index lookup).
    Otherwise look up the project from index.json.
    """
    if project is None:
        index = load_index()
        for g in index.get("groups", []):
            if g.get("gid") == gid:
                project = g.get("project")
                break

    if project:
        d = GROUPS_DIR / "projects" / sanitize_name(project) / str(gid)
    else:
        d = GROUPS_DIR / "general" / str(gid)

    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


# ─── Main (stdin) ────────────────────────────────────────────────────────────

def main():
    init()

    try:
        analysis = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    session_id = analysis.get("session_id", "")
    groups_input = analysis.get("groups", [])
    msg_count = analysis.get("msg_count", 0)

    if not session_id or not groups_input:
        print(json.dumps({"success": False, "error": "Missing session_id or groups"}))
        sys.exit(1)

    results = []

    for g in groups_input:
        title = (g.get("title") or "Untitled")[:TITLE_MAX_CHARS]
        description = (g.get("description") or "")[:DESC_MAX_CHARS]
        summary = (g.get("summary") or "")[:SUMMARY_MAX_CHARS]
        message_ids = g.get("message_ids", [])
        merge_into = g.get("merge_into")
        project = g.get("project") or None

        if not message_ids:
            results.append({
                "group": title,
                "action": "skipped",
                "reason": "no message_ids provided",
            })
            continue

        if merge_into is not None:
            try:
                merge_into_group(
                    merge_into, title, description, summary,
                    message_ids, session_id, project, msg_count=msg_count)
                results.append({
                    "group": title,
                    "gid": merge_into,
                    "action": "merged",
                    "merged_into": merge_into,
                })
            except Exception as e:
                results.append({
                    "group": title,
                    "action": "error",
                    "error": f"merge failed: {e}",
                })
        else:
            try:
                gid = write_group(title, description, summary,
                                  message_ids, session_id, project,
                                  msg_count=msg_count)
                results.append({
                    "group": title,
                    "gid": gid,
                    "action": "archived",
                })
            except Exception as e:
                results.append({
                    "group": title,
                    "action": "error",
                    "error": f"write failed: {e}",
                })

    print(json.dumps({
        "success": True,
        "session_id": session_id,
        "results": results,
    }, ensure_ascii=False, indent=2))


# ─── CLI subcommands ─────────────────────────────────────────────────────────

def _resolve_gids(args):
    """Parse args as either '--title <query>' or '<gid> [<gid> ...]'.
    Returns (gids: list[int], title_query: str|None)."""
    if not args:
        return None, None
    if args[0] == "--title":
        if len(args) < 2:
            return None, None  # caller handles error
        return _find_by_title(args[1]), args[1]
    gids = []
    for a in args:
        try:
            gids.append(int(a))
        except ValueError:
            return None, None
    return gids, None


def cmd_ls(args):
    index = load_index()
    groups = index.get("groups", [])

    project_filter = None
    if args and args[0:1] == ["project"]:
        project_filter = args[1] if len(args) > 1 else None

    result = []
    for g in groups:
        if project_filter and g.get("project") != project_filter:
            continue
        result.append({
            "gid": g.get("gid"),
            "title": g.get("title"),
            "description": g.get("description", ""),
            "project": g.get("project"),
            "message_count": g.get("message_count", 0),
            "created_at": g.get("created_at", ""),
            "updated_at": g.get("updated_at", ""),
        })

    print(json.dumps({"success": True, "groups": result}, ensure_ascii=False, indent=2))


def _find_by_title(query: str, index: dict | None = None) -> list[int]:
    """Fuzzy title match: case-insensitive substring. Returns matching gids."""
    if index is None:
        index = load_index()
    query_lower = query.lower()
    matches = []
    for g in index.get("groups", []):
        title = g.get("title", "")
        if query_lower in title.lower():
            matches.append(g.get("gid"))
    return matches


def cmd_show(args):
    """Show archive groups by gid or --title."""
    gids, title_query = _resolve_gids(args)
    if gids is None:
        if title_query is None:
            print(json.dumps({
                "success": False,
                "error": "Usage: archive show <gid> [<gid> ...] | --title <query>",
            }))
        else:
            print(json.dumps({"success": False, "error": "--title requires a query string"}))
        return

    if title_query and not gids:
        print(json.dumps({
            "success": True,
            "groups": [],
            "title_query": title_query,
            "message": "no matching topics found",
        }))
        return

    index = load_index()
    results = []

    for target_gid in gids:
        group = None
        for g in index.get("groups", []):
            if g.get("gid") == target_gid:
                group = g
                break

        if not group:
            results.append({"gid": target_gid, "error": "not found"})
            continue

        group_dir = _group_dir(target_gid, group.get("project"))
        meta_path = group_dir / "meta.json"
        meta = {}
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

        results.append({
            "gid": meta.get("gid", group.get("gid")),
            "title": meta.get("title", group.get("title")),
            "description": meta.get("description", ""),
            "summary": meta.get("summary", ""),
        })

    print(json.dumps({"success": True, "groups": results}, ensure_ascii=False, indent=2))


def cmd_delete(args):
    """Delete archive groups by gid or --title."""
    gids, title_query = _resolve_gids(args)
    if gids is None:
        if title_query is None:
            print(json.dumps({
                "success": False,
                "error": "Usage: archive delete <gid> [<gid> ...] | --title <query>",
            }))
        else:
            print(json.dumps({"success": False, "error": "--title requires a query string"}))
        return

    if not gids:
        print(json.dumps({
            "success": True,
            "deleted": [],
            "title_query": title_query,
            "message": "no matching topics found",
        }))
        return

    deleted = []
    errors = []
    for gid in gids:
        try:
            if _delete_group(gid):
                deleted.append(gid)
            else:
                errors.append({"gid": gid, "error": "not found"})
        except Exception as e:
            errors.append({"gid": gid, "error": str(e)})

    print(json.dumps({
        "success": True,
        "deleted": deleted,
        "errors": errors,
    }, ensure_ascii=False, indent=2))


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        main()
    else:
        cmd = sys.argv[1]
        sub_args = sys.argv[2:]
        if cmd == "ls":
            cmd_ls(sub_args)
        elif cmd == "show":
            cmd_show(sub_args)
        elif cmd == "delete":
            cmd_delete(sub_args)
        else:
            print(json.dumps({
                "success": False,
                "error": f"Unknown subcommand: {cmd}. Use: ls, show, delete",
            }))
