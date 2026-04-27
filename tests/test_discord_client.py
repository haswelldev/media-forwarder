"""Unit tests for Discord client."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from aiohttp import ClientError
from src.discord_client import DiscordSender


class TestDiscordSender:
    """Test Discord sender."""

    @pytest.fixture
    def sender(self):
        """Create a Discord sender instance."""
        return DiscordSender(
            webhook_url="https://discord.com/api/webhooks/123/abc",
            max_file_size_mb=10
        )

    def test_initialization(self):
        """Test sender initialization."""
        sender = DiscordSender(
            webhook_url="https://discord.com/api/webhooks/123/abc",
            max_file_size_mb=25
        )
        assert sender.webhook_url == "https://discord.com/api/webhooks/123/abc"
        assert sender.max_file_size_mb == 25
        assert sender.max_file_size_bytes == 25 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_send_text_only(self, sender):
        """Test sending text only."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.release = AsyncMock()
        mock_session.post.return_value = mock_response
        
        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Test message")
            
            assert result is True
            mock_session.post.assert_called_once()
            # Check the call was made with data parameter
            call_args = mock_session.post.call_args
            assert call_args[0][0] == "https://discord.com/api/webhooks/123/abc"

    @pytest.mark.asyncio
    async def test_send_empty_message(self, sender):
        """Test sending empty message."""
        result = await sender.send_message()
        assert result is False

    @pytest.mark.asyncio
    async def test_send_with_valid_media(self, sender):
        """Test sending message with valid media."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.release = AsyncMock()
        mock_session.post.return_value = mock_response
        
        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            media_data = b"fake image data" * 1000  # Small enough to pass size check
            
            result = await sender.send_message(text="Test", media_data=media_data, filename="test.jpg")
            
            assert result is True
            mock_session.post.assert_called_once()
            # Check the call was made
            assert mock_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_with_oversized_media(self, sender):
        """Test sending message with oversized media."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.release = AsyncMock()
        mock_session.post.return_value = mock_response
        
        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            # Create data larger than 10MB
            media_data = b"x" * (11 * 1024 * 1024)
            
            result = await sender.send_message(text="Test", media_data=media_data, filename="test.jpg")
            
            assert result is False
            # Should have been called with text (FormData) not JSON
            assert mock_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_with_oversized_media_no_text(self, sender):
        """Test sending oversized media without text."""
        with patch('src.discord_client.get_shared_session', return_value=AsyncMock()):
            # Create data larger than 10MB
            media_data = b"x" * (11 * 1024 * 1024)
            
            result = await sender.send_message(media_data=media_data, filename="test.jpg")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_discord_http_error(self, sender):
        """Test handling Discord HTTP error."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.release = AsyncMock()
        mock_session.post.return_value = mock_response
        
        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Test message")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_generic_exception(self, sender):
        """Test handling generic exception."""
        mock_session = AsyncMock()
        mock_session.post.side_effect = ClientError("Connection error")
        
        with patch('src.discord_client.get_shared_session', return_value=mock_session):
            result = await sender.send_message(text="Test message")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_send_photo(self, sender):
        """Test sending photo."""
        with patch.object(sender, 'send_message', new_callable=AsyncMock) as mock_send_message:
            mock_send_message.return_value = True
            photo_data = b"photo data"
            
            result = await sender.send_photo(text="Photo caption", photo_data=photo_data)
            
            assert result is True
            mock_send_message.assert_called_once_with("Photo caption", photo_data, "photo.jpg")

    @pytest.mark.asyncio
    async def test_send_video(self, sender):
        """Test sending video."""
        with patch.object(sender, 'send_message', new_callable=AsyncMock) as mock_send_message:
            mock_send_message.return_value = True
            video_data = b"video data"
            
            result = await sender.send_video(text="Video caption", video_data=video_data, filename="video.mp4")
            
            assert result is True
            mock_send_message.assert_called_once_with("Video caption", video_data, "video.mp4")

    @pytest.mark.asyncio
    async def test_send_document(self, sender):
        """Test sending document."""
        with patch.object(sender, 'send_message', new_callable=AsyncMock) as mock_send_message:
            mock_send_message.return_value = True
            doc_data = b"document data"
            
            result = await sender.send_document(text="Document", document_data=doc_data, filename="file.pdf")
            
            assert result is True
            mock_send_message.assert_called_once_with("Document", doc_data, "file.pdf")

    @pytest.mark.asyncio
    async def test_close_session(self, sender):
        """Test closing shared session."""
        from src.discord_client import _shared_session, close_shared_session
        import src.discord_client as dc
        
        # Set up a mock session
        mock_session = AsyncMock()
        dc._shared_session = mock_session
        mock_session.closed = False
        
        # Close it
        await close_shared_session()
        
        mock_session.close.assert_called_once()
        
        mock_session.close.assert_called_once()
