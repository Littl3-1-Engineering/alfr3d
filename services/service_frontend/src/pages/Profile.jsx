import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { User, Save } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';
import { useAuth } from '../utils/useAuth';

const Profile = () => {
  const { user } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [aboutMe, setAboutMe] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  const loadProfile = useCallback(() => {
    if (!user) return;
    setLoading(true);
    fetch(`${API_BASE_URL}/api/users`)
      .then((res) => res.json())
      .then((users) => {
        const mine = (users || []).find((u) => String(u.id) === String(user.id));
        if (mine) {
          setName(mine.name || '');
          setEmail(mine.email || '');
          setAboutMe(mine.about_me || '');
        }
      })
      .catch(() => setStatus({ type: 'error', message: 'Failed to load profile' }))
      .finally(() => setLoading(false));
  }, [user]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!user) return;
    setSaving(true);
    setStatus(null);
    try {
      // `type` (role) is deliberately never sent from this form -- self-service edits can
      // never change your own role, even for an owner/technoking. Role changes only happen
      // through the admin-on-someone-else path (Personnel roster), which is enforced
      // server-side regardless of what a client sends here. See todo/todo_user_management.md.
      const response = await apiFetch(`${API_BASE_URL}/api/users/${user.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, about_me: aboutMe }),
      });
      if (response.ok) {
        setStatus({ type: 'success', message: 'Profile updated' });
      } else {
        setStatus({ type: 'error', message: 'Failed to update profile' });
      }
    } catch {
      setStatus({ type: 'error', message: 'Failed to update profile' });
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="min-h-screen p-8"
    >
      <div className="max-w-xl mx-auto">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1, duration: 0.5 }}
          className="glass rounded-2xl p-6 border border-primary/30 bg-card/20"
        >
          <div className="flex items-center space-x-3 mb-6">
            <User className="w-8 h-8 text-primary" />
            <div>
              <h1 className="text-2xl font-bold text-primary">My Profile</h1>
              <p className="text-sm text-primary uppercase">{user.role}</p>
            </div>
          </div>

          {loading ? (
            <p className="text-sm text-text-secondary">Loading...</p>
          ) : (
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label htmlFor="profile-name" className="block text-sm text-primary font-medium mb-1">
                  Name
                </label>
                <input
                  id="profile-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                />
              </div>
              <div>
                <label htmlFor="profile-email" className="block text-sm text-primary font-medium mb-1">
                  Email
                </label>
                <input
                  id="profile-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                  placeholder="Email address"
                />
              </div>
              <div>
                <label htmlFor="profile-about" className="block text-sm text-primary font-medium mb-1">
                  About
                </label>
                <textarea
                  id="profile-about"
                  value={aboutMe}
                  onChange={(e) => setAboutMe(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none resize-none"
                  placeholder="About you"
                />
              </div>

              {status && (
                <p className={`text-sm ${status.type === 'error' ? 'text-error' : 'text-success'}`}>
                  {status.message}
                </p>
              )}

              <button
                type="submit"
                disabled={saving}
                className="flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Save className="w-4 h-4" />
                <span>{saving ? 'Saving...' : 'Save Changes'}</span>
              </button>
            </form>
          )}
        </motion.div>
      </div>
    </motion.div>
  );
};

export default Profile;
