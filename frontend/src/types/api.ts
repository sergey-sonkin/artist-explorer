export interface VoteRequest {
  artistId: string;
  currentPath: number;
  liked: boolean;
}

export interface VoteResponse {
  status: "continue" | "complete";
  currentPath: number;
  song?: Song;
}

export interface SearchResponse {
  searchId: string;
  artistId: string;
  artistName: string;
  currentPath: number;
  song: Song;
}

// We also need to define the Song interface
export interface Song {
  title: string;
  artists: string[];
  song_id: string;
  album_name: string;
  album_art_url: string;
}
