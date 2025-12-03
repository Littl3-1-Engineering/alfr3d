import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Edit, Trash2, Plus, Save, X } from 'lucide-react';
import { API_BASE_URL } from '../config';

const useQuips = () => {
  const [quips, setQuips] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchQuips = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/quips');
      const data = await response.json();
      setQuips(data);
    } catch (error) {
      console.log('API error:', error);
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
      console.log('API error:', error);
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
      console.log('API error:', error);
      console.error('Error adding quip:', error);
    }
  };

  return { newType, newText, showAddForm, setNewType, setNewText, setShowAddForm, handleAdd };
};

const Personality = () => {
  const { quips, loading, fetchQuips } = useQuips();
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
        console.log('API error:', error);
        console.error('Error deleting quip:', error);
      }
    }
  };

  if (loading) {
    return <div className="text-center text-text-tertiary">Loading quips...</div>;
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-primary mb-6 drop-shadow-lg">Personality Settings</h2>

      <div className="space-y-4">
        {quips.map((quip, index) => (
          <motion.div
            key={quip.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1, duration: 0.3 }}
            className="glass rounded-lg p-4"
          >
            <div className="flex items-center justify-between">
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
            </div>
          </motion.div>
        ))}
      </div>

      {showAddForm && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mt-6 glass rounded-lg p-4"
        >
          <h3 className="text-lg font-semibold text-primary mb-4">Add New Quip</h3>
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
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setShowAddForm(true)}
          className="mt-6 flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 transition-colors drop-shadow-lg"
        >
          <Plus className="w-5 h-5" />
          <span>Add New Quip</span>
        </motion.button>
      )}
    </div>
  );
};

export default Personality;
