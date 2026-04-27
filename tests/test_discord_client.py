"""Unit tests for Discord client."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.discord_client import DiscordSender
from discord.errors import HTTPException


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

    def test_send_text_only(self, sender):
        """Test sending text only."""
        with patch('src.discord_client.discord.Webhook') as mock_webhook_class:
            mock_webhook = MagicMock()
            mock_webhook_class.from_url.return_value = mock_webhook
            
            result = sender.send_message(text="Test message")
            
            assert result is True
            mock_webhook.send.assert_called_once_with(content="Test message")

    def test_send_empty_message(self, sender):
        """Test sending empty message."""
        result = sender.send_message()
        assert result is False

    @patch('src.discord_client.discord.Webhook')
    def test_send_with_valid_media(self, mock_webhook_class, sender):
        """Test sending message with valid media."""
        mock_webhook = MagicMock()
        mock_webhook_class.from_url.return_value = mock_webhook
        
        media_data = b"fake image data" * 1000  # Small enough to pass size check
        
        result = sender.send_message(text="Test", media_data=media_data, filename="test.jpg")
        
        assert result is True
        mock_webhook.send.assert_called_once()
        args, kwargs = mock_webhook.send.call_args
        assert 'file' in kwargs
        assert kwargs['content'] == "Test"

    @patch('src.discord_client.discord.Webhook')
    def test_send_with_oversized_media(self, mock_webhook_class, sender):
        """Test sending message with oversized media."""
        mock_webhook = MagicMock()
        mock_webhook_class.from_url.return_value = mock_webhook
        
        # Create data larger than 10MB
        media_data = b"x" * (11 * 1024 * 1024)
        
        result = sender.send_message(text="Test", media_data=media_data, filename="test.jpg")
        
        assert result is False
        # Should send text only
        mock_webhook.send.assert_called_once_with(content="Test")

    @patch('src.discord_client.discord.Webhook')
    def test_send_with_oversized_media_no_text(self, mock_webhook_class, sender):
        """Test sending oversized media without text."""
        mock_webhook = MagicMock()
        mock_webhook_class.from_url.return_value = mock_webhook
        
        media_data = b"x" * (11 * 1024 * 1024)
        
        result = sender.send_message(media_data=media_data, filename="test.jpg")
        
        assert result is False
        # Should not send anything
        mock_webhook.send.assert_not_called()

    @patch('src.discord_client.discord.Webhook')
    def test_discord_http_error(self, mock_webhook_class, sender):
        """Test handling Discord HTTP error."""
        mock_webhook = MagicMock()
        mock_webhook_class.from_url.return_value = mock_webhook
        mock_webhook.send.side_effect = HTTPException(response=Mock(), message="Rate limited")
        
        result = sender.send_message(text="Test message")
        
        assert result is False

    @patch('src.discord_client.discord.Webhook')
    def test_generic_exception(self, mock_webhook_class, sender):
        """Test handling generic exception."""
        mock_webhook_class.from_url.side_effect = Exception("Connection error")
        
        result = sender.send_message(text="Test message")
        
        assert result is False

    @patch('src.discord_client.DiscordSender.send_message')
    def test_send_photo(self, mock_send_message, sender):
        """Test sending photo."""
        photo_data = b"photo data"
        mock_send_message.return_value = True
        
        result = sender.send_photo(text="Photo caption", photo_data=photo_data)
        
        assert result is True
        mock_send_message.assert_called_once_with("Photo caption", photo_data, "photo.jpg")

    @patch('src.discord_client.DiscordSender.send_message')
    def test_send_video(self, mock_send_message, sender):
        """Test sending video."""
        video_data = b"video data"
        mock_send_message.return_value = True
        
        result = sender.send_video(text="Video caption", video_data=video_data, filename="video.mp4")
        
        assert result is True
        mock_send_message.assert_called_once_with("Video caption", video_data, "video.mp4")

    @patch('src.discord_client.DiscordSender.send_message')
    def test_send_document(self, mock_send_message, sender):
        """Test sending document."""
        doc_data = b"document data"
        mock_send_message.return_value = True
        
        result = sender.send_document(text="Document", document_data=doc_data, filename="file.pdf")
        
        assert result is True
        mock_send_message.assert_called_once_with("Document", doc_data, "file.pdf")
