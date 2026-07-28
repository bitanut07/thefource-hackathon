import math

import pytest

from domain.postgres_registry import _query_text, _vector_literal
from llm.schemas import StructuredQuery


def test_query_text_preserves_structured_constraints() -> None:
    query = StructuredQuery(
        intent="find_food_service",
        category="shopping",
        organization="VNG",
        target_user="vng_employee",
    )

    text = _query_text(query)

    assert "find_food_service" in text
    assert "shopping" in text
    assert "VNG" in text


def test_vector_literal_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        _vector_literal((0.2, math.nan))


def test_vector_literal_is_pgvector_compatible() -> None:
    assert _vector_literal((0.25, -0.5)) == "[0.25,-0.5]"
