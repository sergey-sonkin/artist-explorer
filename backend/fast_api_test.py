from redis import Redis
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import asyncio
import json
import traceback

from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict
import aiosqlite
from datetime import datetime, timedelta
import re

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add to FastAPI app
@app.on_event("startup")
async def startup_event():
    await init_db()


redis_client = Redis(host="localhost", port=6379, db=0)

from dataclasses import dataclass


@dataclass
class Song:
    song_id: str
    title: str
    artists: list[str]
    album_name: str = "album name"
    popularity: int = 0

    def to_dict(self):
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


class SessionManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.expire_time = 3600  # 1 hour

    async def create_session(
        self, search_id: str, spotify_id: str, artist_name: str, tree: TreeNode
    ):
        session_data = {
            "spotify_id": spotify_id,
            "artist_name": artist_name,
            "tree": self._serialize_tree(tree),
        }
        self.redis.setex(
            f"session:{search_id}", self.expire_time, json.dumps(session_data)
        )

    async def get_session(self, search_id: str) -> Optional[dict]:
        """Retrieve session data from Redis"""
        data = self.redis.get(f"session:{search_id}")
        if not data:
            return None
        return json.loads(data)

    async def update_session(self, search_id: str, session_data: dict):
        """Update session data in Redis"""
        self.redis.setex(
            f"session:{search_id}", self.expire_time, json.dumps(session_data)
        )

    def _serialize_tree(self, node: TreeNode) -> Optional[dict]:
        if node is None:
            return None
        return {
            "song": node.song.to_dict(),
            "left": self._serialize_tree(node.vote_no) if node.vote_no else None,
            "right": self._serialize_tree(node.vote_yes) if node.vote_yes else None,
        }

    async def get_current_song(
        self, search_id: str, vote_history: list
    ) -> Optional[dict]:
        session_data = json.loads(self.redis.get(f"session:{search_id}"))
        node = session_data["tree"]

        # Navigate to current position in tree
        for vote in vote_history:
            node = node["right"] if vote else node["left"]
            if node is None:
                return None

        return node["song"]


session_manager = SessionManager(redis_client)


class SearchManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.expire_time = 3600  # 1 hour

    async def create_search(self, search_id: str, spotify_id: str, artist_name: str):
        """Store search data in Redis"""
        search_data = {"spotify_id": spotify_id, "artist_name": artist_name}
        self.redis.setex(
            f"search:{search_id}", self.expire_time, json.dumps(search_data)
        )

    async def get_search(self, search_id: str) -> Optional[dict]:
        """Retrieve search data from Redis"""
        data = self.redis.get(f"search:{search_id}")
        if not data:
            return None
        return json.loads(data)

    async def delete_search(self, search_id: str):
        """Remove search data from Redis"""
        self.redis.delete(f"search:{search_id}")


search_manager = SearchManager(redis_client)


async def create_decision_tree(spotify_id: str, artist_name: str) -> TreeNode:
    """Create decision tree based on artist's songs"""
    table_name = await sanitize_table_name(artist_name)

    async with aiosqlite.connect("songs.db") as db:
        # Get all songs for artist
        cursor = await db.execute(f"SELECT * FROM {table_name}")
        songs = await cursor.fetchall()

        # For now, create mock tree structure
        # Later, implement actual recommendation logic here
        return create_mock_decision_tree(artist_name=artist_name)


async def sanitize_table_name(spotify_id: str) -> str:
    """Convert Spotify ID to valid table name"""
    return f"songs_{spotify_id.replace('.', '_')}"


