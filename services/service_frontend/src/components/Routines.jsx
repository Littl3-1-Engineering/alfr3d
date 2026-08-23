import { motion } from 'framer-motion';
import { useState } from 'react';
import {
  Plus, Play, Trash2, Save, Clock, RefreshCw, Zap, Mail, Lightbulb,
  Sunrise, Sunset, UserPlus, UserMinus, Power, PowerOff, UserCheck,
  UserX, Home, DoorClosed, Thermometer, Gauge, Lock, Unlock, Blinds, DoorOpen, Wind, Filter,
  Music4, Volume2, Pause, SkipForward, SkipBack, Cast,
} from 'lucide-react';
import { useTheme } from '../utils/useTheme';
import { useAuth } from '../utils/useAuth';
import { apiFetch } from '../utils/apiClient';
import { API_BASE_URL } from '../config';
import {
  useRoutines, useCreateRoutine, useUpdateRoutine, useDeleteRoutine,
  useIotDevices, useDevices, useUsers,
} from '../hooks/useApi';

const TRIGGER_TYPES = [
  { value: 'sunrise', label: 'Sunrise', icon: <Sunrise className="w-4 h-4" /> },
  { value: 'sunset', label: 'Sunset', icon: <Sunset className="w-4 h-4" /> },
  { value: 'person_arrives', label: 'Person arrives', icon: <UserPlus className="w-4 h-4" /> },
  { value: 'person_leaves', label: 'Person leaves', icon: <UserMinus className="w-4 h-4" /> },
  { value: 'device_turns_on', label: 'Device turns on', icon: <Power className="w-4 h-4" /> },
  { value: 'device_turns_off', label: 'Device turns off', icon: <PowerOff className="w-4 h-4" /> },
];

const CONDITION_TYPES = [
  { value: 'person_is_home', label: 'Person is home', icon: <UserCheck className="w-4 h-4" /> },
  { value: 'person_is_away', label: 'Person is away', icon: <UserX className="w-4 h-4" /> },
  { value: 'anyone_home', label: 'Anyone home', icon: <Home className="w-4 h-4" /> },
  { value: 'no_one_home', label: 'Nobody home', icon: <DoorClosed className="w-4 h-4" /> },
  { value: 'device_is_on', label: 'Device is on', icon: <Power className="w-4 h-4" /> },
  { value: 'device_is_off', label: 'Device is off', icon: <PowerOff className="w-4 h-4" /> },
  { value: 'temperature_above', label: 'Temperature above', icon: <Thermometer className="w-4 h-4" /> },
  { value: 'temperature_below', label: 'Temperature below', icon: <Thermometer className="w-4 h-4" /> },
  { value: 'mode', label: 'Mode is', icon: <Gauge className="w-4 h-4" /> },
];

const ACTION_TYPES = [
  { value: 'speak', label: 'Speak', icon: <Zap className="w-4 h-4" /> },
  { value: 'device', label: 'Device (LAN)', icon: <Lightbulb className="w-4 h-4" /> },
  { value: 'email', label: 'Email', icon: <Mail className="w-4 h-4" /> },
  { value: 'thermostat_set', label: 'Set thermostat', icon: <Thermometer className="w-4 h-4" /> },
  { value: 'lock', label: 'Lock door', icon: <Lock className="w-4 h-4" /> },
  { value: 'unlock', label: 'Unlock door', icon: <Unlock className="w-4 h-4" /> },
  { value: 'cover_open', label: 'Open cover', icon: <Blinds className="w-4 h-4" /> },
  { value: 'cover_close', label: 'Close cover', icon: <DoorOpen className="w-4 h-4" /> },
  { value: 'music', label: 'Music (Spotify)', icon: <Music4 className="w-4 h-4" /> },
];

const MUSIC_ACTIONS = [
  { value: 'play', label: 'Play', icon: <Play className="w-4 h-4" /> },
  { value: 'pause', label: 'Pause', icon: <Pause className="w-4 h-4" /> },
  { value: 'next', label: 'Next', icon: <SkipForward className="w-4 h-4" /> },
  { value: 'previous', label: 'Previous', icon: <SkipBack className="w-4 h-4" /> },
  { value: 'volume', label: 'Volume', icon: <Volume2 className="w-4 h-4" /> },
  { value: 'cast', label: 'Cast to Speaker', icon: <Cast className="w-4 h-4" /> },
  { value: 'stop_cast', label: 'Stop Casting', icon: <Cast className="w-4 h-4" /> },
];

