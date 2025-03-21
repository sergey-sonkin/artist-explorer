import json
import traceback
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from database import (
    RecommendationManager,
    TrackManager,
    TrackResponse,
    get_db,
    get_or_create_artist,
    init_db,
)
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from redis import Redis
from redis_managers import Search, SearchManager, SessionManager, TreeNode
from spotify_client import SpotifyClient
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore
from tree_builder import create_tree_from_tracks

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return create_tree_from_tracks(tracks, artist_name)


async def search_songs_for_artist(
    db: AsyncSession, artist_id: str, artist_name: str, debug: bool = False
) -> list[TrackResponse]:
    """Search for songs, updating database if necessary"""
    if debug:
        print(f"Checking artist status for {artist_name=}")

    # Get or create artist
    artist = await get_or_create_artist(db, artist_id, artist_name)

    # If last_updated is None or older than 2 weeks, update needed
    print("-------------------------------------")
    print(f"Last updated: {artist.last_updated=}")
    print("-------------------------------------")
    needs_update = artist.last_updated is None or datetime.now(
        timezone.utc
    ) - artist.last_updated.replace(tzinfo=timezone.utc) > timedelta(weeks=2)

    if bool(needs_update):
        tracks = await spotify_client.get_all_artist_tracks(artist_id)
        print(tracks)
        _ = await TrackManager.update_tracks(db, artist_id, tracks)

        artist.last_updated = datetime.now(timezone.utc)
        await db.commit()

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
    artist_id = data["artistId"]
    current_path = data["currentPath"]
    liked = data["liked"]

    # Get next recommendation based on vote
    next_track = await RecommendationManager.get_next_recommendation(
        db, artist_id=artist_id, current_path=current_path, liked=liked
    )

    if next_track is None:
        return {"status": "complete"}

    next_path = (current_path << 1) | (1 if liked else 0)
    return {"status": "continue", "currentPath": next_path, "song": next_track.dict()}


@app.post("/api/start-search")
async def start_search(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    spotify_id: str = data["spotifyId"]
    search_id = str(uuid.uuid4())

    artist_info = await spotify_client.get_artist(spotify_id)
    artist_name = artist_info.name

    print(f"{artist_name=}")

    artist = await get_or_create_artist(db, spotify_id, artist_name)
    _ = await search_songs_for_artist(db, spotify_id, artist_name)
    print(f"{artist=}")

    initial_song = await RecommendationManager.get_initial_recommendation(
        db, spotify_id
    )

    search = Search(search_id=search_id, artist_id=spotify_id, artist_name=artist_name)
    _ = await search_manager.create_search(search_id=search_id, search=search)

    return {
        "searchId": search_id,
        "artistId": spotify_id,
        "artistName": artist.name,
        "currentPath": 1,  # Initial path
        "song": initial_song.dict(),
    }


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
