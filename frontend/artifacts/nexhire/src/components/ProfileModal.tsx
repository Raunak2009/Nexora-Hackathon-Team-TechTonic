import { useState } from 'react';
import type { RecruiterUser } from './SignupModal';
import {
  User, Mail, Building, LogOut, LogIn, Check, X,
  ShieldCheck, Edit3, Save, Sparkles, RefreshCw
} from 'lucide-react';

interface ProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: RecruiterUser;
  onUpdateUser: (updated: RecruiterUser) => void;
  onOpenAuthModal: () => void;
}

export function ProfileModal({
  isOpen,
  onClose,
  user,
  onUpdateUser,
  onOpenAuthModal,
}: ProfileModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(user.name);
  const [company, setCompany] = useState(user.company);
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState(user.role);

  if (!isOpen) return null;

  const handleSave = () => {
    onUpdateUser({
      ...user,
      name,
      company,
      email,
      role,
    });
    setIsEditing(false);
  };

  const handleLogout = () => {
    onUpdateUser({
      ...user,
      isLoggedIn: false,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#04101C]/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg rounded-xl border border-[#2F587D] bg-[#122A45] p-6 shadow-2xl animate-rise-in">
        <div className="flex items-center justify-between border-b border-[#24415C] pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[#4A9FE0]/40 bg-[#193F62] text-[13px] font-extrabold text-[#C2E5F7]">
              {user.name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase() || 'RC'}
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white">Recruiter Profile</h3>
              <p className="text-[10px] text-[#789BB3]">Workspace Identity & Organization Details</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[#6C8DA5] hover:text-white"
            data-testid="button-close-profile-modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          {/* Status Badge */}
          <div className="flex items-center justify-between rounded-lg border border-[#24415C] bg-[#0E2238] p-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#3FB27F]" />
              <span className="text-[11px] font-semibold text-[#C5DCED]">
                {user.isLoggedIn ? 'Active Recruiter Session' : 'Logged Out (Guest Mode)'}
              </span>
            </div>
            <span className="rounded bg-[#4A9FE0]/15 px-2 py-0.5 text-[9px] font-bold text-[#6CB9E8] uppercase tracking-wider">
              Recruiter Admin
            </span>
          </div>

          {/* Profile Fields */}
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
                Recruiter Name
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                />
              ) : (
                <div className="flex items-center gap-2 rounded-md border border-[#24415C] bg-[#0E2238] px-3 py-2 text-[12px] font-semibold text-white">
                  <User size={14} className="text-[#4A9FE0]" />
                  <span>{user.name}</span>
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
                Company / Organization
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                />
              ) : (
                <div className="flex items-center gap-2 rounded-md border border-[#24415C] bg-[#0E2238] px-3 py-2 text-[12px] font-semibold text-white">
                  <Building size={14} className="text-[#4A9FE0]" />
                  <span>{user.company}</span>
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
                Gmail / Email Account
              </label>
              {isEditing ? (
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                />
              ) : (
                <div className="flex items-center justify-between rounded-md border border-[#24415C] bg-[#0E2238] px-3 py-2 text-[12px] text-[#D0E2ED]">
                  <div className="flex items-center gap-2">
                    <Mail size={14} className="text-[#4A9FE0]" />
                    <span>{user.email}</span>
                  </div>
                  <span className="flex items-center gap-1 text-[9px] font-bold text-[#62D39D]">
                    <ShieldCheck size={12} /> Google Verified
                  </span>
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
                Role / Title
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                />
              ) : (
                <div className="rounded-md border border-[#24415C] bg-[#0E2238] px-3 py-2 text-[12px] text-[#A6C2D6]">
                  {user.role}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="mt-6 flex items-center justify-between border-t border-[#24415C] pt-5">
          {user.isLoggedIn ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 rounded-md border border-[#E5484D]/40 bg-[#E5484D]/10 px-3 py-2 text-[11px] font-bold text-[#F87171] hover:bg-[#E5484D]/20 transition-colors"
              data-testid="button-profile-logout"
            >
              <LogOut size={14} /> Log Out
            </button>
          ) : (
            <button
              onClick={() => {
                onClose();
                onOpenAuthModal();
              }}
              className="flex items-center gap-1.5 rounded-md bg-[#4A9FE0] px-3.5 py-2 text-[11px] font-bold text-[#0B1B2E] hover:bg-[#6EB9F0] transition-colors"
              data-testid="button-profile-login"
            >
              <LogIn size={14} /> Log In / Sign Up
            </button>
          )}

          <div className="flex items-center gap-2">
            {isEditing ? (
              <button
                onClick={handleSave}
                className="flex items-center gap-1.5 rounded-md bg-[#3FB27F] px-4 py-2 text-[11px] font-bold text-[#0B1B2E] hover:bg-[#57C794] transition-colors"
                data-testid="button-save-profile"
              >
                <Save size={14} /> Save Changes
              </button>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                className="flex items-center gap-1.5 rounded-md border border-[#315674] bg-[#10263E] px-3.5 py-2 text-[11px] font-bold text-[#B9D8EC] hover:border-[#4A9FE0] transition-colors"
                data-testid="button-edit-profile"
              >
                <Edit3 size={14} /> Edit Profile
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