const MODES = ['heat', 'cool', 'auto', 'off'];

const triggerMeta = (type) => TRIGGER_TYPES.find((t) => t.value === type);
const conditionMeta = (type) => CONDITION_TYPES.find((t) => t.value === type);
const actionMeta = (type) => ACTION_TYPES.find((t) => t.value === type);

const emptyForm = () => ({
  name: '',
  time: '08:00',
  recurrence: 'daily',
  enabled: true,
  triggers: [],
  conditions: [],
  actions: [],
});

const Routines = () => {
  useTheme();
  const { isAuthenticated } = useAuth();
  const { data: routines = [], isLoading, error } = useRoutines();
  const createRoutine = useCreateRoutine();
  const updateRoutine = useUpdateRoutine();
  const deleteRoutine = useDeleteRoutine();
  const { data: iotDevices = [] } = useIotDevices();
  const { data: devices = [] } = useDevices();
  const { data: users = [] } = useUsers();

  const [selectedRoutine, setSelectedRoutine] = useState(null);
  const [formData, setFormData] = useState(emptyForm());
  const [showForm, setShowForm] = useState(false);
  const isSunriseSunset = selectedRoutine?.name === 'Sunrise' || selectedRoutine?.name === 'Sunset';

  const handleSave = async () => {
    try {
      if (selectedRoutine) {
        await updateRoutine.mutateAsync({ id: selectedRoutine.id, ...formData });
      } else {
        await createRoutine.mutateAsync(formData);
      }
      resetForm();
    } catch (error) {
      console.error('Failed to save routine:', error);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteRoutine.mutateAsync(id);
      if (selectedRoutine?.id === id) {
        resetForm();
      }
    } catch (error) {
      console.error('Failed to delete routine:', error);
    }
  };

  const handleRun = async (id) => {
    try {
      await apiFetch(`${API_BASE_URL}/api/routines/${id}/run`, { method: 'POST' });
    } catch (error) {
      console.error('Failed to run routine:', error);
    }
  };

  const resetForm = () => {
    setFormData(emptyForm());
    setSelectedRoutine(null);
    setShowForm(false);
  };

  const formatTimeForInput = (timeValue) => {
    if (timeValue && timeValue.match(/^\d{2}:\d{2}$/)) {
      return timeValue;
    }
    if (timeValue && timeValue.match(/^\d{2}:\d{2}:\d{2}$/)) {
      return timeValue.substring(0, 5);
    }
    return '08:00';
  };

  const editRoutine = (routine) => {
    setFormData({
      name: routine.name,
      time: formatTimeForInput(routine.time),
      recurrence: routine.recurrence || 'daily',
      enabled: routine.enabled,
      triggers: routine.triggers || [],
      conditions: routine.conditions || [],
      actions: routine.actions || [],
    });
    setSelectedRoutine(routine);
    setShowForm(true);
  };

  const update = (field, value) => setFormData({ ...formData, [field]: value });

  // --- Trigger / Condition / Action list helpers ---

  const addItem = (field, type, defaults) => {
    const item = { type, params: { ...defaults } };
    update(field, [...formData[field], item]);
  };

  const updateItem = (field, index, value) => {
    const updated = [...formData[field]];
    updated[index] = { type: value, params: {} };
    update(field, updated);
  };

  const updateItemParam = (field, index, key, value) => {
    const updated = [...formData[field]];
    updated[index] = { ...updated[index], params: { ...updated[index].params, [key]: value } };
    update(field, updated);
  };

  const removeItem = (field, index) => {
    update(field, formData[field].filter((_, i) => i !== index));
  };

  const addAction = (type) => {
    const defaults = {};
    if (type === 'speak') defaults.text = '';
    if (type === 'device') { defaults.device_id = ''; defaults.action = 'on'; }
    if (type === 'email') { defaults.to = ''; defaults.subject = ''; defaults.body = ''; }
    if (type === 'thermostat_set') { defaults.device_id = ''; defaults.temperature = 21; defaults.mode = 'heat'; }
    if (type === 'music') { defaults.action = 'play'; defaults.query = ''; defaults.volume_percent = 50; }
    addItem('actions', type, defaults);
  };

  const addTrigger = (type) => {
    const defaults = {};
    if (type === 'person_arrives' || type === 'person_leaves') defaults.user_id = '';
    if (type === 'device_turns_on' || type === 'device_turns_off') defaults.device_id = '';
    addItem('triggers', type, defaults);
  };

  const addCondition = (type) => {
    const defaults = {};
    if (type === 'person_is_home' || type === 'person_is_away') defaults.user_id = '';
    if (type === 'device_is_on' || type === 'device_is_off') defaults.device_id = '';
    if (type === 'temperature_above' || type === 'temperature_below') defaults.value = 25;
    if (type === 'mode') defaults.mode = 'day';
    addItem('conditions', type, defaults);
  };

  const updateAction = (index, field, value) => {
    if (field === 'type') {
      updateItem('actions', index, value);
    } else if (field.startsWith('params.')) {
      updateItemParam('actions', index, field.replace('params.', ''), value);
    }
  };

  const inputCls = "w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-sm";
  const selectCls = "px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm";

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-primary drop-shadow-lg">Automation Routines</h2>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => { resetForm(); setShowForm(true); }}
          disabled={!isAuthenticated}
          className="flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="w-5 h-5" />
          <span>New Routine</span>
        </motion.button>
      </div>

      <div className="flex gap-6">
        {/* Routine List */}
        <div className="w-72 space-y-3">
          {isLoading ? (
            <div className="text-text-tertiary">Loading...</div>
          ) : error ? (
            <div className="text-error">Failed to load routines</div>
          ) : routines.length === 0 ? (
            <div className="text-text-tertiary">No routines yet</div>
          ) : (
            routines.map((routine) => {
              const triggerCount = (routine.triggers || []).length;
              const conditionCount = (routine.conditions || []).length;
              return (
                <motion.div
                  key={routine.id}
                  whileHover={{ scale: 1.02 }}
                  className={`p-4 rounded-lg border cursor-pointer transition-all ${
                    selectedRoutine?.id === routine.id
                      ? 'bg-primary/20 border-primary'
                      : 'bg-white/5 border-white/10 hover:border-primary/50'
                  }`}
                  onClick={() => editRoutine(routine)}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-semibold text-text-primary">{routine.name}</h3>
                      <div className="flex items-center gap-2 mt-1 text-sm text-text-tertiary">
                        <Clock className="w-3 h-3" />
                        <span>{routine.time?.substring(0, 5)}</span>
                        <span className="capitalize">({routine.recurrence || 'daily'})</span>
                      </div>
                      {(triggerCount > 0 || conditionCount > 0) && (
                        <div className="flex items-center gap-2 mt-1 text-xs text-text-tertiary">
                          <span>{triggerCount} trigger{triggerCount === 1 ? '' : 's'}</span>
                          <Filter className="w-3 h-3" />
                          <span>{conditionCount} condition{conditionCount === 1 ? '' : 's'}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRun(routine.id); }}
                        disabled={!isAuthenticated}
                        className="p-1.5 rounded hover:bg-success/20 text-success disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(routine.id); }}
                        disabled={!isAuthenticated}
                        className="p-1.5 rounded hover:bg-error/20 text-error disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })
          )}
        </div>

        {/* Editor Panel */}
        <div className="flex-1">
          {showForm ? (
            <div className="glass rounded-lg p-6 space-y-5">
              <h3 className="text-lg font-semibold text-text-primary">
                {selectedRoutine ? 'Edit Routine' : 'Create Routine'}
              </h3>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Name</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => update('name', e.target.value)}
                    disabled={isSunriseSunset}
                    className={`${inputCls} disabled:opacity-50 disabled:cursor-not-allowed`}
                    placeholder="Morning Routine"
                  />
                </div>
                <div>
                  <label className="block text-sm text-text-secondary mb-1">
                    Time {isSunriseSunset && <span className="text-xs text-text-tertiary">(Auto-synced with sunrise/sunset)</span>}
                  </label>
                  <div className="flex gap-2 items-center">
                    <input
                      type="number"
                      min="0"
                      max="23"
                      value={formData.time.split(':')[0]}
                      onChange={(e) => {
                        const hour = String(e.target.value).padStart(2, '0');
                        const minute = formData.time.split(':')[1] || '00';
                        update('time', `${hour}:${minute}`);
                      }}
                      disabled={isSunriseSunset}
                      className={`w-14 ${inputCls} text-center disabled:opacity-50 disabled:cursor-not-allowed`}
                      placeholder="00"
                    />
                    <span className="text-text-secondary">:</span>
                    <input
                      type="number"
                      min="0"
                      max="59"
                      value={formData.time.split(':')[1]}
                      onChange={(e) => {
                        const hour = formData.time.split(':')[0] || '00';
                        const minute = String(e.target.value).padStart(2, '0');
                        update('time', `${hour}:${minute}`);
                      }}
                      disabled={isSunriseSunset}
                      className={`w-14 ${inputCls} text-center disabled:opacity-50 disabled:cursor-not-allowed`}
                      placeholder="00"
                    />
                    <span className="text-xs text-text-tertiary">(24hr)</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Recurrence</label>
                  <select
                    value={formData.recurrence}
                    onChange={(e) => update('recurrence', e.target.value)}
                    disabled={isSunriseSunset}
                    className={`${inputCls} disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    <option value="once">Once</option>
                    <option value="daily">Daily</option>
                    <option value="weekdays">Weekdays</option>
                    <option value="weekly">Weekly</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="enabled"
                    checked={formData.enabled}
                    onChange={(e) => update('enabled', e.target.checked)}
                    className="w-4 h-4"
                  />
                  <label htmlFor="enabled" className="text-text-primary">Enabled</label>
                </div>
              </div>

              {/* WHEN: Event Triggers */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-text-secondary font-medium">WHEN — Event Triggers <span className="text-xs text-text-tertiary">(any match, in addition to the time above)</span></label>
                  <div className="flex gap-2">
                    {TRIGGER_TYPES.map((t) => (
                      <button
                        key={t.value}
                        onClick={() => addTrigger(t.value)}
                        className="flex items-center gap-1 px-2 py-1 rounded bg-secondary/20 border border-secondary text-secondary text-xs hover:bg-secondary/30"
                        title={t.label}
                      >
                        {t.icon} {t.label}
                      </button>
                    ))}
                  </div>
                </div>
                {formData.triggers.length === 0 && (
                  <p className="text-xs text-text-tertiary mb-2">No event triggers. The routine will fire only at the scheduled time.</p>
                )}
                <div className="space-y-2">
                  {formData.triggers.map((trigger, index) => {
                    const meta = triggerMeta(trigger.type);
                    return (
                      <div key={index} className="flex items-center gap-2 p-3 rounded bg-white/5 border border-white/10">
                        <span className="text-secondary">{meta?.icon || <Wind className="w-4 h-4" />}</span>
                        <select
                          value={trigger.type}
                          onChange={(e) => updateItem('triggers', index, e.target.value)}
                          className={selectCls}
                        >
                          {TRIGGER_TYPES.map((t) => (
                            <option key={t.value} value={t.value}>{t.label}</option>
                          ))}
                        </select>
                        {(trigger.type === 'person_arrives' || trigger.type === 'person_leaves') && (
                          <select
                            value={trigger.params.user_id || ''}
                            onChange={(e) => updateItemParam('triggers', index, 'user_id', e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select person...</option>
                            {users.map((u) => (
                              <option key={u.id} value={u.id}>{u.name}</option>
                            ))}
                          </select>
                        )}
                        {(trigger.type === 'device_turns_on' || trigger.type === 'device_turns_off') && (
                          <select
                            value={trigger.params.device_id || ''}
                            onChange={(e) => updateItemParam('triggers', index, 'device_id', e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select device...</option>
                            {devices.map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                          </select>
                        )}
                        <button
                          onClick={() => removeItem('triggers', index)}
                          className="p-1 rounded hover:bg-error/20 text-error ml-auto"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* IF: Conditions */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-text-secondary font-medium">IF — Conditions <span className="text-xs text-text-tertiary">(all must be true)</span></label>
                  <div className="flex gap-2 flex-wrap">
                    {CONDITION_TYPES.map((t) => (
                      <button
                        key={t.value}
                        onClick={() => addCondition(t.value)}
                        className="flex items-center gap-1 px-2 py-1 rounded bg-env/20 border border-env text-env text-xs hover:bg-env/30"
                        title={t.label}
                      >
                        {t.icon} {t.label}
                      </button>
                    ))}
                  </div>
                </div>
                {formData.conditions.length === 0 && (
                  <p className="text-xs text-text-tertiary mb-2">No conditions. The routine will run whenever its trigger fires.</p>
                )}
                <div className="space-y-2">
                  {formData.conditions.map((condition, index) => {
                    const meta = conditionMeta(condition.type);
                    return (
                      <div key={index} className="flex items-center gap-2 p-3 rounded bg-white/5 border border-white/10">
                        <span className="text-env">{meta?.icon || <Gauge className="w-4 h-4" />}</span>
                        <select
                          value={condition.type}
                          onChange={(e) => updateItem('conditions', index, e.target.value)}
                          className={selectCls}
                        >
                          {CONDITION_TYPES.map((t) => (
                            <option key={t.value} value={t.value}>{t.label}</option>
                          ))}
                        </select>
                        {(condition.type === 'person_is_home' || condition.type === 'person_is_away') && (
                          <select
                            value={condition.params.user_id || ''}
                            onChange={(e) => updateItemParam('conditions', index, 'user_id', e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select person...</option>
                            {users.map((u) => (
                              <option key={u.id} value={u.id}>{u.name}</option>
                            ))}
                          </select>
                        )}
                        {(condition.type === 'device_is_on' || condition.type === 'device_is_off') && (
                          <select
                            value={condition.params.device_id || ''}
                            onChange={(e) => updateItemParam('conditions', index, 'device_id', e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select device...</option>
                            {devices.map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                          </select>
                        )}
                        {(condition.type === 'temperature_above' || condition.type === 'temperature_below') && (
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              value={condition.params.value ?? ''}
                              onChange={(e) => updateItemParam('conditions', index, 'value', Number(e.target.value))}
                              className="w-20 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                            />
                            <span className="text-xs text-text-tertiary">°F</span>
                          </div>
                        )}
                        {condition.type === 'mode' && (
                          <select
                            value={condition.params.mode || 'day'}
                            onChange={(e) => updateItemParam('conditions', index, 'mode', e.target.value)}
                            className={selectCls}
                          >
                            <option value="day">Day</option>
                            <option value="night">Night</option>
                            <option value="home">Home (someone present)</option>
                            <option value="away">Away (nobody present)</option>
                          </select>
                        )}
                        <button
                          onClick={() => removeItem('conditions', index)}
                          className="p-1 rounded hover:bg-error/20 text-error ml-auto"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* THEN: Actions */}
              <div>
                <label className="block text-sm text-text-secondary mb-2">THEN — Actions</label>
                <div className="flex gap-2 mb-3 flex-wrap">
                  {ACTION_TYPES.map((t) => (
                    <button
                      key={t.value}
                      onClick={() => addAction(t.value)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded bg-primary/20 border border-primary text-primary text-sm hover:bg-primary/30"
                    >
                      {t.icon} {t.label}
                    </button>
                  ))}
                </div>

                <div className="space-y-2">
                  {formData.actions.map((action, index) => (
                    <div key={index} className="flex items-center gap-2 p-3 rounded bg-white/5 border border-white/10">
                      <span className="text-text-tertiary">{actionMeta(action.type)?.icon}</span>
                      <select
                        value={action.type}
                        onChange={(e) => updateAction(index, 'type', e.target.value)}
                        className={selectCls}
                      >
                        {ACTION_TYPES.map((t) => (
                          <option key={t.value} value={t.value}>{t.label}</option>
                        ))}
                      </select>
                      {action.type === 'speak' && (
                        <input
                          type="text"
                          placeholder="Text to speak..."
                          value={action.params.text || ''}
                          onChange={(e) => updateAction(index, 'params.text', e.target.value)}
                          className="flex-1 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                        />
                      )}
                      {action.type === 'device' && (
                        <>
                          <select
                            value={action.params.device_id || ''}
                            onChange={(e) => updateAction(index, 'params.device_id', e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select device...</option>
                            {devices.map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                          </select>
                          <select
                            value={action.params.action || 'on'}
                            onChange={(e) => updateAction(index, 'params.action', e.target.value)}
                            className={selectCls}
                          >
                            <option value="on">On</option>
                            <option value="off">Off</option>
                          </select>
                        </>
                      )}
                      {action.type === 'email' && (
                        <>
                          <input
                            type="email"
                            placeholder="To"
                            value={action.params.to || ''}
                            onChange={(e) => updateAction(index, 'params.to', e.target.value)}
                            className="w-32 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                          />
                          <input
                            type="text"
                            placeholder="Subject"
                            value={action.params.subject || ''}
                            onChange={(e) => updateAction(index, 'params.subject', e.target.value)}
                            className="flex-1 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                          />
                        </>
                      )}
                      {(action.type === 'thermostat_set' || action.type === 'lock' || action.type === 'unlock' || action.type === 'cover_open' || action.type === 'cover_close') && (
                        <>
                          <select
                            value={action.params.device_id || ''}
                            onChange={(e) => updateAction(index, 'params.device_id', e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select IoT device...</option>
                            {iotDevices.map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                          </select>
                          {action.type === 'thermostat_set' && (
                            <>
                              <input
                                type="number"
                                value={action.params.temperature ?? ''}
                                onChange={(e) => updateAction(index, 'params.temperature', Number(e.target.value))}
                                className="w-20 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                                placeholder="Temp °F"
                              />
                              <select
                                value={action.params.mode || 'heat'}
                                onChange={(e) => updateAction(index, 'params.mode', e.target.value)}
                                className={selectCls}
                              >
                                {MODES.map((m) => (
                                  <option key={m} value={m}>{m}</option>
                                ))}
                              </select>
                            </>
                          )}
                        </>
                      )}
                      {action.type === 'music' && (
                        <>
                          <select
                            value={action.params.action || 'play'}
                            onChange={(e) => updateAction(index, 'params.action', e.target.value)}
                            className={selectCls}
                          >
                            {MUSIC_ACTIONS.map((m) => (
                              <option key={m.value} value={m.value}>{m.label}</option>
                            ))}
                          </select>
                          {(action.params.action === 'play' || !action.params.action) && (
                            <input
                              type="text"
                              placeholder="Search query (e.g. lo-fi rain, 90s pop)..."
                              value={action.params.query || ''}
                              onChange={(e) => updateAction(index, 'params.query', e.target.value)}
                              className="flex-1 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                            />
                          )}
                          {action.params.action === 'volume' && (
                            <input
                              type="number"
                              min="0"
                              max="100"
                              value={action.params.volume_percent ?? 50}
                              onChange={(e) => updateAction(index, 'params.volume_percent', Number(e.target.value))}
                              className="w-20 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                              placeholder="50"
                            />
                          )}
                          {action.params.action === 'cast' && (
                            <>
                              <input
                                type="text"
                                placeholder="Entity ID (e.g. media_player.living_room)"
                                value={action.params.entity_id || ''}
                                onChange={(e) => updateAction(index, 'params.entity_id', e.target.value)}
                                className="flex-1 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                              />
                              <input
                                type="text"
                                placeholder="or Group name (e.g. Living Room)"
                                value={action.params.group_name || ''}
                                onChange={(e) => updateAction(index, 'params.group_name', e.target.value)}
                                className="flex-1 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                              />
                              <input
                                type="number"
                                min="0"
                                max="100"
                                value={action.params.volume_percent ?? 100}
                                onChange={(e) => updateAction(index, 'params.volume_percent', Number(e.target.value))}
                                className="w-20 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                                placeholder="Vol"
                              />
                            </>
                          )}
                        </>
                      )}
                      <button
                        onClick={() => removeItem('actions', index)}
                        className="p-1 rounded hover:bg-error/20 text-error ml-auto"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <button
                  onClick={resetForm}
                  className="px-4 py-2 rounded border border-white/20 text-text-secondary hover:bg-white/5"
                >
                  Cancel
                </button>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleSave}
                  disabled={!formData.name || !isAuthenticated}
                  className="flex items-center gap-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  Save Routine
                </motion.button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-text-tertiary">
              <div className="text-center">
                <RefreshCw className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Select a routine or create a new one</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Routines;
