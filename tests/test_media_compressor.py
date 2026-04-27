"""Unit tests for media compressor module."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from io import BytesIO
import subprocess

# Import media compressor first
from src.media_compressor import MediaCompressor

# Then check for PIL availability for tests that need it
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None  # Placeholder


@pytest.fixture
def skip_if_no_pil():
    """Skip test if PIL is not available."""
    if not HAS_PIL:
        pytest.skip("PIL not installed")


class TestCanCompress:
    """Test can_compress static method."""
    
    def test_already_under_limit(self):
        # 1MB file, 10MB limit
        data = b"x" * (1 * 1024 * 1024)
        can_compress, reason = MediaCompressor.can_compress(data, 10)
        assert can_compress is False
        assert "already within" in reason
    
    def test_source_too_large(self):
        # 300MB file, 10MB limit (exceeds MAX_SOURCE_SIZE_MB)
        data = b"x" * (300 * 1024 * 1024)
        can_compress, reason = MediaCompressor.can_compress(data, 10)
        assert can_compress is False
        assert "too large" in reason
    
    def test_valid_image(self, skip_if_no_pil):
        # Create a small valid JPEG image
        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        image_data = buffer.getvalue()
        
        # Make sure image is larger than limit
        if len(image_data) <= 0.01 * 1024 * 1024:
            # If image is too small, make it bigger
            img = Image.new('RGB', (1920, 1080), color='red')
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=95)
            image_data = buffer.getvalue()
        
        can_compress, reason = MediaCompressor.can_compress(image_data, 0.01)
        assert can_compress is True
        assert "Image compression" in reason
    
    def test_invalid_image_data(self, skip_if_no_pil):
        # Invalid image data
        data = b"not an image" * 100
        can_compress, reason = MediaCompressor.can_compress(data, 0.001)
        assert can_compress is False


class TestCompressImage:
    """Test compress_image method."""
    
    async def test_no_compression_needed(self, skip_if_no_pil):
        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        image_data = buffer.getvalue()
        
        result = await MediaCompressor.compress_image(image_data, 10)  # 10MB limit
        assert result is None  # Already under limit
    
    async def test_compress_success(self, skip_if_no_pil):
        # Create a large image (high quality)
        img = Image.new('RGB', (1920, 1080), color='blue')
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        large_image_data = buffer.getvalue()
        
        with patch.object(MediaCompressor, 'can_compress', return_value=(True, "Image compression feasible")):
            result = await MediaCompressor.compress_image(large_image_data, 0.5)  # 0.5MB limit
        
        assert result is not None
        assert len(result) < len(large_image_data)
    
    @pytest.mark.asyncio
    async def test_compress_cannot_compress(self):
        with patch.object(MediaCompressor, 'can_compress', return_value=(False, "Source too large")):
            result = await MediaCompressor.compress_image(b"data", 1)
            assert result is None
    
    async def test_compress_ratio_too_low(self, skip_if_no_pil):
        img = Image.new('RGB', (100, 100), color='green')
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=10)  # Already low quality
        image_data = buffer.getvalue()
        
        with patch.object(MediaCompressor, 'can_compress', return_value=(True, "Image compression feasible")):
            result = await MediaCompressor.compress_image(image_data, 100)  # Huge limit
        
        # Should return None because compression ratio would be too low
        assert result is None
    
    @pytest.mark.asyncio
    async def test_compress_exception(self):
        with patch('src.media_compressor.Image') as mock_image:
            mock_image.open.side_effect = Exception("PIL error")
            with patch.object(MediaCompressor, 'can_compress', return_value=(True, "feasible")):
                result = await MediaCompressor.compress_image(b"data", 1)
                assert result is None
    
    async def test_compress_rgba_image(self, skip_if_no_pil):
        # Create RGBA image
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        rgba_data = buffer.getvalue()
        
        with patch.object(MediaCompressor, 'can_compress', return_value=(True, "Image compression feasible")):
            result = await MediaCompressor.compress_image(rgba_data, 0.1)
        
        assert result is not None


class TestCompressVideo:
    """Test compress_video method."""
    
    @pytest.mark.asyncio
    async def test_no_compression_needed(self):
        data = b"small video"
        result = await MediaCompressor.compress_video(data, 10)  # 10MB limit
        assert result is None  # Already under limit
    
    @pytest.mark.asyncio
    async def test_source_too_large(self):
        data = b"x" * (600 * 1024 * 1024)  # 600MB > 500MB limit
        result = await MediaCompressor.compress_video(data, 10)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ffmpeg_not_available(self):
        data = b"x" * (20 * 1024 * 1024)  # 20MB
        
        with patch('src.media_compressor.subprocess.run', side_effect=FileNotFoundError("ffmpeg not found")):
            result = await MediaCompressor.compress_video(data, 10)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_compress_video_success(self):
        data = b"x" * (20 * 1024 * 1024)  # 20MB
        
        with patch('src.media_compressor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            with patch('src.media_compressor.MediaCompressor._get_video_duration', return_value=60.0):
                # Check if ffmpeg module is available
                try:
                    import ffmpeg as ffmpeg_module
                    has_ffmpeg = True
                except ImportError:
                    has_ffmpeg = False
                
                if has_ffmpeg:
                    with patch('src.media_compressor.ffmpeg') as mock_ffmpeg:
                        mock_process = AsyncMock()
                        mock_process.communicate = AsyncMock(return_value=(b"compressed_data", b""))
                        mock_process.returncode = 0
                        
                        mock_stream = Mock()
                        mock_stream.run_async = Mock(return_value=mock_process)
                        
                        mock_output = Mock()
                        mock_output.__getitem__ = Mock(return_value=mock_stream)
                        
                        mock_input = Mock()
                        mock_input.output = Mock(return_value=mock_output)
                        mock_ffmpeg.input = Mock(return_value=mock_input)
                        
                        result = await MediaCompressor.compress_video(data, 10)
                        assert result == b"compressed_data"
                else:
                    # ffmpeg module not available, skip test
                    pytest.skip("ffmpeg-python not installed")
    
    @pytest.mark.asyncio
    async def test_compress_video_ffmpeg_failed(self):
        data = b"x" * (20 * 1024 * 1024)
        
        try:
            import ffmpeg as ffmpeg_module
            has_ffmpeg = True
        except ImportError:
            has_ffmpeg = False
        
        if not has_ffmpeg:
            pytest.skip("ffmpeg-python not installed")
        
        with patch('src.media_compressor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            with patch('src.media_compressor.MediaCompressor._get_video_duration', return_value=60.0):
                with patch('src.media_compressor.ffmpeg') as mock_ffmpeg:
                    mock_process = Mock()
                    mock_process.communicate = Mock(return_value=(b"", b"error"))
                    mock_process.returncode = 1
                    
                    mock_stream = Mock()
                    mock_stream.run_async = Mock(return_value=mock_process)
                    
                    mock_output = Mock()
                    mock_output.__getitem__ = Mock(return_value=mock_stream)
                    
                    mock_input = Mock()
                    mock_input.output = Mock(return_value=mock_output)
                    mock_ffmpeg.input = Mock(return_value=mock_input)
                    
                    result = await MediaCompressor.compress_video(data, 10)
                    assert result is None
    
    @pytest.mark.asyncio
    async def test_ffmpeg_python_not_available(self):
        data = b"x" * (20 * 1024 * 1024)
        
        with patch('src.media_compressor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            with patch('builtins.__import__', side_effect=ImportError("No ffmpeg module")):
                result = await MediaCompressor.compress_video(data, 10)
                assert result is None


class TestGetVideoDuration:
    """Test _get_video_duration method."""
    
    @pytest.mark.asyncio
    async def test_get_duration_success(self):
        mock_probe_data = b'{"format": {"duration": "120.5"}}'
        
        with patch('src.media_compressor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=mock_probe_data, stderr=b"")
            
            duration = await MediaCompressor._get_video_duration(b"video_data")
            assert duration == 120.5
    
    @pytest.mark.asyncio
    async def test_get_duration_ffprobe_failed(self):
        with patch('src.media_compressor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout=b"", stderr=b"error")
            
            duration = await MediaCompressor._get_video_duration(b"video_data")
            assert duration is None
    
    @pytest.mark.asyncio
    async def test_get_duration_timeout(self):
        with patch('src.media_compressor.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)):
            duration = await MediaCompressor._get_video_duration(b"video_data")
            assert duration is None
    
    @pytest.mark.asyncio
    async def test_get_duration_exception(self):
        with patch('src.media_compressor.subprocess.run', side_effect=Exception("Unexpected error")):
            duration = await MediaCompressor._get_video_duration(b"video_data")
            assert duration is None


class TestCompressMedia:
    """Test compress_media method."""
    
    @pytest.mark.asyncio
    async def test_compress_photo(self, skip_if_no_pil):
        with patch.object(MediaCompressor, 'compress_image', new_callable=AsyncMock) as mock_compress:
            mock_compress.return_value = b"compressed"
            
            result = await MediaCompressor.compress_media(b"data", 'photo', 10, 'test.jpg')
            assert result == b"compressed"
            mock_compress.assert_called_once_with(b"data", 10, 'test.jpg')
    
    @pytest.mark.asyncio
    async def test_compress_video(self):
        with patch.object(MediaCompressor, 'compress_video', new_callable=AsyncMock) as mock_compress:
            mock_compress.return_value = b"compressed"
            
            result = await MediaCompressor.compress_media(b"data", 'video', 10, 'test.mp4')
            assert result == b"compressed"
            mock_compress.assert_called_once_with(b"data", 10, 'test.mp4')
    
    @pytest.mark.asyncio
    async def test_compress_document_not_supported(self):
        result = await MediaCompressor.compress_media(b"data", 'document', 10, 'test.pdf')
        assert result is None
    
    @pytest.mark.asyncio
    async def test_compress_unknown_type(self):
        result = await MediaCompressor.compress_media(b"data", 'unknown', 10, 'test.xyz')
        assert result is None


class TestConstants:
    """Test class constants."""
    
    def test_constants_exist(self):
        assert MediaCompressor.MIN_QUALITY == 60
        assert MediaCompressor.MAX_QUALITY == 95
        assert MediaCompressor.TARGET_QUALITY == 85
        assert MediaCompressor.MAX_COMPRESSION_RATIO == 0.3
        assert MediaCompressor.MAX_SOURCE_SIZE_MB == 200
        assert MediaCompressor.MAX_VIDEO_SOURCE_SIZE_MB == 500
