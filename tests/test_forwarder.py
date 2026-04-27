"""Unit tests for media forwarder."""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from telethon.tl.types import Channel, Message, MessageMediaPhoto
from src.forwarder import MediaForwarder
from src.config import ConfigManager
from src.models import Config


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return Config(
        channels=[
            Mock(
                channel="@test_channel",
                destinations=["discord_main"]
            )
        ],
        discord_webhooks={
            "discord_main": {
                "url": "https://discord.com/api/webhooks/123/abc"
            }
        },
        settings=Mock(
            max_file_size_mb=10,
            log_level="INFO",
            include_channel_name=True,
            include_timestamp=True
        )
    )


@pytest.fixture
def mock_config_manager(mock_config):
    """Create a mock configuration manager."""
    manager = Mock(spec=ConfigManager)
    manager.config = mock_config
    manager.telegram_api_id = 12345
    manager.telegram_api_hash = "test_hash"
    manager.telegram_session_name = "test_session"
    manager.get_webhook_url = Mock(return_value="https://discord.com/api/webhooks/123/abc")
    return manager


@pytest.fixture
def mock_channel():
    """Create a mock Telegram channel."""
    channel = Mock(spec=Channel)
    channel.id = -1001234567890
    channel.username = "test_channel"
    channel.title = "Test Channel"
    return channel


@pytest.fixture
def mock_text_message(mock_channel):
    """Create a mock text message."""
    message = Mock(spec=Message)
    message.id = 1
    message.text = "Test message"
    message.message = None
    message.media = None
    message.photo = None
    message.video = None
    message.document = None
    message.date = datetime(2024, 1, 1, 12, 0, 0)
    return message


@pytest.fixture
def mock_photo_message(mock_channel):
    """Create a mock photo message."""
    message = Mock(spec=Message)
    message.id = 2
    message.text = "Photo caption"
    message.message = None
    message.media = Mock(spec=MessageMediaPhoto)
    message.photo = Mock()
    message.video = None
    message.document = None
    message.date = datetime(2024, 1, 1, 12, 0, 0)
    return message


class TestMediaForwarder:
    """Test media forwarder."""

    @pytest.mark.asyncio
    async def test_initialization(self, mock_config_manager):
        """Test forwarder initialization."""
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            assert forwarder.config == mock_config_manager
            assert forwarder.telegram is not None

    def test_get_channel_config_by_username(self, mock_config_manager, mock_channel):
        """Test getting channel config by username."""
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            config = forwarder._get_channel_config(mock_channel)
            assert config is not None
            assert config.channel == "@test_channel"

    def test_get_channel_config_by_id(self, mock_config_manager):
        """Test getting channel config by numeric ID."""
        channel = Mock(spec=Channel)
        channel.id = -1001234567890
        channel.username = None
        
        with patch('src.forwarder.TelegramMonitor'):
            # Update mock config to use numeric ID
            mock_config_manager.config.channels[0].channel = "-1001234567890"
            forwarder = MediaForwarder(mock_config_manager)
            config = forwarder._get_channel_config(channel)
            assert config is not None

    def test_get_channel_config_not_found(self, mock_config_manager, mock_channel):
        """Test getting config for non-existent channel."""
        with patch('src.forwarder.TelegramMonitor'):
            mock_config_manager.config.channels = []
            forwarder = MediaForwarder(mock_config_manager)
            config = forwarder._get_channel_config(mock_channel)
            assert config is None

    def test_format_message_with_all_features(self, mock_config_manager, mock_channel, mock_text_message):
        """Test formatting message with all features enabled."""
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            formatted = forwarder._format_message("Test text", mock_channel, mock_text_message)
            
            assert "Test Channel" in formatted
            assert "2024-01-01 12:00:00" in formatted
            assert "Test text" in formatted
            assert "---" in formatted

    def test_format_message_without_channel_name(self, mock_config_manager, mock_channel, mock_text_message):
        """Test formatting message without channel name."""
        mock_config_manager.config.settings.include_channel_name = False
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            formatted = forwarder._format_message("Test text", mock_channel, mock_text_message)
            
            assert "Test Channel" not in formatted
            assert "2024-01-01 12:00:00" in formatted
            assert "Test text" in formatted

    def test_format_message_without_timestamp(self, mock_config_manager, mock_channel, mock_text_message):
        """Test formatting message without timestamp."""
        mock_config_manager.config.settings.include_timestamp = False
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            formatted = forwarder._format_message("Test text", mock_channel, mock_text_message)
            
            assert "Test Channel" in formatted
            assert "2024-01-01 12:00:00" not in formatted
            assert "Test text" in formatted

    def test_format_message_empty_text(self, mock_config_manager, mock_channel, mock_text_message):
        """Test formatting message with empty text."""
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            formatted = forwarder._format_message("", mock_channel, mock_text_message)
            
            # Should still include metadata
            assert "Test Channel" in formatted or "2024-01-01 12:00:00" in formatted

    def test_format_message_no_features(self, mock_config_manager, mock_channel, mock_text_message):
        """Test formatting message with all features disabled."""
        mock_config_manager.config.settings.include_channel_name = False
        mock_config_manager.config.settings.include_timestamp = False
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            formatted = forwarder._format_message("Test text", mock_channel, mock_text_message)
            
            assert formatted == "Test text"

    @pytest.mark.asyncio
    async def test_handle_text_message(self, mock_config_manager, mock_channel, mock_text_message):
        """Test handling text message."""
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telegram_instance = AsyncMock()
            mock_telethon.return_value = mock_telegram_instance
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=None)
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.DiscordSender') as mock_discord_class:
                mock_sender = AsyncMock()
                mock_discord_class.return_value = mock_sender
                mock_sender.send_message.return_value = True
                
                forwarder = MediaForwarder(mock_config_manager)
                await forwarder.handle_message(mock_text_message, mock_channel)
                
                # Should send text only
                mock_sender.send_message.assert_called_once()
                args, kwargs = mock_sender.send_message.call_args
                assert "Test message" in args[0]

    @pytest.mark.asyncio
    async def test_handle_photo_message(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test handling photo message."""
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=b"photo data")
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.DiscordSender') as mock_discord_class:
                mock_sender = AsyncMock()
                mock_discord_class.return_value = mock_sender
                mock_sender.send_photo.return_value = True
                
                forwarder = MediaForwarder(mock_config_manager)
                await forwarder.handle_message(mock_photo_message, mock_channel)
                
                # Should download and send photo
                mock_telemon_instance.download_media.assert_called_once()
                mock_sender.send_photo.assert_called_once()
                args, kwargs = mock_sender.send_photo.call_args
                assert "Photo caption" in args[0]
                assert args[1] == b"photo data"

    @pytest.mark.asyncio
    async def test_handle_message_channel_not_found(self, mock_config_manager, mock_channel, mock_text_message):
        """Test handling message when channel config is not found."""
        with patch('src.forwarder.TelegramMonitor'):
            mock_config_manager.config.channels = []
            forwarder = MediaForwarder(mock_config_manager)
            
            # Should not raise exception, just log warning
            await forwarder.handle_message(mock_text_message, mock_channel)
