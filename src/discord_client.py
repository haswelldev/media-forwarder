"""Discord client for sending messages via webhooks."""

import logging
from typing import Optional
import aiohttp
from io import BytesIO

logger = logging.getLogger(__name__)

# Global shared session
_shared_session: Optional[aiohttp.ClientSession] = None


async def get_shared_session() -> aiohttp.ClientSession:
    """Get or create shared aiohttp session."""
    global _shared_session
    if _shared_session is None or _shared_session.closed:
        _shared_session = aiohttp.ClientSession()
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

    async def send_message(
        self,
        text: Optional[str] = None,
        media_data: Optional[bytes] = None,
        filename: str = 'file'
    ) -> bool:
        """Send message to Discord."""
        try:
            # Use shared session for connection pooling
            session = await get_shared_session()
            
            # Check media type and log
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
            
            # Prepare data
            data = aiohttp.FormData()
            
            if text:
                data.add_field('content', text)
            
            # Handle file upload
            if media_data:
                # Check file size
                if len(media_data) > self.max_file_size_bytes:
                    logger.warning(
                        f'File too large: {len(media_data) / (1024 * 1024):.2f}MB '
                        f'(max: {self.max_file_size_mb}MB), skipping'
                    )
                    # Send text only if available
                    if text:
                        response = await session.post(self.webhook_url, data=data)
                        if response.status not in (200, 204):
                            logger.error(f'Discord webhook returned status {response.status}')
                            return False
                        await response.release()
                    return False
                
                # Add file to form data
                data.add_field(
                    'file',
                    media_data,
                    filename=filename,
                    content_type='application/octet-stream'
                )
            
            # Send request
            if len(data._fields) > 0:
                response = await session.post(self.webhook_url, data=data)
                if response.status not in (200, 204):
                    logger.error(f'Discord webhook returned status {response.status}')
                    return False
                await response.release()
            else:
                logger.warning('No content to send')
                return False

            logger.info('Message sent to Discord successfully')
            return True

        except aiohttp.ClientError as e:
            logger.error(f'Discord HTTP error: {e}')
            return False
        except Exception as e:
            logger.error(f'Failed to send to Discord: {e}', exc_info=True)
            return False

    async def send_photo(
        self,
        text: Optional[str],
        photo_data: bytes
    ) -> bool:
        """Send photo to Discord."""
        return await self.send_message(text, photo_data, 'photo.jpg')

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
            # Use shared session for connection pooling
            session = await get_shared_session()

            # Prepare data
            data = aiohttp.FormData()

            if text:
                data.add_field('content', text)

            # Add all media files
            for idx, item in enumerate(media_items):
                media_data = item['data']
                filename = item['filename']

                # Check file size for each file
                if len(media_data) > self.max_file_size_bytes:
                    logger.warning(
                        f'File too large: {len(media_data) / (1024 * 1024):.2f}MB '
                        f'(max: {self.max_file_size_mb}MB), skipping {filename}'
                    )
                    continue

                # Add file to form data
                data.add_field(
                    f'file{idx}' if idx > 0 else 'file',
                    media_data,
                    filename=filename,
                    content_type='application/octet-stream'
                )

            # Send request if we have content
            if len(data._fields) > 0:
                response = await session.post(self.webhook_url, data=data)
                if response.status not in (200, 204):
                    logger.error(f'Discord webhook returned status {response.status}')
                    return False
                await response.release()
            else:
                logger.warning('No content to send')
                return False

            logger.info(f'Message with {len(media_items)} media items sent to Discord successfully')
            return True

        except aiohttp.ClientError as e:
            logger.error(f'Discord HTTP error: {e}')
            return False
        except Exception as e:
            logger.error(f'Failed to send to Discord: {e}', exc_info=True)
            return False
