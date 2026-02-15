"use client";

import { useEffect, useState } from "react";
import { Heart, MessageCircle, Repeat2 } from "lucide-react";

interface Tweet {
  id: string;
  tweet_text: string;
  tweet_author_username: string;
  likes_count: number;
  retweets_count: number;
  replies_count: number;
  tweet_created_at: string;
}

interface TweetTickerProps {
  tweets?: Tweet[];
  variant?: "bar" | "pill";
}

function formatCount(count: number): string {
  if (count >= 1000000) {
    return (count / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  }
  if (count >= 1000) {
    return (count / 1000).toFixed(1).replace(/\.0$/, "") + "K";
  }
  return count.toString();
}

function TweetTickerItem({ tweet }: { tweet: Tweet }) {
  return (
    <div className="flex items-center gap-4 px-6 py-2 border-r border-border/50 whitespace-nowrap">
      {/* Avatar */}
      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-foreground/10 flex-shrink-0">
        <span className="text-[10px] font-medium text-foreground/70">
          {tweet.tweet_author_username.charAt(0).toUpperCase()}
        </span>
      </div>

      {/* Username */}
      <span className="text-xs font-medium text-foreground">
        @{tweet.tweet_author_username}
      </span>

      {/* Tweet preview */}
      <span className="text-xs text-muted-foreground max-w-[200px] truncate">
        {tweet.tweet_text}
      </span>

      {/* Engagement */}
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Heart className="h-3 w-3" />
          {formatCount(tweet.likes_count)}
        </span>
        <span className="flex items-center gap-1">
          <Repeat2 className="h-3 w-3" />
          {formatCount(tweet.retweets_count)}
        </span>
        <span className="flex items-center gap-1">
          <MessageCircle className="h-3 w-3" />
          {formatCount(tweet.replies_count)}
        </span>
      </div>
    </div>
  );
}

export function TweetTicker({ tweets = [], variant = "bar" }: TweetTickerProps) {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  if (!isClient || tweets.length === 0) {
    return null;
  }

  // Duplicate tweets for seamless infinite scroll
  const duplicatedTweets = [...tweets, ...tweets, ...tweets];

  const containerClasses =
    variant === "pill"
      ? "relative w-full max-w-xl overflow-hidden rounded-full border border-border/50 bg-card shadow-sm backdrop-blur"
      : "relative w-full max-w-full overflow-hidden border-b border-border/50 bg-card/50 backdrop-blur-sm";

  return (
    <div className={containerClasses}>
      {/* Gradient overlays for fade effect */}
      <div className="absolute left-0 top-0 bottom-0 w-16 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none" />
      <div className="absolute right-0 top-0 bottom-0 w-16 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none" />

      {/* Scrolling container */}
      <div className="tweet-ticker-scroll flex w-max">
        {duplicatedTweets.map((tweet, index) => (
          <TweetTickerItem key={`${tweet.id}-${index}`} tweet={tweet} />
        ))}
      </div>
    </div>
  );
}
