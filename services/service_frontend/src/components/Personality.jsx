import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { MessageSquare, Edit, Trash2, Plus, Save, X } from 'lucide-react';
import { API_BASE_URL } from '../config';

const Personality = () => {
  const [quips, setQuips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editType, setEditType] = useState('');
  const [editText, setEditText] = useState('');
  const [newType, setNewType] = useState('');
  const [newText, setNewText] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    fetchQuips();
  }, []);

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
        await fetchQuips();
        setEditingId(null);
      }
    } catch (error) {
      console.error('Error updating quip:', error);
    }
  };

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

  const handleAdd = async () => {
    if (!newType || !newText) return;
    try {
      const response = await fetch(API_BASE_URL + '/api/quips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: newType, quips: newText }),
      });
      if (response.ok) {
        await fetchQuips();
        setNewType('');
        setNewText('');
        setShowAddForm(false);
      }
    } catch (error) {
      console.error('Error adding quip:', error);
    }
  };

  if (loading) {
    return <div className="text-center text-gray-400">Loading quips...</div>;
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-cyan-400 mb-6 drop-shadow-lg">Personality Settings</h2>

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
                      className="w-full p-2 bg-slate-700 rounded text-gray-200 text-sm uppercase"
                      placeholder="Type"
                    />
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      className="w-full p-2 bg-slate-700 rounded text-gray-200"
                      rows={2}
                    />
                  </div>
                ) : (
                  <>
                    <span className="text-sm text-cyan-400 uppercase tracking-wide">{quip.type}</span>
                    <p className="text-gray-200 mt-1">{quip.quips}</p>
                  </>
                )}
              </div>
              <div className="flex space-x-2 ml-4">
                {editingId === quip.id ? (
                  <>
                    <button
                      onClick={handleSave}
                      className="p-2 text-green-400 hover:bg-green-400/20 rounded"
                    >
                      <Save className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="p-2 text-gray-400 hover:bg-gray-400/20 rounded"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => handleEdit(quip.id, quip.type, quip.quips)}
                    className="p-2 text-cyan-400 hover:bg-cyan-400/20 rounded"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                )}
                <button
                  onClick={() => handleDelete(quip.id)}
                  className="p-2 text-red-400 hover:bg-red-400/20 rounded"
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
          <h3 className="text-lg font-semibold text-cyan-400 mb-4">Add New Quip</h3>
          <div className="space-y-3">
            <input
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              className="w-full p-2 bg-slate-700 rounded text-gray-200"
              placeholder="Type (e.g., smart, email, bedtime)"
            />
            <textarea
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              className="w-full p-2 bg-slate-700 rounded text-gray-200"
              rows={3}
              placeholder="Quip text"
            />
            <div className="flex space-x-2">
              <button
                onClick={handleAdd}
                className="px-4 py-2 bg-green-400/20 border border-green-400 rounded text-green-400 hover:bg-green-400/30"
              >
                Add
              </button>
              <button
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 bg-gray-400/20 border border-gray-400 rounded text-gray-400 hover:bg-gray-400/30"
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
          className="mt-6 flex items-center space-x-2 px-4 py-2 bg-cyan-400/20 border border-cyan-400 rounded-lg text-cyan-400 hover:bg-cyan-400/30 transition-colors drop-shadow-lg"
        >
          <Plus className="w-5 h-5" />
          <span>Add New Quip</span>
        </motion.button>
      )}
    </div>
  );
};

export default Personality;