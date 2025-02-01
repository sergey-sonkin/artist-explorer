from redis import Redis
import uuid
from fastapi import FastAPI, Request
from dataclasses import dataclass
from fastapi.responses import StreamingResponse
from collections.abc import AsyncGenerator

# import asyncio
import json
import traceback

from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import aiosqlite
from datetime import datetime, timedelta
from spotify_client import SpotifyClient, Track

from redis_managers import Search, SearchManager, SessionManager, Song, TreeNode

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    await init_db()


redis_client = Redis(host="localhost", port=6379, db=0)
session_manager = SessionManager(redis_client)
search_manager = SearchManager(redis_client)

spotify_client = SpotifyClient()


@dataclass
class SessionData:
    search_id: str
    spotify_id: str
    artist_name: str
    tree: TreeNode

    def to_dict(self):
        return {
            "search_id": self.search_id,
            "spotify_id": self.spotify_id,
            "artist_name": self.artist_name,
            "tree": self.tree.to_dict(),
        }


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
        _ = await db.execute(
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


async def update_artist_songs(spotify_id: str, artist_name: str, tracks: list[Track]):
    """Store or update songs for an artist"""
    table_name = await sanitize_table_name(artist_name)

    async with aiosqlite.connect("songs.db") as db:
        await db.execute(
            "UPDATE artists SET last_updated = ? WHERE name = ?",
            (datetime.now().isoformat(), artist_name),
        )

        await ensure_artist_table(db=db, table_name=table_name)
        await db.execute(f"DELETE FROM {table_name}")

        # Convert Track models to dictionaries for database storage
        for track in tracks:
            track_dict = spotify_client.track_to_dict(track)
            await db.execute(
                f"""
                INSERT OR REPLACE INTO {table_name}
                (title, spotify_id, album_name, popularity)
                VALUES (?, ?, ?, ?)
                """,
                (
                    track_dict["title"],
                    track_dict["spotify_id"],
                    track_dict["album_name"],
                    track_dict["popularity"],
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
        # Get tracks from Spotify API
        tracks = await spotify_client.get_all_artist_tracks(spotify_id)
        await update_artist_songs(
            spotify_id=spotify_id, artist_name=artist_name, songs=tracks
        )

    # Retrieve songs from database
    async with aiosqlite.connect("songs.db") as db:
        cursor = await db.execute(f"""
            SELECT title, spotify_id, album_name, popularity
            FROM {table_name}
        """)

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

        spotify_id = search_data.artist_id
        artist_name = search_data.artist_name

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
    spotify_id: str = data["spotifyId"]
    search_id = str(uuid.uuid4())
    search = Search(
        search_id=search_id, artist_id=spotify_id, artist_name=f"Artist_{spotify_id}"
    )
    artist_name = f"Artist_{spotify_id}"

    # Store in Redis instead of active_searches
    await search_manager.create_search(search_id=search_id, search=search)

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
