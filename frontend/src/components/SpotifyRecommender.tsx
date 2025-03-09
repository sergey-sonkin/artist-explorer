import React, { useState, useEffect, ChangeEvent, KeyboardEvent } from "react";
import { Search, ThumbsUp, ThumbsDown, Music2, Loader2 } from "lucide-react";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { VoteRequest, VoteResponse, SearchResponse, Song } from "../types/api";
import SpotifyPlayer from "./SpotifyPlayer";

type CurrentState = "search" | "searching" | "loading" | "recommendation";

interface CurrentSong {
  title: string;
  artists: string[];
  id: string;
  albumName: string;
  albumArt: string;
  duration?: string;
}

const SpotifyRecommender: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentState, setCurrentState] = useState<CurrentState>("search");
  const [currentSong, setCurrentSong] = useState<CurrentSong | null>(null);
  const [artistId, setArtistId] = useState<string | null>(null);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [currentPath, setCurrentPath] = useState<number>(1);

  const handleSearch = async (): Promise<void> => {
    setCurrentState("searching");

    try {
      const response = await fetch("http://127.0.0.1:8000/api/start-search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          spotifyId: searchQuery,
        }),
      });

      const data: SearchResponse = await response.json();
      console.log("Data received: ", data);
      setSearchId(data.searchId);
      setArtistId(data.artistId);

      const eventSource = new EventSource(
        `http://127.0.0.1:8000/api/search-updates/${data.searchId}`,
      );

      eventSource.onmessage = (event: MessageEvent) => {
        const data = JSON.parse(event.data);
        console.log("Received update:", data);

        switch (data.status) {
          case "searching":
            setCurrentState("searching");
            break;
          case "completed":
            setCurrentState("recommendation");
            setCurrentSong({
              title: data.song.title,
              artists: data.song.artists,
              id: data.song.song_id,
              albumName: data.song.album_name,
              albumArt: data.song.album_art_url,
            });
            eventSource.close();
            break;
          case "error":
            console.error("Search error:", data.message);
            setCurrentState("search");
            eventSource.close();
            break;
          default:
            console.log("Unknown status:", data.status);
        }
      };

      eventSource.onerror = (error: Event) => {
        console.error("SSE error:", error);
        eventSource.close();
        setCurrentState("search");
      };
    } catch (error) {
      console.error("Failed to start search:", error);
      setCurrentState("search");
    }
  };

  useEffect(() => {
    return () => {
      if (searchId) {
        const eventSource = new EventSource(
          `http://127.0.0.1:8000/api/search-updates/${searchId}`,
        );
        eventSource.close();
      }
    };
  }, [searchId]);

  const handleVote = async (liked: boolean): Promise<void> => {
    setCurrentState("loading");

    try {
      const voteRequest: VoteRequest = {
        artistId: artistId!,
        currentPath: currentPath,
        liked: liked,
      };
      console.log(voteRequest);

      const response = await fetch(`http://127.0.0.1:8000/api/vote`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(voteRequest),
      });

      const data: VoteResponse = await response.json();
      setCurrentPath(data.currentPath);

      if (data.status === "complete") {
        setCurrentState("search");
        setCurrentSong(null);
        setCurrentPath(0);
      } else {
        setCurrentSong({
          title: data.song!.title,
          artists: data.song!.artists,
          id: data.song!.song_id,
          albumName: data.song!.album_name,
          albumArt: data.song!.album_art_url,
        });
        setCurrentPath(data.currentPath);
        setCurrentState("recommendation");
      }
    } catch (error) {
      console.error("Vote failed:", error);
      setCurrentState("search");
    }
  };

  return (
    <div className="max-w-md mx-auto p-6 space-y-6">
      {/* Search Section */}
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Discover New Music</h1>
        <div className="flex gap-2">
          <Input
            placeholder="Enter an artist you like..."
            value={searchQuery}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setSearchQuery(e.target.value)
            }
            onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
              if (e.key === "Enter") {
                handleSearch();
              }
            }}
            className="flex-1"
          />
          <Button onClick={handleSearch}>
            <Search className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      <Card className="w-full">
        <CardContent className="pt-6">
          {currentState === "search" && (
            <div className="text-center py-12 space-y-4">
              <Music2 className="w-12 h-12 mx-auto text-gray-400" />
              <p className="text-gray-500">Enter an artist to get started</p>
            </div>
          )}

          {currentState === "searching" && (
            <div className="text-center py-12 space-y-4">
              <Loader2 className="w-12 h-12 mx-auto animate-spin text-gray-400" />
              <p className="text-gray-500">Searching for artist...</p>
            </div>
          )}

          {currentState === "loading" && (
            <div className="text-center py-12">
              <Loader2 className="w-12 h-12 mx-auto animate-spin text-gray-400" />
            </div>
          )}

          {currentState === "recommendation" && currentSong && (
            <div className="space-y-6">
              {/* Album Art */}
              <div className="aspect-square relative">
                <img
                  src={currentSong.albumArt}
                  alt={`${currentSong.title} album art`}
                  className="w-full h-full object-cover rounded-lg"
                />
              </div>

              {/* Song Info */}
              <div className="text-center space-y-2">
                <h2 className="text-xl font-bold">{currentSong.title}</h2>
                <p className="text-gray-500">
                  {currentSong.artists.join(", ")}
                </p>
                <p className="text-sm text-gray-400">{currentSong.duration}</p>
              </div>

              {/* Spotify Player */}
              <SpotifyPlayer songId={currentSong.id} />

              {/* Voting Buttons */}
              <div className="flex justify-center gap-4">
                <Button
                  variant="outline"
                  size="lg"
                  onClick={() => handleVote(false)}
                  className="w-24"
                >
                  <ThumbsDown className="w-5 h-5" />
                </Button>
                <Button
                  size="lg"
                  onClick={() => handleVote(true)}
                  className="w-24"
                >
                  <ThumbsUp className="w-5 h-5" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default SpotifyRecommender;
