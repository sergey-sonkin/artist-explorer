import pytest
import asyncio
from redis import Redis
from redis.exceptions import ConnectionError
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
import json
from dataclasses import asdict

from database import TrackResponse
from redis_managers import Search, TreeNode, Song, SearchManager, SessionManager
from fast_api_test import event_generator

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def redis_client():
    """Create a Redis client for the test session"""
    client = Redis(host="localhost", port=6379, db=1)  # Use DB 1 for testing
    try:
        client.ping()
    except ConnectionError as e:
        pytest.skip(
            "\nRedis server not available. To run integration tests:\n"
            "1. Install Redis if not installed:\n"
            "   - macOS: brew install redis\n"
            "   - Linux: sudo apt-get install redis-server\n"
            "2. Start Redis server:\n"
            "   - macOS: brew services start redis\n"
            "   - Linux: sudo service redis-server start\n"
            "3. Verify Redis is running: redis-cli ping\n"
            "Then run the tests again."
        )
    except Exception as e:
        pytest.skip(f"Unexpected error connecting to Redis: {str(e)}")

    yield client

    # Cleanup after all tests
    try:
        client.flushdb()
        client.close()
    except:
        pass  # Ignore cleanup errors

@pytest.fixture
def search_manager(redis_client):
    """Create a SearchManager instance"""
    manager = SearchManager(redis_client)
    yield manager
    # Cleanup after each test
    for key in redis_client.keys("search:*"):
        redis_client.delete(key)

@pytest.fixture
def session_manager(redis_client):
    """Create a SessionManager instance"""
    manager = SessionManager(redis_client)
    yield manager
    # Cleanup after each test
    for key in redis_client.keys("session:*"):
        redis_client.delete(key)

@pytest.fixture
def mock_db():
    """Mock DB remains as is since we're not testing DB integration"""
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def sample_track_responses():
    """Reuse sample track responses from unit tests"""
    return [
        TrackResponse(
            spotify_id="track1",
            title="Test Track 1",
            album_id="album1",
            album_name="Test Album 1",
            popularity=80,
            artists=["Test Artist"],
            album_art_url="http://example.com/art1.jpg"
        ),
        TrackResponse(
            spotify_id="track2",
            title="Test Track 2",
            album_id="album2",
            album_name="Test Album 2",
            popularity=70,
            artists=["Test Artist"],
            album_art_url="http://example.com/art2.jpg"
        )
    ]

@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_generator_with_real_redis(
    mock_db, redis_client, search_manager, session_manager, sample_track_responses
):
    """Integration test for event generator using real Redis"""
    search_id = "test-search"
    artist_id = "test-artist"
    artist_name = "Test Artist"

    # Create a real search in Redis
    search = Search(search_id=search_id, artist_id=artist_id, artist_name=artist_name)
    await search_manager.create_search(search_id=search_id, search=search)

    # Mock only the non-Redis components and patch Redis managers
    with patch('fast_api_test.search_manager', search_manager):
        with patch('fast_api_test.session_manager', session_manager):
            with patch('fast_api_test.search_songs_for_artist', return_value=sample_track_responses):
                mock_tree = TreeNode(
                    song=Song(
                        song_id="track1",
                        title="Test Track 1",
                        artists=["Test Artist"],
                        album_name="Test Album 1",
                        album_art_url="http://example.com/art1.jpg"
                    )
                )
                with patch('fast_api_test.create_decision_tree', return_value=mock_tree):
                    # Collect all events
                    events = []
                    async for event in event_generator(search_id, mock_db):
                        events.append(event)

                    # Verify events
                    assert len(events) == 2
                    assert '"status": "searching"' in events[0]
                    assert '"status": "completed"' in events[1]

                    # Verify Redis state
                    assert await search_manager.get_search(search_id) is None  # Search should be deleted
                    session = await session_manager.get_session(search_id)
                    assert session is not None
                    breakpoint()
                    assert session['tree']['song']['song_id'] == "track1"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_searches_with_real_redis(
    mock_db, redis_client, search_manager, session_manager, sample_track_responses
):
    """Test multiple concurrent searches using real Redis"""
    search_ids = ["search1", "search2", "search3"]
    artist_id = "test-artist"
    artist_name = "Test Artist"

    # Create multiple searches
    for search_id in search_ids:
        search = Search(search_id=search_id, artist_id=artist_id, artist_name=artist_name)
        await search_manager.create_search(search_id=search_id, search=search)

    # Mock non-Redis components and patch Redis managers
    with patch('fast_api_test.search_manager', search_manager):
        with patch('fast_api_test.session_manager', session_manager):
            with patch('fast_api_test.search_songs_for_artist', return_value=sample_track_responses):
                mock_tree = TreeNode(
                    song=Song(
                        song_id="track1",
                        title="Test Track 1",
                        artists=["Test Artist"],
                        album_name="Test Album 1",
                        album_art_url="http://example.com/art1.jpg"
                    )
                )
                with patch('fast_api_test.create_decision_tree', return_value=mock_tree):
                    # Run searches concurrently
                    async def run_search(search_id):
                        events = []
                        async for event in event_generator(search_id, mock_db):
                            events.append(event)
                        return events

                    tasks = [run_search(search_id) for search_id in search_ids]
                    results = await asyncio.gather(*tasks)

                    # Verify all searches completed successfully
                    for events in results:
                        assert len(events) == 2
                        assert '"status": "searching"' in events[0]
                        assert '"status": "completed"' in events[1]

                    # Verify Redis state
                    for search_id in search_ids:
                        assert await search_manager.get_search(search_id) is None
                        session = await session_manager.get_session(search_id)
                        assert session is not None

