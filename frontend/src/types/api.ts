export interface VoteRequest {
  artist_id: string;
  artist_name: string;
  vote_history: boolean[];
}

export interface SongData {
  album_name: string;
  artists: string[];
  popularity: number;
  song_id: string;
  title: string;
}
export interface SongResponse {
  song: SongData;
  status: string;
}
