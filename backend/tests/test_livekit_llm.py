from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from livekit.agents import llm

from backend.app.services.livekit_llm import LiveKitLLM


@pytest.fixture
def provider():
    mock_provider = Mock()
    mock_provider.model = "nvidia/nemotron-test"
    mock_provider.generate_response.return_value = (
        "That's interesting. What did you learn from that experience?"
    )
    return mock_provider


@pytest.fixture
def adapter(provider):
    return LiveKitLLM(provider)


def make_chat_context(messages):
    return llm.ChatContext(
        items=[
            llm.ChatMessage(role=role, content=[content])
            for role, content in messages
        ]
    )


def get_default_connection_options():
    return llm.LLM.chat.__kwdefaults__["conn_options"]


def test_adapter_uses_provider_model_name(adapter):
    assert adapter.model == "nvidia/nemotron-test"


@pytest.mark.asyncio
async def test_adapter_generates_assistant_response(adapter, provider):
    context = make_chat_context([
        ("user", "I am studying computer science and robotics.")
    ])

    stream = adapter.chat(
        chat_ctx=context,
        tools=[],
        conn_options=get_default_connection_options(),
    )

    async with stream:
        chunks = [chunk async for chunk in stream]

    assert len(chunks) == 1
    assert chunks[0].delta is not None
    assert chunks[0].delta.role == "assistant"
    assert chunks[0].delta.content == (
        "That's interesting. What did you learn from that experience?"
    )

    provider.generate_response.assert_called_once_with(
        "I am studying computer science and robotics."
    )


@pytest.mark.asyncio
async def test_adapter_uses_latest_user_message(adapter, provider):
    context = make_chat_context([
        ("user", "My name is Alex."),
        ("assistant", "Nice to meet you."),
        ("user", "I am interested in robotics."),
    ])

    stream = adapter.chat(
        chat_ctx=context,
        tools=[],
        conn_options=get_default_connection_options(),
    )

    async with stream:
        chunks = [chunk async for chunk in stream]

    assert len(chunks) == 1

    provider.generate_response.assert_called_once_with(
        "I am interested in robotics."
    )


@pytest.mark.asyncio
async def test_adapter_rejects_context_without_user_message(
    adapter,
    provider,
):
    context = make_chat_context([
        ("assistant", "Welcome to the interview."),
    ])

    stream = adapter.chat(
        chat_ctx=context,
        tools=[],
        conn_options=get_default_connection_options(),
    )

    with pytest.raises(ValueError, match="No candidate message"):
        async with stream:
            async for _ in stream:
                pass

    provider.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_adapter_rejects_empty_provider_response(
    adapter,
    provider,
):
    provider.generate_response.return_value = "   "

    context = make_chat_context([
        ("user", "Tell me about yourself.")
    ])

    stream = adapter.chat(
        chat_ctx=context,
        tools=[],
        conn_options=get_default_connection_options(),
    )

    with pytest.raises(RuntimeError, match="empty response"):
        async with stream:
            async for _ in stream:
                pass


def test_adapter_rejects_tool_calling(adapter):
    context = make_chat_context([
        ("user", "Tell me about yourself.")
    ])

    with pytest.raises(NotImplementedError, match="Tool calling"):
        adapter.chat(
            chat_ctx=context,
            tools=[SimpleNamespace()],
            conn_options=get_default_connection_options(),
        )