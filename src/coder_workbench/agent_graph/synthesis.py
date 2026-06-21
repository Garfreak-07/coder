from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem


def build_synthesis_artifact(
    *,
    item: WorkItem,
    envelope: AgentTaskEnvelope,
    agent_id: str,
) -> dict[str, Any]:
    """Build the deterministic SynthesisArtifact skeleton used by mock runs."""

    sources = _deduplicate_sources(_collect_sources(item=item, envelope=envelope))
    clusters = _cluster_sources(sources)
    ranked_items = _rank_clusters(clusters)
    compressed_summary = _compress_ranked_items(ranked_items)
    summary = compressed_summary or f"Synthesized {len(sources)} source(s)."
    return {
        "artifact_type": "synthesis_artifact",
        "round": envelope.round,
        "work_item_id": item.work_item_id,
        "merge_index": item.merge_index,
        "agent_id": agent_id,
        "status": "completed",
        "summary": summary,
        "sources": sources,
        "deduplicated_source_ids": [source["source_id"] for source in sources],
        "clusters": clusters,
        "ranked_items": ranked_items,
        "compressed_summary": compressed_summary,
        "index": _build_index(sources),
        "outputs": [*envelope.upstream_refs, *envelope.loaded_skill_refs],
        "unexpected_issues": [],
        "out_of_contract": False,
        "needs_planner_decision": False,
    }


def _collect_sources(*, item: WorkItem, envelope: AgentTaskEnvelope) -> list[dict[str, str]]:
    sources = [
        {
            "source_id": "task",
            "ref": envelope.planner_order_ref,
            "source_type": "task",
            "title": item.work_item_id,
            "summary": item.task_summary,
        }
    ]
    for index, ref in enumerate(envelope.upstream_refs, start=1):
        sources.append(
            {
                "source_id": f"upstream-{index}",
                "ref": ref,
                "source_type": "upstream",
                "title": ref,
                "summary": f"Upstream artifact reference: {ref}",
            }
        )
    for index, context in enumerate(envelope.selected_skill_context, start=1):
        skill_id = str(context.get("skill_id") or f"skill-{index}")
        content = str(context.get("content") or "")
        sources.append(
            {
                "source_id": f"skill-{skill_id}",
                "ref": str(context.get("ref") or f"skill:{skill_id}:SKILL.md"),
                "source_type": "skill",
                "title": skill_id,
                "summary": _first_non_empty_line(content) or f"Selected Skill context for {skill_id}.",
            }
        )
    return sources


def _deduplicate_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        key = _normalize_text(source.get("summary", ""))
        if not key:
            key = _normalize_text(source.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _cluster_sources(sources: list[dict[str, str]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source in sources:
        buckets[_cluster_key(source["summary"])].append(source)
    clusters = []
    for index, (key, members) in enumerate(sorted(buckets.items()), start=1):
        title = key.replace("_", " ").title() if key else "General"
        clusters.append(
            {
                "cluster_id": f"cluster-{index}",
                "title": title,
                "summary": " ".join(_truncate(member["summary"], 180) for member in members),
                "source_ids": [member["source_id"] for member in members],
                "rank_score": round(len(members) + sum(len(member["summary"]) for member in members) / 1000, 4),
            }
        )
    return clusters


def _rank_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(clusters, key=lambda cluster: (-float(cluster["rank_score"]), str(cluster["cluster_id"])))
    return [
        {
            "item_id": f"ranked-{index}",
            "rank": index,
            "title": cluster["title"],
            "summary": cluster["summary"],
            "source_ids": cluster["source_ids"],
            "score": cluster["rank_score"],
        }
        for index, cluster in enumerate(ranked, start=1)
    ]


def _compress_ranked_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    parts = [f"{item['rank']}. {item['title']}: {_truncate(str(item['summary']), 220)}" for item in items[:5]]
    return " ".join(parts)


def _build_index(sources: list[dict[str, str]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for source in sources:
        for token in _tokens(source["summary"])[:12]:
            refs = index.setdefault(token, [])
            if source["source_id"] not in refs:
                refs.append(source["source_id"])
    return index


def _cluster_key(text: str) -> str:
    tokens = [token for token in _tokens(text) if len(token) > 2]
    return tokens[0] if tokens else "general"


def _normalize_text(text: str) -> str:
    return " ".join(_tokens(text))


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if token]


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip(" #\t")
        if stripped:
            return stripped
    return ""


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."
