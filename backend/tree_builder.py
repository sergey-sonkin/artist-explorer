import random

from database import TrackResponse
from redis_managers import Song, TreeNode


def create_tree_from_tracks(tracks: list[TrackResponse], artist_name: str) -> TreeNode:
    """Create a decision tree using actual tracks from the database"""
    selected_tracks = random.sample(tracks, min(7, len(tracks)))

    # Create tree using real songs
    return TreeNode(
        song=Song(
            song_id=selected_tracks[0].spotify_id,
            title=selected_tracks[0].title,
            artists=[artist_name],
            album_name=selected_tracks[0].album_name or "Unknown Album",
            album_art_url=selected_tracks[0].album_art_url
            or "https://via.placeholder.com/150",
        ),
        vote_no=TreeNode(
            song=Song(
                song_id=selected_tracks[1].spotify_id,
                title=selected_tracks[1].title,
                artists=[artist_name],
                album_name=selected_tracks[1].album_name or "Unknown Album",
                album_art_url=selected_tracks[1].album_art_url
                or "https://via.placeholder.com/150",
            ),
            vote_no=TreeNode(
                song=Song(
                    song_id=selected_tracks[2].spotify_id,
                    title=selected_tracks[2].title,
                    artists=[artist_name],
                    album_name=selected_tracks[2].album_name or "Unknown Album",
                    album_art_url=selected_tracks[2].album_art_url
                    or "https://via.placeholder.com/150",
                ),
            ),
            vote_yes=TreeNode(
                song=Song(
                    song_id=selected_tracks[3].spotify_id,
                    title=selected_tracks[3].title,
                    artists=[artist_name],
                    album_name=selected_tracks[3].album_name or "Unknown Album",
                    album_art_url=selected_tracks[3].album_art_url
                    or "https://via.placeholder.com/150",
                ),
            ),
        ),
        vote_yes=TreeNode(
            song=Song(
                song_id=selected_tracks[4].spotify_id,
                title=selected_tracks[4].title,
                artists=[artist_name],
                album_name=selected_tracks[4].album_name or "Unknown Album",
                album_art_url=selected_tracks[4].album_art_url
                or "https://via.placeholder.com/150",
            ),
            vote_no=TreeNode(
                song=Song(
                    song_id=selected_tracks[5].spotify_id,
                    title=selected_tracks[5].title,
                    artists=[artist_name],
                    album_name=selected_tracks[5].album_name or "Unknown Album",
                    album_art_url=selected_tracks[5].album_art_url
                    or "https://via.placeholder.com/150",
                ),
            ),
            vote_yes=TreeNode(
                song=Song(
                    song_id=selected_tracks[6].spotify_id,
                    title=selected_tracks[6].title,
                    artists=[artist_name],
                    album_name=selected_tracks[6].album_name or "Unknown Album",
                    album_art_url=selected_tracks[6].album_art_url
                    or "https://via.placeholder.com/150",
                ),
            ),
        ),
    )
