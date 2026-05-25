import logging

import lark_oapi
from lark_oapi.api.docx.v1 import (
    CreateDocumentRequest,
    CreateDocumentRequestBody,
    Block,
    CreateDocumentBlockChildrenRequest,
    CreateDocumentBlockChildrenRequestBody,
)

from src import config

logger = logging.getLogger(__name__)


def _get_client() -> lark_oapi.Client:
    return lark_oapi.Client.builder() \
        .app_id(config.FEISHU_APP_ID) \
        .app_secret(config.FEISHU_APP_SECRET) \
        .log_level(lark_oapi.LogLevel.WARNING) \
        .build()


def create_document(title: str) -> str:
    """Create a new Feishu document, return the document_id."""
    client = _get_client()
    req = CreateDocumentRequest.builder() \
        .request_body(CreateDocumentRequestBody.builder()
            .title(title)
            .build()) \
        .build()
    resp = client.docx.v1.document.create(req)
    if not resp.success():
        raise RuntimeError(f"Failed to create doc: {resp.code} {resp.msg}")
    doc_id = resp.data.document.document_id
    logger.info("Created document: %s (id: %s)", title, doc_id)
    return doc_id


def add_blocks(document_id: str, blocks: list[Block]) -> None:
    """Add content blocks to a Feishu document."""
    if not blocks:
        logger.warning("No blocks to add")
        return

    client = _get_client()
    # Add in chunks of 50 to avoid oversized payloads
    chunk_size = 50
    for i in range(0, len(blocks), chunk_size):
        chunk = blocks[i:i + chunk_size]
        req = CreateDocumentBlockChildrenRequest.builder() \
            .document_id(document_id) \
            .block_id(document_id) \
            .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                .children(chunk)
                .build()) \
            .build()
        resp = client.docx.v1.document_block_children.create(req)
        if not resp.success():
            raise RuntimeError(
                f"Failed to add blocks (chunk {i // chunk_size}): {resp.code} {resp.msg}"
            )
        logger.info("Added %d blocks (offset %d/%d)", len(chunk), i, len(blocks))


def get_document_url(document_id: str) -> str:
    return f"https://{config.FEISHU_APP_ID.split('_')[0]}.feishu.cn/docx/{document_id}"
