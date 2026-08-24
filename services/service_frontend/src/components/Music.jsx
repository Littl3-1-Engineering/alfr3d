import { motion } from 'framer-motion';
import { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import {
  Play, Pause, SkipBack, SkipForward, Volume2, Search, ListMusic,
  RefreshCw, ExternalLink, Settings, Disc3, PlusCircle, AlertTriangle,
  Cast, Save, Trash2,
} from 'lucide-react';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';
import { useAuth } from '../utils/useAuth';
import AudioVisualizer from './AudioVisualizer';

const Section = ({ icon: Icon, title, children, defaultOpen = true, right }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="glass rounded-2xl overflow-hidden mb-6">
      <div className="w-full flex items-center justify-between px-5 py-4">
        <span className="flex items-center gap-3 text-text-primary font-medium">
          <Icon className="w-5 h-5 text-fui-accent" />
          {title}
        </span>
        <div className="flex items-center gap-2">
          {right}
          <button onClick={() => setOpen(!open)} className="p-1 text-fui-text/60 hover:text-fui-accent">
            <ChevronIcon open={open} />
          </button>
        </div>
      </div>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
};

Section.propTypes = {
  icon: PropTypes.elementType.isRequired,
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  defaultOpen: PropTypes.bool,
  right: PropTypes.node,
};

const ChevronIcon = ({ open }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={`transition-transform ${open ? 'rotate-90' : ''}`}>
    <path d="m9 18 6-6-6-6" />
  </svg>
);

ChevronIcon.propTypes = {
  open: PropTypes.bool.isRequired,
};

const formatMs = (ms) => {
  if (!ms && ms !== 0) return '0:00';
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const SpotifySetup = ({ onSaved }) => {
  const { isAuthenticated } = useAuth();
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [redirectUri, setRedirectUri] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/music/spotify/auth`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, redirect_uri: redirectUri }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save');
      setMessage({ type: 'success', text: 'Credentials saved. Authorize below.' });
      onSaved();
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-text-secondary text-sm">
        Enter your Spotify Developer application credentials to enable playback control.
        Create one at <span className="text-fui-accent">developer.spotify.com</span> and add your callback URL.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-text-secondary mb-1">Client ID</label>
          <input
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-sm"
            placeholder="Spotify Client ID"
          />
        </div>
        <div>
          <label className="block text-sm text-text-secondary mb-1">Client Secret</label>
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-sm"
            placeholder="Spotify Client Secret"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm text-text-secondary mb-1">Redirect URI</label>
          <input
            type="text"
            value={redirectUri}
            onChange={(e) => setRedirectUri(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-sm"
            placeholder="http://<host>:8000/api/music/spotify/callback"
          />
        </div>
      </div>
      {message && (
        <div className={`text-sm ${message.type === 'success' ? 'text-success' : 'text-error'}`}>{message.text}</div>
      )}
      <div className="flex justify-end">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleSave}
          disabled={saving || !clientId || !clientSecret || !isAuthenticated}
          className="flex items-center gap-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 disabled:opacity-50"
        >
          <Settings className="w-4 h-4" />
          {saving ? 'Saving...' : 'Save Credentials'}
        </motion.button>
      </div>
    </div>
  );
};

SpotifySetup.propTypes = {
  onSaved: PropTypes.func.isRequired,
};

// Speaker volume/cast control has nothing to do with Spotify (it targets HA media_player
// entities directly) so it's rendered regardless of Spotify configuration/authorization state,
// not just inside the fully-authorized view. See todo_iot_central_control.md.
const CastToSpeakers = ({
  castData, castError, castSelection, setCastSelection, castTo, setCastVolume,
  deleteGroup, newGroupName, setNewGroupName, saveGroup, stopCast,
}) => (
  <Section icon={Cast} title="Cast to Speakers">
    {castError && (
      <p className="text-xs text-error mb-3">{castError}</p>
    )}
    {castData.speakers.length === 0 ? (
      <p className="text-text-tertiary text-sm">
        No Home Assistant speakers found. Enable the HA integration to cast playback.
      </p>
    ) : (
      <div className="space-y-2">
        {castData.speakers.map((s) => {
          const active = (castData.active_casts || []).includes(s.entity_id);
          const vol = s.volume_level != null ? Math.round(s.volume_level * 100) : 100;
          return (
            <div
              key={s.entity_id}
              className={`p-2 rounded-lg border ${active ? 'bg-primary/10 border-primary/40' : 'bg-white/5 border-white/10'}`}
            >
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={castSelection.includes(s.entity_id)}
                  onChange={(e) =>
                    setCastSelection((prev) =>
                      e.target.checked
                        ? [...prev, s.entity_id]
                        : prev.filter((id) => id !== s.entity_id)
                    )
                  }
                  className="accent-fui-accent shrink-0"
                  title="Select for group"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-text-primary text-sm truncate">{s.name}</p>
                  <p className={`text-xs truncate ${active ? 'text-success' : 'text-text-tertiary'}`}>
                    {active ? 'Casting' : s.state || 'off'}
                    {s.media_title ? ` · ${s.media_title}` : ''}
                  </p>
                </div>
                <button
                  onClick={() => castTo(s)}
                  className="p-1.5 rounded hover:bg-primary/20 text-primary shrink-0"
                  title={`Cast to ${s.name}`}
                >
                  <Cast className="w-4 h-4" />
                </button>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={vol}
                onChange={(e) => setCastVolume(s, Number(e.target.value))}
                className="w-full mt-1 accent-fui-accent"
                title={`${s.name} volume`}
              />
            </div>
          );
        })}
      </div>
    )}

    {castData.groups?.length > 0 && (
      <div className="mt-4">
        <p className="text-xs uppercase tracking-wide text-text-tertiary mb-2">Groups</p>
        <div className="space-y-2">
          {castData.groups.map((g) => (
            <div key={g.id} className="flex items-center gap-2 p-2 rounded-lg bg-white/5 border border-white/10">
              <div className="flex-1 min-w-0">
                <p className="text-text-primary text-sm truncate">{g.name}</p>
                <p className="text-text-tertiary text-xs truncate">{(g.entities || []).join(', ')}</p>
              </div>
              <button
                onClick={() => castTo({ name: g.name })}
                className="p-1.5 rounded hover:bg-primary/20 text-primary shrink-0"
                title={`Cast to ${g.name}`}
              >
                <Cast className="w-4 h-4" />
              </button>
              <button
                onClick={() => deleteGroup(g)}
                className="p-1.5 rounded hover:bg-error/20 text-error shrink-0"
                title="Delete group"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    )}

    <div className="mt-4">
      <p className="text-xs uppercase tracking-wide text-text-tertiary mb-2">Create Group</p>
      <div className="flex gap-2">
        <input
          type="text"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          placeholder="e.g. Living Room"
          className="flex-1 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-sm"
        />
        <button
          onClick={saveGroup}
          disabled={!newGroupName.trim() || castSelection.length === 0}
          className="flex items-center gap-1 px-3 py-2 bg-secondary/20 border border-secondary rounded-lg text-xs text-secondary hover:bg-secondary/30 disabled:opacity-50"
          title="Save selected speakers as a group"
        >
          <Save className="w-3.5 h-3.5" /> Save
        </button>
      </div>
    </div>

    {castData.active_casts?.length > 0 && (
      <button
        onClick={stopCast}
        className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-error text-error text-sm hover:bg-error/10"
      >
        Stop Casting
      </button>
    )}
  </Section>
);

CastToSpeakers.propTypes = {
  castData: PropTypes.shape({
    speakers: PropTypes.array,
    groups: PropTypes.array,
    active_casts: PropTypes.array,
  }).isRequired,
  castError: PropTypes.string,
  castSelection: PropTypes.arrayOf(PropTypes.string).isRequired,
  setCastSelection: PropTypes.func.isRequired,
  castTo: PropTypes.func.isRequired,
  setCastVolume: PropTypes.func.isRequired,
  deleteGroup: PropTypes.func.isRequired,
  newGroupName: PropTypes.string.isRequired,
  setNewGroupName: PropTypes.func.isRequired,
  saveGroup: PropTypes.func.isRequired,
  stopCast: PropTypes.func.isRequired,
};

const Music = () => {
  const { isAuthenticated } = useAuth();
  const [auth, setAuth] = useState(null);
  const [state, setState] = useState(null);
  const [devices, setDevices] = useState([]);
  const [queue, setQueue] = useState([]);
  const [playlists, setPlaylists] = useState([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showSetup, setShowSetup] = useState(false);
  const [castData, setCastData] = useState({ speakers: [], groups: [], active_casts: [] });
  const [castSelection, setCastSelection] = useState([]);
  const [newGroupName, setNewGroupName] = useState('');
  const [castError, setCastError] = useState(null);
  const refreshTimerRef = useRef(null);
  const lastTrackIdRef = useRef(null);

  const fetchAuth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/music/spotify/auth`);
      if (res.ok) setAuth(await res.json());
    } catch (e) {
      setError('Failed to check Spotify auth');
    }
  }, []);

  const fetchAll = useCallback(async () => {
    try {
      const [stateRes, devicesRes, queueRes, playlistsRes, speakersRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/music/spotify/status`),
        fetch(`${API_BASE_URL}/api/music/spotify/devices`),
        fetch(`${API_BASE_URL}/api/music/spotify/queue`),
        fetch(`${API_BASE_URL}/api/music/spotify/playlists`),
        fetch(`${API_BASE_URL}/api/music/speakers`),
      ]);
      if (stateRes.ok) setState(await stateRes.json());
      if (devicesRes.ok) setDevices((await devicesRes.json()).devices || []);
      if (queueRes.ok) setQueue(await queueRes.json());
      if (playlistsRes.ok) setPlaylists((await playlistsRes.json()).playlists || []);
      if (speakersRes.ok) setCastData(await speakersRes.json());
      setError(null);
    } catch (e) {
      setError('Failed to load Spotify state');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRecommendations = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/music/recommend?limit=10`);
      if (res.ok) setRecommendations((await res.json()).recommendations || []);
    } catch (e) {
      // non-fatal: recommendations can lag behind
    }
  }, []);

  const refresh = useCallback(() => {
    fetchAuth();
    fetchAll();
    fetchRecommendations();
  }, [fetchAuth, fetchAll, fetchRecommendations]);

  useEffect(() => {
    refresh();
    refreshTimerRef.current = setInterval(fetchAll, 5000);
    return () => clearInterval(refreshTimerRef.current);
  }, [refresh, fetchAll]);

  // Record listening history when the currently playing track changes
  useEffect(() => {
    const item = state?.item;
    if (!item?.id || item.id === lastTrackIdRef.current) return;
    lastTrackIdRef.current = item.id;
    const context = new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'day' : new Date().getHours() < 22 ? 'evening' : 'night';
    apiFetch(`${API_BASE_URL}/api/music/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track_id: item.id,
        name: item.name,
        artists: item.artists,
        album: item.album,
        context,
      }),
    }).catch(() => {});
  }, [state]);

  const control = async (endpoint, method = 'POST', body = null) => {
    try {
      await apiFetch(`${API_BASE_URL}/api/music/spotify/${endpoint}`, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      setTimeout(fetchAll, 300);
    } catch (e) {
      setError(`Control failed: ${e.message}`);
    }
  };

  const handleSeek = (e) => {
    const item = state?.item;
    if (!item?.duration_ms) return;
    const pos = Number(e.target.value);
    control('seek', 'POST', { position_ms: pos, device_id: state?.device?.id });
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/music/spotify/search?q=${encodeURIComponent(query)}`);
      if (res.ok) setResults((await res.json()).tracks || []);
    } catch (e) {
      setError('Search failed');
    } finally {
      setSearching(false);
    }
  };

  const playTrack = (uri) => control('play', 'POST', { context_uri: uri });

  const castFetch = async (endpoint, body) => {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/music/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Cast operation failed');
      }
      setCastError(null);
    } catch (e) {
      setCastError(e.message);
    }
    setTimeout(fetchAll, 400);
  };

  const castTo = (target) => {
    const body = target.entity_id
      ? { entity_id: target.entity_id, volume_percent: target.volume_level != null ? Math.round(target.volume_level * 100) : 100 }
      : { group_name: target.name };
    castFetch('cast', body);
  };

  const stopCast = () => castFetch('cast/stop', {});

  const setCastVolume = (target, vol) => {
    const body = target.entity_id
      ? { entity_id: target.entity_id, volume_percent: vol }
      : { group_name: target.name, volume_percent: vol };
    castFetch('cast/volume', body);
  };

  const saveGroup = () => {
    if (!newGroupName.trim() || castSelection.length === 0) return;
    castFetch('speakers/groups', { name: newGroupName, entities: castSelection });
    setNewGroupName('');
    setCastSelection([]);
  };

  const deleteGroup = (group) => castFetch('speakers/groups', { action: 'delete', id: group.id });

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-text-tertiary">Loading Spotify...</div>;
  }

  if (!auth?.configured) {
    return (
      <div>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-primary drop-shadow-lg">Music / Spotify</h2>
        </div>
        <Section icon={Settings} title="Spotify Setup">
          <SpotifySetup onSaved={() => { fetchAuth(); fetchAll(); }} />
        </Section>
        <CastToSpeakers
          castData={castData}
          castError={castError}
          castSelection={castSelection}
          setCastSelection={setCastSelection}
          castTo={castTo}
          setCastVolume={setCastVolume}
          deleteGroup={deleteGroup}
          newGroupName={newGroupName}
          setNewGroupName={setNewGroupName}
          saveGroup={saveGroup}
          stopCast={stopCast}
        />
      </div>
    );
  }

  if (auth?.configured && !auth?.authorized) {
    return (
      <div>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-primary drop-shadow-lg">Music / Spotify</h2>
        </div>
        <Section icon={Settings} title="Authorization Required">
          <div className="space-y-4">
            <p className="text-text-secondary text-sm">
              Spotify credentials are configured, but playback is not yet authorized.
            </p>
            <div className="flex flex-wrap gap-3">
              {auth.auth_url && (
                <motion.a
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  href={auth.auth_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30"
                >
                  <ExternalLink className="w-4 h-4" />
                  Authorize on Spotify
                </motion.a>
              )}
              <button
                onClick={() => setShowSetup(!showSetup)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-white/20 text-text-secondary hover:bg-white/5"
              >
                <Settings className="w-4 h-4" />
                Update Credentials
              </button>
            </div>
            {showSetup && <SpotifySetup onSaved={refresh} />}
          </div>
        </Section>
        <CastToSpeakers
          castData={castData}
          castError={castError}
          castSelection={castSelection}
          setCastSelection={setCastSelection}
          castTo={castTo}
          setCastVolume={setCastVolume}
          deleteGroup={deleteGroup}
          newGroupName={newGroupName}
          setNewGroupName={setNewGroupName}
          saveGroup={saveGroup}
          stopCast={stopCast}
        />
      </div>
    );
  }

  const item = state?.item;
  const isPlaying = state?.is_playing;
  const activeDevice = state?.device;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-primary drop-shadow-lg">Music / Spotify</h2>
        <button
          onClick={refresh}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/20 text-text-secondary hover:bg-white/5"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-error/10 border border-error text-error text-sm">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Now Playing */}
        <div className="lg:col-span-2">
          <Section icon={Disc3} title="Now Playing">
            <div className="flex flex-col sm:flex-row gap-6">
              <div className="w-48 h-48 shrink-0 rounded-lg overflow-hidden bg-white/5 flex items-center justify-center border border-white/10">
                {item?.album_art ? (
                  <img src={item.album_art} alt={item.album} className="w-full h-full object-cover" />
                ) : (
                  <Disc3 className="w-16 h-16 text-fui-text/40" />
                )}
              </div>
              <div className="flex-1 flex flex-col justify-between">
                <div>
                  {item ? (
                    <>
                      <h3 className="text-xl font-semibold text-text-primary">{item.name}</h3>
                      <p className="text-text-secondary">{item.artists?.join(', ')}</p>
                      <p className="text-text-tertiary text-sm">{item.album}</p>
                    </>
                  ) : (
                    <p className="text-text-tertiary">Nothing playing — pick a track or playlist below.</p>
                  )}
                </div>

                <div className="space-y-2">
                  <input
                    type="range"
                    min="0"
                    max={item?.duration_ms || 0}
                    value={state?.progress_ms || 0}
                    onChange={handleSeek}
                    disabled={!item || !isAuthenticated}
                    className="w-full accent-fui-accent disabled:opacity-40"
                  />
                  <div className="flex justify-between text-xs text-text-tertiary font-mono">
                    <span>{formatMs(state?.progress_ms)}</span>
                    <span>{formatMs(item?.duration_ms)}</span>
                  </div>
                </div>

                <div className="flex items-center justify-center gap-4 pt-2">
                  <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => control('previous')}
                    disabled={!item || !isAuthenticated}
                    className="p-3 rounded-full border border-white/20 text-text-primary hover:text-fui-accent hover:border-fui-accent disabled:opacity-40"
                    title="Previous"
                  >
                    <SkipBack className="w-5 h-5" />
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => control(isPlaying ? 'pause' : 'play')}
                    disabled={!activeDevice || !isAuthenticated}
                    className="p-4 rounded-full bg-primary/20 border border-primary text-primary hover:bg-primary/30 disabled:opacity-40"
                    title={isPlaying ? 'Pause' : 'Play'}
                  >
                    {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => control('next')}
                    disabled={!item || !isAuthenticated}
                    className="p-3 rounded-full border border-white/20 text-text-primary hover:text-fui-accent hover:border-fui-accent disabled:opacity-40"
                    title="Next"
                  >
                    <SkipForward className="w-5 h-5" />
                  </motion.button>
                </div>
              </div>
            </div>

            <AudioVisualizer
              trackId={item?.id}
              isPlaying={isPlaying}
              progressMs={state?.progress_ms || 0}
            />
          </Section>

          {/* Search */}
          <Section icon={Search} title="Search Tracks">
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="flex-1 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-sm"
                placeholder="Search songs on Spotify..."
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleSearch}
                disabled={searching || !query.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 disabled:opacity-50"
              >
                <Search className="w-4 h-4" />
                {searching ? 'Searching...' : 'Search'}
              </motion.button>
            </div>
            {results.length > 0 && (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {results.map((t) => (
                  <div key={t.id} className="flex items-center gap-3 p-2 rounded-lg bg-white/5 border border-white/10 hover:border-fui-accent/50">
                    {t.album_art && (
                      <img src={t.album_art} alt={t.album} className="w-10 h-10 rounded object-cover" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-text-primary text-sm truncate">{t.name}</p>
                      <p className="text-text-tertiary text-xs truncate">{t.artists?.join(', ')} · {t.album}</p>
                    </div>
                    <span className="text-text-tertiary text-xs font-mono">{formatMs(t.duration_ms)}</span>
                    <button
                      onClick={() => playTrack(t.uri)}
                      className="p-1.5 rounded hover:bg-primary/20 text-primary"
                      title="Play now"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => control('queue/add', 'POST', { uri: t.uri })}
                      className="p-1.5 rounded hover:bg-secondary/20 text-secondary"
                      title="Add to queue"
                    >
                      <PlusCircle className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Recommended for You */}
          <Section icon={Disc3} title="Recommended for You">
            {recommendations.length === 0 ? (
              <p className="text-text-tertiary text-sm">
                No recommendations yet — keep playing music and check back.
              </p>
            ) : (
              <>
                <div className="flex gap-2 mb-3">
                  <button
                    onClick={fetchRecommendations}
                    className="flex items-center gap-1 px-3 py-1.5 bg-primary/20 border border-primary rounded-lg text-xs text-primary hover:bg-primary/30"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Refresh
                  </button>
                  <button
                    onClick={() => playTrack(recommendations[0]?.uri)}
                    className="flex items-center gap-1 px-3 py-1.5 bg-secondary/20 border border-secondary rounded-lg text-xs text-secondary hover:bg-secondary/30"
                    title="Play top recommendation"
                  >
                    <Play className="w-3.5 h-3.5" /> Play Recommendations
                  </button>
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {recommendations.map((t) => (
                    <div key={t.id} className="flex items-center gap-3 p-2 rounded-lg bg-white/5 border border-white/10 hover:border-fui-accent/50">
                      {t.album_art && (
                        <img src={t.album_art} alt={t.album} className="w-10 h-10 rounded object-cover" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-text-primary text-sm truncate">{t.name}</p>
                        <p className="text-text-tertiary text-xs truncate">{t.artists?.join(', ')} · {t.album}</p>
                        {t.reason && (
                          <p className="text-env text-[11px] truncate">{t.reason}</p>
                        )}
                      </div>
                      <span className="text-text-tertiary text-xs font-mono">{formatMs(t.duration_ms)}</span>
                      <button
                        onClick={() => playTrack(t.uri)}
                        className="p-1.5 rounded hover:bg-primary/20 text-primary"
                        title="Play now"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => control('queue/add', 'POST', { uri: t.uri })}
                        className="p-1.5 rounded hover:bg-secondary/20 text-secondary"
                        title="Add to queue"
                      >
                        <PlusCircle className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Section>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Playlists */}
          <Section icon={ListMusic} title="Playlists">
            {playlists.length === 0 ? (
              <p className="text-text-tertiary text-sm">No playlists found.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {playlists.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => playTrack(p.uri)}
                    className="w-full flex items-center gap-3 p-2 rounded-lg bg-white/5 border border-white/10 hover:border-fui-accent/50 text-left"
                  >
                    {p.image ? (
                      <img src={p.image} alt={p.name} className="w-10 h-10 rounded object-cover" />
                    ) : (
                      <div className="w-10 h-10 rounded bg-white/10 flex items-center justify-center">
                        <ListMusic className="w-5 h-5 text-fui-text/50" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-text-primary text-sm truncate">{p.name}</p>
                      <p className="text-text-tertiary text-xs">{p.track_count} tracks</p>
                    </div>
                    <Play className="w-4 h-4 text-fui-accent shrink-0" />
                  </button>
                ))}
              </div>
            )}
          </Section>

          {/* Queue */}
          <Section icon={ListMusic} title="Queue">
            {queue?.queue?.length === 0 && !queue?.currently_playing ? (
              <p className="text-text-tertiary text-sm">Queue is empty.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {queue?.currently_playing && (
                  <div className="flex items-center gap-3 p-2 rounded-lg bg-primary/10 border border-primary/40">
                    <span className="text-xs text-primary font-bold uppercase shrink-0">Now</span>
                    <div className="min-w-0">
                      <p className="text-text-primary text-sm truncate">{queue.currently_playing.name}</p>
                      <p className="text-text-tertiary text-xs truncate">{queue.currently_playing.artists?.join(', ')}</p>
                    </div>
                  </div>
                )}
                {queue?.queue?.map((t, i) => (
                  <div key={`${t.id || i}`} className="flex items-center gap-3 p-2 rounded-lg bg-white/5 border border-white/10">
                    <span className="text-text-tertiary text-xs font-mono w-6">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-text-primary text-sm truncate">{t.name}</p>
                      <p className="text-text-tertiary text-xs truncate">{t.artists?.join(', ')}</p>
                    </div>
                    <span className="text-text-tertiary text-xs font-mono">{formatMs(t.duration_ms)}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Devices */}
          <Section icon={Volume2} title={`Devices${activeDevice?.name ? ` — ${activeDevice.name}` : ''}`}>
            {devices.length === 0 ? (
              <p className="text-text-tertiary text-sm">No active devices detected.</p>
            ) : (
              <div className="space-y-2">
                {devices.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => control('device', 'POST', { device_id: d.id })}
                    className={`w-full flex items-center justify-between p-2 rounded-lg border text-left ${
                      d.is_active
                        ? 'bg-primary/20 border-primary'
                        : 'bg-white/5 border-white/10 hover:border-fui-accent/50'
                    }`}
                  >
                    <span className="text-text-primary text-sm">{d.name}</span>
                    <span className={`text-xs ${d.is_active ? 'text-success' : 'text-text-tertiary'}`}>
                      {d.is_active ? 'Active' : d.type}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Section>

          {/* Cast to Speakers */}
          <CastToSpeakers
            castData={castData}
            castError={castError}
            castSelection={castSelection}
            setCastSelection={setCastSelection}
            castTo={castTo}
            setCastVolume={setCastVolume}
            deleteGroup={deleteGroup}
            newGroupName={newGroupName}
            setNewGroupName={setNewGroupName}
            saveGroup={saveGroup}
            stopCast={stopCast}
          />
        </div>
      </div>
    </div>
  );
};

export default Music;
