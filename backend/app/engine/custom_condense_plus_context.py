import time
import asyncio
import logging
from typing import Any, List, Optional, Tuple, Dict
from collections import defaultdict
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.core.indices.query.schema import QueryBundle
from llama_index.core.schema import MetadataMode, NodeWithScore
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.callbacks import CallbackManager, trace_method
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.core.types import Thread

import voyageai
# Created on first use, not at import, so importing app.engine (tests, scripts,
# app.engine.login_links) doesn't need VOYAGE_API_KEY. main.py still refuses to
# boot without it. Tests replace `vo` with a fake.
vo = None


def _voyage_client():
    global vo
    if vo is None:
        vo = voyageai.Client()  # reads VOYAGE_API_KEY
    return vo

# Rerank settings (CLAUDE.md §2 row 15). Module-level so scripts/retrieve.py
# reranks exactly like production. Q15: leave the 0.21 cutoff alone until the
# Phase 2/6 evals show misses caused by it.
RERANK_MODEL = "rerank-lite-1"
RERANK_TOP_K = 17
RERANK_MIN_SCORE = 0.21


def _do_voyage_rerank(
    message: str,
    node_texts: list[str],
    model: str,
    top_k: int,
    retries: int = 3,
    retry_delay: float = 5.0,
) -> tuple[list[str], dict[str, float], bool, Exception | None]:
    """Run Voyage rerank synchronously. Returns (filtered_texts, scores_dict, success, last_exc).

    Extracted so the async path can wrap it in asyncio.to_thread() to avoid
    blocking the event loop (Pinecone's aquery is a sync stub — see #64).
    """
    # A missing or bad key isn't transient: fail at once instead of sleeping
    # through the retries (main.py refuses to boot without the key anyway).
    try:
        client = _voyage_client()
    except Exception as exc:
        return node_texts, {}, False, exc
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            reranking = client.rerank(message, node_texts, model=model, top_k=top_k)
            filtered = [r.document for r in reranking.results if r.relevance_score >= RERANK_MIN_SCORE]
            scores = {
                r.document: r.relevance_score
                for r in reranking.results
                if r.relevance_score >= RERANK_MIN_SCORE
            }
            return filtered, scores, True, None
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(retry_delay)
    return node_texts, {}, False, last_exc


from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.engine.custom_node_with_score import CustomNodeWithScore

from llama_index.core.chat_engine.types import (
    AgentChatResponse,
    BaseChatEngine,
    StreamingAgentChatResponse,
    ToolOutput,
)


logger = logging.getLogger(__name__)


@dataclass
class RerankOutcome:
    """What `rerank_nodes` did, for the engine and for scripts/evals."""

    nodes: List[NodeWithScore]  # kept nodes, best first
    scores: Dict[str, float] = field(default_factory=dict)  # Voyage score by node text
    attempted: bool = False  # False when there was <= 1 unique text to rank
    success: bool = True  # False when Voyage failed and the unranked nodes were kept
    error: Optional[Exception] = None


def _unique_texts(nodes: List[NodeWithScore]) -> List[str]:
    # Order-preserving (upstream used set(), which made the fallback order random).
    return list(dict.fromkeys(node.text for node in nodes))


def needs_rerank(nodes: List[NodeWithScore]) -> bool:
    return len(_unique_texts(nodes)) > 1


def rerank_nodes(nodes: List[NodeWithScore], message: str) -> RerankOutcome:
    """The production rerank rules, shared by the engine and scripts/retrieve.py.

    - Two or more unique texts: Voyage `RERANK_MODEL`, top `RERANK_TOP_K`, keep
      scores >= `RERANK_MIN_SCORE`, best first. If Voyage fails after its
      retries, keep every unique text unranked (retrieval order).
    - One unique text or none: no rerank call and no cutoff.

    Each kept node gets `metadata["rerank_relevance"]` (its Voyage score, or
    its retrieval score when it wasn't reranked).
    """
    texts_ordered = [node.text for node in nodes]
    unique = _unique_texts(nodes)
    outcome = RerankOutcome(nodes=[])
    kept = unique
    if len(unique) > 1:
        outcome.attempted = True
        kept, outcome.scores, outcome.success, outcome.error = _do_voyage_rerank(
            message, unique, RERANK_MODEL, RERANK_TOP_K,
        )
    for text in kept:
        node = nodes[texts_ordered.index(text)]
        node.node.metadata["rerank_relevance"] = outcome.scores.get(text, node.score)
        outcome.nodes.append(node)
    return outcome


# Who publishes the linked pages (instructor-indexer's linked hosts), by domain
# suffix. The label names the owner, so the model can say whose page it is
# (prompt EXTERNAL PAGES); with only a hostname it often didn't (Phase 6 #21).
SITE_OWNERS = (
    ("byupathway.edu", "BYU-Pathway"),
    ("byupathway.org", "BYU-Pathway"),
    ("byui.edu", "BYU-Idaho"),
    ("byu.edu", "BYU"),
    ("churchofjesuschrist.org", "The Church of Jesus Christ of Latter-day Saints"),
    ("canvaslms.com", "Canvas"),
    ("instructure.com", "Canvas"),
    ("whatsapp.com", "WhatsApp"),
)


