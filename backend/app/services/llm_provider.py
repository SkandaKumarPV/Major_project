
import requests

from backend.app.core.config import Settings


class LLMProvider:
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

    def generate_response(self, candidate_answer: str) -> str:
        if not candidate_answer.strip():
            raise ValueError("Candidate answer cannot be empty")

        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional AI interviewer. "
                        "Respond naturally and briefly to the candidate. "
                        "Acknowledge their answer and ask one relevant "
                        "follow-up interview question. Do not ask multiple "
                        "questions at once."
                    ),
                },
                {
                    "role": "user",
                    "content": candidate_answer,
                },
            ],
            "temperature": 0.7,
            "max_tokens": 300,
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        answer = data["choices"][0]["message"]["content"]

        if not answer or not answer.strip():
            raise RuntimeError("LLM returned an empty response")

        return answer.strip()
