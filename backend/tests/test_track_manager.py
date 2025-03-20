import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from database import TrackManager, TrackResponse
from spotify_client import SpotifyTrack, SpotifyArtist

@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def sample_tracks():
    return [
        SpotifyTrack(
            id="track1",  # Note: SpotifyTrack uses 'id', which gets aliased to spotify_id
            name="Test Track 1",  # Note: SpotifyTrack uses 'name', which gets aliased to title
            album_id="album1",
            album_name="Test Album 1",
            popularity=80,
            artists=[SpotifyArtist(id="artist1", name="Test Artist")],
            album_art_url="http://example.com/art1.jpg"
        ),
        SpotifyTrack(
            id="track2",
            name="Test Track 2",
            album_id="album2",
            album_name="Test Album 2",
            popularity=70,
            artists=[SpotifyArtist(id="artist1", name="Test Artist")],
            album_art_url="http://example.com/art2.jpg"
        )
    ]

def test_get_table_name():
    """Test table name generation"""
    artist_id = "test-artist-123"
    expected = "tracks_test_artist_123"
    assert TrackManager.get_table_name(artist_id) == expected

@pytest.mark.asyncio
async def test_ensure_table_exists(mock_db):
    """Test table creation"""
    artist_id = "test-artist"
    
    # Mock the engine and connection
    with patch('database.engine') as mock_engine:
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        
        await TrackManager.ensure_table_exists(mock_db, artist_id)
        
        # Verify that run_sync was called
        assert mock_conn.run_sync.called

@pytest.mark.asyncio
async def test_update_tracks(mock_db, sample_tracks):
    """Test updating tracks for an artist"""
    artist_id = "test-artist"
    
    # Mock ensure_table_exists
    with patch.object(TrackManager, 'ensure_table_exists') as mock_ensure:
        # Mock the execute calls
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value = AsyncMock()
        
        await TrackManager.update_tracks(mock_db, artist_id, sample_tracks)
        
        # Verify table was ensured
        mock_ensure.assert_called_once_with(mock_db, artist_id)
        
        # Verify delete and inserts were executed
        assert mock_db.execute.call_count >= len(sample_tracks) + 1  # delete + inserts
        
        # Verify commit was called
        mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_get_tracks(mock_db):
    """Test retrieving all tracks for an artist"""
    artist_id = "test-artist"
    
    # Create a mock row that matches what SQLAlchemy would return
    mock_row = MagicMock(
        spotify_id="track1",
        title="Test Track",
        album_id="album1", 
        album_name="Test Album",
        popularity=80,
        artists=["Test Artist"],
        album_art_url="http://example.com/art.jpg"
    )
    
    # Mock the execute and fetchall
    mock_result = AsyncMock()
    mock_result.fetchall = lambda: [mock_row]  # Use lambda to avoid coroutine issues
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    # Mock ensure_table_exists
    with patch.object(TrackManager, 'ensure_table_exists'):
        tracks = await TrackManager.get_tracks(mock_db, artist_id)
        
        assert len(tracks) == 1
        assert isinstance(tracks[0], TrackResponse)
        assert tracks[0].spotify_id == "track1"
        assert tracks[0].title == "Test Track"
        assert tracks[0].album_id == "album1"
        assert tracks[0].album_name == "Test Album"
        assert tracks[0].popularity == 80
        assert tracks[0].artists == ["Test Artist"]
        assert tracks[0].album_art_url == "http://example.com/art.jpg"

@pytest.mark.asyncio
async def test_get_track(mock_db):
    """Test retrieving a specific track"""
    artist_id = "test-artist"
    track_id = "track1"
    
    # Create a mock row that matches what SQLAlchemy would return
    mock_row = MagicMock(
        spotify_id=track_id,
        title="Test Track",
        album_id="album1",
        album_name="Test Album",
        popularity=80,
        artists=["Test Artist"],
        album_art_url="http://example.com/art.jpg"
    )
    
    # Mock the execute and first
    mock_result = AsyncMock()
    mock_result.first = lambda: mock_row  # Use lambda to avoid coroutine issues
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    # Mock ensure_table_exists
    with patch.object(TrackManager, 'ensure_table_exists'):
        track = await TrackManager.get_track(mock_db, artist_id, track_id)
        
        assert track is not None
        assert isinstance(track, TrackResponse)
        assert track.spotify_id == track_id
        assert track.title == "Test Track"
        assert track.album_id == "album1"
        assert track.album_name == "Test Album"
        assert track.popularity == 80
        assert track.artists == ["Test Artist"]
        assert track.album_art_url == "http://example.com/art.jpg"

@pytest.mark.asyncio
async def test_get_track_not_found(mock_db):
    """Test retrieving a non-existent track"""
    artist_id = "test-artist"
    track_id = "nonexistent"
    
    # Mock the execute and first
    mock_result = AsyncMock()
    mock_result.first = lambda: None  # Use lambda to avoid coroutine issues
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    # Mock ensure_table_exists
    with patch.object(TrackManager, 'ensure_table_exists'):
        track = await TrackManager.get_track(mock_db, artist_id, track_id)
        assert track is None

@pytest.mark.asyncio
async def test_update_tracks_empty_list(mock_db):
    """Test updating tracks with an empty list"""
    artist_id = "test-artist"
    
    with patch.object(TrackManager, 'ensure_table_exists') as mock_ensure:
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value = AsyncMock()
        
        await TrackManager.update_tracks(mock_db, artist_id, [])
        
        # Should still ensure table exists
        mock_ensure.assert_called_once_with(mock_db, artist_id)
        # Should still execute delete
        assert mock_db.execute.call_count == 1  # only delete, no inserts
        mock_db.commit.assert_called_once() 