def site_owner(host: str) -> str | None:
    """The owner's name for a linked page's host, or None if unknown."""
    host = (host or "").lower().rstrip(".")
    for domain, owner in SITE_OWNERS:
        if host == domain or host.endswith("." + domain):
            return owner
    return None


def source_label(metadata: Dict[str, Any]) -> str:
    """The line the model sees above each context, telling it whose words these are.

    Replaces upstream's missionary audience marker. Instructor guides (the 33
    PDFs) and linked public pages owned by other organizations are labeled
    differently so the prompt's EXTERNAL PAGES rule can apply.
    """
    title = metadata.get("title") or metadata.get("header_1") or "Untitled"
    if metadata.get("source") == "instructor-assistant-linked":
        host = urlparse(metadata.get("url") or "").hostname or "unknown site"
        owner = site_owner(host)
        return f"[Source: {title} — external page from {owner} ({host})]" if owner else (
            f"[Source: {title} — external page ({host})]"
        )
    return f"[Source: {title} — instructor guide]"

class CustomCondensePlusContextChatEngine(CondensePlusContextChatEngine):
    # Set by get_chat_engine(): this engine's AudienceGuardPostprocessor.
    audience_guard: Any = None
    
    def _retrieve_context(self, message: str) -> Tuple[str, List[NodeWithScore]]:
        """Build context for a message from retriever."""
        nodes = self._retriever.retrieve(message)
        for postprocessor in self._node_postprocessors:
            nodes = postprocessor.postprocess_nodes(
                nodes, query_bundle=QueryBundle(message)
            )
        
        # print(nodes)

        # **Organize nodes using the earlier functions**
        organized_nodes = self._organize_nodes(nodes, message=message)
        # print(len(organized_nodes))
        # print(organized_nodes)

        # Custom formatting of context_str
        context_str = "We have {} nodes:\n".format(len(organized_nodes))
        
        nodes_with_citation_node_id = []
        
        for i, node_with_score in enumerate(organized_nodes, start=1):
            node_text = node_with_score.node.get_text()
            _label = source_label(node_with_score.node.metadata)
            context_str += f'node_id: {i}\n{_label}\ntext: {node_text}\n\n'

            # Create a new node with citation_node_id
            new_node = CustomNodeWithScore(node=node_with_score.node, score=node_with_score.score)

            # Assign citation_node_id to the new node
            new_node.citation_node_id = str(i)
            nodes_with_citation_node_id.append(new_node)
            
        return context_str, nodes_with_citation_node_id

    async def _aretrieve_context(self, message: str) -> Tuple[str, List[CustomNodeWithScore]]:
        """Build context for a message from retriever asynchronously."""
        nodes = await self._retriever.aretrieve(message)
        for postprocessor in self._node_postprocessors:
            nodes = postprocessor.postprocess_nodes(
                nodes, query_bundle=QueryBundle(message)
            )
        
        organized_nodes = await self._aorganize_nodes(nodes, message=message)
        # print(len(organized_nodes))
        # for node in organized_nodes:
        #     print(node.text)
        #     print(node.metadata["url"])

        # Custom formatting of context_str
        context_str = "We have {} nodes:\n".format(len(organized_nodes))
        
        nodes_with_citation_node_id = []
        
        for i, node_with_score in enumerate(organized_nodes, start=1):
            node_text = node_with_score.node.get_text()
            _label = source_label(node_with_score.node.metadata)
            context_str += f'node_id: {i}\n{_label}\ntext: {node_text}\n\n'

            # Create a new node with citation_node_id
            new_node = CustomNodeWithScore(node=node_with_score.node, score=node_with_score.score)

            # Assign citation_node_id to the new node
            new_node.citation_node_id = str(i)
            nodes_with_citation_node_id.append(new_node)

        return context_str, nodes_with_citation_node_id

    def _rerank_event_start(self, message: str) -> Optional[str]:
        callback_manager = getattr(self, "callback_manager", None) or getattr(self, "_callback_manager", None)
        if callback_manager is None:
            return None
        return callback_manager.on_event_start(
            CBEventType.RERANKING,
            payload={
                EventPayload.QUERY_STR: message,
                EventPayload.TOP_K: RERANK_TOP_K,
                EventPayload.MODEL_NAME: RERANK_MODEL,
            },
        )

    def _rerank_event_end(self, event_id: Optional[str], outcome: "RerankOutcome") -> None:
        callback_manager = getattr(self, "callback_manager", None) or getattr(self, "_callback_manager", None)
        if callback_manager is None:
            return
        end_payload: dict[str, Any] = {"rerank_success": outcome.success}
        if not outcome.success and outcome.error is not None:
            end_payload[EventPayload.EXCEPTION] = repr(outcome.error)
        callback_manager.on_event_end(
            CBEventType.RERANKING,
            payload=end_payload,
            event_id=event_id or "",
        )

    def _organize_nodes(self, nodes: List[NodeWithScore], message: str = "") -> List[NodeWithScore]:
        """Rerank, then group by URL, order by sequence, and merge per page."""
        event_id = self._rerank_event_start(message) if needs_rerank(nodes) else None
        outcome = rerank_nodes(nodes, message)
        if outcome.attempted:
            self._rerank_event_end(event_id, outcome)
        return self._group_and_merge(outcome.nodes)

    async def _aorganize_nodes(self, nodes: List[NodeWithScore], message: str = "") -> List[NodeWithScore]:
        """Async version: runs the (synchronous) Voyage call in a thread so the
        event loop stays free. Same rerank rules as the sync path."""
        event_id = self._rerank_event_start(message) if needs_rerank(nodes) else None
        outcome = await asyncio.to_thread(rerank_nodes, nodes, message)
        if outcome.attempted:
            self._rerank_event_end(event_id, outcome)
        return self._group_and_merge(outcome.nodes)

    def _group_and_merge(self, nodes_ranked: List[NodeWithScore]) -> List[NodeWithScore]:
        """Group nodes by page (URL), order each page by sequence, and merge
        each page's nodes into one."""
        pages = defaultdict(list)
        for node_with_score in nodes_ranked:
            node = node_with_score.node
            url = node.metadata.get('url', 'unknown_url')
            pages[url].append(node_with_score)

        for url, page_nodes in pages.items():
            pages[url] = sorted(page_nodes, key=lambda x: x.node.metadata.get('sequence', 0))

        organized_nodes = []
        for url, page_nodes in pages.items():
            merged_nodes = self._merge_nodes_with_headers(page_nodes)
            organized_nodes.extend(merged_nodes)

        return organized_nodes

    def _merge_nodes_with_headers(self, nodes: List[NodeWithScore]) -> List[NodeWithScore]:
        """Merge nodes while preserving complete phrases and context."""
        if not nodes:
            return []

        # Use the metadata from the first node
        merged_node_with_score = nodes[0]
        
        # Instead of merging word by word, let's work with complete phrases
        all_texts = [node.node.get_text() for node in nodes] # get all texts
        
        # Create a scoring system for each complete text
        text_scores = []
        for idx, text in enumerate(all_texts):
            score = nodes[idx].score
            sequence = nodes[idx].node.metadata.get('sequence', 0)
            text_scores.append((text, score, sequence)) # add tuple of text and score
        
        # Sort texts by score in ascendent order
        text_scores.sort(key=lambda x: x[2]) # sort by sequence
        
        # Initialize with the first text
        final_text = text_scores[0][0]

        # Concatenate subsequent texts
        for text, _, _ in text_scores[1:]:
            if text.strip():  # Check if text is not empty
                if final_text.strip():  # If final_text is not empty, add double newline
                    final_text += '\n\n'
                final_text += text.strip()
        
        
        # # Function to check if a phrase is semantically different enough to keep
        # def is_unique_content(existing_text: str, new_text: str) -> bool:
        #     existing_words = set(existing_text.lower().split())
        #     new_words = set(new_text.lower().split())
            
        #     # Calculate word overlap
        #     overlap = len(existing_words.intersection(new_words))
        #     total_words = len(new_words)
            
        #     # If less than 70% overlap, consider it unique content
        #     return (overlap / total_words) < 0.7 if total_words > 0 else False
        
        # # Add unique content from other texts
        # for text, _ in text_scores[1:]:
        #     if is_unique_content(final_text, text):
        #         # Add a separator if needed
        #         if not final_text.endswith('.') and not final_text.endswith('?'):
        #             final_text += '. '
        #         else:
        #             final_text += ' '
        #         final_text += text
        
        # Calculate average score
        total_score = sum(node.score for node in nodes)
        average_score = total_score / len(nodes)
        
        # Update the merged node
        merged_node_with_score.node.text = final_text
        merged_node_with_score.score = average_score
        
        return [merged_node_with_score]


    def _split_header_content(self, text: str) -> Tuple[str, str]:
        """Split the text into header and content."""
        lines = text.split('\n', 1)
        if len(lines) > 1:
            return lines[0] + '\n', lines[1]
        return '', text

    def _merge_content(self, existing: str, new: str) -> str:
        """Merge two content strings, removing duplicate words."""
        combined = existing + ' ' + new
        words = combined.split()
        return ' '.join(sorted(set(words), key=words.index))
    
    def reset(self) -> None:
        # Clear chat history
        self._memory.reset()
        self.chat_history.clear()
        
    def get_chat_history(self) -> List[ChatMessage]:
        return self.chat_history
