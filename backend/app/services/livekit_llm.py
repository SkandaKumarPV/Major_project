
import asyncio
import uuid

from livekit.agents import llm


class LiveKitLLM(llm.LLM):
    """Adapts the HTTP LLM provider to LiveKit Agents."""

    def __init__(self, provider, response_handler=None):
        super().__init__()
        self.provider = provider
        self.response_handler = response_handler

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
    """Generates one response for each committed candidate turn."""

    async def _run(self):
        candidate_answer = self._get_latest_user_message()

        if not candidate_answer.strip():
            raise ValueError("No candidate message found in chat context")

        if self._llm.response_handler is not None:
            response_text = await asyncio.to_thread(
                self._llm.response_handler,
                candidate_answer,
            )
        else:
            response_text = await asyncio.to_thread(
                self._llm.provider.generate_response,
                candidate_answer,
            )

        if not isinstance(response_text, str) or not response_text.strip():
            raise RuntimeError("LLM returned an empty response")

        chunk = llm.ChatChunk(
            id=str(uuid.uuid4()),
            delta=llm.ChoiceDelta(
                role="assistant",
                content=response_text.strip(),
            ),
        )

        self._event_ch.send_nowait(chunk)

    def _get_latest_user_message(self) -> str:
        """Extract the latest candidate message from LiveKit chat history."""

        for item in reversed(self._chat_ctx.items):
            if getattr(item, "role", None) != "user":
                continue

            text_content = getattr(item, "text_content", None)

            if isinstance(text_content, str) and text_content.strip():
                return text_content.strip()

            content = getattr(item, "content", None)

            if isinstance(content, str) and content.strip():
                return content.strip()

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
