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
    album_art_url: str | None = None

    class Config:
        populate_by_name: bool = True


class SpotifyAlbum(BaseModel):
    id: str
    name: str
    album_type: str  # album, single, compilation
    release_date: str
    total_tracks: int
    images: list[dict]
    artists: list[SpotifyArtist]
    tracks: list[SpotifyTrack] = []
    external_urls: dict  # Contains Spotify URL
    popularity: int | None = None
    label: str | None = None

    @property
    def cover_image_url(self) -> str | None:
        """Returns the URL of the largest album cover image"""
        if self.images and len(self.images) > 0:
            return self.images[0]["url"]
        return None


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
                track.album_name = album.name
                track.album_id = album.id
                track.album_art_url = album.cover_image_url
                all_tracks.append(track)

        return all_tracks

    async def get_artist(self, artist_id: str) -> SpotifyArtist:
        """Get artist information by ID"""
        token = await self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/artists/{artist_id}"

        print("Grabbing artist")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception(f"Error fetching artist: {response.text}")

            artist_data = response.json()
            if not artist_data["id"] or not artist_data["name"]:
                raise ValueError(
                    f"Spotify returned an invalid artist ID or name: {artist_data=}"
                )
            return SpotifyArtist(id=artist_data["id"], name=artist_data["name"])
