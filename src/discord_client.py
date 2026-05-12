"""Discord client for sending messages via webhooks."""

import asyncio
import logging
from typing import Callable, Optional
import aiohttp

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_STATUSES = {500, 502, 503, 504}
_DISCORD_MAX_ATTACHMENTS = 10
_DISCORD_CONTENT_LIMIT = 2000

# Global shared session
_shared_session: Optional[aiohttp.ClientSession] = None


async def get_shared_session() -> aiohttp.ClientSession:
    """Get or create shared aiohttp session."""
    global _shared_session
    if _shared_session is None or _shared_session.closed:
        _shared_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
    return _shared_session


async def close_shared_session():
    """Close the shared session."""
    global _shared_session
    if _shared_session and not _shared_session.closed:
        await _shared_session.close()
        _shared_session = None


class DiscordSender:
    """Send messages to Discord via webhooks."""

    def __init__(self, webhook_url: str, max_file_size_mb: int = 10):
        """Initialize Discord sender."""
        self.webhook_url = webhook_url
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    async def _post_with_retry(self, data_factory: Callable[[], aiohttp.FormData]) -> bool:
        """POST form data with retry on 429/5xx. data_factory must return a fresh FormData each call."""
        session = await get_shared_session()
        delay = 1.0
        for attempt in range(_MAX_RETRIES):
            try:
                async with session.post(self.webhook_url, data=data_factory()) as response:
                    if response.status in (200, 204):
                        return True
                    if response.status == 429:
                        retry_after = float(response.headers.get('Retry-After', delay))
                        logger.warning(f'Discord rate-limited; retrying after {retry_after:.1f}s')
                        await asyncio.sleep(retry_after)
                        delay = retry_after * 2
                        continue
                    if response.status in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                        logger.warning(f'Discord returned {response.status}; retrying in {delay:.1f}s')
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    logger.error(f'Discord webhook returned status {response.status}')
                    return False
            except aiohttp.ClientError as e:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(f'Discord request error ({e}); retrying in {delay:.1f}s')
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f'Discord HTTP error after {_MAX_RETRIES} attempts: {e}')
                    return False
        return False

    async def send_message(
        self,
        text: Optional[str] = None,
        media_data: Optional[bytes] = None,
        filename: str = 'file'
    ) -> bool:
        """Send message to Discord."""
        try:
            if media_data:
                file_size_mb = len(media_data) / (1024 * 1024)
                if filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    logger.info(f'Sending photo: {filename} ({file_size_mb:.2f}MB)')
                elif filename.endswith(('.mp4', '.mov', '.avi', '.webm')):
                    logger.info(f'Sending video: {filename} ({file_size_mb:.2f}MB)')
                else:
                    logger.info(f'Sending document: {filename} ({file_size_mb:.2f}MB)')
            elif text:
                logger.info('Sending text message')

            if media_data and len(media_data) > self.max_file_size_bytes:
                logger.warning(
                    f'File too large: {len(media_data) / (1024 * 1024):.2f}MB '
                    f'(max: {self.max_file_size_mb}MB), skipping'
                )
                if text:
                    def text_only_data():
                        d = aiohttp.FormData()
                        d.add_field('content', text)
                        return d
                    success = await self._post_with_retry(text_only_data)
                    if success:
                        logger.info('Sent text-only fallback (media exceeded size limit)')
                    return success
                return False

            def build_data():
                d = aiohttp.FormData()
                if text:
                    d.add_field('content', text)
                if media_data:
                    d.add_field(
                        'file',
                        media_data,
                        filename=filename,
                        content_type='application/octet-stream'
                    )
                return d

            if not text and not media_data:
                logger.warning('No content to send')
                return False

            success = await self._post_with_retry(build_data)
            if success:
                logger.info('Message sent to Discord successfully')
            return success

        except Exception as e:
            logger.error(f'Failed to send to Discord: {e}', exc_info=True)
            return False

    async def send_file(
        self,
        text: Optional[str],
        file_path: str,
        filename: str = 'file'
    ) -> bool:
        """Send a file from disk to Discord, streaming without loading entirely into memory."""
        try:
            import os
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)

            if file_size > self.max_file_size_bytes:
                logger.warning(
                    f'File too large: {file_size_mb:.2f}MB '
                    f'(max: {self.max_file_size_mb}MB), skipping'
                )
                if text:
                    def text_only_data():
                        d = aiohttp.FormData()
                        d.add_field('content', text)
                        return d
                    success = await self._post_with_retry(text_only_data)
                    if success:
                        logger.info('Sent text-only fallback (media exceeded size limit)')
                    return success
                return False

            logger.info(f'Sending file: {filename} ({file_size_mb:.2f}MB)')

            def build_data():
                d = aiohttp.FormData()
                if text:
                    d.add_field('content', text)
                d.add_field(
                    'file',
                    open(file_path, 'rb'),
                    filename=filename,
                    content_type='application/octet-stream'
                )
                return d

            success = await self._post_with_retry(build_data)
            if success:
                logger.info('File sent to Discord successfully')
            return success

        except Exception as e:
            logger.error(f'Failed to send file to Discord: {e}', exc_info=True)
            return False

    async def send_photo(
        self,
        text: Optional[str],
        photo_data: bytes,
        filename: str = 'photo.jpg'
    ) -> bool:
        """Send photo to Discord."""
        return await self.send_message(text, photo_data, filename)

    async def send_video(
        self,
        text: Optional[str],
        video_data: bytes,
        filename: str = 'video.mp4'
    ) -> bool:
        """Send video to Discord."""
        return await self.send_message(text, video_data, filename)

    async def send_document(
        self,
        text: Optional[str],
        document_data: bytes,
        filename: str = 'document'
    ) -> bool:
        """Send document to Discord."""
        return await self.send_message(text, document_data, filename)

    async def send_multiple_media(
        self,
        text: Optional[str],
        media_items: list
    ) -> bool:
        """Send multiple media files in one message to Discord."""
        try:
            valid_items = []
            for item in media_items:
                file_path = item.get('file_path')
                if file_path:
                    import os
                    if os.path.getsize(file_path) > self.max_file_size_bytes:
                        logger.warning(
                            f'File too large: {os.path.getsize(file_path) / (1024 * 1024):.2f}MB '
                            f'(max: {self.max_file_size_mb}MB), skipping {item["filename"]}'
                        )
                    else:
                        valid_items.append(item)
                else:
                    data = item.get('data')
                    if data and len(data) > self.max_file_size_bytes:
                        logger.warning(
                            f'File too large: {len(data) / (1024 * 1024):.2f}MB '
                            f'(max: {self.max_file_size_mb}MB), skipping {item["filename"]}'
                        )
                    elif data:
                        valid_items.append(item)

            if len(valid_items) > _DISCORD_MAX_ATTACHMENTS:
                logger.warning(
                    f'Album has {len(valid_items)} items, capping at {_DISCORD_MAX_ATTACHMENTS} (Discord limit)'
                )
                valid_items = valid_items[:_DISCORD_MAX_ATTACHMENTS]

            if not valid_items and not text:
                logger.warning('No content to send')
                return False

            def build_data():
                d = aiohttp.FormData()
                if text:
                    d.add_field('content', text)
                for idx, item in enumerate(valid_items):
                    field_name = f'file{idx}' if idx > 0 else 'file'
                    file_path = item.get('file_path')
                    if file_path:
                        d.add_field(
                            field_name,
                            open(file_path, 'rb'),
                            filename=item['filename'],
                            content_type='application/octet-stream'
                        )
                    else:
                        d.add_field(
                            field_name,
                            item['data'],
                            filename=item['filename'],
                            content_type='application/octet-stream'
                        )
                return d

            success = await self._post_with_retry(build_data)
            if success:
                logger.info(f'Message with {len(valid_items)} media items sent to Discord successfully')
            return success

        except Exception as e:
            logger.error(f'Failed to send to Discord: {e}', exc_info=True)
            return False
