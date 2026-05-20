"""Main entry point for media-forwarder."""

import sys
import logging
import argparse
import asyncio
from .config import ConfigManager
from .forwarder import MediaForwarder
from .telegram_client import TelegramMonitor


def setup_logging(level: str):
    """Setup logging configuration."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


async def login_command(config_manager: ConfigManager):
    """Perform interactive login to Telegram."""
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError, SessionPasswordNeededError
    
    print('Starting interactive Telegram login...')
    print(f'Session file: {config_manager.telegram_session_path}')
    
    client = TelegramClient(
        str(config_manager.telegram_session_path),
        config_manager.telegram_api_id,
        config_manager.telegram_api_hash
    )
    
    try:
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f'\nAlready logged in as: {me.first_name} (@{me.username})')
            print(f'User ID: {me.id}')
            await client.disconnect()
            return
        
        phone = input('Enter your phone number (with country code, e.g. +1234567890): ')
        print(f'Sending code to {phone}...')
        
        try:
            sent = await client.send_code_request(phone)
        except FloodWaitError as e:
            print(f'\nToo many login attempts. Please wait {e.seconds} seconds and try again.')
            await client.disconnect()
            sys.exit(1)
        
        code_type = type(sent.type).__name__ if sent.type else 'unknown'
        delivery_hint = {
            'SentCodeTypeApp': 'Telegram app (check your chat with "Telegram" for a message with the code)',
            'SentCodeTypeSms': 'SMS (check your text messages)',
            'SentCodeTypeCall': 'phone call (you will receive an automated call)',
            'SentCodeTypeFlashCall': 'flash call (you will receive a brief phone call)',
        }.get(code_type, f'{code_type} (check Telegram app and SMS)')
        
        print(f'Code sent via {delivery_hint}')
        
        if hasattr(sent, 'next_type') and sent.next_type:
            next_type = type(sent.next_type).__name__ if sent.next_type else None
            if next_type == 'SentCodeTypeSms':
                print('If you did not receive the code, you can request it via SMS by pressing Enter without entering a code.')
        
        code = input('Enter the code you received: ')
        
        if not code.strip():
            print('Requesting code via SMS...')
            try:
                sent = await client.send_code_request(phone, force_sms=True)
                code_type = type(sent.type).__name__ if sent.type else 'unknown'
                delivery_hint = {
                    'SentCodeTypeApp': 'Telegram app',
                    'SentCodeTypeSms': 'SMS (check your text messages)',
                    'SentCodeTypeCall': 'phone call',
                    'SentCodeTypeFlashCall': 'flash call',
                }.get(code_type, f'{code_type}')
                print(f'Code sent via {delivery_hint}')
                code = input('Enter the code you received: ')
            except FloodWaitError as e:
                print(f'\nToo many login attempts. Please wait {e.seconds} seconds and try again.')
                await client.disconnect()
                sys.exit(1)
        
        try:
            await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
        except SessionPasswordNeededError:
            password = input('Your account has 2FA enabled. Enter your password: ')
            await client.sign_in(password=password)
        
        me = await client.get_me()
        print(f'\nSuccessfully logged in as: {me.first_name} (@{me.username})')
        print(f'User ID: {me.id}')
        print(f'Session saved to: {config_manager.telegram_session_path}')
        
        await client.disconnect()
        print('\nLogin complete! You can now run the forwarder.')
        
    except Exception as e:
        print(f'\nLogin failed: {e}')
        sys.exit(1)


async def run_command(config_manager: ConfigManager):
    """Run the media forwarder."""
    forwarder = None
    try:
        forwarder = MediaForwarder(config_manager)
        await forwarder.initialize()
        await forwarder.run()
    except KeyboardInterrupt:
        print('\nReceived interrupt signal, shutting down...')
        if forwarder:
            await forwarder.stop()
    except Exception as e:
        logging.error(f'Fatal error: {e}', exc_info=True)
        sys.exit(1)


async def validate_command(config_manager: ConfigManager):
    """Validate configuration."""
    print('Validating configuration...')
    
    try:
        # Check environment variables
        print('✓ Environment variables loaded')
        
        # Load configuration
        config = config_manager.load()
        print(f'✓ Configuration loaded from {config_manager.config_path}')
        
        # Validate channels
        print(f'✓ Found {len(config.channels)} channel(s) to monitor:')
        for channel in config.channels:
            print(f'  - {channel.channel} -> {", ".join(channel.destinations)}')
        
        # Validate webhooks
        print(f'✓ Found {len(config.discord_webhooks)} webhook(s):')
        for name, webhook in config.discord_webhooks.items():
            if isinstance(webhook, dict):
                url = webhook['url'][:50] + '...' if len(webhook['url']) > 50 else webhook['url']
            else:
                url = str(webhook)[:50] + '...' if len(str(webhook)) > 50 else str(webhook)
            print(f'  - {name}: {url}')
        
        # Validate settings
        print(f'✓ Settings:')
        print(f'  - Max file size: {config.settings.max_file_size_mb}MB')
        print(f'  - Log level: {config.settings.log_level}')
        print(f'  - Include channel name: {config.settings.include_channel_name}')
        print(f'  - Include timestamp: {config.settings.include_timestamp}')
        
        # Check session file
        if config_manager.telegram_session_path.exists():
            print(f'✓ Session file exists: {config_manager.telegram_session_path}')
        else:
            print(f'⚠ Session file not found: {config_manager.telegram_session_path}')
            print('  Run "login" command to create it.')
        
        print('\n✓ Configuration is valid!')
        
    except Exception as e:
        print(f'\n✗ Validation failed: {e}')
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Media Forwarder - Telegram to Discord forwarding service'
    )
    parser.add_argument(
        'command',
        choices=['login', 'run', 'validate'],
        help='Command to execute'
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to configuration file (default: /app/config/channels.yaml)'
    )
    
    args = parser.parse_args()
    
    # Setup config manager
    config_path = args.config
    if config_path:
        from pathlib import Path
        config_path = Path(config_path)
    
    config_manager = ConfigManager(config_path)
    
    # Setup logging
    try:
        log_level = config_manager.log_level
    except Exception:
        log_level = 'INFO'
    setup_logging(log_level)
    
    # Execute command
    if args.command == 'login':
        asyncio.run(login_command(config_manager))
    elif args.command == 'run':
        asyncio.run(run_command(config_manager))
    elif args.command == 'validate':
        asyncio.run(validate_command(config_manager))


if __name__ == '__main__':
    main()
