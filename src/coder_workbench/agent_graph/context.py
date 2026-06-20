from __future__ import annotations

from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.schema import WorkItem


def upstream_refs_for_item(cache: GraphRunCache, item: WorkItem) -> list[str]:
    refs: list[str] = []
    for upstream_id in item.depends_on:
        refs.extend(cache.refs_for_work_item(upstream_id))
    return refs
