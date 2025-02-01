from dataclasses import dataclass, asdict
import json
from typing import Optional, Any
from redis import Redis


@dataclass
class Song:
    song_id: str
    title: str
    artists: list[str]
    album_name: str = "album name"
    popularity: int = 0

    def to_dict(self) -> dict[str, str | list[str] | int]:
        return {
            "song_id": self.song_id,
            "title": self.title,
            "artists": self.artists,
            "album_name": self.album_name,
            "popularity": self.popularity,
        }


@dataclass
class TreeNode:
    song: Song
    vote_no: Optional["TreeNode"] = None
    vote_yes: Optional["TreeNode"] = None

    def to_dict(self):
        return {
            "song": self.song.to_dict(),
            "left": self.vote_no.to_dict() if self.vote_no else None,
            "right": self.vote_yes.to_dict() if self.vote_yes else None,
        }


@dataclass
class Search:
    search_id: str
    artist_id: str
    artist_name: str


class SearchManager:
    def __init__(self, redis_client: Redis):
        self.redis: Redis = redis_client
        self.expire_time: int = 3600  # 1 hour

    async def create_search(self, search_id: str, search: Search) -> None:
        _ = self.redis.setex(
            f"search:{search_id}", self.expire_time, json.dumps(asdict(search))
        )

    async def get_search(self, search_id: str) -> Search | None:
        data = self.redis.get(f"search:{search_id}")
        if not data:
            return None
        search_dict = json.loads(data)
        return Search(**search_dict) if search_dict else None

    async def delete_search(self, search_id: str) -> None:
        _ = self.redis.delete(f"search:{search_id}")


class SessionManager:
    def __init__(self, redis_client: Redis):
        self.redis: Redis = redis_client
        self.expire_time: int = 3600  # 1 hour

    async def create_session(
        self, search_id: str, spotify_id: str, artist_name: str, tree: TreeNode
    ):
        session_data = {
            "spotify_id": spotify_id,
            "artist_name": artist_name,
            "tree": self._serialize_tree(tree),
        }
        _ = self.redis.setex(
            f"session:{search_id}", self.expire_time, json.dumps(session_data)
        )

    async def get_session(self, search_id: str) -> dict[str, Any] | None:
        """Retrieve session data from Redis"""
        data = self.redis.get(f"session:{search_id}")
        if not data:
            return None
        return json.loads(data)

    async def update_session(self, search_id: str, session_data: dict):
        """Update session data in Redis"""
        _ = self.redis.setex(
            f"session:{search_id}", self.expire_time, json.dumps(session_data)
        )

    def _serialize_tree(self, node: TreeNode | None) -> dict[str, Any] | None:
        if node is None:
            return None
        return {
            "song": node.song.to_dict(),
            "left": self._serialize_tree(node.vote_no) if node.vote_no else None,
            "right": self._serialize_tree(node.vote_yes) if node.vote_yes else None,
        }
