import random
from pydantic import BaseModel
from spotify_client import SpotifyTrack
from sqlalchemy import (
    JSON,
    Column,
    Connection,
    DateTime,
    Float,
    Integer,
    String,
    Table,
    delete,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # type: ignore
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///songs.db"
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# DB session dependency
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class TrackResponse(BaseModel):
    spotify_id: str
    title: str
    album_id: str | None = None
    album_name: str | None = None
    popularity: int = 0
    artists: list[str]
    album_art_url: str | None = None

    model_config = {
        "from_attributes": True
    }

    @classmethod
    def select_all_columns(cls, table: Table):
        return select(
            table.c.spotify_id,
            table.c.title,
            table.c.album_id,
            table.c.album_name,
            table.c.popularity,
            table.c.artists,
            table.c.album_art_url,
        )

    @classmethod
    def select_all_columns_with_features(cls, table: Table):
        return select(
            table.c.spotify_id,
            table.c.title,
            table.c.album_id,
            table.c.album_name,
            table.c.popularity,
            table.c.artists,
            table.c.album_art_url,
        )


class Artist(Base):
    __tablename__ = "artists"

    spotify_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    last_updated = Column(
        DateTime(timezone=True),
        nullable=True,
    )


def create_track_table(artist_id: str) -> Table:
    """Dynamically create a track table for an artist. Does not ensure it is persisted in DB."""
    table_name = f"tracks_{artist_id.replace('-', '_')}"

    return Table(
        table_name,
        Base.metadata,
        Column("spotify_id", String, primary_key=True),
        Column("title", String, nullable=False),
        Column("album_id", String),
        Column("album_name", String),
        Column("artists", JSON),
        Column("popularity", Integer, default=0),
        Column("album_art_url", String),
        Column("acousticness", Float),
        Column("danceability", Float),
        Column("energy", Float),
        Column("instrumentalness", Float),
        Column("key", Integer),
        Column("liveness", Float),
        Column("loudness", Float),
        Column("mode", Integer),
        Column("speechiness", Float),
        Column("tempo", Float),
        Column("time_signature", Integer),
        Column("valence", Float),
        extend_existing=True,
    )


class TrackManager:
    """Manages dynamic track tables"""

    @staticmethod
    def get_table_name(artist_id: str) -> str:
        return f"tracks_{artist_id.replace('-', '_')}"

    @staticmethod
    async def ensure_table_exists(db: AsyncSession, artist_id: str):
        """Create track table if it doesn't exist"""
        table = create_track_table(artist_id)

        engine = db.get_bind()

        def create_table(connection):
            table.create(connection, checkfirst=True)

        conn = await db.connection()
        await conn.run_sync(create_table)

        await db.commit()

    @staticmethod
    async def update_tracks(
        db: AsyncSession, artist_id: str, tracks: list[SpotifyTrack]
    ):
        """Update tracks for an artist"""
        # Ensure table exists before operations
        await TrackManager.ensure_table_exists(db, artist_id)

        table = create_track_table(artist_id)
        print(f"We created or retrieved a table for artist {artist_id=}")

        # Clear existing tracks
        _ = await db.execute(delete(table))

        # Insert new tracks
        for track in tracks:
            stmt = insert(table).values(
                spotify_id=track.spotify_id,
                title=track.title,
                album_id=track.album_id,
                album_name=track.album_name,
                popularity=track.popularity,
                artists=[artist.name for artist in track.artists],
                album_art_url=track.album_art_url,
            )
            _ = await db.execute(stmt)

        await db.commit()

    @staticmethod
    async def get_tracks(
        db: AsyncSession, artist_id: str, debug: bool = False
    ) -> list[TrackResponse]:
        """Get all tracks for an artist"""
        await TrackManager.ensure_table_exists(db, artist_id)

        table = create_track_table(artist_id)
        if debug:
            print(f"TrackManager.get_tracks: Fetching all tracks for {artist_id=}")

        result = await db.execute(TrackResponse.select_all_columns(table))

        if debug:
            print("TrackManager.get_tracks: RESULTS:")
        track_responses = [
            TrackResponse(
                spotify_id=row.spotify_id,
                title=row.title,
                album_id=row.album_id,
                album_name=row.album_name,
                popularity=row.popularity,
                artists=row.artists,
                album_art_url=row.album_art_url,
            )
            for row in result.fetchall()
        ]
        print(f"SONK {track_responses}")
        return track_responses

    @staticmethod
    async def get_track(
        db: AsyncSession, artist_id: str, track_id: str
    ) -> TrackResponse | None:
        """Get a specific track"""
        # Ensure table exists before operations
        await TrackManager.ensure_table_exists(db, artist_id)

        table = create_track_table(artist_id)

        stmt = select(table).where(table.c.spotify_id == track_id)
        result = await db.execute(stmt)
        row = result.first()

        if row is None:
            return None

        return TrackResponse(
            spotify_id=row.spotify_id,
            title=row.title,
            album_id=row.album_id,
            album_name=row.album_name,
            popularity=row.popularity,
            artists=row.artists,
            album_art_url=row.album_art_url,
        )


async def get_or_create_artist(db: AsyncSession, spotify_id: str, name: str) -> Artist:
    """Get existing artist or create new one"""
    stmt = select(Artist).where(Artist.spotify_id == spotify_id)
    result = await db.execute(stmt)
    artist = result.scalar_one_or_none()

    if artist is None:
        artist = Artist(
            spotify_id=spotify_id,
            name=name,
            last_updated=None,
        )
        db.add(artist)
        await db.commit()
        await db.refresh(artist)

        await TrackManager.ensure_table_exists(db, spotify_id)

    return artist


def create_recommendations_table(artist_id: str) -> Table:
    """Create recommendations table for an artist"""
    table_name = f"recommendations_{artist_id.replace('-', '_')}"

    return Table(
        table_name,
        Base.metadata,
        Column("path_id", Integer, primary_key=True),  # Binary path encoding
        Column("track_id", String, nullable=False),
        extend_existing=True,
    )


class RecommendationManager:
    @staticmethod
    def get_table_name(artist_id: str) -> str:
        return f"recommendations_{artist_id.replace('-', '_')}"

    @staticmethod
    async def ensure_table_exists(db: AsyncSession, artist_id: str):
        """Create recommendations table if it doesn't exist"""
        table = create_recommendations_table(artist_id)

        def create_table(connection: Connection):
            table.create(bind=connection, checkfirst=True)

        async with engine.begin() as conn:
            await conn.run_sync(create_table)

    @staticmethod
    async def get_initial_recommendation(
        db: AsyncSession, artist_id: str
    ) -> TrackResponse:
        """Get first recommendation (most popular song)"""
        await RecommendationManager.ensure_table_exists(db, artist_id)
        table = create_recommendations_table(artist_id)

        # Check if root recommendation already exists
        stmt = select(table.c.track_id).where(table.c.path_id == 1)
        result = await db.execute(stmt)
        existing_track_id: str | None = result.scalar_one_or_none()

        if existing_track_id:
            existing_track = await TrackManager.get_track(
                db=db, artist_id=artist_id, track_id=existing_track_id
            )
            if not existing_track:
                raise ValueError(f"Track {existing_track_id} not found")
            return existing_track

        tracks = await TrackManager.get_tracks(db, artist_id)
        if not tracks:
            raise ValueError(f"No tracks found for artist {artist_id}")

        initial_track = max(tracks, key=lambda t: t.popularity)

        try:
            # Use SQLAlchemy's SQLite-specific insert with ON CONFLICT clause
            insert_stmt = (
                insert(table)
                .values(path_id=1, track_id=initial_track.spotify_id)
                .on_conflict_do_nothing()
            )
            await db.execute(insert_stmt)
            await db.commit()
        except:
            ...

        return initial_track

    @staticmethod
    async def get_next_recommendation(
        db: AsyncSession,
        artist_id: str,
        current_path: int,
        liked: bool,
    ) -> TrackResponse | None:
        """Get or create next recommendation"""
        table = create_recommendations_table(artist_id)
        next_path = (current_path << 1) | (1 if liked else 0)

        # Check if recommendation exists
        stmt = select(table.c.track_id).where(table.c.path_id == next_path)
        result = await db.execute(stmt)
        existing_track_id = result.scalar_one_or_none()

        if existing_track_id:
            return await TrackManager.get_track(
                db=db, artist_id=artist_id, track_id=existing_track_id
            )

        # Get used track IDs for this session
        used_stmt = select(table.c.track_id)
        used_track_ids = (await db.execute(used_stmt)).scalars().all()

        # Temporary calculation
        all_tracks = await TrackManager.get_tracks(db, artist_id)
        available_tracks = [t for t in all_tracks if t.spotify_id not in used_track_ids]

        if not available_tracks:
            return None

        next_track = random.choice(available_tracks)

        # Store recommendation
        stmt = insert(table).values(path_id=next_path, track_id=next_track.spotify_id)
        await db.execute(stmt)
        await db.commit()

        return next_track
