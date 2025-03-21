import pytest
import pytest_asyncio  # Add this import
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database import (
    Base, TrackManager, create_track_table
)
from spotify_client import (
    SpotifyTrack, SpotifyArtist, AudioFeatures
)

# Use an in-memory SQLite database for testing
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_db():
    """Create a test database and session"""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestingSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with TestingSessionLocal() as session:
        yield session  # This yields the actual session, not a generator

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
def sample_tracks() -> list[SpotifyTrack]:
    """Create sample track data for testing"""
    return [
        SpotifyTrack(
            id="track1",
            name="Track One",
            artists=[SpotifyArtist(id="artist1", name="Test Artist")],
            album_id="album1",
            album_name="Test Album",
            popularity=80,
            album_art_url="https://example.com/cover1.jpg",
            audio_features=AudioFeatures(
                acousticness=0.5,
                danceability=0.7,
                energy=0.8
            )
        ),
        SpotifyTrack(
            id="track2",
            name="Track Two",
            artists=[
                SpotifyArtist(id="artist1", name="Test Artist"),
                SpotifyArtist(id="artist2", name="Featured Artist")
            ],
            album_id="album1",
            album_name="Test Album",
            popularity=65,
            album_art_url="https://example.com/cover1.jpg",
            audio_features=AudioFeatures(
                acousticness=0.3,
                danceability=0.9,
                energy=0.6
            )
        )
    ]

@pytest.mark.asyncio
async def test_full_track_workflow(test_db, sample_tracks):
    """Test the full workflow of creating tables, adding and retrieving tracks"""
    artist_id = "integration_test_artist"

    await TrackManager.ensure_table_exists(test_db, artist_id)
    await TrackManager.update_tracks(test_db, artist_id, sample_tracks)
    tracks = await TrackManager.get_tracks(test_db, artist_id)

    assert len(tracks) == len(sample_tracks)
    assert tracks[0].spotify_id == sample_tracks[0].spotify_id
    assert tracks[1].title == sample_tracks[1].title

    track = await TrackManager.get_track(test_db, artist_id, sample_tracks[0].spotify_id)
    assert track is not None
    assert track.title == sample_tracks[0].title

    non_existent = await TrackManager.get_track(test_db, artist_id, "nonexistent")
    assert non_existent is None
