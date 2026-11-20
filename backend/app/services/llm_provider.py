import json
import requests

from backend.app.core.config import Settings


class LLMProvider:
    """Configurable OpenAI-compatible chat-completions provider."""

    DEFAULT_SYSTEM_PROMPT = (
        "You are a professional AI interviewer. "
        "Respond naturally and briefly. "
        "Ask only one conversational question at a time. "
        "Do not invent candidate experience or facts."
    )

    def __init__(self, settings: Settings):
        if not settings.llm_api_key:
            raise ValueError("LLM API key is required")

        if not settings.llm_model:
            raise ValueError("LLM model is required")

        if not settings.llm_base_url:
            raise ValueError("LLM base URL is required")

        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url.rstrip("/")

    def generate_response(
        self,
        candidate_answer: str,
        conversation_context: list | None = None,
    ) -> str:
        if (
            not isinstance(candidate_answer, str)
            or not candidate_answer.strip()
        ):
            raise ValueError("Candidate answer cannot be empty")

        messages = self._build_messages(
            candidate_answer,
            conversation_context,
        )

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": 300,
            },
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()
        answer = data["choices"][0]["message"]["content"]

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("LLM returned an empty response")

        return answer.strip()

    def generate_structured_response(
        self,
        system_prompt,
        conversation_context=None,
    ):
        """Return one JSON-object decision for an adaptive interview turn."""

        if (
            not isinstance(system_prompt, str)
            or not system_prompt.strip()
        ):
            raise ValueError("System prompt cannot be empty")

        messages = [
            {
                "role": "system",
                "content": system_prompt.strip(),
            }
        ]

        for item in conversation_context or []:
            if not isinstance(item, dict):
                continue

            speaker = str(
                item.get("speaker", "")
            ).lower()

            content = item.get("text")

            if (
                not isinstance(content, str)
                or not content.strip()
            ):
                continue

            if speaker in {
                "interviewer",
                "assistant",
                "agent",
            }:
                role = "assistant"

            elif speaker in {
                "candidate",
                "user",
            }:
                role = "user"

            elif speaker == "system":
                role = "system"

            else:
                continue

            messages.append({
                "role": role,
                "content": content.strip(),
            })

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 500,
                "response_format": {
                    "type": "json_object",
                },
            },
            timeout=60,
        )

        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(
                "LLM returned an empty structured response"
            )

        try:
            parsed = json.loads(content)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM returned invalid JSON"
            ) from exc

        if not isinstance(parsed, dict):
            raise RuntimeError(
                "LLM structured response must be a JSON object"
            )

        return parsed

    def _build_messages(
        self,
        candidate_answer: str,
        conversation_context: list | None,
    ) -> list[dict]:
        """Convert interview context into chat-completion messages."""

        if not conversation_context:
            return [
                {
                    "role": "system",
                    "content": self.DEFAULT_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": candidate_answer.strip(),
                },
            ]

        messages = []

        for item in conversation_context:
            if not isinstance(item, dict):
                continue

            speaker = str(
                item.get("speaker", "")
            ).lower()

            content = item.get("text")

            if (
                not isinstance(content, str)
                or not content.strip()
            ):
                continue

            if speaker == "system":
                role = "system"

            elif speaker in {
                "interviewer",
                "assistant",
                "agent",
            }:
                role = "assistant"

            elif speaker in {
                "candidate",
                "user",
            }:
                role = "user"

            else:
                continue

            messages.append({
                "role": role,
                "content": content.strip(),
            })

        if (
            not messages
            or messages[0]["role"] != "system"
        ):
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": self.DEFAULT_SYSTEM_PROMPT,
                },
            )

        # Ensure the latest candidate answer is represented exactly once.
        if not any(
            message["role"] == "user"
            and message["content"] == candidate_answer.strip()
            for message in messages
        ):
            messages.append({
                "role": "user",
                "content": candidate_answer.strip(),
            })

        return messages