async def init_db():
    """Initialize the database with artists table"""
    async with aiosqlite.connect("songs.db") as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS artists (
                spotify_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                table_name TEXT UNIQUE,
                last_updated TIMESTAMP
            )
        """
        )
        await db.commit()


async def ensure_artist_table(db, table_name: str):
    """Create artist-specific table if it doesn't exist"""
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            spotify_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            album_id TEXT,
            album_name TEXT,
            popularity INTEGER
        )
    """
    )
    await db.commit()


def create_mock_decision_tree(artist_name: str) -> TreeNode:
    """Create a mock decision tree 5 levels deep"""
    return TreeNode(
        song=Song(
            song_id="0", title="Root song", artists=[artist_name], album_name="Album 0"
        ),
        vote_no=TreeNode(
            song=Song(
                song_id="1",
                title="No Song 1",
                artists=[artist_name],
                album_name="Album 1",
            ),
            vote_no=TreeNode(
                song=Song(
                    song_id="2",
                    title="No-No Song",
                    artists=[artist_name],
                    album_name="Album 2",
                ),
            ),
            vote_yes=TreeNode(
                song=Song(
                    song_id="3",
                    title="No-Yes Song",
                    artists=[artist_name],
                    album_name="Album 3",
                ),
            ),
        ),
        vote_yes=TreeNode(
            song=Song(
                song_id="4",
                title="Yes Song 1",
                artists=[artist_name],
                album_name="Album 4",
            ),
            vote_no=TreeNode(
                song=Song(
                    song_id="5",
                    title="Yes-No Song",
                    artists=[artist_name],
                    album_name="Album 5",
                ),
            ),
            vote_yes=TreeNode(
                song=Song(
                    song_id="6",
                    title="Yes-Yes Song",
                    artists=[artist_name],
                    album_name="Album 6",
                ),
            ),
        ),
    )


def get_next_song(tree: TreeNode, vote_history: list) -> Optional[Song]:
    """Navigate tree based on vote history"""
    current = tree
    for vote in vote_history:
        if vote:
            current = current.vote_yes
        else:
            current = current.vote_no
        if current is None:
            return None
    return current.song


async def check_artist_status(
    spotify_id: str, artist_name: str, debug: bool = False
) -> tuple[bool, str]:
    """
    Check if we need to update songs for this artist
    Returns: (needs_update, table_name)
    """
    table_name = await sanitize_table_name(spotify_id)

    async with aiosqlite.connect("songs.db") as db:
        cursor = await db.execute(
            "SELECT last_updated FROM artists WHERE spotify_id = ?", (spotify_id,)
        )
        result = await cursor.fetchone()

        if result is None:
            # New artist - create entry and table
            if debug:
                print(f"Creating new artist entry for {spotify_id=}")
            await db.execute(
                "INSERT INTO artists (spotify_id, name, table_name, last_updated) VALUES (?, ?, ?, ?)",
                (spotify_id, artist_name, table_name, datetime.now().isoformat()),
            )
            await ensure_artist_table(db=db, table_name=table_name)
            return True, table_name

        last_updated = datetime.fromisoformat(result[0])
        two_weeks_ago = datetime.now() - timedelta(weeks=2)

        return last_updated < two_weeks_ago, table_name


async def update_artist_songs(spotify_id: str, artist_name: str, songs: list):
    """Store or update songs for an artist"""
    table_name = await sanitize_table_name(artist_name)

    async with aiosqlite.connect("songs.db") as db:
        # Update last_updated timestamp
        await db.execute(
            "UPDATE artists SET last_updated = ? WHERE name = ?",
            (datetime.now().isoformat(), artist_name),
        )

        # Ensure table exists
        print(f"Ensuring table {table_name=}")
        await ensure_artist_table(db=db, table_name=table_name)

        # Clear existing songs (optional, depends on your update strategy)
        await db.execute(f"DELETE FROM {table_name}")

        # Insert new songs
        for song in songs:
            await db.execute(
                f"""
                INSERT OR REPLACE INTO {table_name}
                (title, spotify_id, album_name, popularity)
                VALUES (?, ?, ?, ?)
            """,
                (
                    song["title"],
                    song.get("spotify_id"),
                    song.get("album_name"),
                    song.get("popularity", 0),
                ),
            )

        await db.commit()


async def search_songs_for_artist(
    spotify_id: str, artist_name: str, debug=False
) -> list:
    """Search for songs, updating database if necessary"""
    if debug:
        print(f"Checking artist status for {artist_name=}")
    needs_update, table_name = await check_artist_status(
        spotify_id=spotify_id, artist_name=artist_name, debug=True
    )
    if debug:
        print(f"Finished checking artist status for {artist_name=}")

    if needs_update:
        # In real implementation, call Spotify API here
        songs = [
            {
                "title": "Song 1",
                "spotify_id": "abc123",
                "album": "Album 1",
                "popularity": 75,
            },
            {
                "title": "Song 2",
                "spotify_id": "def456",
                "album": "Album 1",
                "popularity": 80,
            },
        ]
        await update_artist_songs(
            spotify_id=spotify_id, artist_name=artist_name, songs=songs
        )

    # Retrieve songs from database
    async with aiosqlite.connect("songs.db") as db:
        cursor = await db.execute(
            f"""
            SELECT title, spotify_id, album_name, popularity
            FROM {table_name}
        """
        )

        rows = await cursor.fetchall()
        return [
            {
                "title": row[0],
                "spotify_id": row[1],
                "album": row[2],
                "popularity": row[3],
                "artist": artist_name,
            }
            for row in rows
        ]


# Modify event_generator to use SearchManager
async def event_generator(search_id: str) -> AsyncGenerator[str, None]:
    debug = True
    try:
        yield f"data: {json.dumps({'status': 'searching', 'progress': 0})}\n\n"

        # Get artist info from Redis instead of active_searches
        search_data = await search_manager.get_search(search_id)
        if not search_data:
            raise KeyError(f"Search {search_id} not found")

        spotify_id = search_data["spotify_id"]
        artist_name = search_data["artist_name"]

        # Process artist and create decision tree
        try:
            songs = await search_songs_for_artist(
                spotify_id=spotify_id, artist_name=artist_name, debug=True
            )
            if debug:
                print(f"Retrieved songs: {songs}")
        except Exception as e:
            print(f"Error in search_songs_for_artist: {e}")
            print(f"Error type: {type(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            raise

        try:
            tree = await create_decision_tree(
                spotify_id=spotify_id, artist_name=artist_name
            )
            if debug:
                print(f"Created decision tree for {spotify_id=}")
        except Exception as e:
            print(f"Error in create_decision_tree: {e}")
            raise

        # Store tree in Redis
        try:
            await session_manager.create_session(
                search_id=search_id,
                spotify_id=spotify_id,
                artist_name=artist_name,
                tree=tree,
            )
            if debug:
                print(f"Created Redis session for {search_id=}")
        except Exception as e:
            print(f"Error creating Redis session: {e}")
            raise

        # Send completion status with first song
        yield f"data: {
            json.dumps(
                {
                    'status': 'completed',
                    'song': tree.song.to_dict(),
                    'artistId': spotify_id,
                    'artistName': artist_name,
                }
            )
        }\n\n"

    except Exception as e:
        error_message = {
            "status": "error",
            "message": str(e),
            "type": str(type(e)),
            "traceback": traceback.format_exc(),
        }
        print(f"Error in event_generator: {error_message}")
        yield f"data: {json.dumps(error_message)}\n\n"

    finally:
        # Clean up from Redis instead of active_searches
        await search_manager.delete_search(search_id)


@app.post("/api/vote")
async def record_vote(request: Request):
    data = await request.json()
    artist_name = data["artist_name"]
    vote_history = data["vote_history"]

    # Create/get tree and navigate to next song
    tree = create_mock_decision_tree(artist_name)
    next_song = get_next_song(tree, vote_history)

    if next_song is None:
        return {"status": "complete"}

    return {"status": "continue", "song": next_song.to_dict()}


@app.post("/api/start-search")
async def start_search(request: Request):
    data = await request.json()
    spotify_id = data["spotifyId"]
    search_id = str(uuid.uuid4())
    artist_name = f"Artist_{spotify_id}"

    # Store in Redis instead of active_searches
    await search_manager.create_search(
        search_id=search_id, spotify_id=spotify_id, artist_name=artist_name
    )

    return {"searchId": search_id, "artistId": spotify_id, "artistName": artist_name}


@app.get("/api/search-updates/{search_id}")
async def search_updates(search_id: str):
    search_data = await search_manager.get_search(search_id)
    if not search_data:
        return {"error": "Search not found"}

    return StreamingResponse(event_generator(search_id), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
