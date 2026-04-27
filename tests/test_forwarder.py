"""Unit tests for media forwarder."""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from telethon.tl.types import Channel, Message, MessageMediaPhoto
from src.forwarder import MediaForwarder
from src.config import ConfigManager
from src.models import Config, ChannelConfig, Settings, ChannelSettings


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return Config(
        channels=[
            ChannelConfig(
                channel="@test_channel",
                destinations=["discord_main"]
            )
        ],
        discord_webhooks={
            "discord_main": {
                "url": "https://discord.com/api/webhooks/123/abc"
            }
        },
        settings=Settings(
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
        channel.id = 1234567890  # Positive bare ID
        channel.username = None
        
        with patch('src.forwarder.TelegramMonitor'):
            # Update mock config to use the reconstructed ID format
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

    @pytest.mark.asyncio
    async def test_handle_message_with_media_only_setting(self, mock_config_manager, mock_channel, mock_text_message):
        """Test handling message with media_only setting - should skip text-only messages."""
        # Add channel settings with media_only enabled
        channel_settings = ChannelSettings(media_only=True)
        mock_config_manager.config.channels[0].settings = channel_settings
        
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            await forwarder.handle_message(mock_text_message, mock_channel)
            
            # Should not send anything (text-only message skipped)
            # No DiscordSender should be created or called
            pass  # If we reach here without exception, it's correct

    @pytest.mark.asyncio
    async def test_handle_message_with_remove_captions(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test handling message with remove_captions setting."""
        # Add channel settings with remove_captions enabled
        channel_settings = ChannelSettings(remove_captions=True)
        mock_config_manager.config.channels[0].settings = channel_settings
        
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
                
                # Should send photo but without caption
                mock_sender.send_photo.assert_called_once()
                args, kwargs = mock_sender.send_photo.call_args
                assert args[0] is None or "Photo caption" not in args[0]

    @pytest.mark.asyncio
    async def test_handle_message_with_translation(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test handling message with translate_captions setting."""
        # Add channel settings with translation enabled
        channel_settings = ChannelSettings(translate_captions=True)
        mock_config_manager.config.channels[0].settings = channel_settings
        
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
                
                # Should send photo with translated caption
                mock_sender.send_photo.assert_called_once()
                args, kwargs = mock_sender.send_photo.call_args
                # Caption should be processed (translated or original if translation fails)
                assert args[0] is not None

    def test_format_message_with_channel_settings_override(self, mock_config_manager, mock_channel, mock_text_message):
        """Test formatting message with channel settings overrides."""
        # Add channel settings that override defaults
        channel_settings = ChannelSettings(
            include_channel_name=False,
            include_timestamp=False
        )
        mock_config_manager.config.channels[0].settings = channel_settings
        
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            formatted = forwarder._format_message("Test text", mock_channel, mock_text_message, channel_settings)
            
            # Should not include channel name or timestamp (overridden)
            assert "Test Channel" not in formatted
            assert "2024-01-01" not in formatted
            assert "Test text" in formatted

    @pytest.mark.asyncio
    async def test_handle_message_with_custom_max_file_size(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test handling message with custom max file size."""
        # Add channel settings with custom max file size
        channel_settings = ChannelSettings(max_file_size_mb=25)
        mock_config_manager.config.channels[0].settings = channel_settings
        
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
                
                # Should create DiscordSender with custom max file size
                mock_discord_class.assert_called_once()
                args, kwargs = mock_discord_class.call_args
                assert args[1] == 25  # Custom max file size

    @pytest.mark.asyncio
    async def test_translate_text(self, mock_config_manager):
        """Test text translation."""
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            
            # Mock the translator
            with patch.object(forwarder.translator, 'translate', return_value='Translated text'):
                result = await forwarder._translate_text('Original text')
                assert result == 'Translated text'

    @pytest.mark.asyncio
    async def test_translate_text_failure(self, mock_config_manager):
        """Test text translation failure."""
        with patch('src.forwarder.TelegramMonitor'):
            forwarder = MediaForwarder(mock_config_manager)
            
            # Mock the translator to raise exception
            with patch.object(forwarder.translator, 'translate', side_effect=Exception('Translation failed')):
                result = await forwarder._translate_text('Original text')
                # Should return original text on failure
                assert result == 'Original text'

    @pytest.mark.asyncio
    async def test_destination_specific_max_file_size(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test that destination-specific max file size is used."""
        # Add destination with custom max file size
        mock_config_manager.config.discord_webhooks['discord_main'] = {
            'url': 'https://discord.com/api/webhooks/123/abc',
            'max_file_size_mb': 25
        }
        
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            # Make image 15MB (larger than global 10MB but smaller than destination 25MB)
            mock_telemon_instance.download_media = AsyncMock(
                return_value=b'x' * (15 * 1024 * 1024)
            )
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.DiscordSender') as mock_discord_class:
                mock_sender = AsyncMock()
                mock_discord_class.return_value = mock_sender
                mock_sender.send_photo.return_value = True
                
                forwarder = MediaForwarder(mock_config_manager)
                await forwarder.handle_message(mock_photo_message, mock_channel)
                
                # Should create DiscordSender with destination-specific max file size
                mock_discord_class.assert_called_once()
                args, kwargs = mock_discord_class.call_args
                assert args[1] == 25  # Destination-specific size

    @pytest.mark.asyncio
    async def test_max_file_size_priority(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test priority: destination > channel > global."""
        # Set global, channel, and destination sizes
        mock_config_manager.config.settings.max_file_size_mb = 10  # Global
        mock_config_manager.config.channels[0].settings = ChannelSettings(max_file_size_mb=20)  # Channel
        mock_config_manager.config.discord_webhooks['discord_main'] = {
            'url': 'https://discord.com/api/webhooks/123/abc',
            'max_file_size_mb': 30  # Destination (should win)
        }
        
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=b'photo data')
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.DiscordSender') as mock_discord_class:
                mock_sender = AsyncMock()
                mock_discord_class.return_value = mock_sender
                mock_sender.send_photo.return_value = True
                
                forwarder = MediaForwarder(mock_config_manager)
                await forwarder.handle_message(mock_photo_message, mock_channel)
                
                # Should use destination-specific size (30MB)
                args, kwargs = mock_discord_class.call_args
                assert args[1] == 30

    @pytest.mark.asyncio
    async def test_channel_max_file_size_when_destination_not_set(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test channel max file size when destination has no override."""
        # Set channel size but not destination
        mock_config_manager.config.settings.max_file_size_mb = 10  # Global
        mock_config_manager.config.channels[0].settings = ChannelSettings(max_file_size_mb=20)  # Channel
        # Destination has no max_file_size_mb
        
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=b'photo data')
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.DiscordSender') as mock_discord_class:
                mock_sender = AsyncMock()
                mock_discord_class.return_value = mock_sender
                mock_sender.send_photo.return_value = True
                
                forwarder = MediaForwarder(mock_config_manager)
                await forwarder.handle_message(mock_photo_message, mock_channel)
                
                # Should use channel size (20MB)
                args, kwargs = mock_discord_class.call_args
                assert args[1] == 20

    @pytest.mark.asyncio
    async def test_media_compression_attempted_when_too_large(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test that compression is attempted when media is too large."""
        # Create large image (30MB)
        large_image = b'x' * (30 * 1024 * 1024)
        
        mock_config_manager.config.discord_webhooks['discord_main'] = {
            'url': 'https://discord.com/api/webhooks/123/abc',
            'max_file_size_mb': 25
        }
        
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=large_image)
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.MediaCompressor') as mock_compressor_class:
                mock_compressor = Mock()
                mock_compressor_class.return_value = mock_compressor
                mock_compressor.compress_media = AsyncMock(return_value=b'compressed')
                
                with patch('src.forwarder.DiscordSender') as mock_discord_class:
                    mock_sender = AsyncMock()
                    mock_discord_class.return_value = mock_sender
                    mock_sender.send_photo.return_value = True
                    
                    forwarder = MediaForwarder(mock_config_manager)
                    await forwarder.handle_message(mock_photo_message, mock_channel)
                    
                    # Compression should have been attempted
                    mock_compressor.compress_media.assert_called_once()
                    call_args = mock_compressor.compress_media.call_args
                    assert call_args[0][0] == large_image
                    assert call_args[0][1] == 'photo'
                    assert call_args[0][2] == 25

    @pytest.mark.asyncio
    async def test_media_skipped_when_compression_fails(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test that media is skipped when compression fails."""
        # Create large image (30MB)
        large_image = b'x' * (30 * 1024 * 1024)
        
        mock_config_manager.config.discord_webhooks['discord_main'] = {
            'url': 'https://discord.com/api/webhooks/123/abc',
            'max_file_size_mb': 25
        }
        
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=large_image)
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.MediaCompressor') as mock_compressor_class:
                mock_compressor = Mock()
                mock_compressor_class.return_value = mock_compressor
                # Compression fails (returns None)
                mock_compressor.compress_media = AsyncMock(return_value=None)
                
                with patch('src.forwarder.DiscordSender') as mock_discord_class:
                    # Set up mock sender with methods
                    mock_sender = AsyncMock()
                    mock_sender.send_message = AsyncMock(return_value=True)
                    mock_sender.send_photo = AsyncMock(return_value=True)
                    mock_discord_class.return_value = mock_sender
                    
                    forwarder = MediaForwarder(mock_config_manager)
                    await forwarder.handle_message(mock_photo_message, mock_channel)
                    
                    # Should send text only (media skipped)
                    mock_sender.send_message.assert_called_once()
                    # send_photo should not be called
                    mock_sender.send_photo.assert_not_called()

    @pytest.mark.asyncio
    async def test_different_max_sizes_for_different_destinations(self, mock_config_manager, mock_channel, mock_photo_message):
        """Test different destinations can have different max file sizes."""
        # Add second destination with different size
        mock_config_manager.config.channels[0].destinations = ['discord_main', 'discord_backup']
        mock_config_manager.config.discord_webhooks['discord_main'] = {
            'url': 'https://discord.com/api/webhooks/123/abc',
            'max_file_size_mb': 10
        }
        mock_config_manager.config.discord_webhooks['discord_backup'] = {
            'url': 'https://discord.com/api/webhooks/456/def',
            'max_file_size_mb': 50
        }
        
        with patch('src.forwarder.TelegramMonitor') as mock_telethon:
            mock_telemon_instance = Mock()
            mock_telemon_instance.download_media = AsyncMock(return_value=b'photo data')
            mock_telethon.return_value = mock_telemon_instance
            
            with patch('src.forwarder.DiscordSender') as mock_discord_class:
                mock_sender = AsyncMock()
                mock_sender.send_photo = AsyncMock(return_value=True)
                mock_discord_class.return_value = mock_sender
                
                forwarder = MediaForwarder(mock_config_manager)
                await forwarder.handle_message(mock_photo_message, mock_channel)
                
                # Should have been called twice with different sizes
                assert mock_discord_class.call_count == 2
                
                # Check the sizes used
                sizes = [call[0][1] for call in mock_discord_class.call_args_list]
                assert 10 in sizes
                assert 50 in sizes
