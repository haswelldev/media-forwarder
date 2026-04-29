"""Unit tests for Discord client."""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import aiohttp
from src.discord_client import DiscordSender, get_shared_session, close_shared_session


@pytest.fixture(autouse=True)
async def cleanup_session():
    """Clean up shared session after each test."""
    yield
    await close_shared_session()


def make_mock_session(status=200, headers=None):
    """Return (mock_session, mock_response) with session.post as an async context manager."""
    mock_response = Mock()
    mock_response.status = status
    mock_response.headers = headers or {}

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = Mock()
    mock_session.post = Mock(return_value=mock_cm)
    mock_session.closed = False
    return mock_session, mock_response


class TestGetSharedSession:
    """Test shared session management."""

    @pytest.mark.asyncio
    async def test_create_new_session(self):
        await close_shared_session()
        session = await get_shared_session()
        assert session is not None
        assert not session.closed

    @pytest.mark.asyncio
    async def test_reuse_existing_session(self):
        await close_shared_session()
        session1 = await get_shared_session()
        session2 = await get_shared_session()
        assert session1 is session2

    @pytest.mark.asyncio
    async def test_recreate_closed_session(self):
        await close_shared_session()
        session1 = await get_shared_session()
        await session1.close()
        session2 = await get_shared_session()
        assert session1 is not session2
        assert not session2.closed


class TestCloseSharedSession:
    """Test closing shared session."""

    @pytest.mark.asyncio
    async def test_close_existing_session(self):
        session = await get_shared_session()
        assert not session.closed
        await close_shared_session()
        assert session.closed

    @pytest.mark.asyncio
    async def test_close_none_session(self):
        await close_shared_session()
        await close_shared_session()  # Should not raise


class TestDiscordSenderInit:
    """Test DiscordSender initialization."""

    def test_init_with_defaults(self):
        sender = DiscordSender("https://discord.com/webhook")
        assert sender.webhook_url == "https://discord.com/webhook"
        assert sender.max_file_size_mb == 10
        assert sender.max_file_size_bytes == 10 * 1024 * 1024

    def test_init_with_custom_size(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=50)
        assert sender.max_file_size_mb == 50
        assert sender.max_file_size_bytes == 50 * 1024 * 1024


