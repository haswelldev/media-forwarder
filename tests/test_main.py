"""Unit tests for main entry point."""

import sys
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path


class TestSetupLogging:

    def test_setup_logging_debug(self):
        import logging
        from src.main import setup_logging
        with patch('src.main.logging.basicConfig') as mock_basic:
            setup_logging("DEBUG")
            mock_basic.assert_called_once()
            assert mock_basic.call_args[1]['level'] == 10

    def test_setup_logging_info(self):
        import logging
        from src.main import setup_logging
        with patch('src.main.logging.basicConfig') as mock_basic:
            setup_logging("INFO")
            assert mock_basic.call_args[1]['level'] == 20

    def test_setup_logging_invalid_falls_back_to_info(self):
        import logging
        from src.main import setup_logging
        with patch('src.main.logging.basicConfig') as mock_basic:
            setup_logging("INVALID_LEVEL")
            assert mock_basic.call_args[1]['level'] == 20


class TestLoginCommand:

    def _make_mock_sent(self, code_type_name='SentCodeTypeApp'):
        mock_type = Mock()
        type(mock_type).__name__ = code_type_name
        mock_sent = Mock()
        mock_sent.type = mock_type
        mock_sent.phone_code_hash = 'hash123'
        mock_sent.next_type = None
        return mock_sent

    @pytest.mark.asyncio
    async def test_login_command_success(self):
        from src.main import login_command

        mock_config = Mock()
        mock_config.telegram_session_path = Path("/tmp/test.session")
        mock_config.telegram_api_id = 123
        mock_config.telegram_api_hash = "hash"

        mock_me = Mock()
        mock_me.first_name = "Test User"
        mock_me.username = "testuser"
        mock_me.id = 12345

        mock_sent = self._make_mock_sent()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=False)
        mock_client.send_code_request = AsyncMock(return_value=mock_sent)
        mock_client.sign_in = AsyncMock()
        mock_client.get_me = AsyncMock(return_value=mock_me)
        mock_client.disconnect = AsyncMock()

        with patch('telethon.TelegramClient', return_value=mock_client), \
             patch('builtins.input', side_effect=['+1234567890', '12345']):
            await login_command(mock_config)
            mock_client.connect.assert_called_once()
            mock_client.send_code_request.assert_called_once_with('+1234567890')
            mock_client.sign_in.assert_called_once_with('+1234567890', '12345', phone_code_hash='hash123')
            mock_client.get_me.assert_called_once()
            mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_command_already_authorized(self):
        from src.main import login_command

        mock_config = Mock()
        mock_config.telegram_session_path = Path("/tmp/test.session")
        mock_config.telegram_api_id = 123
        mock_config.telegram_api_hash = "hash"

        mock_me = Mock()
        mock_me.first_name = "Test User"
        mock_me.username = "testuser"
        mock_me.id = 12345

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=True)
        mock_client.get_me = AsyncMock(return_value=mock_me)
        mock_client.disconnect = AsyncMock()

        with patch('telethon.TelegramClient', return_value=mock_client):
            await login_command(mock_config)
            mock_client.send_code_request.assert_not_called()
            mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_command_2fa(self):
        from src.main import login_command
        from telethon.errors import SessionPasswordNeededError

        mock_config = Mock()
        mock_config.telegram_session_path = Path("/tmp/test.session")
        mock_config.telegram_api_id = 123
        mock_config.telegram_api_hash = "hash"

        mock_me = Mock()
        mock_me.first_name = "Test User"
        mock_me.username = "testuser"
        mock_me.id = 12345

        mock_sent = self._make_mock_sent()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=False)
        mock_client.send_code_request = AsyncMock(return_value=mock_sent)
        mock_client.sign_in = AsyncMock(side_effect=[SessionPasswordNeededError(None), None])
        mock_client.get_me = AsyncMock(return_value=mock_me)
        mock_client.disconnect = AsyncMock()

        with patch('telethon.TelegramClient', return_value=mock_client), \
             patch('builtins.input', side_effect=['+1234567890', '12345', 'mypassword']):
            await login_command(mock_config)
            assert mock_client.sign_in.call_count == 2

    @pytest.mark.asyncio
    async def test_login_command_failure(self):
        from src.main import login_command

        mock_config = Mock()
        mock_config.telegram_session_path = Path("/tmp/test.session")
        mock_config.telegram_api_id = 123
        mock_config.telegram_api_hash = "hash"

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=Exception("Login failed"))

        with patch('telethon.TelegramClient', return_value=mock_client):
            with pytest.raises(SystemExit) as exc_info:
                await login_command(mock_config)
            assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_login_command_flood_wait(self):
        from src.main import login_command
        from telethon.errors import FloodWaitError

        mock_config = Mock()
        mock_config.telegram_session_path = Path("/tmp/test.session")
        mock_config.telegram_api_id = 123
        mock_config.telegram_api_hash = "hash"

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=False)
        mock_client.send_code_request = AsyncMock(side_effect=FloodWaitError(request=None, capture=0))
        mock_client.disconnect = AsyncMock()

        with patch('telethon.TelegramClient', return_value=mock_client), \
             patch('builtins.input', return_value='+1234567890'):
            with pytest.raises(SystemExit) as exc_info:
                await login_command(mock_config)
            assert exc_info.value.code == 1


