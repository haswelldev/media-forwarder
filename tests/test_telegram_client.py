"""Unit tests for Telegram client."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from telethon.tl.types import Channel, User
from src.telegram_client import TelegramMonitor
from src.config import ConfigManager


def _make_input_peer_channel(channel_id):
    """Create a mock InputPeerChannel with channel_id attribute."""
    entity = Mock()
    entity.channel_id = channel_id
    entity.id = None
    return entity


def _make_channel_event(chat, message_text="Hello", has_media=True):
    """Create a mock NewMessage event."""
    event = Mock()
    event.chat = chat
    event.message = Mock()
    event.message.id = 123
    event.message.text = message_text
    event.message.media = Mock() if has_media else None
    return event


@pytest.fixture
def mock_config_manager():
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


@pytest.fixture
def mock_channel():
    channel = Mock(spec=Channel)
    channel.id = -1001234567890
    channel.username = "test_channel"
    channel.title = "Test Channel"
    return channel


class TestTelegramMonitor:
    """Test Telegram monitor."""

    @pytest.mark.asyncio
    async def test_initialization(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=True)

            monitor = TelegramMonitor(mock_config_manager)
            await monitor.initialize()
            assert monitor.client is not None
            mock_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_unauthorized_session(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=False)

            monitor = TelegramMonitor(mock_config_manager)
            with pytest.raises(Exception, match="not authorized"):
                await monitor.initialize()

    @pytest.mark.asyncio
    async def test_initialize_connection_failure(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock(side_effect=ConnectionError("No network"))

            monitor = TelegramMonitor(mock_config_manager)
            with pytest.raises(ConnectionError, match="No network"):
                await monitor.initialize()

    def test_set_message_callback(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)

            async def dummy_callback(message, chat):
                pass

            monitor.set_message_callback(dummy_callback)
            assert monitor.message_callback == dummy_callback

    @pytest.mark.asyncio
    async def test_start_monitoring(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get_input_entity = AsyncMock(
                return_value=_make_input_peer_channel(1234567890)
            )

            mock_client.on = lambda event: (lambda f: f)

            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            await monitor.start_monitoring()
            mock_client.get_input_entity.assert_called_once_with("@test_channel")

    @pytest.mark.asyncio
    async def test_start_monitoring_with_numeric_channel_id(self, mock_config_manager):
        mock_config_manager.config.channels = [
            Mock(channel="-1001234567890", destinations=["discord_main"])
        ]

        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get_input_entity = AsyncMock(
                return_value=_make_input_peer_channel(1234567890)
            )
            mock_client.on = lambda event: (lambda f: f)

            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            await monitor.start_monitoring()
            mock_client.get_input_entity.assert_called_once_with(-1001234567890)

    @pytest.mark.asyncio
    async def test_start_monitoring_with_inaccessible_channel(self, mock_config_manager):
        mock_config_manager.config.channels = [
            Mock(channel="@accessible_channel", destinations=["discord_main"]),
            Mock(channel="@inaccessible_channel", destinations=["discord_backup"])
        ]

        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            async def get_entity_side_effect(channel):
                if channel == "@accessible_channel":
                    return _make_input_peer_channel(111)
                raise ValueError(f"Cannot find entity for {channel}")

            mock_client.get_input_entity = AsyncMock(side_effect=get_entity_side_effect)
            mock_client.on = lambda event: (lambda f: f)

            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            await monitor.start_monitoring()
            assert mock_client.get_input_entity.call_count == 2

    @pytest.mark.asyncio
    async def test_start_monitoring_all_inaccessible(self, mock_config_manager):
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
            assert not hasattr(monitor, 'monitored_channel_ids') or not monitor.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_start_monitoring_stores_monitored_ids(self, mock_config_manager):
        mock_config_manager.config.channels = [
            Mock(channel="@ch1", destinations=["discord_main"]),
            Mock(channel="@ch2", destinations=["discord_main"]),
        ]

        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            call_count = [0]
            async def get_entity_side_effect(channel):
                call_count[0] += 1
                return _make_input_peer_channel(call_count[0] * 100)

            mock_client.get_input_entity = AsyncMock(side_effect=get_entity_side_effect)
            mock_client.on = lambda event: (lambda f: f)

            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            await monitor.start_monitoring()
            assert monitor.monitored_channel_ids == {100, 200}

    @pytest.mark.asyncio
    async def test_start_monitoring_entity_id_extraction_failure(self, mock_config_manager):
        mock_config_manager.config.channels = [
            Mock(channel="@bad_channel", destinations=["discord_main"])
        ]

        with patch('src.telegram_client.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            bad_entity = Mock(spec=[])
            mock_client.get_input_entity = AsyncMock(return_value=bad_entity)
            mock_client.on = lambda event: (lambda f: f)

            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = mock_client
            await monitor.start_monitoring()
            assert not hasattr(monitor, 'monitored_channel_ids') or not monitor.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_start_monitoring_no_client(self, mock_config_manager):
        monitor = TelegramMonitor(mock_config_manager)
        with pytest.raises(Exception, match="not initialized"):
            await monitor.start_monitoring()

    @pytest.mark.asyncio
    async def test_run_calls_start_monitoring(self, mock_config_manager):
        monitor = TelegramMonitor(mock_config_manager)
        monitor.client = AsyncMock()
        monitor.client.run_until_disconnected = AsyncMock()

        with patch.object(monitor, 'start_monitoring', new_callable=AsyncMock):
            await monitor.run()
            monitor.start_monitoring.assert_called_once()
            monitor.client.run_until_disconnected.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_raises_without_client(self, mock_config_manager):
        monitor = TelegramMonitor(mock_config_manager)
        with pytest.raises(Exception, match="not initialized"):
            await monitor.run()

    @pytest.mark.asyncio
    async def test_download_media_success(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            mock_message = Mock()
            mock_message.media = Mock()
            mock_message.download_media = AsyncMock(return_value=b"test data")

            result = await monitor.download_media(mock_message)
            assert result == b"test data"

    @pytest.mark.asyncio
    async def test_download_media_no_media(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            mock_message = Mock()
            mock_message.media = None

            result = await monitor.download_media(mock_message)
            assert result is None

    @pytest.mark.asyncio
    async def test_download_media_failure(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            mock_message = Mock()
            mock_message.media = Mock()
            mock_message.download_media = AsyncMock(side_effect=Exception("Download failed"))

            result = await monitor.download_media(mock_message)
            assert result is None

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_config_manager):
        with patch('src.telegram_client.TelegramClient'):
            monitor = TelegramMonitor(mock_config_manager)
            monitor.client = AsyncMock()
            await monitor.disconnect()
            monitor.client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_no_client(self, mock_config_manager):
        monitor = TelegramMonitor(mock_config_manager)
        await monitor.disconnect()


# Event Handler Tests (direct testing of handler logic)

@pytest.fixture
def monitor_with_handlers(mock_config_manager):
    monitor = TelegramMonitor(mock_config_manager)
    monitor.client = AsyncMock()
    monitor.monitored_channel_ids = {1234567890, -1001234567890}
    return monitor


def _setup_handlers(monitor):
    """Set up event handlers and return them in a list."""
    handlers = []

    def capture_handler(event_filter):
        def decorator(func):
            handlers.append(func)
            return func
        return decorator

    monitor.client.on = capture_handler
    mock_entity = _make_input_peer_channel(1234567890)
    monitor.client.get_input_entity = AsyncMock(return_value=mock_entity)
    monitor.config.config.channels = [Mock(channel="@test", destinations=["d"])]

    return handlers


@pytest.mark.asyncio
async def test_channel_message_handler_valid(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    channel = Mock(spec=Channel)
    channel.id = 1234567890
    channel.title = "Test"
    channel.username = "test"

    event = _make_channel_event(channel, "Hello world", has_media=True)
    await handlers[0](event)
    callback.assert_called_once()


@pytest.mark.asyncio
async def test_channel_message_handler_no_text_no_media(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    channel = Mock(spec=Channel)
    channel.title = "Test"

    event = Mock()
    event.chat = channel
    event.message = Mock()
    event.message.id = 1
    event.message.text = None
    event.message.media = None

    await handlers[0](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_channel_message_handler_non_channel_filtered(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    event = Mock()
    event.chat = "not_a_channel"
    event.message = Mock()
    event.message.id = 1
    event.message.text = "Hello"
    event.message.media = None

    await handlers[0](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_channel_message_handler_callback_exception(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock(side_effect=RuntimeError("callback error"))
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    channel = Mock(spec=Channel)
    channel.title = "Test"

    event = _make_channel_event(channel, "Hello", has_media=True)
    await handlers[0](event)
    callback.assert_called()


@pytest.mark.asyncio
async def test_private_message_handler_from_monitored_channel(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    user_chat = Mock(spec=User)
    user_chat.id = 999

    forward_channel = Mock(spec=Channel)
    forward_channel.id = 1234567890
    forward_channel.title = "Forwarded Channel"

    event = Mock()
    event.chat = user_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = "Forwarded text"
    event.message.media = None
    event.message.forward = Mock()
    event.message.forward.from_ = forward_channel

    await handlers[1](event)
    callback.assert_called_once()
    assert callback.call_args[0][1] == forward_channel


@pytest.mark.asyncio
async def test_private_message_handler_from_unmonitored_channel(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    user_chat = Mock(spec=User)
    forward_channel = Mock(spec=Channel)
    forward_channel.id = 9999999
    forward_channel.title = "Unmonitored"

    event = Mock()
    event.chat = user_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = "Forwarded text"
    event.message.media = None
    event.message.forward = Mock()
    event.message.forward.from_ = forward_channel

    await handlers[1](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_private_message_handler_not_forwarded(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    user_chat = Mock(spec=User)
    event = Mock()
    event.chat = user_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = "Not forwarded"
    event.message.media = None
    event.message.forward = None

    await handlers[1](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_private_message_handler_from_channel_chat(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    channel_chat = Mock(spec=Channel)
    event = Mock()
    event.chat = channel_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = "Direct channel msg"
    event.message.media = None

    await handlers[1](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_private_message_handler_forward_from_user(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    user_chat = Mock(spec=User)
    forward_user = Mock(spec=User)

    event = Mock()
    event.chat = user_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = "Forwarded from user"
    event.message.media = None
    event.message.forward = Mock()
    event.message.forward.from_ = forward_user

    await handlers[1](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_private_message_handler_no_text_no_media(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock()
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    user_chat = Mock(spec=User)
    event = Mock()
    event.chat = user_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = None
    event.message.media = None
    event.message.forward = Mock()
    event.message.forward.from_ = Mock(spec=Channel)

    await handlers[1](event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_private_message_handler_callback_exception(monitor_with_handlers):
    monitor = monitor_with_handlers
    callback = AsyncMock(side_effect=RuntimeError("callback error"))
    monitor.message_callback = callback

    handlers = _setup_handlers(monitor)
    await monitor.start_monitoring()

    user_chat = Mock(spec=User)
    forward_channel = Mock(spec=Channel)
    forward_channel.id = 1234567890
    forward_channel.title = "Forwarded Channel"

    event = Mock()
    event.chat = user_chat
    event.message = Mock()
    event.message.id = 456
    event.message.text = "Forwarded text"
    event.message.media = None
    event.message.forward = Mock()
    event.message.forward.from_ = forward_channel

    await handlers[1](event)
    callback.assert_called()
