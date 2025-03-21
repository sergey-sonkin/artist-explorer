import pytest
from unittest.mock import AsyncMock, patch

from spotify_client import (
    SpotifyClient, SpotifyArtist, SpotifyTrack, AudioFeatures, SpotifyAlbum
)

@pytest.fixture
def spotify_client():
    client = SpotifyClient()
    client.token = "mock_token"
    return client

@pytest.mark.asyncio
async def test_get_token_success():
    """Test token acquisition works correctly"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"access_token": "mock_token_123"}
        mock_post.return_value = mock_response

        client = SpotifyClient()
        token = await client.get_token()

        assert token == "mock_token_123"
        assert client.token == "mock_token_123"
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_get_token_failure():
    """Test token acquisition failure"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"error": "invalid_client"}
        mock_post.return_value = mock_response

        client = SpotifyClient()
        with pytest.raises(ValueError, match="Failed to get Spotify access token"):
            await client.get_token()

@pytest.mark.asyncio
async def test_get_artist_success(spotify_client: SpotifyClient):
    """Test artist retrieval works correctly"""
    artist_id = "1Xyo4u8uXC1ZmMpatF05PJ"  # Example artist ID
    artist_data = {
        "id": artist_id,
        "name": "Test Artist",
        "popularity": 90,
        "genres": ["pop"]
    }

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = artist_data
        mock_get.return_value = mock_response

        artist = await spotify_client.get_artist(artist_id)

        assert isinstance(artist, SpotifyArtist)
        assert artist.id == artist_id
        assert artist.name == "Test Artist"

@pytest.mark.asyncio
async def test_get_artist_error(spotify_client: SpotifyClient):
    """Test artist retrieval with API error"""
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="Error fetching artist"):
            _ = await spotify_client.get_artist("invalid_id")

@pytest.mark.asyncio
async def test_get_artist_albums(spotify_client: SpotifyClient):
    """Test retrieval of artist albums"""
    artist_id = "1Xyo4u8uXC1ZmMpatF05PJ"
    mock_albums_data = {
        "items": [
            {
                "id": "album1",
                "name": "Album 1",
                "album_type": "album",
                "release_date": "2020-01-01",
                "total_tracks": 10,
                "images": [{"url": "https://example.com/cover.jpg", "height": 640, "width": 640}],
                "artists": [{"id": artist_id, "name": "Test Artist"}],
                "external_urls": {"spotify": "https://open.spotify.com/album/album1"}
            }
        ],
        "next": None
    }

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_albums_data
        mock_get.return_value = mock_response

        albums = await spotify_client.get_artist_albums(artist_id)

        assert len(albums) == 1
        assert isinstance(albums[0], SpotifyAlbum)
        assert albums[0].id == "album1"
        assert albums[0].name == "Album 1"
        assert albums[0].cover_image_url == "https://example.com/cover.jpg"

@pytest.mark.asyncio
async def test_get_album_tracks(spotify_client: SpotifyClient):
    """Test retrieval of album tracks"""
    album_id = "album1"
    mock_tracks_data = {
        "items": [
            {
                "id": "track1",
                "name": "Track 1",
                "artists": [{"id": "artist1", "name": "Test Artist"}]
            }
        ],
        "next": None
    }

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_tracks_data
        mock_get.return_value = mock_response

        tracks = await spotify_client.get_album_tracks(album_id)

        assert len(tracks) == 1
        assert isinstance(tracks[0], SpotifyTrack)
        assert tracks[0].spotify_id == "track1"
        assert tracks[0].title == "Track 1"

@pytest.mark.asyncio
async def test_get_audio_features_batch(spotify_client: SpotifyClient):
    """Test retrieval of audio features for multiple tracks"""
    track_ids = ["track1", "track2"]
    mock_features_data = {
        "audio_features": [
            {
                "id": "track1",
                "acousticness": 0.5,
                "danceability": 0.8,
                "energy": 0.6,
                "instrumentalness": 0.02,
                "key": 5,
                "liveness": 0.1,
                "loudness": -7.0,
                "mode": 1,
                "speechiness": 0.03,
                "tempo": 120.0,
                "time_signature": 4,
                "valence": 0.7
            },
            {
                "id": "track2",
                "acousticness": 0.3,
                "danceability": 0.9,
                "energy": 0.8,
                "instrumentalness": 0.01,
                "key": 7,
                "liveness": 0.2,
                "loudness": -5.0,
                "mode": 0,
                "speechiness": 0.04,
                "tempo": 130.0,
                "time_signature": 4,
                "valence": 0.9
            }
        ]
    }

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_features_data
        mock_get.return_value = mock_response

        features = await spotify_client.get_audio_features_batch(track_ids)

        assert len(features) == 2
        assert "track1" in features
        assert "track2" in features
        assert isinstance(features["track1"], AudioFeatures)
        assert features["track1"].acousticness == 0.5
        assert features["track2"].tempo == 130.0

@pytest.mark.asyncio
async def test_get_all_artist_tracks(spotify_client: SpotifyClient):
    """Test the integrated function to get all tracks by an artist"""
    artist_id = "artist1"

    # Mock the dependent methods
    with patch.object(spotify_client, 'get_artist_albums') as mock_get_albums, \
         patch.object(spotify_client, 'get_album_tracks') as mock_get_tracks, \
         patch.object(spotify_client, 'get_audio_features_batch') as mock_get_features:

        # Setup album mocks
        mock_albums = [
            SpotifyAlbum(
                id="album1",
                name="Album 1",
                album_type="album",
                release_date="2020-01-01",
                total_tracks=1,
                images=[{"url": "https://example.com/cover.jpg"}],
                artists=[{"id": artist_id, "name": "Test Artist"}],
                external_urls={"spotify": "https://open.spotify.com/album/album1"}
            )
        ]
        mock_get_albums.side_effect = [mock_albums, []]  # Albums then singles

        # Setup tracks mock
        mock_tracks = [
            SpotifyTrack(
                id="track1",
                name="Track 1",
                artists=[{"id": artist_id, "name": "Test Artist"}]
            )
        ]
        mock_get_tracks.return_value = mock_tracks

        # Setup features mock
        mock_features = {
            "track1": AudioFeatures(
                acousticness=0.5,
                danceability=0.8
            )
        }
        mock_get_features.return_value = mock_features

        # Call the method
        tracks = await spotify_client.get_all_artist_tracks(artist_id)

        # Verify results
        assert len(tracks) == 1
        assert tracks[0].spotify_id == "track1"
        assert tracks[0].album_name == "Album 1"
        assert tracks[0].album_art_url == "https://example.com/cover.jpg"
        assert tracks[0].audio_features == mock_features["track1"]
