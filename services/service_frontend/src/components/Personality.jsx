import { motion } from 'framer-motion';
import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { Edit, Trash2, Plus, Save, X, User, Sparkles, Settings, RefreshCw } from 'lucide-react';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';

const usePersonality = () => {
  const [personality, setPersonality] = useState({
    name: 'Butler',
    sarcasm: 0.3,
    formality: 1.0,
    warmth: 0.4,
    patience: 0.8,
    linguistic_style: 'Archaic Butler',
    forbidden_words: '',
    verbal_tics: '',
  });
  const [presets, setPresets] = useState([]);
  const [llmConfig, setLlmConfig] = useState({ api_key: '', usage_limit: 10 });
  const [currentMood, setCurrentMood] = useState('neutral');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchPersonality = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/personality`);
      if (response.ok) {
        const data = await response.json();
        setPersonality(data);
      }
    } catch (error) {
      console.error('Error fetching personality:', error);
    }
  };

  const fetchPresets = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/personality/presets`);
      if (response.ok) {
        const data = await response.json();
        setPresets(data);
      }
    } catch (error) {
      console.error('Error fetching presets:', error);
    }
  };

  const fetchLlmConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/personality/llm-config`);
      if (response.ok) {
        const data = await response.json();
        setLlmConfig(data);
      }
    } catch (error) {
      console.error('Error fetching LLM config:', error);
    }
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchPersonality(), fetchPresets(), fetchLlmConfig()]);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();

    socket.on('personality_state', (state) => {
      setCurrentMood(state.mood || 'neutral');
    });

    return () => {
      socket.off('personality_state');
    };
  }, [fetchAll]);

  const savePersonality = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/personality`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(personality),
      });
      if (response.ok) {
        await fetchPresets();
      }
    } catch (error) {
      console.error('Error saving personality:', error);
    }
    setSaving(false);
  };

  const applyPreset = async (presetName) => {
    const preset = presets.find(p => p.name === presetName);
    if (preset) {
      setPersonality(preset);
    }
  };

  const saveLlmConfig = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/personality/llm-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(llmConfig),
      });
    } catch (error) {
      console.error('Error saving LLM config:', error);
    }
  };

  return {
    personality,
    setPersonality,
    presets,
    llmConfig,
    setLlmConfig,
    currentMood,
    loading,
    saving,
    savePersonality,
    applyPreset,
    saveLlmConfig,
    refresh: fetchAll,
  };
};

const useQuips = () => {
  const [quips, setQuips] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchQuips = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/quips');
      const data = await response.json();
      setQuips(data);
    } catch (error) {
      console.error('Error fetching quips:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuips();
  }, []);

  return { quips, loading, fetchQuips };
};

const useEditQuip = (onSave) => {
  const [editingId, setEditingId] = useState(null);
  const [editType, setEditType] = useState('');
  const [editText, setEditText] = useState('');

  const handleEdit = (id, type, text) => {
    setEditingId(id);
    setEditType(type);
    setEditText(text);
  };

  const handleSave = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/quips/' + editingId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: editType, quips: editText }),
      });
      if (response.ok) {
        onSave();
        setEditingId(null);
      }
    } catch (error) {
      console.error('Error updating quip:', error);
    }
  };

  return { editingId, editType, editText, setEditType, setEditText, handleEdit, handleSave, setEditingId };
};

const useAddQuip = (onSave) => {
  const [newType, setNewType] = useState('');
  const [newText, setNewText] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  const handleAdd = async () => {
    if (!newType || !newText) return;
    try {
      const response = await fetch(API_BASE_URL + '/api/quips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: newType, quips: newText }),
      });
      if (response.ok) {
        onSave();
        setNewType('');
        setNewText('');
        setShowAddForm(false);
      }
    } catch (error) {
      console.error('Error adding quip:', error);
    }
  };

  return { newType, newText, showAddForm, setNewType, setNewText, setShowAddForm, handleAdd };
};

const TraitSlider = ({ label, value, onChange, leftLabel, rightLabel }) => (
  <div className="mb-4">
    <div className="flex justify-between items-center mb-1">
      <span className="text-sm text-text-primary font-medium">{label}</span>
      <span className="text-xs text-text-secondary">{value.toFixed(1)}</span>
    </div>
    <input
      type="range"
      min="0"
      max="1"
      step="0.1"
      value={value}
      onChange={(e) => onChange(parseFloat(e.target.value))}
      className="w-full h-2 bg-fui-dim rounded-lg appearance-none cursor-pointer accent-fui-accent"
    />
    <div className="flex justify-between text-xs text-text-tertiary mt-1">
      <span>{leftLabel}</span>
      <span>{rightLabel}</span>
    </div>
  </div>
);

