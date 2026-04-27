"""Unit tests for Telegram client."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Message
from src.telegram_client import TelegramMonitor
from src.config import ConfigManager


class TestTelegramMonitor:
    """Test Telegram monitor."""

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock configuration manager."""
        manager = Mock(spec=ConfigManager)
        manager.config = Mock()
        manager.config.channels = [
            Mock(channel="@test_channel", destinations=["discord_main"])
        ]
        manager.config.settings = Mock(
            max_file_size_mb=10,
            log_level="INFO"
        )
        return manager

    @pytest.mark.asyncio
    async def test_initialization(self, mock_config_manager):
        """Test monitor initialization."""
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=True)
            
            monitor = TelegramMonitor(mock_config_manager)
            await monitor.initialize()
            assert monitor.client is not None
            mock_client.connect.assert_called_once()

    def test_set_message_callback(self, mock_config_manager):
        """Test setting message callback."""
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            
            async def dummy_callback(message, chat):
                pass
            
            monitor.set_message_callback(dummy_callback)
            assert monitor.message_callback == dummy_callback

    @pytest.mark.asyncio
    async def test_start_monitoring(self, mock_config_manager):
        """Test starting monitoring."""
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_entity = Mock()
            mock_client.get_input_entity = AsyncMock(return_value=mock_entity)
            
            # Mock the on() method to return the decorator
            def mock_on(event):
                def decorator(func):
                    return func
                return decorator
            mock_client.on = mock_on
            
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            
            await monitor.start_monitoring()
            
            # Verify channel was resolved
            mock_client.get_input_entity.assert_called_once_with("@test_channel")

    @pytest.mark.asyncio
    async def test_start_monitoring_with_inaccessible_channel(self, mock_config_manager):
        """Test starting monitoring with inaccessible channel."""
        # Add an inaccessible channel
        mock_config_manager.config.channels = [
            Mock(channel="@accessible_channel", destinations=["discord_main"]),
            Mock(channel="@inaccessible_channel", destinations=["discord_backup"])
        ]
        
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_entity = Mock()
            
            # Make second channel inaccessible
            async def get_input_entity_side_effect(channel):
                if channel == "@accessible_channel":
                    return mock_entity
                else:
                    raise ValueError(f"Cannot find entity for {channel}")
            
            mock_client.get_input_entity = AsyncMock(side_effect=get_input_entity_side_effect)
            
            # Mock the on() method to return the decorator
            def mock_on(event):
                def decorator(func):
                    return func
                return decorator
            mock_client.on = mock_on
            
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            
            await monitor.start_monitoring()
            
            # Verify only accessible channel was added
            assert mock_client.get_input_entity.call_count == 2
            # Should not raise exception, just log warning

    @pytest.mark.asyncio
    async def test_start_monitoring_all_inaccessible(self, mock_config_manager):
        """Test starting monitoring when all channels are inaccessible."""
        mock_config_manager.config.channels = [
            Mock(channel="@inaccessible_channel", destinations=["discord_main"])
        ]
        
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get_input_entity = AsyncMock(
                side_effect=ValueError("Cannot find entity")
            )
            
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            
            await monitor.start_monitoring()
            
            # Should handle gracefully without crashing
            assert mock_client.get_input_entity.called

    @pytest.mark.asyncio
    async def test_download_media(self, mock_config_manager):
        """Test downloading media."""
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = AsyncMock()
            
            mock_message = Mock()
            mock_message.download_media = AsyncMock(return_value=b"test data")
            
            result = await monitor.download_media(mock_message)
            
            assert result == b"test data"
            mock_message.download_media.assert_called_once_with(file=bytes)

    @pytest.mark.asyncio
    async def test_download_media_failure(self, mock_config_manager):
        """Test download media failure."""
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = AsyncMock()
            
            mock_message = Mock()
            mock_message.download_media = AsyncMock(side_effect=Exception("Download failed"))
            
            result = await monitor.download_media(mock_message)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_config_manager):
        """Test disconnecting."""
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = AsyncMock()
            
            await monitor.disconnect()
            
            monitor.client.disconnect.assert_called_once()
