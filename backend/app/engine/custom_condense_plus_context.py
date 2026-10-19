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
vo = voyageai.Client()  # This will automatically use the environment variable VOYAGE_API_KEY.

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
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            reranking = vo.rerank(message, node_texts, model=model, top_k=top_k)
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


from urllib.parse import urlparse

from app.engine.custom_node_with_score import CustomNodeWithScore

from llama_index.core.chat_engine.types import (
    AgentChatResponse,
    BaseChatEngine,
    StreamingAgentChatResponse,
    ToolOutput,
)


logger = logging.getLogger(__name__)


def source_label(metadata: Dict[str, Any]) -> str:
    """The line the model sees above each context, telling it whose words these are.

    Replaces upstream's missionary audience marker. Instructor guides (the 33
    PDFs) and linked public pages owned by other organizations are labeled
    differently so the prompt's EXTERNAL PAGES rule can apply.
    """
    title = metadata.get("title") or metadata.get("header_1") or "Untitled"
    if metadata.get("source") == "instructor-assistant-linked":
        host = urlparse(metadata.get("url") or "").hostname or "unknown site"
        return f"[Source: {title} — external page ({host})]"
    return f"[Source: {title} — instructor guide]"

class CustomCondensePlusContextChatEngine(CondensePlusContextChatEngine):
    
    def _retrieve_context(self, message: str) -> Tuple[str, List[NodeWithScore]]:
        """Build context for a message from retriever."""
        nodes = self._retriever.retrieve(message)
        for i, node in enumerate(nodes):
            print(f"Node {i+1}: {node.text}\n\n\n")
        for postprocessor in self._node_postprocessors:
            nodes = postprocessor.postprocess_nodes(
                nodes, query_bundle=QueryBundle(message)
            )
            for i, node in enumerate(nodes):
                print(f"Node {i+1}: {node.text}\n\n\n")
        
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

    def _organize_nodes(self, nodes: List[NodeWithScore], message: str = "") -> List[NodeWithScore]:
        """Organize nodes by URL, sequence, and merge overlapping nodes."""
        rerank_model = RERANK_MODEL
        rerank_k = RERANK_TOP_K

        node_texts_ordered = [node.text for node in nodes]
        node_texts = list(set(node_texts_ordered))
        rerank_scores: dict[str, float] = {}

        if len(node_texts) > 1:
            callback_manager = getattr(self, "callback_manager", None) or getattr(self, "_callback_manager", None)
            event_id = None
            if callback_manager is not None:
                event_id = callback_manager.on_event_start(
                    CBEventType.RERANKING,
                    payload={
                        EventPayload.QUERY_STR: message,
                        EventPayload.TOP_K: rerank_k,
                        EventPayload.MODEL_NAME: rerank_model,
                    },
                )

            node_texts, rerank_scores, success, last_exc = _do_voyage_rerank(
                message, node_texts, rerank_model, rerank_k,
            )

            if callback_manager is not None:
                end_payload: dict[str, Any] = {"rerank_success": success}
                if not success and last_exc is not None:
                    end_payload[EventPayload.EXCEPTION] = repr(last_exc)
                callback_manager.on_event_end(
                    CBEventType.RERANKING,
                    payload=end_payload,
                    event_id=event_id or "",
                )

        nodes_ranked = []
        if len(node_texts) == 0:
            node_texts = ['qwer asdf']
        else:
            # CHANGED - get filtered and reranked nodes; stash Voyage relevance score on metadata
            for node_text in node_texts:
                node = nodes[node_texts_ordered.index(node_text)]
                node.node.metadata["rerank_relevance"] = rerank_scores.get(node_text, node.score)
                nodes_ranked.append(node)
            # for node_text in node_texts:
            #     node_text_nodes.append((node_text, nodes[node_texts_ordered.index(node_text)]))

        # Defensive backfill: ensure every node has rerank_relevance regardless of path taken
        # (covers no-rerank fallback, len <= 1, and exception paths where rerank_scores may not exist)
        for node in nodes_ranked:
            node.node.metadata.setdefault("rerank_relevance", node.score)

        # Step 5: Group nodes by page (URL)
        pages = defaultdict(list)
        for node_with_score in nodes_ranked:
            node = node_with_score.node
            url = node.metadata.get('url', 'unknown_url')
            pages[url].append(node_with_score)
                
        # Step 6: Order nodes on each page by sequence number
        for url, page_nodes in pages.items():
            pages[url] = sorted(page_nodes, key=lambda x: x.node.metadata.get('sequence', 0))

        # Step 7: Merge overlapping nodes with the same headers
        organized_nodes = []
        for url, page_nodes in pages.items():
            merged_nodes = self._merge_nodes_with_headers(page_nodes)
            organized_nodes.extend(merged_nodes)
        
        return organized_nodes

    async def _aorganize_nodes(self, nodes: List[NodeWithScore], message: str = "") -> List[NodeWithScore]:
        """Async version: wraps the Voyage rerank in asyncio.to_thread() so the
        event loop stays free during the synchronous HTTP call to Voyage's API.
        Node grouping/merging is CPU-trivial and stays on the main thread."""
        rerank_model = RERANK_MODEL
        rerank_k = RERANK_TOP_K

        node_texts_ordered = [node.text for node in nodes]
        node_texts = list(set(node_texts_ordered))
        rerank_scores: dict[str, float] = {}

        if len(node_texts) > 1:
            callback_manager = getattr(self, "callback_manager", None) or getattr(self, "_callback_manager", None)
            event_id = None
            if callback_manager is not None:
                event_id = callback_manager.on_event_start(
                    CBEventType.RERANKING,
                    payload={
                        EventPayload.QUERY_STR: message,
                        EventPayload.TOP_K: rerank_k,
                        EventPayload.MODEL_NAME: rerank_model,
                    },
                )

            node_texts, rerank_scores, success, last_exc = await asyncio.to_thread(
                _do_voyage_rerank, message, node_texts, rerank_model, rerank_k,
            )

            if callback_manager is not None:
                end_payload: dict[str, Any] = {"rerank_success": success}
                if not success and last_exc is not None:
                    end_payload[EventPayload.EXCEPTION] = repr(last_exc)
                callback_manager.on_event_end(
                    CBEventType.RERANKING,
                    payload=end_payload,
                    event_id=event_id or "",
                )

        nodes_ranked = []
        if len(node_texts) == 0:
            node_texts = ['qwer asdf']
        else:
            for node_text in node_texts:
                node = nodes[node_texts_ordered.index(node_text)]
                node.node.metadata["rerank_relevance"] = rerank_scores.get(node_text, node.score)
                nodes_ranked.append(node)

        for node in nodes_ranked:
            node.node.metadata.setdefault("rerank_relevance", node.score)

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
