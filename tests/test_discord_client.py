"""Unit tests for Discord client."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.discord_client import DiscordSender, get_shared_session, close_shared_session


@pytest.fixture(autouse=True)
async def cleanup_session():
    """Clean up shared session after each test."""
    yield
    await close_shared_session()


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


class TestDiscordSenderSendMessage:
    """Test send_message method."""

    @pytest.mark.asyncio
    async def test_send_text_only(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Hello Discord")

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_only(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        media_data = b"fake image data"

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(media_data=media_data, filename="test.jpg")

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_text_and_media(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                text="Check this out",
                media_data=b"data",
                filename="test.jpg"
            )

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_file_too_large_with_text(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        # 2MB file > 1MB limit
        large_file = b"x" * (2 * 1024 * 1024)

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                text="Text only",
                media_data=large_file,
                filename="large.jpg"
            )

        assert result is False
        # Should still send text only
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_file_too_large_no_text(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock()
        mock_session.closed = False

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

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_no_content(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_session = AsyncMock()
        mock_session.post = AsyncMock()
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message()

        assert result is False
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_http_error(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(side_effect=Exception("Connection error"))
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_photo_logging(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                media_data=b"data",
                filename="test.JPG"
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_video_logging(self):
        sender = DiscordSender("https://discord.com/webhook")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(
                media_data=b"data",
                filename="test.mp4"
            )

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

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

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

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        media_items = [
            {'data': b"photo1", 'type': 'photo', 'filename': 'photo1.jpg'},
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large.jpg'},  # 2MB
            {'data': b"photo2", 'type': 'photo', 'filename': 'photo2.jpg'},
        ]

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_multiple_media("Check these photos", media_items)

        assert result is True
        # Should still send, but with only 2 files (the large one is skipped)

    @pytest.mark.asyncio
    async def test_send_multiple_media_all_too_large_with_text(self):
        sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        media_items = [
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large1.jpg'},
            {'data': b"x" * (2 * 1024 * 1024), 'type': 'photo', 'filename': 'large2.jpg'},
        ]

        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_multiple_media("Text only", media_items)

        assert result is True
        # Should still send, with text only (all media skipped)
