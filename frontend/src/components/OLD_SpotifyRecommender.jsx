import React, { useState, useEffect } from "react";
import { Search, ThumbsUp, ThumbsDown, Music2, Loader2 } from "lucide-react";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";

const SpotifyRecommender = () => {
  const [searchQuery, setSearchQuery] = useState("");
  const [currentState, setCurrentState] = useState("search");
  const [currentSong, setCurrentSong] = useState(null);
  const [voteHistory, setVoteHistory] = useState([]);
  const [artistId, setArtistId] = useState(null);
  const [artistName, setArtistName] = useState(null);
  const [artist, setArtist] = useState(null);
  const [searchId, setSearchId] = useState(null);

  const handleSearch = async () => {
    setCurrentState("searching");

    try {
      // First, initiate the search
      const response = await fetch("http://127.0.0.1:8000/api/start-search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          spotifyId: searchQuery, // The search term
        }),
      });

      const data = await response.json();
      setSearchId(data.searchId);
      setArtistId(data.artistId);
      setArtistName(data.artistName);

      // Set up SSE to monitor processing
      const eventSource = new EventSource(
        `http://127.0.0.1:8000/api/search-updates/${data.searchId}`,
      );

      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("Received update:", data);

        switch (data.status) {
          case "searching":
            setCurrentState("searching");
            break;
          case "completed":
            // Processing complete, tree is ready
            setCurrentState("recommendation");
            setCurrentSong({
              title: data.song.title,
              artist: data.song.artist,
              id: data.song.id,
              albumArt: "/api/placeholder/300/300",
            });
            setArtist(searchQuery); // Add this line
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

      eventSource.onerror = (error) => {
        console.error("SSE error:", error);
        eventSource.close();
        setCurrentState("search");
      };
    } catch (error) {
      console.error("Failed to start search:", error);
      setCurrentState("search");
    }
  };

  // Clean up SSE connection when component unmounts
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

  const handleVote = async (isLike) => {
    setCurrentState("loading");
    const newVoteHistory = [...voteHistory, isLike];

    try {
      const response = await fetch(`http://127.0.0.1:8000/api/vote`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          artist_id: artistId,
          artist_name: artistName,
          vote_history: newVoteHistory,
        }),
      });

      const data = await response.json();

      if (data.status === "complete") {
        setCurrentState("search");
        setCurrentSong(null);
        setVoteHistory([]);
        setArtist(null);
      } else {
        setCurrentSong({
          title: data.song.title,
          artist: data.song.artist,
          id: data.song.id,
          albumArt: "/api/placeholder/300/300",
        });
        setVoteHistory(newVoteHistory);
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
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
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
                <p className="text-gray-500">{currentSong.artist}</p>
                <p className="text-sm text-gray-400">{currentSong.duration}</p>
              </div>

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
