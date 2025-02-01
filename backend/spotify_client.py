from typing import Optional, List
from pydantic import BaseModel, Field
import httpx
import base64
import os


class Artist(BaseModel):
    id: str
    name: str


class Track(BaseModel):
    title: str = Field(..., alias="name")
    spotify_id: str = Field(..., alias="id")
    artists: list[Artist]
    album_name: str | None = None
    album_id: str | None = None
    popularity: int = 0

    class Config:
        allow_population_by_field_name: bool = True


class Album(BaseModel):
    id: str
    name: str
    tracks: list[Track] = []


class SpotifyClient:
    def __init__(self):
        self.client_id: str | None = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret: str | None = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.token: str | None = None
        self.base_url: str = "https://api.spotify.com/v1"

    async def get_token(self) -> str:
        """Get or refresh Spotify access token"""
        if self.token:
            return self.token

        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode("utf-8")
        auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, data=data)
            json_result = response.json()
            self.token = json_result.get("access_token")
            return self.token

    async def get_artist_albums(self, artist_id: str) -> List[Album]:
        """Get all albums for an artist"""
        token = await self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/artists/{artist_id}/albums"
        params = {"include_groups": "album,single", "limit": 50}

        albums = []
        async with httpx.AsyncClient() as client:
            while url:
                response = await client.get(url, headers=headers, params=params)
                json_result = response.json()

                # Convert each album dict to Album model
                albums.extend([Album(**item) for item in json_result["items"]])

                url = json_result.get("next")
                params = {}

        return albums

    async def get_album_tracks(self, album_id: str) -> List[Track]:
        """Get all tracks from an album"""
        token = await self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/albums/{album_id}/tracks"
        params = {"limit": 50}

        tracks = []
        async with httpx.AsyncClient() as client:
            while url:
                response = await client.get(url, headers=headers, params=params)
                json_result = response.json()

                # Convert each track dict to Track model
                tracks.extend([Track(**item) for item in json_result["items"]])

                url = json_result.get("next")
                params = {}

        return tracks

    async def get_all_artist_tracks(self, artist_id: str) -> List[Track]:
        """Get all tracks by an artist through their albums"""
        albums = await self.get_artist_albums(artist_id)

        all_tracks: List[Track] = []
        for album in albums:
            album_tracks = await self.get_album_tracks(album.id)
            for track in album_tracks:
                # Only include tracks where the artist is a primary artist
                if any(artist.id == artist_id for artist in track.artists):
                    track.album_name = album.name
                    track.album_id = album.id
                    all_tracks.append(track)

        return all_tracks

    def track_to_dict(self, track: Track) -> dict:
        """Convert Track model to dictionary format expected by database"""
        return {
            "title": track.title,
            "spotify_id": track.spotify_id,
            "album_name": track.album_name,
            "album_id": track.album_id,
            "popularity": track.popularity,
        }