class TestRunCommand:

    @pytest.mark.asyncio
    async def test_run_command_normal(self):
        from src.main import run_command

        mock_config = Mock()
        with patch('src.main.MediaForwarder') as mock_forwarder_class:
            mock_forwarder = AsyncMock()
            mock_forwarder_class.return_value = mock_forwarder

            await run_command(mock_config)
            mock_forwarder.initialize.assert_called_once()
            mock_forwarder.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_command_keyboard_interrupt(self):
        from src.main import run_command

        mock_config = Mock()
        with patch('src.main.MediaForwarder') as mock_forwarder_class:
            mock_forwarder = AsyncMock()
            mock_forwarder.run = AsyncMock(side_effect=KeyboardInterrupt)
            mock_forwarder_class.return_value = mock_forwarder

            await run_command(mock_config)
            mock_forwarder.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_command_fatal_error(self):
        from src.main import run_command

        mock_config = Mock()
        with patch('src.main.MediaForwarder') as mock_forwarder_class:
            mock_forwarder = AsyncMock()
            mock_forwarder.initialize = AsyncMock(side_effect=RuntimeError("Fatal"))
            mock_forwarder_class.return_value = mock_forwarder

            with pytest.raises(SystemExit) as exc_info:
                await run_command(mock_config)
            assert exc_info.value.code == 1


class TestValidateCommand:

    @pytest.mark.asyncio
    async def test_validate_command_success(self, capsys):
        from src.main import validate_command
        from src.models import Config, ChannelConfig, Settings

        mock_config_manager = Mock()
        mock_config_manager.telegram_session_path = Path("/tmp/existing.session")
        mock_config_manager.config_path = Path("/app/config/channels.yaml")

        config = Config(
            channels=[ChannelConfig(channel="@test_channel", destinations=["main"])],
            discord_webhooks={"main": {"url": "https://discord.com/api/webhooks/123/abc"}},
            settings=Settings()
        )
        mock_config_manager.load = Mock(return_value=config)

        with patch.object(Path, 'exists', return_value=True):
            await validate_command(mock_config_manager)

        captured = capsys.readouterr()
        assert "valid" in captured.out.lower()

    @pytest.mark.asyncio
    async def test_validate_command_no_session_file(self, capsys):
        from src.main import validate_command
        from src.models import Config, ChannelConfig, Settings

        mock_config_manager = Mock()
        mock_config_manager.telegram_session_path = Path("/tmp/missing.session")
        mock_config_manager.config_path = Path("/app/config/channels.yaml")

        config = Config(
            channels=[ChannelConfig(channel="@test_channel", destinations=["main"])],
            discord_webhooks={"main": {"url": "https://discord.com/api/webhooks/123/abc"}},
            settings=Settings()
        )
        mock_config_manager.load = Mock(return_value=config)

        with patch.object(Path, 'exists', return_value=False):
            await validate_command(mock_config_manager)

        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    @pytest.mark.asyncio
    async def test_validate_command_failure(self):
        from src.main import validate_command

        mock_config_manager = Mock()
        mock_config_manager.load = Mock(side_effect=FileNotFoundError("Config not found"))

        with pytest.raises(SystemExit) as exc_info:
            await validate_command(mock_config_manager)
        assert exc_info.value.code == 1


class TestMain:

    def test_main_with_run_command(self):
        from src.main import main

        with patch('sys.argv', ['main.py', 'run']):
            with patch('src.main.asyncio.run') as mock_run:
                with patch('src.main.ConfigManager') as mock_cm:
                    mock_cm_instance = Mock()
                    mock_cm_instance.log_level = "INFO"
                    mock_cm.return_value = mock_cm_instance
                    main()
                    mock_run.assert_called_once()

    def test_main_with_login_command(self):
        from src.main import main

        with patch('sys.argv', ['main.py', 'login']):
            with patch('src.main.asyncio.run') as mock_run:
                with patch('src.main.ConfigManager') as mock_cm:
                    mock_cm_instance = Mock()
                    mock_cm_instance.log_level = "INFO"
                    mock_cm.return_value = mock_cm_instance
                    main()
                    mock_run.assert_called_once()

    def test_main_with_validate_command(self):
        from src.main import main

        with patch('sys.argv', ['main.py', 'validate']):
            with patch('src.main.asyncio.run') as mock_run:
                with patch('src.main.ConfigManager') as mock_cm:
                    mock_cm_instance = Mock()
                    mock_cm_instance.log_level = "INFO"
                    mock_cm.return_value = mock_cm_instance
                    main()
                    mock_run.assert_called_once()

    def test_main_with_custom_config_path(self):
        from src.main import main

        with patch('sys.argv', ['main.py', '--config', '/custom/path.yaml', 'run']):
            with patch('src.main.asyncio.run'):
                with patch('src.main.ConfigManager') as mock_cm:
                    mock_cm_instance = Mock()
                    mock_cm_instance.log_level = "INFO"
                    mock_cm.return_value = mock_cm_instance
                    main()
                    mock_cm.assert_called_once()
                    call_args = mock_cm.call_args[0][0]
                    assert call_args == Path("/custom/path.yaml")

    def test_main_log_level_fallback(self):
        from src.main import main

        with patch('sys.argv', ['main.py', 'run']):
            with patch('src.main.asyncio.run'):
                with patch('src.main.ConfigManager') as mock_cm:
                    mock_cm_instance = Mock()
                    mock_cm_instance.log_level = property(lambda s: (_ for _ in ()).throw(Exception("no env")))
                    type(mock_cm_instance).log_level = property(lambda s: (_ for _ in ()).throw(Exception("no env")))
                    mock_cm.return_value = mock_cm_instance
                    with patch('src.main.setup_logging') as mock_setup:
                        main()
                        mock_setup.assert_called_once_with('INFO')
