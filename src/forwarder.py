"""Main forwarding logic."""

import logging
import os
from datetime import datetime
import time
from typing import Dict, List, Optional, Tuple
import asyncio
from telethon.tl.types import Channel, Message, MessageMediaPhoto
from src.config import ConfigManager
from src.telegram_client import TelegramMonitor
from src.discord_client import DiscordSender
from src.media_compressor import MediaCompressor

logger = logging.getLogger(__name__)


class MediaForwarder:
    """Forward media from Telegram to Discord."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize media forwarder."""
        self.config = config_manager
        self.telegram = TelegramMonitor(config_manager)
        self._translator = None  # lazy-init on first use
        self.compressor = MediaCompressor()
        self.message_groups = {}
        self.group_timeout = config_manager.config.settings.group_timeout_seconds
        self.metrics = {
            'messages_received': 0,
            'messages_forwarded': 0,
            'messages_skipped': 0,
            'compression_attempts': 0,
            'compression_success': 0,
            'discord_retries': 0,
        }
        self._cleanup_task: Optional[asyncio.Task] = None

    @property
    def translator(self):
        if self._translator is None:
            from deep_translator import GoogleTranslator
            self._translator = GoogleTranslator(source='auto', target='en')
        return self._translator

    async def initialize(self):
        """Initialize forwarder."""
        await self.telegram.initialize()
        self.telegram.set_message_callback(self.handle_message)
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_groups())

    async def handle_message(self, message: Message, chat: Channel):
        """Handle incoming Telegram message."""
        self.metrics['messages_received'] += 1
        # Check if message is part of a group (album)
        grouped_id = getattr(message, 'grouped_id', None)
        if grouped_id:
            await self._handle_grouped_message(message, chat)
        else:
            await self._handle_single_message(message, chat)

    async def _handle_grouped_message(self, message: Message, chat: Channel):
        """Handle message that's part of a group (album)."""
        grouped_id = message.grouped_id

        if grouped_id not in self.message_groups:
            self.message_groups[grouped_id] = {
                'messages': [],
                'timer_task': None,
                'created_at': time.monotonic(),
            }
        elif self.message_groups[grouped_id] is None:
            # Group is already being processed — late arrival, log and discard
            logger.warning(
                f'Late message {message.id} for group {grouped_id} arrived after processing started; skipping'
            )
            return

        group = self.message_groups[grouped_id]
        group['messages'].append((message, chat))

        logger.debug(f'Added message {message.id} to group {grouped_id}, total: {len(group["messages"])}')

        # Cancel existing timer if any
        if group['timer_task'] and not group['timer_task'].done():
            group['timer_task'].cancel()

        # Set new timer to process the group
        async def process_group():
            await asyncio.sleep(self.group_timeout)
            await self._process_message_group(grouped_id)

        group['timer_task'] = asyncio.create_task(process_group())

    async def _process_message_group(self, grouped_id):
        """Process all messages in a group and forward together."""
        if grouped_id not in self.message_groups:
            return

        group = self.message_groups.pop(grouped_id)
        # Sentinel so late-arriving messages can detect the group is processing
        self.message_groups[grouped_id] = None
        try:
            await self._process_message_group_inner(grouped_id, group)
        finally:
            self.message_groups.pop(grouped_id, None)

    async def _process_message_group_inner(self, grouped_id, group):
        """Inner logic for _process_message_group, called with sentinel already set."""
        messages_and_chats = group['messages']

        if not messages_and_chats:
            return

        logger.info(f'Processing group {grouped_id} with {len(messages_and_chats)} messages')

        first_message, chat = messages_and_chats[0]

        channel_config = self._get_channel_config(chat)
        if not channel_config:
            if chat.username:
                channel_id = f'@{chat.username}'
            else:
                channel_id = f'-100{chat.id}'
            logger.warning(f'No configuration found for channel: {channel_id}')
            return

        channel_settings = channel_config.settings

        text = first_message.text or first_message.message

        media_items = []
        temp_paths = []
        try:
            for msg, _ in messages_and_chats:
                media_data = None
                temp_path = None
                media_type = None
                filename = 'file'

                if msg.photo:
                    media_data, temp_path = await self._download_media(msg)
                    media_type = 'photo'
                    filename = f'photo_{msg.id}.jpg'
                elif msg.video:
                    media_data, temp_path = await self._download_media(msg)
                    media_type = 'video'
                    if msg.video.attributes:
                        for attr in msg.video.attributes:
                            if hasattr(attr, 'file_name') and attr.file_name:
                                filename = attr.file_name
                                break
                    if filename == 'file':
                        filename = f'video_{msg.id}.mp4'
                elif msg.document:
                    media_data, temp_path = await self._download_media(msg)
                    media_type = 'document'
                    if msg.document.attributes:
                        for attr in msg.document.attributes:
                            if hasattr(attr, 'file_name') and attr.file_name:
                                filename = attr.file_name
                                break
                    if filename == 'file':
                        filename = f'document_{msg.id}'

                if temp_path:
                    temp_paths.append(temp_path)
                    file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                    media_items.append({
                        'file_path': temp_path,
                        'type': media_type,
                        'filename': filename,
                        'size_mb': file_size_mb,
                    })
                elif media_data:
                    media_items.append({
                        'data': media_data,
                        'type': media_type,
                        'filename': filename,
                    })

            if not media_items:
                logger.debug(f'No media found in group {grouped_id}, skipping')
                return

            if channel_settings and channel_settings.media_only:
                pass

            if channel_settings and channel_settings.remove_captions:
                text = None
                logger.debug(f'Removed caption from group {grouped_id}')

            if text and channel_settings and channel_settings.translate_captions:
                text = await self._translate_text(text)
                if text:
                    logger.debug(f'Translated caption for group {grouped_id}')

            formatted_text = self._format_message(text, chat, first_message, channel_settings)

            for destination_name in channel_config.destinations:
                await self._forward_group_to_destination(
                    first_message, chat, destination_name,
                    text, formatted_text, media_items, channel_settings
                )
        finally:
            for tp in temp_paths:
                try:
                    os.unlink(tp)
                except OSError:
                    pass

    async def _download_media(self, msg) -> Tuple[Optional[bytes], Optional[str]]:
        """Download media, returning (data, temp_file_path).

        Returns (bytes, None) for small files or (None, path) for large files.
        Caller must delete temp_file_path when done.
        """
        data = await self.telegram.download_media(msg)
        if data is not None:
            return data, None

        temp_path = await self.telegram.download_media_to_file(msg)
        if temp_path is not None:
            return None, temp_path

        return None, None

    async def _handle_single_message(self, message: Message, chat: Channel):
        """Handle a single (non-grouped) message."""
        channel_config = self._get_channel_config(chat)
        if not channel_config:
            if chat.username:
                channel_id = f'@{chat.username}'
            else:
                channel_id = f'-100{chat.id}'
            logger.warning(f'No configuration found for channel: {channel_id}')
            return

        channel_settings = channel_config.settings

        text = message.text or message.message
        media_data = None
        temp_file_path = None
        media_type = None
        filename = 'file'
        has_media = False

        if message.photo:
            media_data, temp_file_path = await self._download_media(message)
            media_type = 'photo'
            filename = f'photo_{message.id}.jpg'
            has_media = True

        elif message.video:
            media_data, temp_file_path = await self._download_media(message)
            media_type = 'video'
            if message.video.attributes:
                for attr in message.video.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        filename = attr.file_name
                        break
            if filename == 'file':
                filename = f'video_{message.id}.mp4'
            has_media = True

        elif message.document:
            media_data, temp_file_path = await self._download_media(message)
            media_type = 'document'
            if message.document.attributes:
                for attr in message.document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        filename = attr.file_name
                        break
            if filename == 'file':
                filename = f'document_{message.id}'
            has_media = True

        if channel_settings and channel_settings.media_only and not has_media:
            logger.debug(f'Skipping text-only message {message.id} (media_only=True)')
            return

        if channel_settings and channel_settings.remove_captions and has_media:
            text = None
            logger.debug(f'Removed caption from message {message.id}')

        if text and channel_settings and channel_settings.translate_captions:
            text = await self._translate_text(text)
            if text:
                logger.debug(f'Translated caption for message {message.id}')

        formatted_text = self._format_message(text, chat, message, channel_settings)

        try:
            for destination_name in channel_config.destinations:
                await self._forward_to_destination(
                    message, chat, destination_name,
                    text, formatted_text, media_data, temp_file_path, media_type,
                    filename, has_media, channel_settings
                )
        finally:
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

    async def _forward_to_destination(
        self,
        message: Message,
        chat: Channel,
        destination_name: str,
        text: str,
        formatted_text: str,
        media_data: Optional[bytes],
        temp_file_path: Optional[str],
        media_type: str,
        filename: str,
        has_media: bool,
        channel_settings
    ):
        """Forward message to a specific destination."""
        try:
            webhook_config = self.config.config.discord_webhooks.get(destination_name)
            if not webhook_config:
                logger.error(f'Destination config not found: {destination_name}')
                return

            if isinstance(webhook_config, dict):
                webhook_url = webhook_config['url']
                max_file_size = webhook_config.get('max_file_size_mb')
            else:
                webhook_url = webhook_config.url
                max_file_size = webhook_config.max_file_size_mb

            if max_file_size:
                pass
            elif channel_settings and channel_settings.max_file_size_mb:
                max_file_size = channel_settings.max_file_size_mb
            else:
                max_file_size = self.config.config.settings.max_file_size_mb

            sender = DiscordSender(webhook_url, max_file_size)

            final_media_data = media_data
            final_temp_path = temp_file_path
            skip_reason: Optional[str] = None

            if has_media and (media_data or temp_file_path):
                if temp_file_path:
                    file_size_mb = os.path.getsize(temp_file_path) / (1024 * 1024)
                else:
                    file_size_mb = len(media_data) / (1024 * 1024)
                logger.debug(f"Media file {filename}: {file_size_mb:.2f}MB, type: {media_type}")

                if file_size_mb < 0.01:
                    logger.warning(f"Downloaded media {filename} is too small ({file_size_mb:.2f}MB), skipping")
                    final_media_data = None
                    final_temp_path = None
                    skip_reason = f'media too small ({file_size_mb:.2f}MB)'
                elif file_size_mb > max_file_size:
                    logger.info(
                        f'Media too large ({file_size_mb:.2f}MB > {max_file_size}MB), '
                        f'attempting compression for {destination_name}'
                    )
                    self.metrics['compression_attempts'] += 1

                    if final_temp_path:
                        with open(final_temp_path, 'rb') as f:
                            raw_data = f.read()
                        compressed_data = await self.compressor.compress_media(
                            raw_data, media_type, max_file_size, filename
                        )
                    else:
                        compressed_data = await self.compressor.compress_media(
                            media_data, media_type, max_file_size, filename
                        )

                    if compressed_data:
                        final_media_data = compressed_data
                        final_temp_path = None
                        self.metrics['compression_success'] += 1
                        logger.info(
                            f'Successfully compressed media for {destination_name}: '
                            f'{file_size_mb:.2f}MB -> {len(compressed_data)/(1024*1024):.2f}MB'
                        )
                    else:
                        logger.warning(
                            f'Could not compress media for {destination_name}, skipping media'
                        )
                        if not text:
                            skip_reason = 'compression failed, no caption fallback'
                        else:
                            logger.info(f'Sending text-only fallback for message {message.id} (compression failed)')
                            final_media_data = None
                            final_temp_path = None

            if skip_reason or (not final_media_data and not final_temp_path and not formatted_text):
                reason_str = f' (reason: {skip_reason})' if skip_reason else ''
                logger.info(f'Skipping message {message.id} to {destination_name}{reason_str}')
                self.metrics['messages_skipped'] += 1
                return

            send_text = self._truncate_for_discord(formatted_text)
            success = False

            if final_temp_path:
                success = await sender.send_file(send_text, final_temp_path, filename)
            elif media_type == 'photo' and final_media_data:
                success = await sender.send_photo(send_text, final_media_data, filename)
            elif media_type == 'video' and final_media_data:
                success = await sender.send_video(send_text, final_media_data, filename)
            elif media_type == 'document' and final_media_data:
                success = await sender.send_document(send_text, final_media_data, filename)
            elif send_text:
                success = await sender.send_message(send_text)

            if success:
                self.metrics['messages_forwarded'] += 1
                logger.info(
                    f'Forwarded message {message.id} from {chat.username or chat.id} '
                    f'to {destination_name}'
                )
            else:
                logger.warning(
                    f'Failed to forward message {message.id} to {destination_name}'
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f'Error forwarding to {destination_name}: {e}',
                exc_info=True
            )

    async def _forward_group_to_destination(
        self,
        message: Message,
        chat: Channel,
        destination_name: str,
        text: str,
        formatted_text: str,
        media_items: List[dict],
        channel_settings
    ):
        """Forward grouped messages (album) to a specific destination."""
        try:
            webhook_config = self.config.config.discord_webhooks.get(destination_name)
            if not webhook_config:
                logger.error(f'Destination config not found: {destination_name}')
                return

            if isinstance(webhook_config, dict):
                webhook_url = webhook_config['url']
                max_file_size = webhook_config.get('max_file_size_mb')
            else:
                webhook_url = webhook_config.url
                max_file_size = webhook_config.max_file_size_mb

            if max_file_size:
                pass
            elif channel_settings and channel_settings.max_file_size_mb:
                max_file_size = channel_settings.max_file_size_mb
            else:
                max_file_size = self.config.config.settings.max_file_size_mb

            sender = DiscordSender(webhook_url, max_file_size)

            final_media_items = []
            failed_compression = 0

            for item in media_items:
                file_path = item.get('file_path')
                if file_path:
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                else:
                    media_data = item['data']
                    if not media_data:
                        continue
                    file_size_mb = len(media_data) / (1024 * 1024)

                media_type = item['type']
                filename = item['filename']

                logger.debug(f"Media file {filename}: {file_size_mb:.2f}MB, type: {media_type}")

                if file_size_mb < 0.01:
                    logger.warning(f"Downloaded media {filename} is too small ({file_size_mb:.2f}MB), skipping")
                    continue
                elif file_size_mb > max_file_size:
                    logger.info(
                        f'Media too large ({file_size_mb:.2f}MB > {max_file_size}MB), '
                        f'attempting compression for {destination_name}'
                    )
                    self.metrics['compression_attempts'] += 1

                    if file_path:
                        with open(file_path, 'rb') as f:
                            raw_data = f.read()
                    else:
                        raw_data = media_data

                    compressed_data = await self.compressor.compress_media(
                        raw_data, media_type, max_file_size, filename
                    )

                    if compressed_data:
                        final_media_items.append({
                            'data': compressed_data,
                            'type': media_type,
                            'filename': filename
                        })
                        self.metrics['compression_success'] += 1
                        logger.info(
                            f'Successfully compressed media for {destination_name}: '
                            f'{file_size_mb:.2f}MB -> {len(compressed_data)/(1024*1024):.2f}MB'
                        )
                    else:
                        failed_compression += 1
                        logger.warning(
                            f'Could not compress media {filename} for {destination_name}, skipping this item'
                        )
                else:
                    if file_path:
                        final_media_items.append({
                            'file_path': file_path,
                            'type': media_type,
                            'filename': filename,
                        })
                    else:
                        final_media_items.append({
                            'data': item['data'],
                            'type': media_type,
                            'filename': filename
                        })

            if not final_media_items and not formatted_text:
                reason = 'all media failed compression, no caption' if failed_compression else 'no media or text'
                logger.info(f'Skipping group message to {destination_name} (reason: {reason})')
                self.metrics['messages_skipped'] += 1
                return

            if not final_media_items and formatted_text:
                logger.info(
                    f'Sending text-only fallback for group to {destination_name} '
                    f'({failed_compression} item(s) failed compression)'
                )

            send_text = self._truncate_for_discord(formatted_text)
            success = await sender.send_multiple_media(send_text, final_media_items)

            if success:
                self.metrics['messages_forwarded'] += 1
                logger.info(
                    f'Forwarded grouped message from {chat.username or chat.id} '
                    f'with {len(final_media_items)} media items to {destination_name}'
                )
            else:
                logger.warning(
                    f'Failed to forward grouped message to {destination_name}'
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f'Error forwarding group to {destination_name}: {e}',
                exc_info=True
            )

    async def _cleanup_stale_groups(self):
        """Background task: evict message_groups entries that were never processed."""
        sweep_interval = max(self.group_timeout * 3, 10.0)
        stale_threshold = self.group_timeout * 10  # 30s at default timeout
        while True:
            try:
                await asyncio.sleep(sweep_interval)
                now = time.monotonic()
                stale = [
                    gid for gid, entry in list(self.message_groups.items())
                    if entry is not None and now - entry.get('created_at', now) > stale_threshold
                    and (entry['timer_task'] is None or entry['timer_task'].done())
                ]
                for gid in stale:
                    logger.warning(f'Evicting stale message group {gid} (never processed)')
                    self.message_groups.pop(gid, None)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f'Error in group cleanup sweep: {e}')

    async def _translate_text(self, text: str) -> str:
        """Translate text to English."""
        try:
            translated = await asyncio.to_thread(self.translator.translate, text)
            return translated
        except Exception as e:
            logger.warning(f'Translation failed: {e}')
            return text

    @staticmethod
    def _truncate_for_discord(text: str, limit: int = 2000) -> str:
        """Truncate text to fit within Discord's content length limit."""
        if not text or len(text) <= limit:
            return text
        truncated = text[:limit - 3] + '...'
        logger.debug(f'Truncated message from {len(text)} to {limit} chars for Discord')
        return truncated

    def _get_channel_config(self, chat: Channel):
        """Get channel configuration for a chat."""
        # Try multiple identifiers: username, then numeric ID forms
        possible_identifiers = []

        if chat.username:
            possible_identifiers.append(f'@{chat.username}')

        # Telethon's chat.id is the bare numeric part (e.g. 1234567890).
        # Config may store the full -100-prefixed ID or the bare integer string.
        bare_id = chat.id
        possible_identifiers.append(f'-100{bare_id}')
        possible_identifiers.append(str(bare_id))

        logger.debug(f'Looking for config with identifiers: {possible_identifiers}')
        
        for channel_config in self.config.config.channels:
            if channel_config.channel in possible_identifiers:
                return channel_config
        
        logger.warning(f'No configuration found for channel: {chat.title or chat.username or chat.id}')
        return None

    def _format_message(self, text: str, chat: Channel, message: Message, channel_settings=None) -> str:
        """Format message for Discord."""
        parts = []

        # Determine settings
        include_channel_name = self.config.config.settings.include_channel_name
        include_timestamp = self.config.config.settings.include_timestamp
        
        if channel_settings:
            if channel_settings.include_channel_name is not None:
                include_channel_name = channel_settings.include_channel_name
            if channel_settings.include_timestamp is not None:
                include_timestamp = channel_settings.include_timestamp

        # Add channel name if enabled
        if include_channel_name:
            channel_name = chat.title or chat.username or str(chat.id)
            parts.append(f'**From:** {channel_name}')

        # Add timestamp if enabled
        if include_timestamp:
            timestamp = message.date.strftime('%Y-%m-%d %H:%M:%S')
            parts.append(f'**Time:** {timestamp}')

        # Add message text
        if text:
            if parts:
                parts.append('---')
            parts.append(text)

        return '\n'.join(parts) if parts else ''

    async def run(self):
        """Run the forwarder."""
        logger.info('Starting media forwarder')
        try:
            await self.telegram.run()
        finally:
            await self.stop()

    async def stop(self):
        """Stop the forwarder."""
        logger.info('Stopping media forwarder')
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        await self.telegram.disconnect()
        from src.discord_client import close_shared_session
        await close_shared_session()
        logger.info('Discord session closed')
