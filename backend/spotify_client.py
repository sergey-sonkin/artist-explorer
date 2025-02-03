import base64
import os

import httpx
from pydantic import BaseModel, Field


class SpotifyArtist(BaseModel):
    id: str
    name: str


class SpotifyTrack(BaseModel):
    title: str = Field(..., alias="name")
    spotify_id: str = Field(..., alias="id")
    artists: list[SpotifyArtist]
    album_name: str | None = None
    album_id: str | None = None
    popularity: int = 0

    class Config:
        populate_by_name: bool = True


class SpotifyAlbum(BaseModel):
    id: str
    name: str
    tracks: list[SpotifyTrack] = []


class SpotifyClient:
    def __init__(self, debug: bool = False):
        self.client_id: str | None = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret: str | None = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.token: str | None = None
        self.base_url: str = "https://api.spotify.com/v1"
        self.debug: bool = debug

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

    async def get_artist_albums(self, artist_id: str) -> list[SpotifyAlbum]:
        """Get all albums for an artist"""
        token = await self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/artists/{artist_id}/albums"
        params = {"include_groups": "album,single", "limit": 50}

        albums: list[SpotifyAlbum] = []
        async with httpx.AsyncClient() as client:
            while url:
                response = await client.get(url, headers=headers, params=params)
                json_result = response.json()

                # Convert each album dict to Album model
                albums.extend([SpotifyAlbum(**item) for item in json_result["items"]])

                url = json_result.get("next")
                params = {}

        return albums

    async def get_album_tracks(self, album_id: str) -> list[SpotifyTrack]:
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
                print("==========================")
                print(json_result)
                print("==========================")

                tracks.extend([SpotifyTrack(**item) for item in json_result["items"]])

                url = json_result.get("next")
                params = {}

        return tracks

    async def get_all_artist_tracks(self, artist_id: str) -> list[SpotifyTrack]:
        """Get all tracks by an artist through their albums"""
        albums = await self.get_artist_albums(artist_id)

        all_tracks: list[SpotifyTrack] = []
        for album in albums:
            album_tracks = await self.get_album_tracks(album.id)
            for track in album_tracks:
                # Only include tracks where the artist is a primary artist
                if any(artist.id == artist_id for artist in track.artists):
                    track.album_name = album.name
                    track.album_id = album.id
                    all_tracks.append(track)

        return all_tracks
