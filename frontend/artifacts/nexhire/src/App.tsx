import { type ReactNode, useMemo, useState, useEffect, createContext, useContext } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  AlertTriangle, ArrowUpRight, Bell, BriefcaseBusiness, Check,
  ChevronDown, Clock3, Download, ExternalLink, FileDown, GitCompare,
  LayoutDashboard, Menu, MessageSquareText, MoreHorizontal, Pencil, Plus,
  RefreshCw, Save, Search, Send, ShieldCheck, SlidersHorizontal,
  Sparkles, Target, Trash2, UsersRound, X, CheckCircle2, User, Building,
  LogOut, LogIn, Filter, Award, Briefcase, Clock
} from 'lucide-react';
import { Link, Route, Switch, Router as WouterRouter, useLocation, useParams } from 'wouter';
import { Toaster } from '@/components/ui/toaster';
import { ErrorBoundary } from '@/components/error-boundary';
import NotFound from '@/pages/not-found';

import { Logo } from '@/components/Logo';
import { CandidateBarGraph } from '@/components/CandidateBarGraph';
import { ResumeUploadHub } from '@/components/ResumeUploadHub';
import { HeadToHeadCompare } from '@/components/HeadToHeadCompare';
import { SignupModal, type RecruiterUser } from '@/components/SignupModal';
import { ProfileModal } from '@/components/ProfileModal';
import { NotificationCenter } from '@/components/NotificationCenter';

import {
  INITIAL_CANDIDATES, INITIAL_JOB,
  computeRelativeStrengthsAndWeaknesses, queryRecruiterAI,
  type CandidateProfile, type JobProfile
} from '@/lib/ai-engine';
import {
  exportRankedCandidatesCSV,
  exportComparisonReportHTML,
  exportSkillGapCSV,
  type ExportCandidateData
} from '@/lib/export-utils';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

const navItems = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/compare', label: 'Compare', icon: GitCompare },
  { href: '/jobs', label: 'Job descriptions', icon: BriefcaseBusiness },
  { href: '/chat', label: 'AI workspace', icon: MessageSquareText },
  { href: '/exports', label: 'Exports', icon: Download },
];

/* -------------------------------------------------------------------------
   GLOBAL APPLICATION STATE PROVIDER & HOOKS
   ------------------------------------------------------------------------- */
interface AppContextType {
  candidates: CandidateProfile[];
  setCandidates: React.Dispatch<React.SetStateAction<CandidateProfile[]>>;
  activeJob: JobProfile;
  setActiveJob: React.Dispatch<React.SetStateAction<JobProfile>>;
  recruiterUser: RecruiterUser;
  setRecruiterUser: React.Dispatch<React.SetStateAction<RecruiterUser>>;
  jobs: JobProfile[];
  setJobs: React.Dispatch<React.SetStateAction<JobProfile[]>>;
  openAuthModal: () => void;
  openProfileModal: () => void;
  openNotifModal: () => void;
}

const AppContext = createContext<AppContextType | null>(null);

function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppContext.Provider');
  return ctx;
}

/* -------------------------------------------------------------------------
   SHELL COMPONENT (SIDEBAR + HEADER)
   ------------------------------------------------------------------------- */
