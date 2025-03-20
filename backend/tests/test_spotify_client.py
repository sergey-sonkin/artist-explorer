import pytest
from unittest.mock import AsyncMock, patch
from spotify_client import SpotifyClient, SpotifyArtist, SpotifyAlbum, SpotifyTrack, AudioFeatures

@pytest.fixture
def spotify_client():
    with patch.dict('os.environ', {
        'SPOTIFY_CLIENT_ID': 'test_client_id',
        'SPOTIFY_CLIENT_SECRET': 'test_client_secret'
    }):
        return SpotifyClient(debug=True)

@pytest.fixture
def mock_httpx_client():
    with patch('httpx.AsyncClient') as mock_client:
        yield mock_client

@pytest.mark.asyncio
async def test_get_token(spotify_client, mock_httpx_client):
    # Mock the response from Spotify's token endpoint
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"access_token": "test_token"})
    mock_httpx_client.return_value.__aenter__.return_value.post.return_value = mock_response

    token = await spotify_client.get_token()
    assert token == "test_token"

    # Verify the token is cached
    cached_token = await spotify_client.get_token()
    assert cached_token == "test_token"
    # Verify we only made one API call
    assert mock_httpx_client.return_value.__aenter__.return_value.post.call_count == 1

@pytest.mark.asyncio
async def test_get_artist(spotify_client, mock_httpx_client):
    # Mock the response from Spotify's artist endpoint
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = AsyncMock(return_value={
        "id": "test_artist_id",
        "name": "Test Artist"
    })
    mock_httpx_client.return_value.__aenter__.return_value.get.return_value = mock_response

    artist = await spotify_client.get_artist("test_artist_id")
    assert isinstance(artist, SpotifyArtist)
    assert artist.id == "test_artist_id"
    assert artist.name == "Test Artist"

@pytest.mark.asyncio
async def test_get_artist_albums(spotify_client, mock_httpx_client):
    # Mock the response from Spotify's albums endpoint
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={
        "items": [
            {
                "id": "album1",
                "name": "Album 1",
                "album_type": "album",
                "release_date": "2024-01-01",
                "total_tracks": 10,
                "images": [{"url": "http://example.com/cover1.jpg"}],
                "artists": [{"id": "artist1", "name": "Artist 1"}],
                "external_urls": {"spotify": "http://spotify.com/album1"},
                "popularity": 80,
                "label": "Test Label"
            }
        ],
        "next": None
    })
    mock_httpx_client.return_value.__aenter__.return_value.get.return_value = mock_response

    albums = await spotify_client.get_artist_albums("test_artist_id")
    assert len(albums) == 1
    assert isinstance(albums[0], SpotifyAlbum)
    assert albums[0].id == "album1"
    assert albums[0].name == "Album 1"
    assert albums[0].cover_image_url == "http://example.com/cover1.jpg"

@pytest.mark.asyncio
async def test_get_audio_features_batch(spotify_client, mock_httpx_client):
    # Mock the response from Spotify's audio features endpoint
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = AsyncMock(return_value={
        "audio_features": [
            {
                "id": "track1",
                "acousticness": 0.5,
                "danceability": 0.7,
                "energy": 0.8,
                "instrumentalness": 0.3,
                "key": 1,
                "liveness": 0.2,
                "loudness": -10.0,
                "mode": 1,
                "speechiness": 0.1,
                "tempo": 120.0,
                "time_signature": 4,
                "valence": 0.6
            }
        ]
    })
    mock_httpx_client.return_value.__aenter__.return_value.get.return_value = mock_response

    features = await spotify_client.get_audio_features_batch(["track1"])
    assert len(features) == 1
    assert isinstance(features["track1"], AudioFeatures)
    assert features["track1"].acousticness == 0.5
    assert features["track1"].danceability == 0.7
    assert features["track1"].energy == 0.8

@pytest.mark.asyncio
async def test_get_all_artist_tracks(spotify_client, mock_httpx_client):
    # Mock the responses for albums and tracks
    mock_album_response = AsyncMock()
    mock_album_response.json = AsyncMock(return_value={
        "items": [
            {
                "id": "album1",
                "name": "Album 1",
                "album_type": "album",
                "release_date": "2024-01-01",
                "total_tracks": 2,
                "images": [{"url": "http://example.com/cover1.jpg"}],
                "artists": [{"id": "artist1", "name": "Artist 1"}],
                "external_urls": {"spotify": "http://spotify.com/album1"}
            }
        ],
        "next": None
    })

    mock_tracks_response = AsyncMock()
    mock_tracks_response.json = AsyncMock(return_value={
        "items": [
            {
                "id": "track1",
                "name": "Track 1",
                "artists": [{"id": "artist1", "name": "Artist 1"}]
            },
            {
                "id": "track2",
                "name": "Track 2",
                "artists": [{"id": "artist1", "name": "Artist 1"}]
            }
        ],
        "next": None
    })

    mock_features_response = AsyncMock()
    mock_features_response.status_code = 200
    mock_features_response.json = AsyncMock(return_value={
        "audio_features": [
            {
                "id": "track1",
                "acousticness": 0.5,
                "danceability": 0.7,
                "energy": 0.8,
                "instrumentalness": 0.3,
                "key": 1,
                "liveness": 0.2,
                "loudness": -10.0,
                "mode": 1,
                "speechiness": 0.1,
                "tempo": 120.0,
                "time_signature": 4,
                "valence": 0.6
            },
            {
                "id": "track2",
                "acousticness": 0.4,
                "danceability": 0.6,
                "energy": 0.7,
                "instrumentalness": 0.2,
                "key": 2,
                "liveness": 0.3,
                "loudness": -9.0,
                "mode": 0,
                "speechiness": 0.2,
                "tempo": 110.0,
                "time_signature": 4,
                "valence": 0.5
            }
        ]
    })

    # Set up the mock client to return different responses for different URLs
    async def mock_get(*args, **kwargs):
        url = args[0]
        if "albums" in url and "tracks" not in url:
            return mock_album_response
        elif "tracks" in url:
            return mock_tracks_response
        elif "audio-features" in url:
            return mock_features_response
        return mock_album_response

    mock_httpx_client.return_value.__aenter__.return_value.get.side_effect = mock_get

    tracks = await spotify_client.get_all_artist_tracks("test_artist_id")
    assert len(tracks) == 2
    assert all(isinstance(track, SpotifyTrack) for track in tracks)
    assert all(track.audio_features is not None for track in tracks)
    assert tracks[0].title == "Track 1"
    assert tracks[1].title == "Track 2" 