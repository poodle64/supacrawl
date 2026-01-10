"""Tests for LLMClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from supacrawl.exceptions import ProviderError
from supacrawl.llm import LLMClient, LLMConfig


class TestLLMClient:
    """Tests for LLMClient."""

    @pytest.fixture
    def ollama_config(self) -> LLMConfig:
        """Create Ollama config for testing."""
        return LLMConfig(
            provider="ollama",
            model="qwen3:8b",
            base_url="http://localhost:11434",
        )

    @pytest.fixture
    def openai_config(self) -> LLMConfig:
        """Create OpenAI config for testing."""
        return LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com",
            api_key="sk-test",
        )

    @pytest.fixture
    def anthropic_config(self) -> LLMConfig:
        """Create Anthropic config for testing."""
        return LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
        )

    def test_client_init(self, ollama_config: LLMConfig) -> None:
        """Test client initialisation."""
        client = LLMClient(ollama_config)

        assert client._config == ollama_config
        assert client._http_client is None
        assert client._ollama_client is None

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self, openai_config: LLMConfig) -> None:
        """Test that close() properly closes the HTTP client."""
        client = LLMClient(openai_config)

        # Create a mock HTTP client
        mock_http_client = AsyncMock()
        client._http_client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_chat_raises_for_unsupported_provider(self) -> None:
        """Test that chat raises for unsupported provider."""
        # Create a config with invalid provider by bypassing validation
        config = LLMConfig(
            provider="unsupported",  # type: ignore[arg-type]
            model="model",
            base_url="http://localhost",
        )
        client = LLMClient(config)

        with pytest.raises(ProviderError) as exc_info:
            await client.chat([{"role": "user", "content": "test"}])

        assert "unsupported" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_chat_json_parses_valid_json(self, ollama_config: LLMConfig) -> None:
        """Test that chat_json parses valid JSON responses."""
        client = LLMClient(ollama_config)

        # Mock the chat method
        with patch.object(client, "chat", return_value='{"key": "value"}'):
            result = await client.chat_json([{"role": "user", "content": "test"}])

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_chat_json_extracts_from_code_block(self, ollama_config: LLMConfig) -> None:
        """Test that chat_json extracts JSON from markdown code blocks."""
        client = LLMClient(ollama_config)

        # Mock the chat method to return JSON in code block
        with patch.object(client, "chat", return_value='```json\n{"key": "value"}\n```'):
            result = await client.chat_json([{"role": "user", "content": "test"}])

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_chat_json_raises_on_invalid_json(self, ollama_config: LLMConfig) -> None:
        """Test that chat_json raises on unparseable response."""
        client = LLMClient(ollama_config)

        # Mock the chat method to return invalid JSON
        with patch.object(client, "chat", return_value="not valid json at all"):
            with pytest.raises(ProviderError) as exc_info:
                await client.chat_json([{"role": "user", "content": "test"}])

        assert "JSON" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_summarize_calls_chat(self, ollama_config: LLMConfig) -> None:
        """Test that summarize calls chat with correct prompt."""
        client = LLMClient(ollama_config)

        with patch.object(client, "chat", return_value="Summary text") as mock_chat:
            result = await client.summarize("Long text to summarize")

        assert result == "Summary text"
        mock_chat.assert_called_once()
        # Check that the text is in the prompt
        call_args = mock_chat.call_args[0][0]
        assert len(call_args) == 1
        assert "Long text to summarize" in call_args[0]["content"]

    @pytest.mark.asyncio
    async def test_summarize_with_max_length(self, ollama_config: LLMConfig) -> None:
        """Test that summarize includes max_length in prompt."""
        client = LLMClient(ollama_config)

        with patch.object(client, "chat", return_value="Short summary") as mock_chat:
            await client.summarize("Text to summarize", max_length=100)

        call_args = mock_chat.call_args[0][0]
        assert "100" in call_args[0]["content"]

    def test_extract_json_from_plain_json(self, ollama_config: LLMConfig) -> None:
        """Test extracting plain JSON."""
        client = LLMClient(ollama_config)

        result = client._extract_json('{"key": "value"}')

        assert result == {"key": "value"}

    def test_extract_json_from_json_code_block(self, ollama_config: LLMConfig) -> None:
        """Test extracting JSON from ```json block."""
        client = LLMClient(ollama_config)

        content = '```json\n{"key": "value"}\n```'
        result = client._extract_json(content)

        assert result == {"key": "value"}

    def test_extract_json_from_generic_code_block(self, ollama_config: LLMConfig) -> None:
        """Test extracting JSON from generic ``` block."""
        client = LLMClient(ollama_config)

        content = '```\n{"key": "value"}\n```'
        result = client._extract_json(content)

        assert result == {"key": "value"}

    def test_extract_json_returns_none_for_invalid(self, ollama_config: LLMConfig) -> None:
        """Test that _extract_json returns None for invalid content."""
        client = LLMClient(ollama_config)

        result = client._extract_json("not json at all")

        assert result is None


class TestLLMClientOllama:
    """Tests for Ollama-specific LLMClient methods."""

    @pytest.fixture
    def config(self) -> LLMConfig:
        """Create Ollama config."""
        return LLMConfig(
            provider="ollama",
            model="qwen3:8b",
            base_url="http://localhost:11434",
        )

    @pytest.mark.asyncio
    async def test_chat_ollama_success(self, config: LLMConfig) -> None:
        """Test successful Ollama chat call."""
        client = LLMClient(config)

        # Mock the Ollama client
        mock_response = MagicMock()
        mock_response.message.content = "Response text"

        mock_ollama = AsyncMock()
        mock_ollama.chat.return_value = mock_response

        with patch.object(client, "_get_ollama_client", return_value=mock_ollama):
            result = await client.chat([{"role": "user", "content": "Hello"}])

        assert result == "Response text"
        mock_ollama.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_ollama_json_mode(self, config: LLMConfig) -> None:
        """Test Ollama chat with JSON mode enabled."""
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.message.content = '{"result": true}'

        mock_ollama = AsyncMock()
        mock_ollama.chat.return_value = mock_response

        with patch.object(client, "_get_ollama_client", return_value=mock_ollama):
            await client.chat([{"role": "user", "content": "Return JSON"}], json_mode=True)

        # Verify format="json" was passed
        call_kwargs = mock_ollama.chat.call_args[1]
        assert call_kwargs.get("format") == "json"


class TestLLMClientOpenAI:
    """Tests for OpenAI-specific LLMClient methods."""

    @pytest.fixture
    def config(self) -> LLMConfig:
        """Create OpenAI config."""
        return LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com",
            api_key="sk-test",
        )

    @pytest.mark.asyncio
    async def test_chat_openai_success(self, config: LLMConfig) -> None:
        """Test successful OpenAI chat call."""
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "OpenAI response"}}]}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_http):
            result = await client.chat([{"role": "user", "content": "Hello"}])

        assert result == "OpenAI response"

    @pytest.mark.asyncio
    async def test_chat_openai_json_mode(self, config: LLMConfig) -> None:
        """Test OpenAI chat with JSON mode enabled."""
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"result": true}'}}]}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_http):
            await client.chat([{"role": "user", "content": "Return JSON"}], json_mode=True)

        # Verify response_format was passed
        call_kwargs = mock_http.post.call_args[1]
        request_body = call_kwargs.get("json", {})
        assert request_body.get("response_format") == {"type": "json_object"}


class TestLLMClientAnthropic:
    """Tests for Anthropic-specific LLMClient methods."""

    @pytest.fixture
    def config(self) -> LLMConfig:
        """Create Anthropic config."""
        return LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
        )

    @pytest.mark.asyncio
    async def test_chat_anthropic_success(self, config: LLMConfig) -> None:
        """Test successful Anthropic chat call."""
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"content": [{"text": "Anthropic response"}]}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_http):
            result = await client.chat([{"role": "user", "content": "Hello"}])

        assert result == "Anthropic response"

    @pytest.mark.asyncio
    async def test_chat_anthropic_extracts_system_message(self, config: LLMConfig) -> None:
        """Test that Anthropic chat extracts system message."""
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"content": [{"text": "Response"}]}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]

        with patch.object(client, "_get_http_client", return_value=mock_http):
            await client.chat(messages)

        # Verify system was extracted to separate field
        call_kwargs = mock_http.post.call_args[1]
        request_body = call_kwargs.get("json", {})
        assert request_body.get("system") == "You are helpful"
        # User message should still be in messages array
        assert len(request_body.get("messages", [])) == 1
        assert request_body["messages"][0]["role"] == "user"
