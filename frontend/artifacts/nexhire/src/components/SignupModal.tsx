import { useState } from 'react';
import {
  Sparkles, ShieldCheck, ArrowRight, Lock, Mail,
  Building, User, X, Check
} from 'lucide-react';
import { NexHireIcon } from './Logo';

export interface RecruiterUser {
  name: string;
  email: string;
  company: string;
  role: string;
  isLoggedIn: boolean;
  avatarUrl?: string;
}

interface SignupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAuthSuccess: (user: RecruiterUser) => void;
  currentUser: RecruiterUser;
}

export function SignupModal({ isOpen, onClose, onAuthSuccess, currentUser }: SignupModalProps) {
  const [mode, setMode] = useState<'signup' | 'login'>('signup');
  const [name, setName] = useState(currentUser.name || 'Avery Rios');
  const [email, setEmail] = useState(currentUser.email || 'avery.rios@techtonic.ai');
  const [company, setCompany] = useState(currentUser.company || 'TechTonic Labs');
  const [role, setRole] = useState(currentUser.role || 'Recruiting Lead');
  const [password, setPassword] = useState('••••••••••••');
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      onAuthSuccess({
        name,
        email,
        company,
        role,
        isLoggedIn: true,
      });
      onClose();
    }, 600);
  };

  const handleGoogleSignIn = () => {
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      onAuthSuccess({
        name: 'Avery Rios (Google)',
        email: 'avery.rios.recruiter@gmail.com',
        company: company || 'TechTonic Labs',
        role: 'Senior Hiring Lead',
        isLoggedIn: true,
      });
      onClose();
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#04101C]/85 backdrop-blur-sm p-4 overflow-y-auto">
      {/* Animated Glowing Card */}
      <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-[#305E85] bg-gradient-to-b from-[#122A45] to-[#0A1A2D] shadow-[0_25px_60px_-15px_rgba(4,16,29,0.8)] animate-rise-in">
        {/* Ambient Glowing Background Orbs */}
        <div className="absolute -top-24 -left-24 h-64 w-64 rounded-full bg-[#4A9FE0]/20 blur-3xl pointer-events-none animate-pulse" />
        <div className="absolute -bottom-24 -right-24 h-64 w-64 rounded-full bg-[#3FB27F]/20 blur-3xl pointer-events-none animate-pulse delay-2" />

        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 z-20 text-[#7193AB] hover:text-white transition-colors"
          data-testid="button-close-auth-modal"
        >
          <X size={20} />
        </button>

        {/* Hero Tagline Section */}
        <div className="relative border-b border-[#24415C] px-8 pt-8 pb-6">
          <div className="flex items-center gap-2 mb-3">
            <NexHireIcon className="h-6 w-6" />
            <span className="text-[12px] font-black tracking-[0.16em] text-[#4A9FE0] uppercase">
              NexHire Intelligent Talent Platform
            </span>
          </div>

          <h2 className="text-[24px] font-black tracking-tight text-white md:text-[28px] leading-tight">
            "Want to know which resume is best?{' '}
            <span className="bg-gradient-to-r from-[#4A9FE0] to-[#62D39D] bg-clip-text text-transparent">
              AI does the judging, you do the selection.
            </span>"
          </h2>

          <p className="mt-2 text-[12px] leading-6 text-[#9BB5C9]">
            Precision candidate ranking powered by AI semantic analysis. Upload hundreds of resumes, surface the strongest talent, and eliminate screening bias.
          </p>

          {/* Quick Perks Pill */}
          <div className="mt-4 flex flex-wrap items-center gap-3 text-[10px] font-bold text-[#62D39D]">
            <span className="flex items-center gap-1">
              <Check size={13} /> Multi-Vector Resume Scoring
            </span>
            <span className="flex items-center gap-1">
              <Check size={13} /> Relative Cohort Strengths &amp; Weaknesses
            </span>
            <span className="flex items-center gap-1">
              <Check size={13} /> 100% Evidence-Led
            </span>
          </div>
        </div>

        {/* Mode Switcher */}
        <div className="flex border-b border-[#24415C] bg-[#0E2034]/60">
          <button
            type="button"
            onClick={() => setMode('signup')}
            className={`flex-1 py-3 text-center text-[12px] font-bold transition-colors ${
              mode === 'signup'
                ? 'border-b-2 border-[#4A9FE0] text-white bg-[#132B47]/60'
                : 'text-[#6F90A8] hover:text-[#BBD5E6]'
            }`}
            data-testid="tab-signup"
          >
            Create Recruiter Account
          </button>
          <button
            type="button"
            onClick={() => setMode('login')}
            className={`flex-1 py-3 text-center text-[12px] font-bold transition-colors ${
              mode === 'login'
                ? 'border-b-2 border-[#4A9FE0] text-white bg-[#132B47]/60'
                : 'text-[#6F90A8] hover:text-[#BBD5E6]'
            }`}
            data-testid="tab-login"
          >
            Recruiter Sign In
          </button>
        </div>

        {/* Form Container */}
        <form onSubmit={handleSubmit} className="p-8 space-y-4">
          {/* Google One-Click Sign In */}
          <button
            type="button"
            onClick={handleGoogleSignIn}
            disabled={isLoading}
            className="flex w-full items-center justify-center gap-3 rounded-lg border border-[#315674] bg-[#10263E] py-2.5 text-[12px] font-bold text-white shadow-sm hover:border-[#4A9FE0] hover:bg-[#163351] transition-all"
            data-testid="button-google-signin"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4">
              <path
                fill="#EA4335"
                d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.4 9 5 12 5z"
              />
              <path
                fill="#4285F4"
                d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.8z"
              />
              <path
                fill="#FBBC05"
                d="M5.6 14.8c-.3-.8-.4-1.8-.4-2.8s.1-2 .4-2.8L1.9 6.3C.7 8.7 0 11.3 0 14s.7 5.3 1.9 7.7l3.7-2.9z"
              />
              <path
                fill="#34A853"
                d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.4-6.4-5.2L1.9 16C3.7 19.7 7.5 23 12 23z"
              />
            </svg>
            Continue with Gmail / Google
          </button>

          <div className="relative flex items-center justify-center my-2">
            <span className="h-px w-full bg-[#24415C]" />
            <span className="absolute bg-[#0D2138] px-3 text-[10px] uppercase tracking-[.15em] text-[#5F819A]">
              or enter credentials
            </span>
          </div>

          {mode === 'signup' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#789BB3]">
                  Recruiter Full Name
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Avery Rios"
                    className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                    data-testid="input-auth-name"
                  />
                  <User size={14} className="absolute right-3 top-2.5 text-[#5A7B94]" />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#789BB3]">
                  Company Name
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="e.g. TechTonic Labs"
                    className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                    data-testid="input-auth-company"
                  />
                  <Building size={14} className="absolute right-3 top-2.5 text-[#5A7B94]" />
                </div>
              </div>
            </div>
          )}

          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#789BB3]">
              Recruiter Gmail / Work Email
            </label>
            <div className="relative">
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="recruiter@company.com"
                className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                data-testid="input-auth-email"
              />
              <Mail size={14} className="absolute right-3 top-2.5 text-[#5A7B94]" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-[.14em] text-[#789BB3]">
              Password
            </label>
            <div className="relative">
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-white outline-none focus:border-[#4A9FE0]"
                data-testid="input-auth-password"
              />
              <Lock size={14} className="absolute right-3 top-2.5 text-[#5A7B94]" />
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-gradient-to-r from-[#4A9FE0] to-[#3B82F6] py-3 text-[12px] font-extrabold text-[#0B1B2E] shadow-md hover:from-[#60B2ED] hover:to-[#5B95F5] transition-all"
              data-testid="button-auth-submit"
            >
              {isLoading ? (
                'Connecting with AI Engine...'
              ) : (
                <>
                  <Sparkles size={15} />
                  {mode === 'signup' ? 'Start Candidate Screening' : 'Access Recruiter Workspace'}
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