TraitSlider.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.number.isRequired,
  onChange: PropTypes.func.isRequired,
  leftLabel: PropTypes.string.isRequired,
  rightLabel: PropTypes.string.isRequired,
};

const Personality = () => {
  const { personality, setPersonality, presets, llmConfig, setLlmConfig, currentMood, loading, saving, savePersonality, applyPreset, saveLlmConfig, refresh } = usePersonality();
  const { quips, loading: quipsLoading, fetchQuips } = useQuips();
  const { editingId, editType, editText, setEditType, setEditText, handleEdit, handleSave, setEditingId } = useEditQuip(fetchQuips);
  const { newType, newText, showAddForm, setNewType, setNewText, setShowAddForm, handleAdd } = useAddQuip(fetchQuips);

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this quip?')) {
      try {
        const response = await fetch(API_BASE_URL + '/api/quips/' + id, {
          method: 'DELETE',
        });
        if (response.ok) {
          await fetchQuips();
        }
      } catch (error) {
        console.error('Error deleting quip:', error);
      }
    }
  };

  const handlePresetChange = (e) => {
    const presetName = e.target.value;
    applyPreset(presetName);
  };

  if (loading) {
    return <div className="text-center text-text-tertiary">Loading personality settings...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-primary drop-shadow-lg">Personality Matrix</h2>
        <button
          onClick={refresh}
          className="p-2 text-text-tertiary hover:text-fui-accent rounded transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <User className="w-5 h-5 text-fui-accent" />
            <h3 className="text-lg font-semibold text-fui-accent">Personality Traits</h3>
          </div>

          <div className="mb-4">
            <label className="block text-sm text-text-primary mb-2">Preset</label>
            <select
              value={personality.name}
              onChange={handlePresetChange}
              className="w-full p-2 bg-fui-dim border border-fui-border rounded text-text-primary"
            >
              {presets.map((preset) => (
                <option key={preset.name} value={preset.name}>
                  {preset.name}
                </option>
              ))}
              <option value="Custom">Custom</option>
            </select>
          </div>

          <TraitSlider
            label="Sarcasm"
            value={personality.sarcasm}
            onChange={(v) => setPersonality({ ...personality, sarcasm: v })}
            leftLabel="Earnest"
            rightLabel="Snarky"
          />

          <TraitSlider
            label="Formality"
            value={personality.formality}
            onChange={(v) => setPersonality({ ...personality, formality: v })}
            leftLabel="Slang"
            rightLabel="Royal"
          />

          <TraitSlider
            label="Warmth"
            value={personality.warmth}
            onChange={(v) => setPersonality({ ...personality, warmth: v })}
            leftLabel="Cold"
            rightLabel="Nurturing"
          />

          <TraitSlider
            label="Patience"
            value={personality.patience}
            onChange={(v) => setPersonality({ ...personality, patience: v })}
            leftLabel="Irritable"
            rightLabel="Saint"
          />

          <div className="mb-4">
            <label className="block text-sm text-text-primary mb-2">Linguistic Style</label>
            <input
              type="text"
              value={personality.linguistic_style}
              onChange={(e) => setPersonality({ ...personality, linguistic_style: e.target.value })}
              className="w-full p-2 bg-fui-dim border border-fui-border rounded text-text-primary"
              placeholder="e.g., Archaic Butler"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm text-text-primary mb-2">Verbal Tics</label>
            <input
              type="text"
              value={personality.verbal_tics}
              onChange={(e) => setPersonality({ ...personality, verbal_tics: e.target.value })}
              className="w-full p-2 bg-fui-dim border border-fui-border rounded text-text-primary"
              placeholder="e.g., I presume,Your Grace"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm text-text-primary mb-2">Forbidden Words</label>
            <input
              type="text"
              value={personality.forbidden_words}
              onChange={(e) => setPersonality({ ...personality, forbidden_words: e.target.value })}
              className="w-full p-2 bg-fui-dim border border-fui-border rounded text-text-primary"
              placeholder="e.g., stupid,dumb"
            />
          </div>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={savePersonality}
            disabled={saving}
            className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-fui-accent/20 border border-fui-accent rounded-lg text-fui-accent hover:bg-fui-accent/30 transition-colors"
          >
            <Save className="w-4 h-4" />
            <span>{saving ? 'Saving...' : 'Save Personality'}</span>
          </motion.button>
        </div>

        <div className="space-y-6">
          <div className="glass rounded-lg p-4">
            <div className="flex items-center space-x-2 mb-4">
              <Sparkles className="w-5 h-5 text-fui-accent" />
              <h3 className="text-lg font-semibold text-fui-accent">Current Mood</h3>
            </div>
            <div className="flex items-center justify-center p-6 bg-fui-dim rounded-lg">
              <div className="text-center">
                <div className={`text-4xl font-bold ${
                  currentMood === 'cheerful' ? 'text-success' :
                  currentMood === 'snarky' ? 'text-fui-accent' :
                  currentMood === 'exasperated' ? 'text-error' :
                  currentMood === 'irritable' ? 'text-warning' :
                  'text-text-primary'
                }`}>
                  {currentMood.toUpperCase()}
                </div>
                <div className="text-sm text-text-tertiary mt-2">
                  {personality.name} personality active
                </div>
              </div>
            </div>
          </div>

          <div className="glass rounded-lg p-4">
            <div className="flex items-center space-x-2 mb-4">
              <Settings className="w-5 h-5 text-fui-accent" />
              <h3 className="text-lg font-semibold text-fui-accent">LLM Settings</h3>
            </div>

            <div className="mb-4">
              <label className="block text-sm text-text-primary mb-2">API Key (Anthropic)</label>
              <input
                type="password"
                value={llmConfig.api_key}
                onChange={(e) => setLlmConfig({ ...llmConfig, api_key: e.target.value })}
                className="w-full p-2 bg-fui-dim border border-fui-border rounded text-text-primary"
                placeholder="sk-ant-..."
              />
            </div>

            <div className="mb-4">
              <label className="block text-sm text-text-primary mb-2">Daily Usage Limit</label>
              <input
                type="number"
                min="1"
                max="100"
                value={llmConfig.usage_limit}
                onChange={(e) => setLlmConfig({ ...llmConfig, usage_limit: parseInt(e.target.value) || 10 })}
                className="w-full p-2 bg-fui-dim border border-fui-border rounded text-text-primary"
              />
            </div>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={saveLlmConfig}
              className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-fui-accent/20 border border-fui-accent rounded-lg text-fui-accent hover:bg-fui-accent/30 transition-colors"
            >
              <Save className="w-4 h-4" />
              <span>Save LLM Settings</span>
            </motion.button>
          </div>
        </div>
      </div>

      <div className="glass rounded-lg p-4">
        <h3 className="text-lg font-semibold text-fui-accent mb-4">Quips</h3>

        {quipsLoading ? (
          <div className="text-center text-text-tertiary">Loading quips...</div>
        ) : (
          <div className="space-y-4">
            {quips.map((quip, index) => (
              <motion.div
                key={quip.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                className="flex items-center justify-between p-3 bg-fui-dim rounded-lg"
              >
                <div className="flex-1">
                  {editingId === quip.id ? (
                    <div className="space-y-2">
                      <input
                        value={editType}
                        onChange={(e) => setEditType(e.target.value)}
                        className="w-full p-2 bg-card rounded text-text-primary text-sm uppercase"
                        placeholder="Type"
                      />
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="w-full p-2 bg-card rounded text-text-primary"
                        rows={2}
                      />
                    </div>
                  ) : (
                    <>
                      <span className="text-sm text-primary uppercase tracking-wide">{quip.type}</span>
                      <p className="text-text-primary mt-1">{quip.quips}</p>
                    </>
                  )}
                </div>
                <div className="flex space-x-2 ml-4">
                  {editingId === quip.id ? (
                    <>
                      <button
                        onClick={handleSave}
                        className="p-2 text-success hover:bg-success/20 rounded"
                      >
                        <Save className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="p-2 text-text-tertiary hover:bg-border/20 rounded"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => handleEdit(quip.id, quip.type, quip.quips)}
                      className="p-2 text-primary hover:bg-primary/20 rounded"
                    >
                      <Edit className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(quip.id)}
                    className="p-2 text-error hover:bg-error/20 rounded"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {showAddForm && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mt-4 p-4 bg-fui-dim rounded-lg"
          >
            <h4 className="text-lg font-semibold text-primary mb-4">Add New Quip</h4>
            <div className="space-y-3">
              <input
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Type (e.g., smart, email, bedtime)"
              />
              <textarea
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                className="w-full p-2 bg-card rounded text-text-primary"
                rows={3}
                placeholder="Quip text"
              />
              <div className="flex space-x-2">
                <button
                  onClick={handleAdd}
                  className="px-4 py-2 bg-success/20 border border-success rounded text-success hover:bg-success/30"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="px-4 py-2 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30"
                >
                  Cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {!showAddForm && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowAddForm(true)}
            className="mt-4 flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 transition-colors"
          >
            <Plus className="w-5 h-5" />
            <span>Add New Quip</span>
          </motion.button>
        )}
      </div>
    </div>
  );
};

export default Personality;
