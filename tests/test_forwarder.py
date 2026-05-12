"""Unit tests for forwarder module."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from telethon.tl.types import Channel, Message, MessageMediaPhoto, MessageMediaDocument
from src.forwarder import MediaForwarder
from src.config import ConfigManager


@pytest.fixture
def mock_config_manager():
    manager = Mock(spec=ConfigManager)
    manager.config = Mock()
    manager.config.channels = [
        Mock(channel="@test_channel", destinations=["discord_main"], settings=None)
    ]
    manager.config.discord_webhooks = {
        "discord_main": Mock(url="https://discord.com/webhook1", max_file_size_mb=10)
    }
    manager.config.settings = Mock(
        max_file_size_mb=10,
        include_channel_name=True,
        include_timestamp=True,
        log_level="INFO",
        group_timeout_seconds=3.0,
    )
    return manager


@pytest.fixture
def mock_channel():
    channel = Mock(spec=Channel)
    channel.id = 1234567890
    channel.username = "test_channel"
    channel.title = "Test Channel"
    return channel


@pytest.fixture
def mock_message():
    message = Mock(spec=Message)
    message.id = 123
    message.text = "Hello world"
    message.message = "Hello world"
    message.photo = None
    message.video = None
    message.document = None
    message.media = None
    message.grouped_id = None
    message.date = datetime(2024, 1, 15, 10, 30, 0)
    return message


@pytest.fixture
def forwarder(mock_config_manager):
    with patch('src.forwarder.TelegramMonitor') as mock_tg_class, \
         patch('src.forwarder.MediaCompressor') as mock_compressor_class:

        mock_tg = AsyncMock()
        mock_tg_class.return_value = mock_tg

        mock_compressor = AsyncMock()
        mock_compressor_class.return_value = mock_compressor

        fwd = MediaForwarder(mock_config_manager)
        fwd.telegram = mock_tg
        # Inject translator mock via the private backing attribute
        mock_translator = Mock()
        mock_translator.translate = Mock(return_value="translated")
        fwd._translator = mock_translator
        fwd.compressor = mock_compressor

        return fwd


class TestMediaForwarderInit:
    """Test MediaForwarder initialization."""
    
    def test_init(self, mock_config_manager):
        with patch('src.forwarder.TelegramMonitor') as mock_tg, \
             patch('src.forwarder.MediaCompressor'):

            fwd = MediaForwarder(mock_config_manager)
            assert fwd.config == mock_config_manager
            mock_tg.assert_called_once_with(mock_config_manager)
            assert fwd._translator is None  # lazy — not created yet
            assert fwd.group_timeout == 3.0


class TestInitialize:
    """Test initialize method."""

    @pytest.mark.asyncio
    async def test_initialize(self, forwarder):
        await forwarder.initialize()
        forwarder.telegram.initialize.assert_called_once()
        forwarder.telegram.set_message_callback.assert_called_once()
        assert forwarder.telegram.set_message_callback.call_args[0][0] == forwarder.handle_message
        assert forwarder._cleanup_task is not None
        # Clean up the background task so it doesn't linger
        forwarder._cleanup_task.cancel()


class TestGetChannelConfig:
    """Test _get_channel_config method."""
    
    def test_get_config_by_username(self, forwarder, mock_channel):
        mock_channel.username = "test_channel"
        mock_channel.id = 1234567890
        
        config = forwarder._get_channel_config(mock_channel)
        assert config is not None
        assert config.channel == "@test_channel"
    
    def test_get_config_by_id(self, forwarder, mock_channel):
        mock_channel.username = None
        mock_channel.id = 1234567890
        
        forwarder.config.config.channels = [
            Mock(channel="-1001234567890", destinations=["discord_main"], settings=None)
        ]
        
        config = forwarder._get_channel_config(mock_channel)
        assert config is not None
        assert config.channel == "-1001234567890"
    
    def test_get_config_not_found(self, forwarder, mock_channel):
        mock_channel.username = "unknown_channel"
        mock_channel.id = 9999999999
        
        config = forwarder._get_channel_config(mock_channel)
        assert config is None


class TestFormatMessage:
    """Test _format_message method."""
    
    def test_format_with_channel_name_and_timestamp(self, forwarder, mock_channel, mock_message):
        result = forwarder._format_message("Hello", mock_channel, mock_message)
        assert "**From:** Test Channel" in result
        assert "**Time:**" in result
        assert "Hello" in result
    
    def test_format_without_channel_name(self, forwarder, mock_channel, mock_message):
        forwarder.config.config.settings.include_channel_name = False
        
        result = forwarder._format_message("Hello", mock_channel, mock_message)
        assert "**From:**" not in result
        assert "Hello" in result
    
    def test_format_without_timestamp(self, forwarder, mock_channel, mock_message):
        forwarder.config.config.settings.include_timestamp = False
        
        result = forwarder._format_message("Hello", mock_channel, mock_message)
        assert "**Time:**" not in result
        assert "Hello" in result
    
    def test_format_no_text(self, forwarder, mock_channel, mock_message):
        result = forwarder._format_message(None, mock_channel, mock_message)
        # When text is None but channel name and timestamp are enabled, it still formats those
        assert "**From:**" in result
        assert "**Time:**" in result
    
    def test_format_with_channel_settings_override(self, forwarder, mock_channel, mock_message):
        channel_settings = Mock()
        channel_settings.include_channel_name = False
        channel_settings.include_timestamp = False
        
        result = forwarder._format_message("Hello", mock_channel, mock_message, channel_settings)
        assert "**From:**" not in result
        assert "**Time:**" not in result
        assert "Hello" in result


class TestTranslateText:
    """Test _translate_text method."""
    
    @pytest.mark.asyncio
    async def test_translate_failure(self, forwarder):
        forwarder.translator.translate.return_value = "Hola mundo"

        result = await forwarder._translate_text("Hello world")
        assert result == "Hello world"
        forwarder.translator.translate.assert_called_once_with("Hello world")

    class TestTruncateForDiscord:
        """Test _truncate_for_discord static method."""

        def test_at_limit(self):
            text = "A" * 2000
            result = MediaForwarder._truncate_for_discord(text, limit=2000)
            assert result == text
            assert len(result) == 2000

        def test_over_limit(self):
            text = "B" * 2000
            result = MediaForwarder._truncate_for_discord(text, limit=1000)
            expected = "B" * 997 + "..."
            assert result == expected
            assert len(result) == 1000

        def test_empty_string(self):
            result = MediaForwarder._truncate_for_discord("", limit=2000)
            assert result == ""
            assert len(result) == 0

        def test_none_input(self):
            result = MediaForwarder._truncate_for_discord(None, limit=2000)
            assert result is None

    class TestDownloadMedia:
        """Test _download_media helper method."""

        @pytest.mark.asyncio
        async def test_small_file_returns_bytes(self, forwarder):
            """Small files should be downloaded to bytes, not temp file."""
            forwarder.telegram.download_media = AsyncMock(return_value=b"small_data")
            forwarder.telegram.download_media_to_file = AsyncMock(return_value=None)

            data, temp_path = await forwarder._download_media(Mock())
            assert data == b"small_data"
            assert temp_path is None

        @pytest.mark.asyncio
        async def test_large_file_returns_temp_path(self, forwarder):
            """Large files (>50MB) should use temp file, not bytes."""
            forwarder.telegram.download_media = AsyncMock(return_value=None)

            temp_path = "/tmp/test_media_123.bin"
            forwarder.telegram.download_media_to_file = AsyncMock(return_value=temp_path)

            data, path = await forwarder._download_media(Mock())
            assert data is None
            assert path == temp_path

        @pytest.mark.asyncio
        async def test_download_returns_none_on_both_fail(self, forwarder):
            """If both downloads fail, should return (None, None)."""
            forwarder.telegram.download_media = AsyncMock(return_value=None)
            forwarder.telegram.download_media_to_file = AsyncMock(return_value=None)

            data, path = await forwarder._download_media(Mock())
            assert data is None
            assert path is None

    class TestDiscordClientSendFile:
        """Test DiscordSender.send_file method for streaming large files."""

        @pytest.mark.asyncio
        async def test_send_file_success(self):
            """Successfully send file from disk."""
            import tempfile
            from src.discord_client import DiscordSender

            mock_session = Mock()
            mock_response = Mock()
            mock_response.status = 200
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = Mock(return_value=mock_cm)
            mock_session.closed = False

            with patch('src.discord_client.get_shared_session', return_value=mock_session):
                sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=10)

                with tempfile.NamedTemporaryFile(delete=False) as temp_f:
                    temp_f.write(b"test data")
                    temp_f.flush()
                    result = await sender.send_file("text", temp_f.name, "test.bin")

            assert result is True

        @pytest.mark.asyncio
        async def test_send_file_too_large_with_text_fallback(self):
            """File too large should send text-only fallback."""
            import tempfile
            from src.discord_client import DiscordSender

            mock_session = Mock()
            mock_response = Mock()
            mock_response.status = 200
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = Mock(return_value=mock_cm)
            mock_session.closed = False

            with patch('src.discord_client.get_shared_session', return_value=mock_session):
                sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)

                large_file = tempfile.NamedTemporaryFile(delete=False)
                large_file.write(b"x" * (2 * 1024 * 1024))
                large_file.flush()

                result = await sender.send_file("fallback text", large_file.name, "large.bin")

            assert result is True
            mock_session.post.assert_called_once()

        @pytest.mark.asyncio
        async def test_send_file_too_large_no_text(self):
            """File too large with no text should return False."""
            import tempfile
            from src.discord_client import DiscordSender

            mock_session = Mock()
            mock_session.closed = False

            with patch('src.discord_client.get_shared_session', return_value=mock_session):
                sender = DiscordSender("https://discord.com/webhook", max_file_size_mb=1)

                large_file = tempfile.NamedTemporaryFile(delete=False)
                large_file.write(b"x" * (2 * 1024 * 1024))
                large_file.flush()

                result = await sender.send_file(None, large_file.name, "large.bin")

            assert result is False
            mock_session.post.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_translate_failure(self, forwarder):
        forwarder.translator.translate.side_effect = Exception("Translation error")
        
        result = await forwarder._translate_text("Hello world")
        assert result == "Hello world"  # Returns original text


class TestHandleMessage:
    """Test handle_message method."""
    
    @pytest.mark.asyncio
    async def test_handle_message_no_config(self, forwarder, mock_channel, mock_message):
        forwarder.config.config.channels = []
        
        await forwarder.handle_message(mock_message, mock_channel)
        # Should log warning and return
        forwarder.telegram.download_media.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_text_only(self, forwarder, mock_channel, mock_message):
        mock_message.text = "Hello"
        mock_message.message = "Hello"
        mock_message.media = None
        
        with patch.object(forwarder, '_forward_to_destination', new_callable=AsyncMock) as mock_forward:
            await forwarder.handle_message(mock_message, mock_channel)
            mock_forward.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_message_photo(self, forwarder, mock_channel, mock_message):
        mock_message.photo = Mock()
        mock_message.media = Mock(spec=MessageMediaPhoto)
        
        forwarder.telegram.download_media = AsyncMock(return_value=b"photo_data")
        
        with patch.object(forwarder, '_forward_to_destination', new_callable=AsyncMock) as mock_forward:
            await forwarder.handle_message(mock_message, mock_channel)
            forwarder.telegram.download_media.assert_called_once()
            mock_forward.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_message_video(self, forwarder, mock_channel, mock_message):
        mock_message.video = Mock()
        mock_message.media = Mock(spec=MessageMediaDocument)
        mock_message.video.attributes = []
        
        forwarder.telegram.download_media = AsyncMock(return_value=b"video_data")
        
        with patch.object(forwarder, '_forward_to_destination', new_callable=AsyncMock) as mock_forward:
            await forwarder.handle_message(mock_message, mock_channel)
            forwarder.telegram.download_media.assert_called_once()
            mock_forward.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_message_media_only_filter(self, forwarder, mock_channel, mock_message):
        # Set up channel with media_only=True
        channel_config = Mock()
        channel_config.channel = "@test_channel"
        channel_config.destinations = ["discord_main"]
        channel_settings = Mock()
        channel_settings.media_only = True
        channel_settings.remove_captions = False
        channel_settings.translate_captions = False
        channel_settings.include_channel_name = None
        channel_settings.include_timestamp = None
        channel_settings.max_file_size_mb = None
        channel_config.settings = channel_settings
        
        forwarder.config.config.channels = [channel_config]
        
        mock_message.text = "Text only"
        mock_message.message = "Text only"
        mock_message.photo = None
        mock_message.video = None
        mock_message.document = None
        mock_message.media = None
        
        with patch.object(forwarder, '_forward_to_destination', new_callable=AsyncMock) as mock_forward:
            await forwarder.handle_message(mock_message, mock_channel)
            mock_forward.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_remove_captions(self, forwarder, mock_channel, mock_message):
        channel_config = Mock()
        channel_config.channel = "@test_channel"
        channel_config.destinations = ["discord_main"]
        channel_settings = Mock()
        channel_settings.media_only = False
        channel_settings.remove_captions = True
        channel_settings.translate_captions = False
        channel_settings.include_channel_name = None
        channel_settings.include_timestamp = None
        channel_settings.max_file_size_mb = None
        channel_config.settings = channel_settings

        forwarder.config.config.channels = [channel_config]

        mock_message.photo = Mock()
        mock_message.media = Mock()
        forwarder.telegram.download_media = AsyncMock(return_value=b"data")

        with patch.object(forwarder, '_forward_to_destination', new_callable=AsyncMock) as mock_forward:
            await forwarder.handle_message(mock_message, mock_channel)
            # Text should be None due to remove_captions
            call_args = mock_forward.call_args
            # text is the 4th positional arg
            assert call_args[0][3] is None

    @pytest.mark.asyncio
    async def test_handle_grouped_messages(self, forwarder, mock_channel, mock_message):
        """Test handling grouped messages (album)."""
        channel_config = Mock()
        channel_config.channel = "@test_channel"
        channel_config.destinations = ["discord_main"]
        channel_config.settings = None

        forwarder.config.config.channels = [channel_config]

        # Create two messages with the same grouped_id (simulating an album)
        mock_message1 = Mock(spec=Message)
        mock_message1.id = 123
        mock_message1.text = "Album caption"
        mock_message1.message = "Album caption"
        mock_message1.photo = Mock()
        mock_message1.video = None
        mock_message1.document = None
        mock_message1.media = Mock()
        mock_message1.grouped_id = 999
        mock_message1.date = datetime(2024, 1, 15, 10, 30, 0)

        mock_message2 = Mock(spec=Message)
        mock_message2.id = 124
        mock_message2.text = None
        mock_message2.message = None
        mock_message2.photo = Mock()
        mock_message2.video = None
        mock_message2.document = None
        mock_message2.media = Mock()
        mock_message2.grouped_id = 999
        mock_message2.date = datetime(2024, 1, 15, 10, 30, 0)

        forwarder.telegram.download_media = AsyncMock(side_effect=[b"photo1", b"photo2"])

        with patch.object(forwarder, '_forward_group_to_destination', new_callable=AsyncMock) as mock_forward_group:
            await forwarder.handle_message(mock_message1, mock_channel)
            # First message should be buffered, not forwarded immediately
            mock_forward_group.assert_not_called()

            await forwarder.handle_message(mock_message2, mock_channel)
            # Second message should also be buffered
            mock_forward_group.assert_not_called()

            await asyncio.sleep(forwarder.group_timeout + 0.1)
            # After timeout, group should be processed
            mock_forward_group.assert_called_once()
            call_args = mock_forward_group.call_args
            # Should have 2 media items (at index 5)
            assert len(call_args[0][5]) == 2


class TestForwardToDestination:
    """Test _forward_to_destination method."""
    
    @pytest.mark.asyncio
    async def test_forward_text_only(self, forwarder):
        mock_chat = Mock(spec=Channel)
        mock_message = Mock(spec=Message)

        with patch('src.forwarder.DiscordSender') as mock_sender_class:
            mock_sender = AsyncMock()
            mock_sender.send_message = AsyncMock(return_value=True)
            mock_sender_class.return_value = mock_sender

            await forwarder._forward_to_destination(
                mock_message, mock_chat, "discord_main",
                "Hello", "Formatted: Hello", None, None, None, "file", False, None
            )

            mock_sender.send_message.assert_called_once_with("Formatted: Hello")

    @pytest.mark.asyncio
    async def test_forward_photo(self, forwarder):
        mock_chat = Mock(spec=Channel)
        mock_message = Mock(spec=Message)
        mock_message.id = 1

        with patch('src.forwarder.DiscordSender') as mock_sender_class:
            mock_sender = AsyncMock()
            mock_sender.send_photo = AsyncMock(return_value=True)
            mock_sender_class.return_value = mock_sender

            photo_data = b"x" * (20 * 1024)

            await forwarder._forward_to_destination(
                mock_message, mock_chat, "discord_main",
                "Caption", "Formatted: Caption", photo_data, None, "photo", "photo.jpg", True, None
            )

            mock_sender.send_photo.assert_called_once_with("Formatted: Caption", photo_data, "photo.jpg")

    @pytest.mark.asyncio
    async def test_forward_media_too_large_with_compression(self, forwarder):
        mock_chat = Mock(spec=Channel)
        mock_message = Mock(spec=Message)

        large_data = b"x" * (20 * 1024 * 1024)

        forwarder.compressor.compress_media = AsyncMock(return_value=b"compressed_data")

        with patch('src.forwarder.DiscordSender') as mock_sender_class:
            mock_sender = AsyncMock()
            mock_sender.send_video = AsyncMock(return_value=True)
            mock_sender_class.return_value = mock_sender

            await forwarder._forward_to_destination(
                mock_message, mock_chat, "discord_main",
                "Video", "Formatted: Video", large_data, None, "video", "video.mp4", True, None
            )

            forwarder.compressor.compress_media.assert_called_once()
            mock_sender.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_media_compression_failed_with_text(self, forwarder):
        mock_chat = Mock(spec=Channel)
        mock_message = Mock(spec=Message)
        mock_message.id = 42

        large_data = b"x" * (20 * 1024 * 1024)

        forwarder.compressor.compress_media = AsyncMock(return_value=None)

        with patch('src.forwarder.DiscordSender') as mock_sender_class:
            mock_sender = AsyncMock()
            mock_sender.send_message = AsyncMock(return_value=True)
            mock_sender_class.return_value = mock_sender

            await forwarder._forward_to_destination(
                mock_message, mock_chat, "discord_main",
                "Text only", "Formatted: Text only", large_data, None, "video", "video.mp4", True, None
            )

            mock_sender.send_message.assert_called_once_with("Formatted: Text only")

    @pytest.mark.asyncio
    async def test_forward_destination_not_found(self, forwarder):
        forwarder.config.config.discord_webhooks = {}

        mock_chat = Mock(spec=Channel)
        mock_message = Mock(spec=Message)

        await forwarder._forward_to_destination(
            mock_message, mock_chat, "nonexistent",
            "Hello", "Formatted: Hello", None, None, None, "file", False, None
        )


class TestRunStop:
    """Test run and stop methods."""
    
    @pytest.mark.asyncio
    async def test_run(self, forwarder):
        forwarder.telegram.run = AsyncMock()
        
        await forwarder.run()
        forwarder.telegram.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop(self, forwarder):
        forwarder.telegram.disconnect = AsyncMock()

        with patch('src.discord_client.close_shared_session', new_callable=AsyncMock) as mock_close:
            await forwarder.stop()
            forwarder.telegram.disconnect.assert_called_once()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_calls_stop_on_exception(self, forwarder):
        """try/finally in run() must call stop() even when telegram.run() raises."""
        forwarder.telegram.run = AsyncMock(side_effect=RuntimeError("disconnected"))
        forwarder.telegram.disconnect = AsyncMock()

        with patch('src.discord_client.close_shared_session', new_callable=AsyncMock):
            with pytest.raises(RuntimeError):
                await forwarder.run()

        forwarder.telegram.disconnect.assert_called_once()


class TestGetChannelConfigBareId:
    """Test _get_channel_config with bare numeric channel IDs (bug fix #4)."""

    @pytest.mark.asyncio
    async def test_get_config_by_bare_numeric_id(self):
        """Config with bare numeric ID should match Telethon's chat.id."""
        manager = Mock()
        manager.config = Mock()
        manager.config.channels = [
            Mock(channel="1234567890", destinations=["discord_main"], settings=None)
        ]
        manager.config.discord_webhooks = {
            "discord_main": Mock(url="https://discord.com/webhook", max_file_size_mb=10)
        }
        manager.config.settings = Mock(
            max_file_size_mb=10,
            include_channel_name=True,
            include_timestamp=True,
            group_timeout_seconds=3.0,
        )

        with patch('src.forwarder.TelegramMonitor'), \
             patch('src.forwarder.MediaCompressor'):
            fwd = MediaForwarder(manager)

        channel = Mock()
        channel.id = 1234567890
        channel.username = None

        config = fwd._get_channel_config(channel)
        assert config is not None
        assert config.channel == "1234567890"

    @pytest.mark.asyncio
    async def test_get_config_by_full_id(self):
        """Config with -100-prefixed ID should match."""
        manager = Mock()
        manager.config = Mock()
        manager.config.channels = [
            Mock(channel="-1001234567890", destinations=["discord_main"], settings=None)
        ]
        manager.config.discord_webhooks = {}
        manager.config.settings = Mock(
            max_file_size_mb=10, include_channel_name=True, include_timestamp=True,
            group_timeout_seconds=3.0
        )

        with patch('src.forwarder.TelegramMonitor'), \
             patch('src.forwarder.MediaCompressor'):
            fwd = MediaForwarder(manager)

        channel = Mock()
        channel.id = 1234567890  # Telethon's bare ID
        channel.username = None

        config = fwd._get_channel_config(channel)
        assert config is not None
        assert config.channel == "-1001234567890"


class TestAlbumRaceCondition:
    """Test album race condition sentinel (bug fix #3)."""

    @pytest.mark.asyncio
    async def test_late_message_after_processing_is_discarded(self, forwarder, mock_channel):
        """A message arriving after _process_message_group pops the group gets discarded."""
        grouped_id = 42
        # Simulate the sentinel left by _process_message_group
        forwarder.message_groups[grouped_id] = None

        late_message = Mock()
        late_message.id = 999
        late_message.grouped_id = grouped_id

        with patch.object(forwarder, '_forward_group_to_destination', new_callable=AsyncMock) as mock_fwd:
            await forwarder._handle_grouped_message(late_message, mock_channel)
            mock_fwd.assert_not_called()

        # Sentinel should still be there (not replaced with a new group)
        assert forwarder.message_groups[grouped_id] is None

    @pytest.mark.asyncio
    async def test_sentinel_cleared_after_processing(self, forwarder, mock_channel, mock_message):
        """Sentinel is cleaned up after _process_message_group finishes."""
        channel_config = Mock()
        channel_config.channel = "@test_channel"
        channel_config.destinations = ["discord_main"]
        channel_config.settings = None
        forwarder.config.config.channels = [channel_config]

        grouped_id = 77
        mock_message.grouped_id = grouped_id
        mock_message.photo = None
        mock_message.video = None
        mock_message.document = None

        # Manually set up the group as if messages arrived
        forwarder.message_groups[grouped_id] = {'messages': [(mock_message, mock_channel)], 'timer_task': None}

        with patch.object(forwarder, '_forward_group_to_destination', new_callable=AsyncMock):
            await forwarder._process_message_group(grouped_id)

        # Sentinel should be removed after processing
        assert grouped_id not in forwarder.message_groups
