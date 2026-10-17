import logging
import os
from typing import Any, Dict, List, Literal, Optional

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.schema import NodeWithScore
from pydantic import BaseModel, Field, validator
from pydantic.alias_generators import to_camel

from app.engine.custom_node_with_score import CustomNodeWithScore

logger = logging.getLogger("uvicorn")


class FileContent(BaseModel):
    type: Literal["text", "ref"]
    # If the file is pure text then the value is be a string
    # otherwise, it's a list of document IDs
    value: str | List[str]


class File(BaseModel):
    id: str
    content: FileContent
    filename: str
    filesize: int
    filetype: str


class AnnotationFileData(BaseModel):
    files: List[File] = Field(
        default=[],
        description="List of files",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "csvFiles": [
                    {
                        "content": "Name, Age\nAlice, 25\nBob, 30",
                        "filename": "example.csv",
                        "filesize": 123,
                        "id": "123",
                        "type": "text/csv",
                    }
                ]
            }
        }
        alias_generator = to_camel


class Annotation(BaseModel):
    type: str
    data: AnnotationFileData | List[str]


class Message(BaseModel):
    role: MessageRole
    content: str
    annotations: List[Annotation] | None = None
    trace_id: str | None = None


_CLIENT_ROLES = (MessageRole.USER, MessageRole.ASSISTANT)


class ChatData(BaseModel):
    messages: List[Message]
    data: Any = None

    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {
                        "role": "user",
                        "content": "What standards for letters exist?",
                    }
                ]
            }
        }

    @validator("messages")
    def messages_must_not_be_empty(cls, v):
        if len(v) == 0:
            raise ValueError("Messages must not be empty")
        if len(v) > 50:
            raise ValueError("Too many messages. Conversation history is limited to 50 messages.")
        # History comes from the client and goes into chat memory unscreened
        # (only the last message passes the security screen). A client-supplied
        # system/tool turn would sit beside the system prompt, so only the two
        # conversational roles are accepted, and the turn being answered must
        # be the user's.
        for message in v:
            if message.role not in _CLIENT_ROLES:
                raise ValueError("Messages may only have the roles 'user' and 'assistant'.")
        if v[-1].role != MessageRole.USER:
            raise ValueError("The last message must be from the user.")
        # Enforce 10KB limit on the last user message only (not full history)
        last_message = v[-1]
        if len(last_message.content.encode("utf-8")) > 10 * 1024:
            raise ValueError("Message too long. Please keep your message under 10KB.")
        return v

    def get_last_message_content(self) -> str:
        """The content of the last message.

        Upstream also appended text from `document_file` annotations (the
        upload feature). Uploads are not ported, so annotations never reach
        the prompt.
        """
        if len(self.messages) == 0:
            raise ValueError("There is not any message in the chat")
        return self.messages[-1].content

    def get_history_messages(self) -> List[ChatMessage]:
        """
        Get the history messages
        """
        return [
            ChatMessage(role=message.role, content=message.content)
            for message in self.messages[:-1]
        ]

    def is_last_message_from_user(self) -> bool:
        return self.messages[-1].role == MessageRole.USER

    def clear_chat_messages(self):
        self.messages = []
        return self


class SourceNodes(BaseModel):
    id: str
    citation_node_id: str
    metadata: Dict[str, Any]
    score: Optional[float]
    text: str
    url: Optional[str]

    @classmethod
    def from_source_node(cls, source_node: CustomNodeWithScore):
        metadata = source_node.node.metadata
        url = cls.get_url_from_metadata(metadata)
        logger.info(f"Metadata{metadata}")

        return cls(
            id=source_node.node.node_id,
            citation_node_id=source_node.citation_node_id,
            metadata=metadata,
            score=source_node.score,
            text=source_node.node.text,  # type: ignore
            url=url,
        )

    @classmethod
    def get_url_from_metadata(cls, metadata: Dict[str, Any]) -> str:
        # The index stores the citation URL directly: the public PDF for an
        # instructor guide, or the page itself for a linked page.
        return metadata.get("url")

    @classmethod
    def from_source_nodes(cls, source_nodes: List[CustomNodeWithScore]):
        return [cls.from_source_node(node) for node in source_nodes]


class Result(BaseModel):
    result: Message
    nodes: List[SourceNodes]


class ChatConfig(BaseModel):
    starter_questions: Optional[List[str]] = Field(
        default=None,
        description="List of starter questions",
        serialization_alias="starterQuestions",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "starterQuestions": [
                    "What standards for letters exist?",
                    "What are the requirements for a letter to be considered a letter?",
                ]
            }
        }


class ThumbsRequest(BaseModel):
    trace_id: str
    value: str
    comment: Optional[str] = None


class DraftEditRequest(BaseModel):
    draft_type: Literal["email", "message"]
    instruction: str
    selected_text: str
    full_content: str
    subject: Optional[str] = None

    @validator("instruction")
    def instruction_must_not_be_empty(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("Instruction is required")
        if len(value.encode("utf-8")) > 2 * 1024:
            raise ValueError("Instruction is too long")
        return value

    @validator("selected_text")
    def selected_text_must_not_be_empty(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("Selected text is required")
        if len(value.encode("utf-8")) > 12 * 1024:
            raise ValueError("Selected text is too long")
        return value

    @validator("full_content")
    def full_content_limit(cls, v):
        value = v or ""
        if len(value.encode("utf-8")) > 64 * 1024:
            raise ValueError("Full content is too long")
        return value


class DraftEditResponse(BaseModel):
    edited_text: Optional[str] = None
    blocked: bool = False
    message: Optional[str] = None
    reason: Optional[str] = None
