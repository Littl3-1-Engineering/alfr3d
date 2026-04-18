import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';

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
          const response = await fetch(API_BASE_URL + nextAudio.audio_url, { method: 'HEAD' });
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
        return newSet;
      });
      setAudioQueue(prev => prev.slice(1));
      return;
    }

    setIsPlaying(true);

    if (audioRef.current) {
      const audio = audioRef.current;

      // Wait for audio to be ready before playing to prevent interrupted error
      const audioReady = new Promise((resolve, reject) => {
        const onCanPlay = () => {
          audio.removeEventListener('canplay', onCanPlay);
          audio.removeEventListener('error', onError);
          resolve(true);
        };
        const onError = () => {
          audio.removeEventListener('canplay', onCanPlay);
          audio.removeEventListener('error', onError);
          reject(new Error('Audio failed to load'));
        };
        audio.addEventListener('canplay', onCanPlay);
        audio.addEventListener('error', onError);

        // Timeout fallback - if canplay doesn't fire within 10s, try to play anyway
        setTimeout(() => {
          audio.removeEventListener('canplay', onCanPlay);
          audio.removeEventListener('error', onError);
          resolve(false);
        }, 10000);
      });

      audio.src = API_BASE_URL + nextAudio.audio_url;
      audio.load();

      try {
        await audioReady;
        await audio.play();
      } catch (error) {
        console.error('Audio playback failed:', error);
        console.error('Audio element error details:', {
          src: audio.src,
          error: error.message,
          networkState: audio.networkState,
          readyState: audio.readyState,
          duration: audio.duration
        });
        setPlayedAudioUrls(current => new Set([...current, nextAudio.audio_url]));
        setAudioQueue(prev => prev.slice(1));
        setIsPlaying(false);
      }
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

  const processAudioEvents = (events) => {
    const audioEvents = events.filter(event => event.type === 'audio' && event.audio_url);

    if (audioEvents.length > 0) {
      setAudioQueue(prevQueue => {
        const existingUrls = prevQueue.map(item => item.audio_url);

        const newItems = audioEvents.filter(event => {
          const isAlreadyQueued = existingUrls.includes(event.audio_url);
          const isAlreadyPlayed = playedUrlsRef.current.has(event.audio_url);

          if (isAlreadyPlayed) {
            return false;
          }

          return !isAlreadyQueued && !isAlreadyPlayed;
        });
        return [...prevQueue, ...newItems];
      });
    }
  };

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/events');
        const events = await response.json();
        processAudioEvents(events);
      } catch (error) {
        console.error('Error fetching events for audio:', error);
      }
    };

    fetchEvents();
    const interval = setInterval(fetchEvents, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    socket.on('events', (events) => {
      processAudioEvents(events);
    });

    return () => {
      socket.off('events');
    };
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
    setAudioQueue(prev => {
      if (prev.length > 0) {
        setPlayedAudioUrls(current => {
          return new Set([...current, prev[0].audio_url]);
        });
      }
      return prev.slice(1);
    });
    setIsPlaying(false);
  };

  const handleAudioError = () => {
    setAudioQueue(prev => {
      if (prev.length > 0) {
        setPlayedAudioUrls(current => {
          return new Set([...current, prev[0].audio_url]);
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
      preload="auto"
      style={{ display: 'none' }}
    />
  );
};

export default AudioPlayer;
