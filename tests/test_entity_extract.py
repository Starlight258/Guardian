from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.service.entity_extract import (
    AnthropicEntityExtractor,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    _extraction_result_from_payload,
)


def _tool_use_block(payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extracted_graph"
    block.input = payload
    return block


def test_anthropic_entity_extractor_uses_tool_use_forced() -> None:
    mock_anthropic = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [
        _tool_use_block(
            {
                "entities": [
                    {"name": "BGE-M3", "entity_type": "TECHNOLOGY"},
                    {"name": "Chroma", "entity_type": "TECHNOLOGY"},
                ],
                "relations": [
                    {
                        "source": "BGE-M3",
                        "target": "Chroma",
                        "relation_type": "stores_into",
                        "description": "BGE-M3로 임베딩한 벡터를 Chroma에 저장한다",
                    }
                ],
            }
        )
    ]
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        extractor = AnthropicEntityExtractor()
        result = extractor.extract("BGE-M3로 임베딩하고 Chroma에 저장한다")

    kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "extracted_graph"}
    assert kwargs["max_tokens"] >= 4096
    assert result.entities == [
        ExtractedEntity(name="BGE-M3", entity_type="TECHNOLOGY"),
        ExtractedEntity(name="Chroma", entity_type="TECHNOLOGY"),
    ]
    assert result.relations == [
        ExtractedRelation(
            source="BGE-M3",
            target="Chroma",
            relation_type="stores_into",
            description="BGE-M3로 임베딩한 벡터를 Chroma에 저장한다",
        )
    ]


def test_anthropic_entity_extractor_returns_empty_result_without_tool_use() -> None:
    mock_anthropic = MagicMock()
    mock_response = MagicMock()
    mock_response.content = []
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        extractor = AnthropicEntityExtractor()
        result = extractor.extract("아무 내용")

    assert result == ExtractionResult()


def test_extraction_result_drops_relations_with_unknown_entities() -> None:
    payload = {
        "entities": [{"name": "RAG", "entity_type": "CONCEPT"}],
        "relations": [
            {
                "source": "RAG",
                "target": "존재하지 않는 엔티티",
                "relation_type": "uses",
                "description": "ignored",
            }
        ],
    }

    result = _extraction_result_from_payload(payload)

    assert result.entities == [ExtractedEntity(name="RAG", entity_type="CONCEPT")]
    assert result.relations == []


def test_extraction_result_drops_self_loop_relations() -> None:
    payload = {
        "entities": [{"name": "RAG", "entity_type": "CONCEPT"}],
        "relations": [
            {
                "source": "RAG",
                "target": "RAG",
                "relation_type": "self",
                "description": "ignored",
            }
        ],
    }

    result = _extraction_result_from_payload(payload)

    assert result.relations == []


def test_extraction_result_skips_entities_missing_required_fields() -> None:
    payload = {
        "entities": [
            {"name": "RAG", "entity_type": "CONCEPT"},
            {"name": "", "entity_type": "CONCEPT"},
            {"name": "NoType"},
        ],
        "relations": [],
    }

    result = _extraction_result_from_payload(payload)

    assert result.entities == [ExtractedEntity(name="RAG", entity_type="CONCEPT")]
