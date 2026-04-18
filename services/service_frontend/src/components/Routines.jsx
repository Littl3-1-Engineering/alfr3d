import { motion } from 'framer-motion';
import { useState } from 'react';
import { Plus, Play, Trash2, Save, Clock, RefreshCw, Zap, Mail, Lightbulb } from 'lucide-react';
import { useTheme } from '../utils/useTheme';
import { useRoutines, useCreateRoutine, useUpdateRoutine, useDeleteRoutine } from '../hooks/useApi';

const Routines = () => {
  useTheme();
  const { data: routines = [], isLoading, error } = useRoutines();
  const createRoutine = useCreateRoutine();
  const updateRoutine = useUpdateRoutine();
  const deleteRoutine = useDeleteRoutine();

  const [selectedRoutine, setSelectedRoutine] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    time: '08:00',
    recurrence: 'daily',
    enabled: true,
    actions: [],
  });
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
      await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/routines/${id}/run`, { method: 'POST' });
    } catch (error) {
      console.error('Failed to run routine:', error);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      time: '08:00',
      recurrence: 'daily',
      enabled: true,
      actions: [],
    });
    setSelectedRoutine(null);
    setShowForm(false);
  };

  const formatTimeForInput = (timeValue) => {

    // If it's already in HH:MM format, return as-is
    if (timeValue.match(/^\d{2}:\d{2}$/)) {
      return timeValue;
    }

    // Extract HH:MM from HH:MM:SS format
    if (timeValue.match(/^\d{2}:\d{2}:\d{2}$/)) {
      return timeValue.substring(0, 5);
    }

    // Fallback to default
    return '08:00';
  };

  const editRoutine = (routine) => {
    setFormData({
      name: routine.name,
      time: formatTimeForInput(routine.time),
      recurrence: routine.recurrence || 'daily',
      enabled: routine.enabled,
      actions: routine.actions || [],
    });
    setSelectedRoutine(routine);
    setShowForm(true);
  };

  const addAction = (type) => {
    const newAction = { type, params: {} };
    if (type === 'speak') newAction.params.text = '';
    if (type === 'device') { newAction.params.device_id = ''; newAction.params.action = 'on'; }
    if (type === 'email') { newAction.params.to = ''; newAction.params.subject = ''; newAction.params.body = ''; }
    setFormData({ ...formData, actions: [...formData.actions, newAction] });
  };

  const updateAction = (index, field, value) => {
    const updated = [...formData.actions];
    if (field === 'type') {
      updated[index] = { type: value, params: {} };
    } else if (field.startsWith('params.')) {
      const paramKey = field.replace('params.', '');
      updated[index].params[paramKey] = value;
    }
    setFormData({ ...formData, actions: updated });
  };

  const removeAction = (index) => {
    setFormData({ ...formData, actions: formData.actions.filter((_, i) => i !== index) });
  };

  const actionIcons = {
    speak: <Zap className="w-4 h-4" />,
    device: <Lightbulb className="w-4 h-4" />,
    email: <Mail className="w-4 h-4" />,
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-primary drop-shadow-lg">Automation Routines</h2>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30"
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
            routines.map((routine) => (
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
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRun(routine.id); }}
                      className="p-1.5 rounded hover:bg-success/20 text-success"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(routine.id); }}
                      className="p-1.5 rounded hover:bg-error/20 text-error"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>

        {/* Editor Panel */}
        <div className="flex-1">
          {showForm ? (
            <div className="glass rounded-lg p-6 space-y-4">
              <h3 className="text-lg font-semibold text-text-primary">
                {selectedRoutine ? 'Edit Routine' : 'Create Routine'}
              </h3>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Name</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    disabled={isSunriseSunset}
                    className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
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
                        setFormData({ ...formData, time: `${hour}:${minute}` });
                      }}
                      disabled={isSunriseSunset}
                      className="w-14 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-center disabled:opacity-50 disabled:cursor-not-allowed"
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
                        setFormData({ ...formData, time: `${hour}:${minute}` });
                      }}
                      disabled={isSunriseSunset}
                      className="w-14 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary text-center disabled:opacity-50 disabled:cursor-not-allowed"
                      placeholder="00"
                    />
                    <span className="text-xs text-text-tertiary">(24hr)</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Recurrence</label>
                  <select
                    value={formData.recurrence}
                    onChange={(e) => setFormData({ ...formData, recurrence: e.target.value })}
                    disabled={isSunriseSunset}
                    className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
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
                    onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                    className="w-4 h-4"
                  />
                  <label htmlFor="enabled" className="text-text-primary">Enabled</label>
                </div>
              </div>

              {/* Actions Section */}
              <div>
                <label className="block text-sm text-text-secondary mb-2">Actions</label>
                <div className="flex gap-2 mb-3">
                  <button
                    onClick={() => addAction('speak')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded bg-warning/20 border border-warning text-warning text-sm"
                  >
                    <Zap className="w-3 h-3" /> Speak
                  </button>
                  <button
                    onClick={() => addAction('device')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded bg-success/20 border border-success text-success text-sm"
                  >
                    <Lightbulb className="w-3 h-3" /> Device
                  </button>
                  <button
                    onClick={() => addAction('email')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded bg-error/20 border border-error text-error text-sm"
                  >
                    <Mail className="w-3 h-3" /> Email
                  </button>
                </div>

                <div className="space-y-2">
                  {formData.actions.map((action, index) => (
                    <div key={index} className="flex items-center gap-2 p-3 rounded bg-white/5 border border-white/10">
                      <span className="text-text-tertiary">{actionIcons[action.type]}</span>
                      <select
                        value={action.type}
                        onChange={(e) => updateAction(index, 'type', e.target.value)}
                        className="px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                      >
                        <option value="speak">Speak</option>
                        <option value="device">Device</option>
                        <option value="email">Email</option>
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
                          <input
                            type="text"
                            placeholder="Device ID"
                            value={action.params.device_id || ''}
                            onChange={(e) => updateAction(index, 'params.device_id', e.target.value)}
                            className="w-24 px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
                          />
                          <select
                            value={action.params.action || 'on'}
                            onChange={(e) => updateAction(index, 'params.action', e.target.value)}
                            className="px-2 py-1 rounded bg-white/10 border border-white/20 text-text-primary text-sm"
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
                      <button
                        onClick={() => removeAction(index)}
                        className="p-1 rounded hover:bg-error/20 text-error"
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
                  disabled={!formData.name}
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
