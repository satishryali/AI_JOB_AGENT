"""DeepSeek API client using OpenAI-compatible interface."""

import asyncio
import json
from functools import wraps
from typing import Any, Callable, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from src.config.settings import LLMSettings
from src.config.config_loader import get_settings
from src.config.logging import get_logger

logger = get_logger(__name__)


class DeepSeekError(Exception):
    """Base exception for DeepSeek client errors."""
    pass


class DeepSeekRateLimitError(DeepSeekError):
    """Rate limit exceeded."""
    pass


class DeepSeekResponseError(DeepSeekError):
    """Invalid or unexpected response."""
    pass


def with_deepseek_retry(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
    """Decorator for retrying DeepSeek API calls with exponential backoff and jitter."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except DeepSeekResponseError:
                    raise
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    if "rate limit" in error_str or "quota" in error_str or "429" in error_str:
                        if attempt < max_retries:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            import random
                            delay += random.uniform(0, delay * 0.1)
                            logger.warning(
                                "DeepSeek rate limited, retrying",
                                attempt=attempt + 1,
                                delay=round(delay, 2),
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise DeepSeekRateLimitError(f"Rate limit exceeded after {max_retries} retries") from e

                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            "DeepSeek call failed, retrying",
                            func=func.__name__,
                            attempt=attempt + 1,
                            delay=round(delay, 2),
                            error=str(e)[:200],
                        )
                        await asyncio.sleep(delay)
                        continue

                    raise DeepSeekError(f"DeepSeek call failed after {max_retries} retries: {e}") from e

            raise last_error

        return wrapper

    return decorator


class DeepSeekClient:
    """Async client for DeepSeek API with structured output support."""

    def __init__(self, settings: Optional[LLMSettings] = None):
        self._settings = settings or get_settings().llm
        self._client: Optional[AsyncOpenAI] = None

    def _ensure_client(self) -> AsyncOpenAI:
        """Ensure the OpenAI client is configured."""
        if self._client is not None:
            return self._client

        api_key = self._settings.api_key
        if not api_key:
            raise DeepSeekError("LLM API key not set in settings or environment")

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._settings.base_url,
            timeout=getattr(self._settings, "timeout", 60.0),
            max_retries=0,
        )
        logger.info("DeepSeek client configured", model=self._settings.model)
        return self._client

    @with_deepseek_retry()
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate text response from DeepSeek."""
        client = self._ensure_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.debug("Generating response", prompt_length=len(prompt))

        response = await client.chat.completions.create(
            model=self._settings.model,
            messages=messages,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
        )

        if not response.choices or not response.choices[0].message.content:
            raise DeepSeekResponseError("Empty response from DeepSeek")

        content = response.choices[0].message.content.strip()
        logger.debug("Response generated", response_length=len(content))
        return content

    @with_deepseek_retry()
    async def generate_json(
        self,
        prompt: str,
        schema: Optional[type[BaseModel]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """Generate structured JSON response from DeepSeek."""
        client = self._ensure_client()

        json_instruction = (
            "Respond ONLY with valid JSON. No markdown, no explanations, no extra text."
        )
        if schema:
            json_instruction += f" Match this schema: {schema.model_json_schema()}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"{prompt}\n\n{json_instruction}"})

        logger.debug("Generating JSON response", prompt_length=len(prompt))

        response = await client.chat.completions.create(
            model=self._settings.model,
            messages=messages,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            response_format={"type": "json_object"},
        )

        if not response.choices or not response.choices[0].message.content:
            raise DeepSeekResponseError("Empty response from DeepSeek")

        text = response.choices[0].message.content.strip()

        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response", response=text[:500])
            raise DeepSeekResponseError(f"Invalid JSON response: {e}") from e

        if schema:
            try:
                validated = schema(**data)
                return validated.model_dump()
            except ValidationError as e:
                logger.error("Response validation failed", errors=str(e)[:500])
                raise DeepSeekResponseError(f"Response validation failed: {e}") from e

        logger.debug("JSON response parsed successfully")
        return data

    async def score_resume_match(
        self,
        job_description: str,
        resume_text: str,
        skills: Optional[list[str]] = None,
    ) -> float:
        """Score how well resume matches job (0.0 to 1.0)."""
        from src.prompts import RESUME_MATCH_PROMPT

        prompt = RESUME_MATCH_PROMPT.format(
            job_description=job_description,
            resume_text=resume_text,
            skills="\n- ".join(skills) if skills else "Not provided",
        )

        from src.ai.schemas import MatchScoreResponse

        result = await self.generate_json(prompt, schema=MatchScoreResponse)
        score = max(0.0, min(1.0, result["score"]))
        logger.info("Resume match scored", score=score, reasoning=result["reasoning"][:100])
        return score

    async def generate_answers(
        self,
        questions: list[str],
        resume_text: str,
        job_description: str,
    ) -> dict[str, str]:
        """Generate answers to application questions."""
        from src.prompts import QA_GENERATION_PROMPT

        prompt = QA_GENERATION_PROMPT.format(
            questions="\n".join(f"- {q}" for q in questions),
            resume_text=resume_text,
            job_description=job_description,
        )

        from src.ai.schemas import AnswersResponse

        result = await self.generate_json(prompt, schema=AnswersResponse)
        logger.info("Generated answers", count=len(result["answers"]))
        return result["answers"]

    async def generate_cover_letter(
        self,
        job_title: str,
        company: str,
        job_description: str,
        resume_text: str,
    ) -> str:
        """Generate a tailored cover letter."""
        from src.prompts import COVER_LETTER_PROMPT

        prompt = COVER_LETTER_PROMPT.format(
            job_title=job_title,
            company=company,
            job_description=job_description,
            resume_text=resume_text,
        )

        return await self.generate(prompt)

    async def decide_apply(
        self,
        job_title: str,
        company: str,
        job_description: str,
        resume_text: str,
        match_score: float,
    ) -> tuple[bool, str]:
        """Decide whether to apply based on match score and job details."""
        from src.prompts import APPLY_DECISION_PROMPT

        prompt = APPLY_DECISION_PROMPT.format(
            job_title=job_title,
            company=company,
            job_description=job_description,
            resume_text=resume_text,
            match_score=match_score,
        )

        from src.ai.schemas import ApplyDecisionResponse

        result = await self.generate_json(prompt, schema=ApplyDecisionResponse)
        logger.info("Apply decision", should_apply=result["should_apply"], reasoning=result["reasoning"][:100])
        return result["should_apply"], result["reasoning"]


_deepseek_client: Optional[DeepSeekClient] = None


def get_deepseek_client(settings: Optional[LLMSettings] = None) -> DeepSeekClient:
    """Get or create the global DeepSeek client instance."""
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient(settings)
    return _deepseek_client


def reset_deepseek_client() -> None:
    """Reset the global DeepSeek client (useful for testing)."""
    global _deepseek_client
    _deepseek_client = None
