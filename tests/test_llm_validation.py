import pytest
from pydantic import ValidationError

from src.ai.deepseek_client import DeepSeekClient, DeepSeekResponseError
from src.ai.schemas import MatchScoreResponse


def test_match_schema_accepts_valid_payload():
    data = MatchScoreResponse(
        score=0.87,
        reasoning="strong overlap",
        matched_skills=["Python", "SQL"],
        missing_skills=["AWS"],
    )
    assert data.score == 0.87
    assert data.missing_skills == ["AWS"]


def test_match_schema_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        MatchScoreResponse(score=1.5, reasoning="nope")


@pytest.mark.asyncio
async def test_generate_json_validates_schema():
    class FakeCompletions:
        async def create(self, **kwargs):
            class Msg:
                content = '{"score": 2.5, "reasoning": "bad"}'

            class Choice:
                message = Msg()

            class Resp:
                choices = [Choice()]

            return Resp()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    client = DeepSeekClient()
    client._client = FakeClient()
    with pytest.raises(DeepSeekResponseError):
        await client.generate_json("prompt", schema=MatchScoreResponse)
