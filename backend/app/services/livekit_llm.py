import asyncio
import uuid

from livekit.agents import llm


class LiveKitLLM(llm.LLM):
    """Adapts our configurable HTTP LLM provider to LiveKit Agents."""

    def __init__(self, provider):
        super().__init__()
        self.provider = provider

    @property
    def model(self) -> str:
        return self.provider.model

    def chat(
        self,
        *,
        chat_ctx,
        tools=None,
        conn_options,
        **kwargs,
    ):
        if tools:
            raise NotImplementedError(
                "Tool calling is not supported by this interviewer"
            )

        return LiveKitLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=[],
            conn_options=conn_options,
        )


class LiveKitLLMStream(llm.LLMStream):
    """Runs the HTTP request and emits its response as one chunk."""

    async def _run(self):
        candidate_answer = self._get_latest_user_message()

        if not candidate_answer.strip():
            raise ValueError("No candidate message found in chat context")

        response_text = await asyncio.to_thread(
            self._llm.provider.generate_response,
            candidate_answer,
        )

        if not response_text or not response_text.strip():
            raise RuntimeError("LLM provider returned an empty response")

        yield_chunk = llm.ChatChunk(
            id=str(uuid.uuid4()),
            delta=llm.ChoiceDelta(
                role="assistant",
                content=response_text.strip(),
            ),
        )

        self._event_ch.send_nowait(yield_chunk)

    def _get_latest_user_message(self) -> str:
        """Extracts the most recent candidate message from chat history."""

        for item in reversed(self._chat_ctx.items):
            role = getattr(item, "role", None)

            if role != "user":
                continue

            # Some LiveKit message types expose text_content.
            text_content = getattr(item, "text_content", None)

            if isinstance(text_content, str) and text_content.strip():
                return text_content.strip()

            # Other message types expose content directly.
            content = getattr(item, "content", None)

            if isinstance(content, str):
                return content.strip()

            # Handle a list of text/audio/image content items.
            if isinstance(content, list):
                parts = []

                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    else:
                        text = getattr(part, "text", None)
                        if isinstance(text, str):
                            parts.append(text)

                result = " ".join(parts).strip()

                if result:
                    return result

        return ""