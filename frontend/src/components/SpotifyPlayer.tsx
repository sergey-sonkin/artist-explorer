import React, { useEffect, useState } from "react";

interface SpotifyPlayerProps {
  songId: string;
  compact?: boolean;
}

const SpotifyPlayer: React.FC<SpotifyPlayerProps> = ({
  songId,
  compact = false,
}) => {
  const [embeddedUrl, setEmbeddedUrl] = useState<string>("");

  useEffect(() => {
    if (songId) {
      const formattedId = songId.replace("spotify:track:", "");
      setEmbeddedUrl(`https://open.spotify.com/embed/track/${formattedId}`);
    }
  }, [songId]);

  if (!songId) return null;

  const height = compact ? 80 : 380;

  return (
    <div className="w-full mb-4">
      {embeddedUrl && (
        <iframe
          src={embeddedUrl}
          width="100%"
          height={height}
          allowTransparency={true}
          allow="encrypted-media"
          title={`Spotify Player - ${songId}`}
        />
      )}
    </div>
  );
};

export default SpotifyPlayer;
