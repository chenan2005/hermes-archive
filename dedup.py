"""
SimHash-based message deduplication for archive topics.

When archiving new messages into an existing topic, compare each message
against the topic summary using SimHash fingerprinting + Hamming distance.
Messages that are near-duplicates (recaps of already-archived content)
are filtered out — only incremental information is kept.

SimHash (character bigrams → MD5 → weighted bit vector → sign) provides
better paraphrase tolerance than Jaccard n-gram overlap.  A length filter
(≥100 chars) ensures short conversational messages aren't incorrectly
compared against the topic summary.

Usage (from execute_code):
    from dedup import dedup_messages

    kept_ids, skipped = dedup_messages(messages, topic_summary, threshold=22)
"""

import hashlib
from typing import Any

MIN_MESSAGE_LENGTH = 100  # only dedup messages with ≥100 chars of content


def simhash(text: str, bits: int = 64) -> int:
    """Compute SimHash fingerprint using character bigrams.

    Character bigrams are language-agnostic and work equally well for
    Chinese, English, and mixed text without tokenizer dependencies.
    """
    v = [0] * bits
    for i in range(len(text) - 1):
        token = text[i : i + 2]
        h = int(hashlib.md5(token.encode()).hexdigest()[:16], 16)
        for j in range(bits):
            if h & (1 << j):
                v[j] += 1
            else:
                v[j] -= 1
    fingerprint = 0
    for j in range(bits):
        if v[j] > 0:
            fingerprint |= 1 << j
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Hamming distance between two 64-bit SimHash fingerprints."""
    return (a ^ b).bit_count()


def dedup_messages(
    messages: list[dict[str, Any]],
    topic_summary: str,
    threshold: int = 20,
) -> tuple[list[int], int]:
    """Filter messages that are near-duplicates of the topic summary.

    Only messages with ≥100 chars of content are considered for dedup —
    short messages (greetings, one-line questions) pass through unchanged.

    Args:
        messages: List of message dicts with ``id`` and ``content`` keys.
        topic_summary: The existing topic summary to compare against.
        threshold: Maximum Hamming distance to consider a duplicate
            (range 0–64, lower = stricter).  Default 22 ≈ ~66% similarity.
            Calibrated: recap summaries score 15–20, unrelated long messages
            score 25–36, providing a clean 5-point separation gap.

    Returns:
        (kept_message_ids, skipped_count).
    """
    summary_fp = simhash(topic_summary)

    kept_ids: list[int] = []
    skipped = 0
    for msg in messages:
        mid = msg.get("id")
        content = msg.get("content", "").strip()

        # Short messages can't be meaningful recaps — keep them
        if not content or len(content) < MIN_MESSAGE_LENGTH:
            kept_ids.append(mid)
            continue

        msg_fp = simhash(content[:2000])
        dist = hamming_distance(msg_fp, summary_fp)

        if dist <= threshold:
            skipped += 1
        else:
            kept_ids.append(mid)

    return kept_ids, skipped
