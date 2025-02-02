from collections.abc import AsyncGenerator
from database import get_db, TrackManager, get_or_create_artist, TrackResponse, init_db
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from redis import Redis
from redis_managers import Search, SearchManager, SessionManager, Song, TreeNode
from spotify_client import SpotifyClient
from sqlalchemy.ext.asyncio import AsyncSession
import json
import traceback
import uuid

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


async def create_decision_tree(
    db: AsyncSession, spotify_id: str, artist_name: str
) -> TreeNode:
    """Create decision tree based on artist's songs"""
    tracks = await TrackManager.get_tracks(db, spotify_id)

    # For now, create mock tree structure
    # Later, use tracks to create real decision tree
    return create_mock_decision_tree(artist_name=artist_name)


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


def get_next_song(tree: TreeNode, vote_history: list) -> Song | None:
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


async def search_songs_for_artist(
    db: AsyncSession, artist_id: str, artist_name: str, debug: bool = False
) -> list[TrackResponse]:
    """Search for songs, updating database if necessary"""
    if debug:
        print(f"Checking artist status for {artist_name=}")

    # Get or create artist
    if debug:
        print(f"Getting or creating artist for {artist_name=}")
    artist = await get_or_create_artist(db, artist_id, artist_name)
    current_time = datetime.now(timezone.utc)
    last_updated = (
        artist.last_updated.replace(tzinfo=timezone.utc)
        if artist.last_updated.tzinfo is None
        else artist.last_updated
    )
    needs_update = current_time - last_updated > timedelta(weeks=2)

    if debug:
        print(f"About to calculate tracks for {artist_name=}")
    if needs_update:
        # Get tracks from Spotify API
        tracks = await spotify_client.get_all_artist_tracks(artist_id)
        await TrackManager.update_tracks(db, artist_id, tracks)

    return await TrackManager.get_tracks(db, artist_id)


# Modify event_generator to use SearchManager
async def event_generator(
    search_id: str, db: AsyncSession
) -> AsyncGenerator[str, None]:
    debug = True
    try:
        yield f"data: {json.dumps({'status': 'searching', 'progress': 0})}\n\n"

        search_data = await search_manager.get_search(search_id)
        if not search_data:
            raise KeyError(f"Search {search_id} not found")

        spotify_id = search_data.artist_id
        artist_name = search_data.artist_name

        try:
            songs = await search_songs_for_artist(
                db=db, artist_id=spotify_id, artist_name=artist_name, debug=True
            )
            if debug:
                print(f"Retrieved songs: {songs}")
        except Exception as e:
            print(f"Error in search_songs_for_artist: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            raise

        try:
            tree = await create_decision_tree(
                db=db, spotify_id=spotify_id, artist_name=artist_name
            )
            if debug:
                print(f"Created decision tree for {spotify_id=}")
        except Exception as e:
            print(f"Error in create_decision_tree: {e}")
            raise

        await session_manager.create_session(
            search_id=search_id,
            spotify_id=spotify_id,
            artist_name=artist_name,
            tree=tree,
        )

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
        await search_manager.delete_search(search_id)


@app.post("/api/vote")
async def record_vote(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    artist_name = data["artist_name"]
    vote_history = data["vote_history"]

    tree = create_mock_decision_tree(artist_name)
    next_song = get_next_song(tree, vote_history)

    if next_song is None:
        return {"status": "complete"}

    return {"status": "continue", "song": next_song.to_dict()}


@app.post("/api/start-search")
async def start_search(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    spotify_id: str = data["spotifyId"]
    search_id = str(uuid.uuid4())

    # Get or create artist
    artist = await get_or_create_artist(db, spotify_id, f"Artist_{spotify_id}")

    search = Search(search_id=search_id, artist_id=spotify_id, artist_name=artist.name)

    await search_manager.create_search(search_id=search_id, search=search)

    return {"searchId": search_id, "artistId": spotify_id, "artistName": artist.name}


@app.get("/api/search-updates/{search_id}")
async def search_updates(search_id: str, db: AsyncSession = Depends(get_db)):
    search_data = await search_manager.get_search(search_id)
    if not search_data:
        raise HTTPException(status_code=404, detail="Search not found")

    return StreamingResponse(
        event_generator(search_id, db), media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