@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_generator_search_not_found(mock_db, redis_client, search_manager, session_manager):
    """Test event generator when search doesn't exist in Redis"""
    search_id = "nonexistent-search"

    # Mock Redis managers in the event_generator module
    with patch('fast_api_test.search_manager', search_manager):
        with patch('fast_api_test.session_manager', session_manager):
            # Collect all events
            events = []
            async for event in event_generator(search_id, mock_db):
                events.append(event)

            # Verify we get searching and error events
            assert len(events) == 2
            assert '"status": "searching"' in events[0]
            assert '"status": "error"' in events[1]
            assert 'Search nonexistent-search not found' in events[1]

@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_generator_malformed_search(mock_db, redis_client, search_manager, session_manager):
    """Test event generator when search data in Redis is malformed"""
    search_id = "malformed-search"

    # Create a malformed search directly in Redis
    redis_client.setex(
        f"search:{search_id}",
        3600,
        json.dumps({"invalid": "data"})  # Missing required fields
    )

    # Mock Redis managers in the event_generator module
    with patch('fast_api_test.search_manager', search_manager):
        with patch('fast_api_test.session_manager', session_manager):
            # Collect all events
            events = []
            async for event in event_generator(search_id, mock_db):
                events.append(event)

            # Verify we get searching and error events
            assert len(events) == 2
            assert '"status": "searching"' in events[0]
            assert '"status": "error"' in events[1]
            assert 'unexpected keyword argument' in events[1].lower()

            # Verify the malformed search is cleaned up
            assert await search_manager.get_search(search_id) is None

@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_generator_expired_search(mock_db, redis_client, search_manager, session_manager):
    """Test event generator when search has expired in Redis"""
    search_id = "expired-search"

    # Create a search that expires immediately
    search = Search(search_id=search_id, artist_id="test-artist", artist_name="Test Artist")
    redis_client.setex(
        f"search:{search_id}",
        1,  # Expire after 1 second
        json.dumps(asdict(search))
    )

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Mock Redis managers in the event_generator module
    with patch('fast_api_test.search_manager', search_manager):
        with patch('fast_api_test.session_manager', session_manager):
            # Collect all events
            events = []
            async for event in event_generator(search_id, mock_db):
                events.append(event)

            # Verify we get searching and error events
            assert len(events) == 2
            assert '"status": "searching"' in events[0]
            assert '"status": "error"' in events[1]
            assert 'Search expired-search not found' in events[1]