function Shell({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const {
    recruiterUser, openAuthModal, openProfileModal, openNotifModal,
    candidates
  } = useApp();

  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return [];
    return candidates.filter(c =>
      `${c.name} ${c.role} ${c.previousCompanies.join(' ')} ${c.skills.map(s => s.name).join(' ')}`
        .toLowerCase()
        .includes(searchQuery.toLowerCase())
    );
  }, [searchQuery, candidates]);

  return (
    <div className="min-h-[100dvh] bg-[#0B1B2E] text-[#D9E6F0]">
      {/* Sidebar Navigation */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[252px] border-r border-[#24415C] bg-[#0B1B2E] px-5 py-6 transition-transform md:translate-x-0 ${
          menuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between">
          <Logo showTagline={false} size="md" />
          <button
            onClick={() => setMenuOpen(false)}
            className="text-[#7F9CB5] md:hidden"
            data-testid="button-close-menu"
          >
            <X size={18} />
          </button>
        </div>

        {/* Clean Nav Links (removed "Workspace" header) */}
        <div className="mt-8">
          <nav className="space-y-1">
            {navItems.map(({ href, label, icon: Icon }) => {
              const active = href === '/' ? location === '/' : location.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMenuOpen(false)}
                  className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-[12px] font-semibold transition-colors ${
                    active
                      ? 'bg-[#132A45] text-[#E6F3FC] shadow-[inset_2px_0_0_#4A9FE0]'
                      : 'text-[#86A1B8] hover:bg-[#10263E] hover:text-[#D9E6F0]'
                  }`}
                  data-testid={`link-nav-${label.toLowerCase().replaceAll(' ', '-')}`}
                >
                  <Icon size={16} strokeWidth={active ? 2.2 : 1.7} />
                  <span>{label}</span>
                  {label === 'AI workspace' && (
                    <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#3FB27F]" />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* General Recruiter Profile (Removed decision guide and workspace settings) */}
        <div className="absolute bottom-6 left-5 right-5">
          <button
            onClick={openProfileModal}
            className="group flex w-full items-center gap-3 rounded-lg border border-[#24415C] bg-[#10263E] p-3 text-left transition-all hover:border-[#4A9FE0]/60 hover:bg-[#153250]"
            data-testid="button-open-profile-bottom"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[#4A9FE0]/40 bg-[#1A3F60] text-[12px] font-bold text-[#C5E7F9]">
              {recruiterUser.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'RC'}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-bold text-[#E2EEF5] group-hover:text-[#4A9FE0]">
                {recruiterUser.name}
              </div>
              <div className="truncate text-[10px] text-[#69889E]">
                {recruiterUser.company}
              </div>
            </div>
            <MoreHorizontal size={16} className="text-[#64859E]" />
          </button>
        </div>
      </aside>

      {menuOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-[#04101C]/70 md:hidden"
          onClick={() => setMenuOpen(false)}
          data-testid="button-overlay"
        />
      )}

      {/* Main Content Area */}
      <div className="md:pl-[252px]">
        {/* Sticky Header */}
        <header className="sticky top-0 z-20 flex h-[68px] items-center border-b border-[#24415C] bg-[#0B1B2E]/95 px-5 backdrop-blur md:px-9">
          <button
            className="mr-4 text-[#9CB4C8] md:hidden"
            onClick={() => setMenuOpen(true)}
            data-testid="button-open-menu"
          >
            <Menu size={20} />
          </button>

          {/* Greeting: "Hello, {name}" */}
          <div className="flex items-center gap-3">
            <span className="text-[13px] font-bold text-[#CBE1EE]">
              Hello, <span className="text-[#4A9FE0]">{recruiterUser.name.split(' ')[0]}</span>
            </span>
            <span className="hidden sm:inline text-[11px] text-[#64859E]">·</span>
            <span className="hidden sm:inline text-[11px] text-[#7192A9]">
              {recruiterUser.company}
            </span>
          </div>

          <div className="ml-auto flex items-center gap-4">
            {/* Search Candidates Bar */}
            <div
              onClick={() => setIsSearchOpen(true)}
              className="hidden items-center gap-2 rounded-md border border-[#294963] bg-[#10263E] px-3 py-2 text-[11px] text-[#6F8CA4] lg:flex cursor-pointer hover:border-[#4A9FE0]"
              data-testid="button-search-candidates"
            >
              <Search size={14} />
              <span>Search candidates...</span>
              <span className="ml-4 rounded border border-[#35536C] px-1.5 py-0.5 font-mono text-[9px]">
                ⌘ K
              </span>
            </div>

            {/* Notifications Button */}
            <button
              onClick={openNotifModal}
              className="relative text-[#87A5BB] hover:text-[#D7E8F2] transition-colors p-1"
              data-testid="button-notifications"
            >
              <Bell size={18} />
              <span className="absolute right-0 top-0 h-2 w-2 rounded-full bg-[#4A9FE0] ring-2 ring-[#0B1B2E]" />
            </button>

            {/* Recruiter Auth / Profile Switcher */}
            <button
              onClick={openProfileModal}
              className="flex items-center gap-2 rounded-md border border-[#2B4E6F] bg-[#10263E] px-3 py-1.5 text-[11px] font-bold text-[#C7E3F4] hover:border-[#4A9FE0]"
              data-testid="button-header-profile"
            >
              <User size={13} className="text-[#4A9FE0]" />
              <span>{recruiterUser.name.split(' ')[0]}</span>
            </button>
          </div>
        </header>

        {/* Global Search Dialog Modal */}
        {isSearchOpen && (
          <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm p-4 pt-20">
            <div className="w-full max-w-lg rounded-xl border border-[#305E85] bg-[#10263E] p-4 shadow-2xl animate-rise-in">
              <div className="flex items-center gap-2 border-b border-[#24415C] pb-3">
                <Search size={16} className="text-[#4A9FE0]" />
                <input
                  type="text"
                  autoFocus
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search by candidate name, company, skill (e.g. Microsoft, React)..."
                  className="w-full bg-transparent text-[13px] text-white outline-none placeholder:text-[#5F7F98]"
                />
                <button onClick={() => setIsSearchOpen(false)} className="text-[#6C8DA5] hover:text-white">
                  <X size={16} />
                </button>
              </div>

              <div className="mt-3 max-h-72 overflow-y-auto divide-y divide-[#24415C]">
                {searchResults.length === 0 ? (
                  <div className="p-6 text-center text-[12px] text-[#7896AA]">
                    {searchQuery.trim() ? 'No matching candidates found.' : 'Type to search candidates...'}
                  </div>
                ) : (
                  searchResults.map(c => (
                    <Link
                      key={c.id}
                      href={`/candidate/${c.id}`}
                      onClick={() => setIsSearchOpen(false)}
                      className="flex items-center justify-between p-3 hover:bg-[#163351] transition-colors"
                    >
                      <div>
                        <div className="text-[12px] font-bold text-white">{c.name}</div>
                        <div className="text-[10px] text-[#7192A9]">
                          {c.role} · Past: {c.previousCompanies.join(', ')} · {c.yearsExperience} yrs exp
                        </div>
                      </div>
                      <span className="data-mono font-bold text-[13px] text-[#62D39D]">
                        {c.overallScore}%
                      </span>
                    </Link>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        <main className="relative min-h-[calc(100dvh-68px)] overflow-hidden bg-[linear-gradient(120deg,#0B1B2E_0%,#0F2038_100%)] px-5 py-7 md:px-9 lg:px-12">
          {children}
        </main>
      </div>
    </div>
  );
}

function PageHeading({
  eyebrow, title, description, action
}: {
  eyebrow: string; title: string; description: string; action?: ReactNode
}) {
  return (
    <div className="mb-7 flex flex-col gap-5 border-b border-[#24415C] pb-7 md:flex-row md:items-end md:justify-between">
      <div>
        <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.22em] text-[#4A9FE0]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#4A9FE0]" />
          {eyebrow}
        </div>
        <h1 className="text-[26px] font-extrabold tracking-[-.04em] text-[#E6F2F8] md:text-[32px]">
          {title}
        </h1>
        <p className="mt-2 max-w-2xl text-[12px] leading-5 text-[#89A5BA]">
          {description}
        </p>
      </div>
      {action}
    </div>
  );
}

function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-[#24415C] bg-[#132A45]/85 panel-shadow ${className}`}>
      {children}
    </section>
  );
}

function Stat({ label, value, note, tone = 'blue' }: { label: string; value: string | number; note: string; tone?: 'blue' | 'green' | 'red' }) {
  const colors = {
    blue: 'text-[#69B7EC] bg-[#4A9FE0]/10',
    green: 'text-[#62D39D] bg-[#3FB27F]/10',
    red: 'text-[#F47D80] bg-[#E5484D]/10'
  };
  return (
    <div className="border-r border-[#24415C] px-5 py-1 last:border-0">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-[.16em] text-[#7694AA]">{label}</div>
      <div className="flex items-end gap-2">
        <span className="data-mono text-[25px] font-medium tracking-[-.08em] text-[#E6F2F8]">{value}</span>
        <span className={`mb-1 rounded px-1.5 py-0.5 text-[9px] font-bold ${colors[tone]}`}>{note}</span>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const style = status === 'shortlisted'
    ? 'border-[#3FB27F]/30 bg-[#3FB27F]/10 text-[#6BD6A4]'
    : status === 'flagged'
    ? 'border-[#E5484D]/30 bg-[#E5484D]/10 text-[#F47D80]'
    : 'border-[#4A9FE0]/30 bg-[#4A9FE0]/10 text-[#80C9F5]';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[9px] font-bold capitalize ${style}`} data-testid={`status-${status}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

function Score({ value, large = false }: { value: number; large?: boolean }) {
  return (
    <span className={`data-mono font-medium tracking-[-.07em] ${large ? 'text-[34px]' : 'text-[15px]'} ${value >= 80 ? 'text-[#72D3A5]' : value >= 65 ? 'text-[#76BFEA]' : 'text-[#F0B36B]'}`}>
      {value}<span className="ml-0.5 text-[10px] text-[#66879F]">%</span>
    </span>
  );
}

/* -------------------------------------------------------------------------
   OVERVIEW / DASHBOARD PAGE
   ------------------------------------------------------------------------- */
function DashboardPage() {
  const { candidates, setCandidates, activeJob, setActiveJob, recruiterUser } = useApp();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'shortlisted' | 'flagged' | 'review'>('all');
  const [selectedSkillFilter, setSelectedSkillFilter] = useState<string>('all');
  const [minExpFilter, setMinExpFilter] = useState<number>(0);
  const [semanticWeight, setSemanticWeight] = useState(70);
  const [keywordWeight, setKeywordWeight] = useState(30);

  // Available skills extracted from candidate pool for filter chips
  const availableSkills = useMemo(() => {
    const s = new Set<string>();
    candidates.forEach(c => c.skills.forEach(sk => s.add(sk.name)));
    return Array.from(s);
  }, [candidates]);

  // Filter candidates based on search, status, skill, and years of experience
  const filteredCandidates = useMemo(() => {
    return candidates.filter((c) => {
      const matchesSearch = `${c.name} ${c.role} ${c.email} ${c.previousCompanies.join(' ')}`
        .toLowerCase()
        .includes(search.toLowerCase());
      const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
      const matchesSkill = selectedSkillFilter === 'all' || c.skills.some(sk => sk.name === selectedSkillFilter && sk.matched);
      const matchesExp = c.yearsExperience >= minExpFilter;
      return matchesSearch && matchesStatus && matchesSkill && matchesExp;
    });
  }, [candidates, search, statusFilter, selectedSkillFilter, minExpFilter]);

  const handleScreenComplete = (newCandidates: CandidateProfile[], updatedJob: JobProfile) => {
    setCandidates(newCandidates);
    setActiveJob(updatedJob);
  };

  const handleExportRankedList = () => {
    exportRankedCandidatesCSV(filteredCandidates as ExportCandidateData[], activeJob.title);
  };

  const resetWeights = () => {
    setSemanticWeight(70);
    setKeywordWeight(30);
  };

  return (
    <div className="mx-auto max-w-[1400px] animate-rise-in space-y-8">
      {/* Page Heading */}
      <PageHeading
        eyebrow="Recruiting Cockpit / Active Role"
        title={`Hello, ${recruiterUser.name.split(' ')[0]}`}
        description={`Screening candidates for "${activeJob.title}" at ${activeJob.company}. Powered by AI semantic analysis.`}
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportRankedList}
              className="flex items-center gap-2 rounded-md border border-[#315674] bg-[#10263E] px-3.5 py-2.5 text-[11px] font-bold text-[#B7D7EA] hover:border-[#4A9FE0] hover:text-white transition-colors"
              data-testid="button-export-overview"
            >
              <FileDown size={14} /> Export Ranked CSV
            </button>
            <Link
              href="/jobs"
              className="flex items-center gap-2 rounded-md border border-[#315674] bg-[#132A45] px-3 py-2.5 text-[11px] font-bold text-[#B7D7EA] hover:border-[#4A9FE0]"
              data-testid="link-manage-job"
            >
              <BriefcaseBusiness size={14} /> Manage Job <ArrowUpRight size={13} />
            </Link>
          </div>
        }
      />

      {/* Top Stats Overview */}
      <div className="grid grid-cols-2 divide-x divide-[#24415C] rounded-lg border border-[#24415C] bg-[#132A45]/70 py-4 md:grid-cols-4">
        <Stat label="Candidates Screened" value={candidates.length} note="AI Evaluated" />
        <Stat
          label="Average Fit Score"
          value={`${candidates.length ? Math.round(candidates.reduce((a, b) => a + b.overallScore, 0) / candidates.length) : 0}%`}
          note="Cohort Average"
        />
        <Stat
          label="Shortlisted"
          value={candidates.filter(c => c.status === 'shortlisted').length}
          note="Ready for Interview"
          tone="green"
        />
        <Stat
          label="Flagged / Review"
          value={candidates.filter(c => c.status === 'flagged').length}
          note="Needs Human Read"
          tone="red"
        />
      </div>

      {/* AI Resume Upload & Job Description Hub */}
      <ResumeUploadHub currentJob={activeJob} onScreenComplete={handleScreenComplete} />

      {/* Candidate Bar Graph with 1st, 2nd, 3rd Badges */}
      <CandidateBarGraph candidates={filteredCandidates} />

      {/* Main Analysis Section */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.75fr)_minmax(300px,.75fr)]">
        {/* Left Column: Filterable Candidate List */}
        <Panel className="overflow-hidden">
          {/* Filter Bar */}
          <div className="border-b border-[#24415C] p-5 space-y-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-[15px] font-bold text-[#E1EEF5]">Ranked Candidates</h2>
                  <span className="rounded bg-[#24415C] px-2 py-0.5 data-mono text-[10px] text-[#9DB8CA]">
                    {filteredCandidates.length} of {candidates.length} shown
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-[#708EA5]">
                  Sorted by overall fit score, previous company signals, and experience.
                </p>
              </div>

              {/* Search Bar */}
              <div className="flex items-center gap-2 rounded-md border border-[#294963] bg-[#10263E] px-3 py-2">
                <Search size={13} className="text-[#6E8CA4]" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Find by name, company, role..."
                  className="w-[180px] bg-transparent text-[11px] text-[#D9E6F0] outline-none placeholder:text-[#58738A]"
                  data-testid="input-candidate-search"
                />
              </div>
            </div>

            {/* Recruiter Filters (Skills & Years of Experience) */}
            <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-[#24415C]/60 text-[11px]">
              {/* Status Filter */}
              <div className="flex rounded-md border border-[#294963] bg-[#10263E] p-0.5">
                {(['all', 'shortlisted', 'review', 'flagged'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setStatusFilter(f)}
                    className={`rounded px-2.5 py-1 text-[10px] font-bold capitalize transition-colors ${
                      statusFilter === f ? 'bg-[#244C69] text-[#D7EDF8]' : 'text-[#6F8DA4] hover:text-white'
                    }`}
                    data-testid={`button-filter-${f}`}
                  >
                    {f}
                  </button>
                ))}
              </div>

              {/* Experience Filter Buttons */}
              <div className="flex items-center gap-1">
                <span className="text-[10px] uppercase font-bold tracking-wider text-[#69889E]">Exp:</span>
                {[
                  { label: 'All Exp', val: 0 },
                  { label: '1+ yrs', val: 1 },
                  { label: '3+ yrs', val: 3 },
                  { label: '4+ yrs', val: 4 },
                ].map((item) => (
                  <button
                    key={item.label}
                    onClick={() => setMinExpFilter(item.val)}
                    className={`rounded border px-2 py-1 text-[9px] font-bold transition-colors ${
                      minExpFilter === item.val
                        ? 'border-[#4A9FE0] bg-[#4A9FE0]/20 text-[#67B8ED]'
                        : 'border-[#294963] bg-[#10263E] text-[#86A3B8] hover:border-[#4A9FE0]'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              {/* Skills Filter Dropdown / Chips */}
              <div className="flex items-center gap-1.5 ml-auto">
                <span className="text-[10px] uppercase font-bold tracking-wider text-[#69889E]">Skill:</span>
                <select
                  value={selectedSkillFilter}
                  onChange={(e) => setSelectedSkillFilter(e.target.value)}
                  className="rounded border border-[#294963] bg-[#10263E] px-2.5 py-1 text-[10px] font-bold text-[#9BBCCC] outline-none"
                  data-testid="select-skill-filter"
                >
                  <option value="all">All Skills</option>
                  {availableSkills.map((sk) => (
                    <option key={sk} value={sk}>
                      {sk}
                    </option>
                  ))}
                </select>

                {(search || statusFilter !== 'all' || selectedSkillFilter !== 'all' || minExpFilter > 0) && (
                  <button
                    onClick={() => {
                      setSearch('');
                      setStatusFilter('all');
                      setSelectedSkillFilter('all');
                      setMinExpFilter(0);
                    }}
                    className="text-[10px] text-[#F87171] hover:underline ml-1"
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Candidates Rows */}
          {filteredCandidates.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
              <UsersRound size={24} className="mb-3 text-[#53758F]" />
              <p className="text-[13px] font-bold text-[#BFD5E2]">No candidates match this view</p>
              <p className="mt-1 text-[11px] text-[#708EA5]">Try adjusting your skill or experience filters.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#24415C]/70">
              {filteredCandidates.map((candidate, index) => (
                <CandidateRow key={candidate.id} candidate={candidate} index={index} />
              ))}
            </div>
          )}
        </Panel>

        {/* Right Column: Score Weighting & Signal Overview */}
        <div className="space-y-6">
          <Panel className="overflow-hidden">
            <div className="border-b border-[#24415C] px-5 py-4">
              <div className="flex items-center justify-between">
                <h2 className="text-[14px] font-bold text-[#E1EEF5]">Score Weighting Knobs</h2>
                <SlidersHorizontal size={15} className="text-[#5C88A7]" />
              </div>
              <p className="mt-1 text-[11px] leading-5 text-[#7895AA]">
                Tune semantic comprehension vs exact keyword match for this role.
              </p>
            </div>

            <div className="space-y-5 px-5 py-5">
              <label className="block">
                <div className="mb-2 flex items-center justify-between text-[11px] font-semibold text-[#B4CBD9]">
                  <span>Semantic Alignment</span>
                  <span className="data-mono text-[#4A9FE0]">{semanticWeight}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={semanticWeight}
                  onChange={(e) => {
                    const s = Number(e.target.value);
                    setSemanticWeight(s);
                    setKeywordWeight(100 - s);
                  }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[#284762] accent-[#4A9FE0]"
                  data-testid="input-weight-semantic"
                />
              </label>

              <label className="block">
                <div className="mb-2 flex items-center justify-between text-[11px] font-semibold text-[#B4CBD9]">
                  <span>Keyword Exact Match</span>
                  <span className="data-mono text-[#3FB27F]">{keywordWeight}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={keywordWeight}
                  onChange={(e) => {
                    const k = Number(e.target.value);
                    setKeywordWeight(k);
                    setSemanticWeight(100 - k);
                  }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[#284762] accent-[#3FB27F]"
                  data-testid="input-weight-keyword"
                />
              </label>

              <div className="flex items-start gap-2 border-t border-[#24415C] pt-4 text-[10px] leading-4 text-[#7593A8]">
                <Sparkles size={13} className="mt-0.5 shrink-0 text-[#4A9FE0]" />
                The AI reads for contextual experience, not just keyword checklists.
              </div>

              <button
                onClick={resetWeights}
                className="flex items-center gap-2 text-[10px] font-bold text-[#72B9E6] hover:text-[#A4D9F5]"
                data-testid="button-reset-weights"
              >
                <RefreshCw size={12} /> Reset to Recommended (70/30)
              </button>
            </div>
          </Panel>

          <Panel className="node-grid relative overflow-hidden p-5">
            <div className="relative z-10">
              <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.16em] text-[#4A9FE0]">
                <Target size={13} /> Cohort Signal Overview
              </div>
              <div className="text-[20px] font-extrabold tracking-[-.04em] text-[#E1EEF5]">
                {filteredCandidates[0]?.name || 'Top Talent'} Leads Funnel
              </div>
              <p className="mt-2 text-[11px] leading-5 text-[#91ACBD]">
                {filteredCandidates.length} candidate profiles currently screened. Leading candidate brings experience from{' '}
                {filteredCandidates[0]?.previousCompanies.join(', ') || 'top technology firms'}.
              </p>
              <Link
                href="/compare"
                className="mt-4 inline-flex items-center gap-1.5 text-[10px] font-bold text-[#6FC2F0]"
                data-testid="link-view-comparison"
              >
                Compare Top Candidates <ArrowUpRight size={12} />
              </Link>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------
   CANDIDATE ROW (WITH PREVIOUS COMPANIES & RELATIVE STRENGTHS / WEAKNESSES)
   ------------------------------------------------------------------------- */
function CandidateRow({ candidate, index }: { candidate: CandidateProfile; index: number }) {
  return (
    <Link
      href={`/candidate/${candidate.id}`}
      className="flex flex-col gap-3 p-5 transition-colors hover:bg-[#163351] md:flex-row md:items-center md:justify-between"
      data-testid={`row-candidate-${candidate.id}`}
    >
      {/* Candidate Identification & Past Companies */}
      <div className="flex items-start gap-3.5 min-w-0 flex-1">
        <span className="data-mono w-5 text-[11px] font-bold text-[#55758D] mt-1.5">
          {String(candidate.rank || index + 1).padStart(2, '0')}
        </span>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#315674] bg-[#1A3A56] text-[11px] font-bold text-[#B8DCEC]">
          {candidate.initials}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-bold text-[#DDEBF3] hover:text-[#4A9FE0]">
              {candidate.name}
            </span>
            <StatusPill status={candidate.status} />
          </div>

          <div className="mt-1 flex items-center gap-2 text-[11px] text-[#789BB3] flex-wrap">
            <span>{candidate.role}</span>
            <span>·</span>
            <span className="font-mono text-[#BBD8EC] font-bold flex items-center gap-1">
              <Clock size={11} /> {candidate.yearsExperience} yrs exp
            </span>
          </div>

          {/* Previous Companies */}
          <div className="mt-2 flex items-center gap-1.5 flex-wrap">
            <span className="text-[9px] font-bold uppercase tracking-wider text-[#60829A]">Past:</span>
            {candidate.previousCompanies.map((company) => (
              <span
                key={company}
                className="rounded bg-[#10263E] border border-[#2B4E6F] px-2 py-0.5 text-[9px] font-semibold text-[#8EB8D0]"
              >
                {company}
              </span>
            ))}
          </div>

          {/* Relative Strengths & Weaknesses vs Others */}
          <div className="mt-2.5 flex flex-wrap gap-2 text-[10px]">
            {candidate.strengths?.[0] && (
              <span className="flex items-center gap-1 rounded bg-[#3FB27F]/10 border border-[#3FB27F]/30 px-2 py-0.5 text-[#62D39D]">
                <Check size={11} />
                <span className="font-medium truncate max-w-[280px]">{candidate.strengths[0]}</span>
              </span>
            )}
            {candidate.weaknesses?.[0] && (
              <span className="flex items-center gap-1 rounded bg-[#F59E0B]/10 border border-[#F59E0B]/30 px-2 py-0.5 text-[#FBBF24]">
                <AlertTriangle size={11} />
                <span className="font-medium truncate max-w-[280px]">{candidate.weaknesses[0]}</span>
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Metrics & Fit Score */}
      <div className="flex items-center gap-6 self-end md:self-auto shrink-0 pt-2 md:pt-0">
        <div className="text-right">
          <div className="text-[9px] font-bold uppercase tracking-wider text-[#69889E]">Fit Score</div>
          <Score value={candidate.overallScore} />
        </div>

        <div className="hidden sm:block text-right">
          <div className="text-[9px] font-bold uppercase tracking-wider text-[#69889E]">Semantic</div>
          <span className="data-mono text-[12px] text-[#86C8ED]">{candidate.semanticScore}%</span>
        </div>

        <div className="hidden sm:block text-right">
          <div className="text-[9px] font-bold uppercase tracking-wider text-[#69889E]">Keywords</div>
          <span className="data-mono text-[12px] text-[#74D6A8]">{candidate.keywordScore}%</span>
        </div>

        <ArrowUpRight size={16} className="text-[#587B95] group-hover:text-white transition-colors" />
      </div>
    </Link>
  );
}

/* -------------------------------------------------------------------------
   CANDIDATE DETAIL VIEW PAGE
   ------------------------------------------------------------------------- */
function CandidatePage() {
  const { candidateId = '' } = useParams<{ candidateId: string }>();
  const { candidates, setCandidates, activeJob } = useApp();
  const [showActions, setShowActions] = useState(false);

  const candidate = candidates.find(c => c.id === candidateId);

  if (!candidate) {
    return (
      <div className="mx-auto max-w-[1200px]">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-[11px] font-bold text-[#76BFEA]">
          ← Back to overview
        </Link>
        <Panel className="p-8 text-center text-[#89A5BA]">
          Candidate profile not found in active workspace.
        </Panel>
      </div>
    );
  }

  const toggleStatus = (newStatus: 'shortlisted' | 'flagged' | 'review') => {
    setCandidates(prev => prev.map(c => c.id === candidate.id ? { ...c, status: newStatus } : c));
    setShowActions(false);
  };

  const handleExportProfile = () => {
    exportRankedCandidatesCSV([candidate] as ExportCandidateData[], `${candidate.name}_Profile`);
    setShowActions(false);
  };

  const matched = candidate.skills.filter(s => s.matched).length;

  return (
    <div className="mx-auto max-w-[1200px] animate-rise-in space-y-6">
      <Link href="/" className="inline-flex items-center gap-2 text-[11px] font-bold text-[#76BFEA] hover:text-[#B5E3F9]" data-testid="link-back-overview">
        ← Back to overview
      </Link>

      <PageHeading
        eyebrow="Candidate Profile / Evidence View"
        title={candidate.name}
        description={`${candidate.role} · ${candidate.email} · ${candidate.yearsExperience} years of experience`}
        action={
          <div className="relative flex items-center gap-2">
            <StatusPill status={candidate.status} />
            <button
              onClick={() => setShowActions(!showActions)}
              className="flex items-center gap-2 rounded-md border border-[#315674] bg-[#10263E] px-3 py-2 text-[11px] font-bold text-[#BCD9E8] hover:border-[#4A9FE0]"
              data-testid="button-more-candidate"
            >
              <MoreHorizontal size={14} /> Actions
            </button>

            {/* Actions Dropdown */}
            {showActions && (
              <div className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-[#315674] bg-[#0E2238] p-1.5 shadow-xl z-20">
                <button
                  onClick={() => toggleStatus('shortlisted')}
                  className="flex w-full items-center gap-2 rounded px-3 py-2 text-[11px] font-bold text-[#62D39D] hover:bg-[#163553]"
                >
                  <Check size={13} /> Mark Shortlisted
                </button>
                <button
                  onClick={() => toggleStatus('flagged')}
                  className="flex w-full items-center gap-2 rounded px-3 py-2 text-[11px] font-bold text-[#F87171] hover:bg-[#163553]"
                >
                  <AlertTriangle size={13} /> Flag for Review
                </button>
                <button
                  onClick={() => toggleStatus('review')}
                  className="flex w-full items-center gap-2 rounded px-3 py-2 text-[11px] font-bold text-[#74B8E3] hover:bg-[#163553]"
                >
                  <Clock3 size={13} /> Reset to Review
                </button>
                <div className="my-1 border-t border-[#24415C]" />
                <button
                  onClick={handleExportProfile}
                  className="flex w-full items-center gap-2 rounded px-3 py-2 text-[11px] font-bold text-white hover:bg-[#163553]"
                >
                  <FileDown size={13} /> Export Candidate CSV
                </button>
              </div>
            )}
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[.9fr_1.1fr]">
        <Panel className="p-6">
          <div className="flex items-center gap-4 border-b border-[#24415C] pb-6">
            <div className="flex h-16 w-16 items-center justify-center rounded-full border border-[#4A9FE0]/40 bg-[#1B4667] text-[20px] font-bold text-[#C9E8F7]">
              {candidate.initials}
            </div>
            <div>
              <div className="text-[18px] font-bold text-[#E3EFF6]">{candidate.name}</div>
              <div className="mt-1 text-[11px] text-[#84A2B6]">{candidate.role}</div>
              <div className="mt-2 flex items-center gap-2 text-[10px] text-[#69889F]">
                <span>{candidate.email}</span>
                <span className="h-1 w-1 rounded-full bg-[#4A9FE0]" />
                <span>{candidate.yearsExperience} yrs exp</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 py-6">
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-[.14em] text-[#6F8CA4]">Overall Fit</div>
              <Score value={candidate.overallScore} large />
            </div>
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-[.14em] text-[#6F8CA4]">Model Confidence</div>
              <div className="data-mono text-[34px] font-medium tracking-[-.07em] text-[#72D3A5]">
                {candidate.confidence}<span className="text-[10px] text-[#66879F]">%</span>
              </div>
            </div>
          </div>

          {/* Previous Companies */}
          <div className="border-t border-[#24415C] pt-5">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[.14em] text-[#6F8CA4]">
              Previous Companies Worked
            </div>
            <div className="flex flex-wrap gap-2">
              {candidate.previousCompanies.map(comp => (
                <span key={comp} className="rounded-md border border-[#315674] bg-[#10263E] px-2.5 py-1 text-[11px] font-semibold text-[#B7D8EC]">
                  {comp}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-5 border-t border-[#24415C] pt-5">
            <div className="mb-3 text-[10px] font-bold uppercase tracking-[.14em] text-[#6F8CA4]">Recruiter Read</div>
            <p className="text-[12px] leading-6 text-[#B2C9D7]">
              {candidate.summary}
            </p>
          </div>
        </Panel>

        {/* Strengths & Weaknesses Panel */}
        <Panel className="p-6 space-y-6">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[14px] font-bold text-[#E1EEF5]">
                Relative Strengths (vs Applicant Pool)
              </h2>
              <span className="rounded bg-[#3FB27F]/15 px-2 py-0.5 text-[9px] font-bold text-[#62D39D]">
                AI Benchmark
              </span>
            </div>
            <ul className="space-y-2">
              {candidate.strengths.map((str, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[11px] leading-5 text-[#BBD8EC]">
                  <CheckCircle2 size={14} className="mt-0.5 text-[#3FB27F] shrink-0" />
                  <span>{str}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-[#24415C] pt-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[14px] font-bold text-[#E1EEF5]">
                Areas to Probe (Relative Weaknesses)
              </h2>
              <span className="rounded bg-[#F59E0B]/15 px-2 py-0.5 text-[9px] font-bold text-[#FBBF24]">
                Interview Focus
              </span>
            </div>
            <ul className="space-y-2">
              {candidate.weaknesses.map((weak, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[11px] leading-5 text-[#E0C0A4]">
                  <AlertTriangle size={14} className="mt-0.5 text-[#F59E0B] shrink-0" />
                  <span>{weak}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-[#24415C] pt-5">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[.14em] text-[#6F8CA4]">Next Action</div>
            <Link
              href="/compare"
              className="flex items-center justify-between rounded-md border border-[#315674] bg-[#10263E] px-4 py-3 text-[11px] font-bold text-[#BFE0EF] hover:border-[#4A9FE0]"
              data-testid="link-compare-candidate"
            >
              Compare with other candidates <ArrowUpRight size={14} />
            </Link>
          </div>
        </Panel>
      </div>

      {/* Skills Evidence Grid */}
      <Panel className="p-6">
        <div className="flex items-center justify-between border-b border-[#24415C] pb-4 mb-4">
          <div>
            <h3 className="text-[14px] font-bold text-white">Skill Evidence & Matching</h3>
            <p className="text-[11px] text-[#7192A9]">
              {matched} of {candidate.skills.length} role signals matched for {activeJob.title}
            </p>
          </div>
          <span className="data-mono font-bold text-[13px] text-[#76BFEA]">
            {matched}/{candidate.skills.length}
          </span>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {candidate.skills.map(sk => (
            <div
              key={sk.name}
              className={`flex items-center justify-between rounded-md border p-3 text-[11px] font-semibold ${
                sk.matched
                  ? 'border-[#3FB27F]/30 bg-[#3FB27F]/10 text-[#71D4A6]'
                  : 'border-[#24415C] bg-[#10263E] text-[#86A4BC]'
              }`}
            >
              <span>{sk.name}</span>
              {sk.matched ? <Check size={14} /> : <X size={14} className="text-[#F87171]" />}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------
   COMPARE CANDIDATES PAGE
   ------------------------------------------------------------------------- */
function ComparePage() {
  const { candidates, activeJob } = useApp();

  const handleExportComparison = () => {
    exportComparisonReportHTML(candidates as ExportCandidateData[], activeJob.title, activeJob.company);
  };

  return (
    <div className="mx-auto max-w-[1200px] animate-rise-in space-y-6">
      <PageHeading
        eyebrow="Decision Room / Head-to-Head Comparison"
        title="Candidate Comparison Matrix"
        description="Select any two candidates to run relative strength and weakness analysis and get AI recommendations."
        action={
          <button
            onClick={handleExportComparison}
            className="flex items-center gap-2 rounded-md border border-[#315674] bg-[#10263E] px-3.5 py-2.5 text-[11px] font-bold text-[#BCD9E8] hover:border-[#4A9FE0] hover:text-white transition-colors"
            data-testid="button-export-comparison"
          >
            <FileDown size={14} /> Export Comparison Report
          </button>
        }
      />

      {/* Interactive Two Candidate Comparator */}
      <HeadToHeadCompare candidates={candidates} />
    </div>
  );
}

/* -------------------------------------------------------------------------
   JOB DESCRIPTIONS MANAGEMENT PAGE (UPDATED "INTERN" -> "EMPLOYEE")
   ------------------------------------------------------------------------- */
function JobsPage() {
  const { jobs, setJobs, activeJob, setActiveJob } = useApp();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [company, setCompany] = useState('NexHire Labs');
  const [location, setLocation] = useState('Bengaluru · Hybrid');
  const [skills, setSkills] = useState<string[]>(['React', 'TypeScript', 'Node.js']);
  const [skillInput, setSkillInput] = useState('');

  const handleCreateJob = () => {
    if (!title.trim()) return;
    const newJob: JobProfile = {
      id: `job-${Date.now()}`,
      title,
      company,
      location,
      status: 'draft',
      skills,
      description: `Targeting candidates for ${title}`,
      semanticWeight: 0.7,
      keywordWeight: 0.3,
      candidateCount: 0,
      updatedAt: new Date().toISOString(),
    };
    setJobs([...jobs, newJob]);
    setIsModalOpen(false);
    setTitle('');
  };

  const makeActive = (job: JobProfile) => {
    setJobs(jobs.map(j => ({ ...j, status: j.id === job.id ? 'active' : 'draft' })));
    setActiveJob({ ...job, status: 'active' });
  };

  const deleteJob = (id: string) => {
    if (confirm('Delete this job description?')) {
      setJobs(jobs.filter(j => j.id !== id));
    }
  };

  return (
    <div className="mx-auto max-w-[1200px] animate-rise-in space-y-6">
      <PageHeading
        eyebrow="Workspace Configuration"
        title="Job Descriptions"
        description="Configure target employee roles. Active role drives your overview and AI workspace."
        action={
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 rounded-md bg-[#4A9FE0] px-3.5 py-2.5 text-[11px] font-extrabold text-[#0B1B2E] hover:bg-[#67B7ED]"
            data-testid="button-create-job"
          >
            <Plus size={14} /> New Job Description
          </button>
        }
      />

      <div className="space-y-4">
        {jobs.map((job) => (
          <Panel
            key={job.id}
            className="flex flex-col gap-4 p-5 transition-colors hover:border-[#39627F] md:flex-row md:items-center"
          >
            <div
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md border ${
                job.id === activeJob.id
                  ? 'border-[#4A9FE0]/40 bg-[#4A9FE0]/10 text-[#71C4F1]'
                  : 'border-[#315674] bg-[#10263E] text-[#7898AE]'
              }`}
            >
              <BriefcaseBusiness size={19} />
            </div>

            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-2">
                <h2 className="text-[14px] font-bold text-[#DFECF4]">{job.title}</h2>
                <StatusPill status={job.id === activeJob.id ? 'active' : 'draft'} />
              </div>
              <p className="text-[11px] text-[#7896AA]">
                {job.company} · {job.location} · {job.candidateCount} candidates evaluated
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {job.skills.map((skill) => (
                  <span
                    key={skill}
                    className="rounded border border-[#315674] bg-[#10263E] px-2 py-1 text-[9px] text-[#91B1C4]"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2 md:ml-6">
              {job.id !== activeJob.id && (
                <button
                  onClick={() => makeActive(job)}
                  className="rounded-md border border-[#3FB27F]/30 px-3 py-2 text-[10px] font-bold text-[#67CF9C] hover:bg-[#3FB27F]/10"
                >
                  Make Active
                </button>
              )}
              <button
                onClick={() => deleteJob(job.id)}
                className="rounded-md border border-[#315674] p-2 text-[#8EAABE] hover:text-[#F87171]"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </Panel>
        ))}
      </div>

      {/* New Job Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#04101C]/80 p-4">
          <div className="w-full max-w-lg rounded-lg border border-[#315674] bg-[#132A45] p-5">
            <div className="flex items-center justify-between border-b border-[#24415C] pb-3 mb-4">
              <h3 className="text-[15px] font-bold text-white">Create Employee Role Model</h3>
              <button onClick={() => setIsModalOpen(false)} className="text-[#6B8CA3] hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase text-[#7192A9]">Role Title</label>
                <input
                  type="text"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="e.g. Backend Cloud Employee"
                  className="w-full rounded border border-[#315674] bg-[#0E2238] p-2 text-[12px] text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[10px] font-bold uppercase text-[#7192A9]">Company</label>
                  <input
                    type="text"
                    value={company}
                    onChange={e => setCompany(e.target.value)}
                    className="w-full rounded border border-[#315674] bg-[#0E2238] p-2 text-[12px] text-white"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-bold uppercase text-[#7192A9]">Location</label>
                  <input
                    type="text"
                    value={location}
                    onChange={e => setLocation(e.target.value)}
                    className="w-full rounded border border-[#315674] bg-[#0E2238] p-2 text-[12px] text-white"
                  />
                </div>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2 border-t border-[#24415C] pt-3">
              <button onClick={() => setIsModalOpen(false)} className="px-3 py-1.5 text-[11px] text-[#7192A9]">
                Cancel
              </button>
              <button
                onClick={handleCreateJob}
                className="rounded bg-[#4A9FE0] px-4 py-1.5 text-[11px] font-bold text-[#0B1B2E]"
              >
                Save Role
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------
   AI WORKSPACE CHAT PAGE
   ------------------------------------------------------------------------- */
function ChatPage() {
  const { candidates, activeJob } = useApp();
  const [messages, setMessages] = useState<Array<{ id: string; role: 'user' | 'assistant'; content: string; time: string }>>([
    {
      id: 'm-1',
      role: 'assistant',
      content: `Hello! I have screened all candidates for the "${activeJob.title}" position. Ask me to compare candidate strengths, summarize skill gaps, or explain why #${candidates[0]?.rank || 1} ${candidates[0]?.name || 'the leader'} is ahead.`,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);

  const sendMessage = (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text) return;

    const userMsg = {
      id: `u-${Date.now()}`,
      role: 'user' as const,
      content: text,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsThinking(true);

    setTimeout(() => {
      const reply = queryRecruiterAI(text, candidates, activeJob);
      const aiMsg = {
        id: `ai-${Date.now()}`,
        role: 'assistant' as const,
        content: reply,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, aiMsg]);
      setIsThinking(false);
    }, 450);
  };

  return (
    <div className="mx-auto max-w-[1000px] animate-rise-in space-y-6">
      <PageHeading
        eyebrow={`AI Reasoning Assistant / ${activeJob.title}`}
        title="Refine the Hiring Brief"
        description="Ask the model to explain rankings, surface skill gaps, or compare candidates."
        action={
          <span className="rounded border border-[#3FB27F]/30 bg-[#3FB27F]/10 px-3 py-1.5 text-[10px] font-bold text-[#6BD6A1]">
            Active Role: {activeJob.title}
          </span>
        }
      />

      <Panel className="overflow-hidden">
        <div className="node-grid relative border-b border-[#24415C] px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#4A9FE0]/15 text-[#4A9FE0]">
              <Sparkles size={16} />
            </div>
            <div>
              <div className="text-[13px] font-bold text-white">NexHire AI Recruiter Agent</div>
              <div className="text-[10px] text-[#7192A9]">Scoped to active candidate evidence</div>
            </div>
          </div>
        </div>

        {/* Chat History */}
        <div className="min-h-[380px] max-h-[460px] overflow-y-auto space-y-4 p-5">
          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] rounded-lg border p-4 text-[12px] leading-6 ${
                  m.role === 'user'
                    ? 'border-[#315674] bg-[#163654] text-[#E4F0F7]'
                    : 'border-[#24415C] bg-[#10263E] text-[#D0E2ED]'
                }`}
              >
                <div className="mb-1 flex items-center gap-2 text-[9px] font-bold uppercase tracking-wider text-[#6F93AC]">
                  <span>{m.role === 'user' ? 'You' : 'NexHire AI'}</span>
                  <span>· {m.time}</span>
                </div>
                <div className="whitespace-pre-line">{m.content}</div>
              </div>
            </div>
          ))}

          {isThinking && (
            <div className="flex justify-start">
              <div className="rounded-lg border border-[#24415C] bg-[#10263E] p-3 text-[11px] text-[#62D39D] flex items-center gap-2">
                <Sparkles size={13} className="animate-spin" />
                AI reading candidate evidence...
              </div>
            </div>
          )}
        </div>

        {/* Quick Suggestion Prompt Chips */}
        <div className="flex flex-wrap gap-2 border-t border-[#24415C] bg-[#0E2034] px-5 py-3">
          {[
            'Who should I interview first?',
            'Compare the top two candidates',
            'Surface the biggest skill gaps',
            'Are there any flagged profiles?',
          ].map((prompt) => (
            <button
              key={prompt}
              onClick={() => sendMessage(prompt)}
              className="rounded border border-[#315674] bg-[#10263E] px-3 py-1.5 text-[10px] font-semibold text-[#8EBBD6] hover:border-[#4A9FE0] hover:text-white transition-colors"
              data-testid={`prompt-${prompt.slice(0, 8)}`}
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <div className="border-t border-[#24415C] bg-[#10263E]/60 p-4">
          <div className="flex items-end gap-3 rounded-md border border-[#315674] bg-[#0F2339] p-2 focus-within:border-[#4A9FE0]">
            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Ask about candidate strengths, previous companies, or skill matches..."
              className="flex-1 resize-none bg-transparent px-2 py-1 text-[12px] text-white outline-none placeholder:text-[#5F7F96]"
              data-testid="input-chat-message"
            />
            <button
              onClick={() => sendMessage()}
              disabled={isThinking || !input.trim()}
              className="flex h-9 w-9 items-center justify-center rounded-md bg-[#4A9FE0] text-[#0B1B2E] disabled:opacity-40"
              data-testid="button-send-chat"
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------
   EXPORTS PAGE (FIXED DOWNLOAD & EXPORT BUTTONS)
   ------------------------------------------------------------------------- */
function ExportsPage() {
  const { candidates, activeJob } = useApp();
  const [recentExports, setRecentExports] = useState<Array<{ id: string; name: string; type: string; date: string }>>([
    {
      id: 'e-1',
      name: `NexHire_${activeJob.title.replace(/\s+/g, '_')}_Ranked_List.csv`,
      type: 'CSV Ranked Report',
      date: new Date().toLocaleTimeString(),
    },
  ]);

  const handleExportRanked = () => {
    const filename = exportRankedCandidatesCSV(candidates as ExportCandidateData[], activeJob.title);
    setRecentExports(prev => [{ id: `e-${Date.now()}`, name: filename, type: 'Ranked Candidate List (CSV)', date: new Date().toLocaleTimeString() }, ...prev]);
  };

  const handleExportComparison = () => {
    const filename = exportComparisonReportHTML(candidates as ExportCandidateData[], activeJob.title, activeJob.company);
    setRecentExports(prev => [{ id: `e-${Date.now()}`, name: filename, type: 'Decision Comparison (HTML/PDF)', date: new Date().toLocaleTimeString() }, ...prev]);
  };

  const handleExportSkillGap = () => {
    const filename = exportSkillGapCSV(candidates as ExportCandidateData[], activeJob.title);
    setRecentExports(prev => [{ id: `e-${Date.now()}`, name: filename, type: 'Skill Gap Matrix (CSV)', date: new Date().toLocaleTimeString() }, ...prev]);
  };

  return (
    <div className="mx-auto max-w-[1100px] animate-rise-in space-y-7">
      <PageHeading
        eyebrow="Decision Artifacts"
        title="Export Center"
        description="Download ready-to-share decision files from the active role's candidate evidence."
      />

      <div className="grid gap-5 md:grid-cols-3">
        {/* Export Ranked List */}
        <Panel className="flex flex-col p-5">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-[#4A9FE0]/15 text-[#4A9FE0]">
            <UsersRound size={20} />
          </div>
          <h3 className="text-[14px] font-bold text-white">Ranked Candidate List</h3>
          <p className="mt-2 min-h-[44px] text-[11px] leading-5 text-[#7F9CB3]">
            Every candidate with fit scores, previous companies, years of exp, and relative strengths.
          </p>
          <button
            onClick={handleExportRanked}
            className="mt-5 flex items-center justify-center gap-2 rounded-md bg-[#10263E] border border-[#315674] py-2.5 text-[11px] font-bold text-[#B9D8E8] hover:border-[#4A9FE0] hover:text-white transition-colors"
            data-testid="button-export-ranked"
          >
            <FileDown size={14} /> Download CSV List
          </button>
        </Panel>

        {/* Export Comparison */}
        <Panel className="flex flex-col p-5">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-[#4A9FE0]/15 text-[#4A9FE0]">
            <GitCompare size={20} />
          </div>
          <h3 className="text-[14px] font-bold text-white">Top Candidate Comparison</h3>
          <p className="mt-2 min-h-[44px] text-[11px] leading-5 text-[#7F9CB3]">
            Printable HTML / PDF-ready side-by-side comparison of the strongest profiles.
          </p>
          <button
            onClick={handleExportComparison}
            className="mt-5 flex items-center justify-center gap-2 rounded-md bg-[#10263E] border border-[#315674] py-2.5 text-[11px] font-bold text-[#B9D8E8] hover:border-[#4A9FE0] hover:text-white transition-colors"
            data-testid="button-export-comparison"
          >
            <FileDown size={14} /> Download Comparison
          </button>
        </Panel>

        {/* Export Skill Gap */}
        <Panel className="flex flex-col p-5">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-[#4A9FE0]/15 text-[#4A9FE0]">
            <Target size={20} />
          </div>
          <h3 className="text-[14px] font-bold text-white">Skill-Gap Analysis</h3>
          <p className="mt-2 min-h-[44px] text-[11px] leading-5 text-[#7F9CB3]">
            Matched signals, shortages, and candidate coverage distribution across the pool.
          </p>
          <button
            onClick={handleExportSkillGap}
            className="mt-5 flex items-center justify-center gap-2 rounded-md bg-[#10263E] border border-[#315674] py-2.5 text-[11px] font-bold text-[#B9D8E8] hover:border-[#4A9FE0] hover:text-white transition-colors"
            data-testid="button-export-skill-gap"
          >
            <FileDown size={14} /> Download Gap Report
          </button>
        </Panel>
      </div>

      {/* Recent Exports Log */}
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-[#24415C] px-5 py-4">
          <div>
            <h3 className="text-[14px] font-bold text-white">Generated Exports</h3>
            <p className="text-[11px] text-[#7192A9]">Artifacts downloaded during this session.</p>
          </div>
          <Download size={16} className="text-[#6488A3]" />
        </div>

        <div className="divide-y divide-[#24415C]">
          {recentExports.map((exp) => (
            <div key={exp.id} className="flex items-center justify-between px-5 py-3.5 hover:bg-[#153250] transition-colors">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded bg-[#3FB27F]/10 text-[#62D39D]">
                  <Check size={14} />
                </div>
                <div>
                  <div className="text-[12px] font-bold text-[#D3E5F2]">{exp.name}</div>
                  <div className="text-[10px] text-[#69889E]">{exp.type} · Generated at {exp.date}</div>
                </div>
              </div>
              <span className="text-[10px] font-bold text-[#62D39D] flex items-center gap-1">
                <Check size={11} /> Ready
              </span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------
   ROUTER & APP ROOT
   ------------------------------------------------------------------------- */
function Router() {
  return (
    <ErrorBoundary resetKey={useLocation()[0]}>
      <Shell>
        <Switch>
          <Route path="/" component={DashboardPage} />
          <Route path="/candidate/:candidateId" component={CandidatePage} />
          <Route path="/compare" component={ComparePage} />
          <Route path="/jobs" component={JobsPage} />
          <Route path="/chat" component={ChatPage} />
          <Route path="/exports" component={ExportsPage} />
          <Route component={NotFound} />
        </Switch>
      </Shell>
    </ErrorBoundary>
  );
}

export default function App() {
  const [candidates, setCandidates] = useState<CandidateProfile[]>(() =>
    computeRelativeStrengthsAndWeaknesses(INITIAL_CANDIDATES)
  );
  const [activeJob, setActiveJob] = useState<JobProfile>(INITIAL_JOB);
  const [jobs, setJobs] = useState<JobProfile[]>([INITIAL_JOB]);
  const [recruiterUser, setRecruiterUser] = useState<RecruiterUser>({
    name: 'Avery Rios',
    email: 'avery.rios.recruiter@gmail.com',
    company: 'TechTonic Labs',
    role: 'Hiring Lead',
    isLoggedIn: true,
  });

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [isNotifModalOpen, setIsNotifModalOpen] = useState(false);

  const contextValue: AppContextType = {
    candidates,
    setCandidates,
    activeJob,
    setActiveJob,
    recruiterUser,
    setRecruiterUser,
    jobs,
    setJobs,
    openAuthModal: () => setIsAuthModalOpen(true),
    openProfileModal: () => setIsProfileModalOpen(true),
    openNotifModal: () => setIsNotifModalOpen(true),
  };

  return (
    <QueryClientProvider client={queryClient}>
      <AppContext.Provider value={contextValue}>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>

        {/* Global Signup / Auth Modal with Animations */}
        <SignupModal
          isOpen={isAuthModalOpen}
          onClose={() => setIsAuthModalOpen(false)}
          onAuthSuccess={(user) => setRecruiterUser(user)}
          currentUser={recruiterUser}
        />

        {/* General Recruiter Profile Modal */}
        <ProfileModal
          isOpen={isProfileModalOpen}
          onClose={() => setIsProfileModalOpen(false)}
          user={recruiterUser}
          onUpdateUser={(updated) => setRecruiterUser(updated)}
          onOpenAuthModal={() => setIsAuthModalOpen(true)}
        />

        {/* Notifications Modal */}
        <NotificationCenter
          isOpen={isNotifModalOpen}
          onClose={() => setIsNotifModalOpen(false)}
        />

        <Toaster />
      </AppContext.Provider>
    </QueryClientProvider>
  );
}