class TestPostWithRetry:
    """Test _post_with_retry retry logic."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender._post_with_retry(lambda: aiohttp.FormData())

        assert result is True
        assert mock_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        sender = DiscordSender("https://discord.com/webhook")

        # First two calls return 500, third returns 200
        responses = [500, 500, 200]
        call_count = 0

        def make_cm():
            nonlocal call_count
            status = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            mock_response = Mock()
            mock_response.status = status
            mock_response.headers = {}
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            return mock_cm

        mock_session = Mock()
        mock_session.post = Mock(side_effect=lambda *a, **kw: make_cm())
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await sender._post_with_retry(lambda: aiohttp.FormData())

        assert result is True
        assert mock_session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_429_with_retry_after(self):
        sender = DiscordSender("https://discord.com/webhook")

        responses = [(429, {'Retry-After': '1'}), (200, {})]
        call_count = 0

        def make_cm():
            nonlocal call_count
            status, headers = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            mock_response = Mock()
            mock_response.status = status
            mock_response.headers = headers
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            return mock_cm

        mock_session = Mock()
        mock_session.post = Mock(side_effect=lambda *a, **kw: make_cm())
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await sender._post_with_retry(lambda: aiohttp.FormData())

        assert result is True
        mock_sleep.assert_called_once_with(1.0)

    @pytest.mark.asyncio
    async def test_fail_after_max_retries(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=500)

        with patch('src.discord_client.get_shared_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await sender._post_with_retry(lambda: aiohttp.FormData())

        assert result is False
        assert mock_session.post.call_count == 3  # _MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retry_on_client_error(self):
        sender = DiscordSender("https://discord.com/webhook")
        call_count = 0

        def make_cm():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise aiohttp.ClientError("connection reset")
            mock_response = Mock()
            mock_response.status = 200
            mock_response.headers = {}
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            return mock_cm

        mock_session = Mock()
        mock_session.post = Mock(side_effect=lambda *a, **kw: make_cm())
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await sender._post_with_retry(lambda: aiohttp.FormData())

        assert result is True


class TestDiscordSenderSendMessage:
    """Test send_message method."""

    @pytest.mark.asyncio
    async def test_send_text_only(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Hello Discord")

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_only(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(media_data=b"fake image data", filename="test.jpg")

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_text_and_media(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                text="Check this out",
                media_data=b"data",
                filename="test.jpg"
            )

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_file_too_large_with_text_returns_true(self):
        """Bug fix #1: text fallback should return True, not False."""
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)
        mock_session, _ = make_mock_session(status=200)

        large_file = b"x" * (2 * 1024 * 1024)  # 2MB > 1MB limit

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                text="Text only",
                media_data=large_file,
                filename="large.jpg"
            )

        assert result is True  # text was sent successfully
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_file_too_large_with_text_post_fails_returns_false(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)
        mock_session, _ = make_mock_session(status=500)

        large_file = b"x" * (2 * 1024 * 1024)

        with patch('src.discord_client.get_shared_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await sender.send_message(
                text="Text only",
                media_data=large_file,
                filename="large.jpg"
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_file_too_large_no_text(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)
        mock_session, _ = make_mock_session()

        large_file = b"x" * (2 * 1024 * 1024)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                media_data=large_file,
                filename="large.jpg"
            )

        assert result is False
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_discord_error_status(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=400)

        with patch('src.discord_client.get_shared_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await sender.send_message(text="Hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_no_content(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session()

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message()

        assert result is False
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_http_error(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session = Mock()
        mock_session.post = Mock(side_effect=Exception("Connection error"))
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_photo_logging(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(media_data=b"data", filename="test.jpg")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_video_logging(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(media_data=b"data", filename="test.mp4")

        assert result is True


class TestDiscordSenderHelpers:
    """Test helper methods."""

    @pytest.mark.asyncio
    async def test_send_photo(self):
        sender = DiscordSender("https://discord.com/webhook")

        with patch.object(sender, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await sender.send_photo("Check this", b"photo_data")

        assert result is True
        mock_send.assert_called_once_with("Check this", b"photo_data", "photo.jpg")

    @pytest.mark.asyncio
    async def test_send_video(self):
        sender = DiscordSender("https://discord.com/webhook")

        with patch.object(sender, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await sender.send_video("Watch this", b"video_data", "custom.mp4")

        assert result is True
        mock_send.assert_called_once_with("Watch this", b"video_data", "custom.mp4")

    @pytest.mark.asyncio
    async def test_send_document(self):
        sender = DiscordSender("https://discord.com/webhook")

        with patch.object(sender, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await sender.send_document("File", b"doc_data", "report.pdf")

        assert result is True
        mock_send.assert_called_once_with("File", b"doc_data", "report.pdf")

    @pytest.mark.asyncio
    async def test_send_multiple_media(self):
        sender = DiscordSender("https://discord.com/webhook")
        mock_session, _ = make_mock_session(status=200)

        media_items = [
            {'data': b"photo1", 'type': 'photo', 'filename': 'photo1.jpg'},
            {'data': b"photo2", 'type': 'photo', 'filename': 'photo2.jpg'},
        ]

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_multiple_media("Check these photos", media_items)

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_multiple_media_one_too_large(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)
        mock_session, _ = make_mock_session(status=200)

        media_items = [
            {'data': b"photo1", 'type': 'photo', 'filename': 'photo1.jpg'},
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large.jpg'},
            {'data': b"photo2", 'type': 'photo', 'filename': 'photo2.jpg'},
        ]

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_multiple_media("Check these photos", media_items)

        assert result is True  # sends with the 2 valid items

    @pytest.mark.asyncio
    async def test_send_multiple_media_all_too_large_with_text(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)
        mock_session, _ = make_mock_session(status=200)

        media_items = [
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large1.jpg'},
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large2.jpg'},
        ]

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_multiple_media("Text only", media_items)

        assert result is True  # text-only send

    @pytest.mark.asyncio
    async def test_send_multiple_media_all_too_large_no_text(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)
        mock_session, _ = make_mock_session()

        media_items = [
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large1.jpg'},
        ]

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_multiple_media(None, media_items)

        assert result is False
        mock_session.post.assert_not_called()
