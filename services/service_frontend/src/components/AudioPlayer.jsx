import { useState, useEffect, useRef, useCallback } from 'react';

const AudioPlayer = () => {
  const [audioQueue, setAudioQueue] = useState([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [userInteracted, setUserInteracted] = useState(false);
  const [playedAudioUrls, setPlayedAudioUrls] = useState(new Set());
  const audioRef = useRef(null);

  const playNextAudio = useCallback(async () => {
    if (audioQueue.length === 0) return;

    const nextAudio = audioQueue[0];

    // Check if audio file exists before attempting to play (with retry)
    const checkFileExists = async (retries = 3) => {
      for (let i = 0; i < retries; i++) {
        try {
          const response = await fetch(nextAudio.audio_url, { method: 'HEAD' });
          if (response.ok) {
            return true;
          }
          // Wait before retry
          if (i < retries - 1) {
            await new Promise(resolve => setTimeout(resolve, 1000));
          }
        } catch (error) {
          console.warn(`Audio file check attempt ${i + 1} failed:`, error);
          if (i < retries - 1) {
            await new Promise(resolve => setTimeout(resolve, 1000));
          }
        }
      }
      return false;
    };

    const fileExists = await checkFileExists();
    if (!fileExists) {
      console.error('Audio file not found after retries:', nextAudio.audio_url);
      // Mark as played to prevent future attempts
      setPlayedAudioUrls(current => {
        const newSet = new Set([...current, nextAudio.audio_url]);
        console.log('Marked missing file as played, total played URLs:', newSet.size);
        return newSet;
      });
      setAudioQueue(prev => prev.slice(1));
      return;
    }

    setIsPlaying(true);

    if (audioRef.current) {
      audioRef.current.src = nextAudio.audio_url;
      audioRef.current.play().catch(error => {
        console.error('Audio playback failed:', error);
        // Mark as played and remove from queue
        setPlayedAudioUrls(current => new Set([...current, nextAudio.audio_url]));
        setAudioQueue(prev => prev.slice(1));
        setIsPlaying(false);
      });
    }
  }, [audioQueue]);

  // Detect user interaction for audio autoplay
  useEffect(() => {
    const handleUserInteraction = () => {
      setUserInteracted(true);
      // Remove listeners after first interaction
      document.removeEventListener('click', handleUserInteraction);
      document.removeEventListener('keydown', handleUserInteraction);
      document.removeEventListener('touchstart', handleUserInteraction);
    };

    document.addEventListener('click', handleUserInteraction);
    document.addEventListener('keydown', handleUserInteraction);
    document.addEventListener('touchstart', handleUserInteraction);

    return () => {
      document.removeEventListener('click', handleUserInteraction);
      document.removeEventListener('keydown', handleUserInteraction);
      document.removeEventListener('touchstart', handleUserInteraction);
    };
  }, []);

  // Periodically clean up old played URLs to prevent memory leaks
  useEffect(() => {
    const cleanupInterval = setInterval(() => {
      setPlayedAudioUrls(current => {
        // Keep only the most recent 50 played URLs
        const urls = Array.from(current);
        if (urls.length > 50) {
          return new Set(urls.slice(-50));
        }
        return current;
      });
    }, 60000); // Clean up every minute

    return () => clearInterval(cleanupInterval);
  }, []);

  // Use ref to avoid dependency issues
  const playedUrlsRef = useRef(playedAudioUrls);
  playedUrlsRef.current = playedAudioUrls;

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const response = await fetch('/api/events');
        const events = await response.json();

        // Find new audio events
        const audioEvents = events.filter(event => event.type === 'audio' && event.audio_url);

        if (audioEvents.length > 0) {
          // Add to queue if not already there, not previously played, and recent
          setAudioQueue(prevQueue => {
            const existingUrls = prevQueue.map(item => item.audio_url);
            const now = new Date();
            const tenMinutesAgo = new Date(now.getTime() - 10 * 60 * 1000); // 10 minutes ago

            const newItems = audioEvents.filter(event => {
              // Check if event is recent (within last 10 minutes)
              const eventTime = new Date(event.time);
              if (eventTime < tenMinutesAgo) {
                console.log('Skipping old audio event:', event.audio_url, 'time:', event.time);
                return false; // Skip old events
              }

              const isAlreadyQueued = existingUrls.includes(event.audio_url);
              const isAlreadyPlayed = playedUrlsRef.current.has(event.audio_url);

              if (isAlreadyPlayed) {
                console.log('Skipping already played audio:', event.audio_url);
              }

              return !isAlreadyQueued && !isAlreadyPlayed;
            });
            return [...prevQueue, ...newItems];
          });
        }
      } catch (error) {
        console.error('Error fetching events for audio:', error);
      }
    };

    fetchEvents();
    const interval = setInterval(fetchEvents, 2000); // Check more frequently for audio
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!isPlaying && audioQueue.length > 0 && userInteracted) {
      // Add delay to ensure audio file is fully written and available
      const timer = setTimeout(() => {
        playNextAudio();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [audioQueue, isPlaying, playNextAudio, userInteracted]);

  const handleAudioEnded = () => {
    // Mark this audio as played and remove from queue
    setAudioQueue(prev => {
      if (prev.length > 0) {
        console.log('Marking audio as played:', prev[0].audio_url);
        setPlayedAudioUrls(current => {
          const newSet = new Set([...current, prev[0].audio_url]);
          console.log('Played URLs count:', newSet.size);
          return newSet;
        });
      }
      return prev.slice(1);
    });
    setIsPlaying(false);
  };

  const handleAudioError = () => {
    console.error('Audio error occurred');
    // Mark failed audio as played and remove from queue
    setAudioQueue(prev => {
      if (prev.length > 0) {
        console.log('Marking failed audio as played:', prev[0].audio_url);
        setPlayedAudioUrls(current => {
          const newSet = new Set([...current, prev[0].audio_url]);
          console.log('Played URLs count after error:', newSet.size);
          return newSet;
        });
      }
      return prev.slice(1);
    });
    setIsPlaying(false);
  };

  return (
    <audio
      ref={audioRef}
      onEnded={handleAudioEnded}
      onError={handleAudioError}
      style={{ display: 'none' }}
    />
  );
};

export default AudioPlayer;
