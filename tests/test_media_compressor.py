"""Unit tests for media compressor."""

import pytest
from unittest.mock import Mock, patch
from src.media_compressor import MediaCompressor


class TestMediaCompressor:
    """Test media compression logic."""

    def test_can_compress_image_within_limit(self):
        """Test that image within size limit doesn't need compression."""
        small_image = b'x' * (5 * 1024 * 1024)  # 5MB
        can_compress, reason = MediaCompressor.can_compress(small_image, 10)
        
        assert not can_compress
        assert "already within size limit" in reason

    def test_can_compress_image_too_large(self):
        """Test that very large images cannot be compressed."""
        huge_image = b'x' * (60 * 1024 * 1024)  # 60MB
        can_compress, reason = MediaCompressor.can_compress(huge_image, 25)
        
        assert not can_compress
        assert "too large" in reason

    def test_can_compress_non_image(self):
        """Test that non-image data cannot be compressed."""
        non_image = b'This is not an image' * 1000
        # Make it large enough to exceed the limit but not too large
        large_non_image = non_image * 500  # ~5MB
        
        can_compress, reason = MediaCompressor.can_compress(large_non_image, 2)
        
        assert not can_compress
        assert "compressible image format" in reason.lower()

    def test_can_compress_feasible_image(self):
        """Test that compressible image is identified correctly."""
        # Create a simple 1x1 PNG (minimal valid PNG)
        minimal_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        # Make it 15MB by repeating
        large_png = minimal_png * 500000
        
        can_compress, reason = MediaCompressor.can_compress(large_png, 10)
        
        assert can_compress
        assert "feasible" in reason

    @pytest.mark.asyncio
    async def test_compress_image_too_large_source(self):
        """Test compression of too large source file."""
        huge_image = b'x' * (60 * 1024 * 1024)  # 60MB
        
        result = await MediaCompressor.compress_image(huge_image, 25, 'huge.jpg')
        
        assert result is None

    @pytest.mark.asyncio
    async def test_compress_non_image(self):
        """Test compression of non-image data."""
        non_image = b'This is not an image' * 1000
        
        result = await MediaCompressor.compress_image(non_image, 10, 'text.jpg')
        
        assert result is None

    @pytest.mark.asyncio
    async def test_compress_image_invalid_format(self):
        """Test compression of invalid image data."""
        invalid_image = b'\x00\x00\x00\x00' * 100
        
        result = await MediaCompressor.compress_image(invalid_image, 10, 'invalid.jpg')
        
        assert result is None

    @pytest.mark.asyncio
    async def test_compress_media_video(self):
        """Test that video compression is not implemented."""
        video_data = b'fake video data' * 1000
        
        result = await MediaCompressor.compress_media(video_data, 'video', 10, 'video.mp4')
        
        assert result is None

    @pytest.mark.asyncio
    async def test_compress_media_document(self):
        """Test that document compression is not implemented."""
        doc_data = b'fake document data' * 1000
        
        result = await MediaCompressor.compress_media(doc_data, 'document', 10, 'doc.pdf')
        
        assert result is None

    @pytest.mark.asyncio
    async def test_compress_media_photo_calls_image_compressor(self):
        """Test that photo compression calls image compressor."""
        photo_data = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        ) * 100000  # Make it large enough to trigger compression
        
        with patch.object(MediaCompressor, 'compress_image', return_value=b'compressed'):
            result = await MediaCompressor.compress_media(photo_data, 'photo', 5, 'photo.png')
            
            assert result == b'compressed'

    def test_quality_constants(self):
        """Test that quality constants are set correctly."""
        assert MediaCompressor.MIN_QUALITY == 60
        assert MediaCompressor.MAX_QUALITY == 95
        assert MediaCompressor.TARGET_QUALITY == 85
        assert MediaCompressor.MAX_COMPRESSION_RATIO == 0.3
        assert MediaCompressor.MAX_SOURCE_SIZE_MB == 50
