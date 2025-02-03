from datetime import datetime, timezone
from pydantic import BaseModel
from spotify_client import SpotifyTrack
from sqlalchemy import (
    Column,
    Connection,
    DateTime,
    Integer,
    String,
    Table,
    delete,
    insert,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///songs.db"
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class TrackResponse(BaseModel):
    spotify_id: str
    title: str
    album_id: str | None = None
    album_name: str | None = None
    popularity: int = 0

    class Config:
        from_attributes: bool = True


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
        Column("popularity", Integer, default=0),
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

        def create_table(connection: Connection):
            table.create(bind=connection, checkfirst=True)

        async with engine.begin() as conn:
            await conn.run_sync(create_table)

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
            )
            _ = await db.execute(stmt)

        await db.commit()

    @staticmethod
    async def get_tracks(db: AsyncSession, artist_id: str) -> list[TrackResponse]:
        """Get all tracks for an artist"""
        await TrackManager.ensure_table_exists(db, artist_id)

        table = create_track_table(artist_id)
        print(f"About to fetch all tracks for {artist_id=}")

        stmt = select(
            table.c.spotify_id,
            table.c.title,
            table.c.album_id,
            table.c.album_name,
            table.c.popularity,
        )

        result = await db.execute(stmt)

        return [
            TrackResponse(
                spotify_id=row.spotify_id,
                title=row.title,
                album_id=row.album_id,
                album_name=row.album_name,
                popularity=row.popularity,
            )
            for row in result.fetchall()
        ]

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


# Initialize database
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
