"""Statistical recommendation advisor using the LLM provider."""

from __future__ import annotations

import json

from app.core.exceptions import ValidationError
from app.core.llm_provider import LLMProvider
from app.models.user import User


class StatisticalAdvisor:
    """
    Given a dataset and a hypothesis/question, recommends the appropriate statistical test.
    This is FORGE's differentiator — neither Quadratic nor Julius has this.
    """

    ADVISOR_SYSTEM_PROMPT = """You are a PhD-level statistician. Given a dataset schema,
sample statistics, and the user's analysis question, you MUST:
1. Recommend the single most appropriate statistical test
2. State the assumptions required and whether they're likely met
3. Explain WHY this test vs alternatives in 2-3 sentences
4. Provide Python code using scipy.stats to run the test
5. Explain how to interpret the p-value and effect size
Respond in JSON format with keys: test_name, assumptions, rationale, code, interpretation"""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or LLMProvider()

    async def recommend_test(
        self,
        user: User,
        dataset_profile: dict,
        question: str,
    ) -> dict:
        prompt = (
            "Dataset profile:\n"
            f"{json.dumps(dataset_profile)}\n\n"
            "User question:\n"
            f"{question}"
        )
        response = await self.llm_provider.complete(
            user=user,
            messages=[{"role": "user", "content": prompt}],
            system=self.ADVISOR_SYSTEM_PROMPT,
            stream=False,
            max_tokens=600,
        )
        text = response if isinstance(response, str) else ""
        parsed = self._parse_json_response(text)
        self._validate(parsed)
        return parsed

    def _parse_json_response(self, text: str) -> dict:
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start : end + 1])
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

        raise ValidationError("Could not parse statistical advisor JSON response")

    def _validate(self, payload: dict) -> None:
        required = {"test_name", "assumptions", "rationale", "code", "interpretation"}
        missing = required.difference(payload.keys())
        if missing:
            raise ValidationError(
                f"Statistical advisor response missing keys: {', '.join(sorted(missing))}"
            )
