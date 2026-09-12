import { useState } from 'react';
import type { CandidateProfile } from '@/lib/ai-engine';
import { Award, BriefcaseBusiness, ChevronRight, TrendingUp } from 'lucide-react';
import { Link } from 'wouter';

interface CandidateBarGraphProps {
  candidates: CandidateProfile[];
  onSelectCandidate?: (candidate: CandidateProfile) => void;
}

export function CandidateBarGraph({ candidates, onSelectCandidate }: CandidateBarGraphProps) {
  const [hoveredCandidate, setHoveredCandidate] = useState<CandidateProfile | null>(null);

  // Take top 8 candidates for clean visualization
  const displayed = candidates.slice(0, 8);

  const getRankBadge = (index: number) => {
    switch (index) {
      case 0:
        return {
          text: '1st',
          bg: 'bg-amber-400 text-slate-950 font-black shadow-[0_0_12px_rgba(251,191,36,0.5)] border border-amber-300',
        };
      case 1:
        return {
          text: '2nd',
          bg: 'bg-slate-200 text-slate-900 font-extrabold shadow-[0_0_10px_rgba(226,232,240,0.4)] border border-white',
        };
      case 2:
        return {
          text: '3rd',
          bg: 'bg-amber-700 text-amber-100 font-bold border border-amber-600',
        };
      default:
        return {
          text: `${index + 1}th`,
          bg: 'bg-[#1C3A57] text-[#9CBCCC] font-semibold border border-[#2E5274]',
        };
    }
  };

  const getBarColor = (score: number) => {
    if (score >= 85) return 'from-[#3FB27F] to-[#62D39D]';
    if (score >= 75) return 'from-[#2563EB] to-[#4A9FE0]';
    if (score >= 65) return 'from-[#D97706] to-[#FBBF24]';
    return 'from-[#DC2626] to-[#F87171]';
  };

  if (candidates.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-[#24415C] bg-[#10263E]/40 p-8 text-center text-[#7F9CB5]">
        No candidate data to plot. Upload resumes or run screening to view rankings.
      </div>
    );
  }

  return (
    <div className="relative rounded-lg border border-[#24415C] bg-[#132A45]/90 p-5 panel-shadow">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-[#24415C] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-[#4A9FE0]/15 text-[#4A9FE0]">
              <TrendingUp size={14} />
            </span>
            <h3 className="text-[15px] font-extrabold text-[#E6F2F8]">
              Candidate Fit Benchmark — Scores out of 100
            </h3>
          </div>
          <p className="mt-1 text-[11px] text-[#86A4BC]">
            Comparative AI ranking with top cohort honors (1st, 2nd, 3rd) and relative scores.
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-[#7896AA]">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#62D39D]" /> &gt;= 85% Strong
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#4A9FE0]" /> 75-84% Solid
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#FBBF24]" /> &lt; 75% Moderate
          </span>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="relative pt-6 pb-2">
        {/* Y-axis guide lines */}
        <div className="absolute inset-x-0 top-6 bottom-14 flex flex-col justify-between pointer-events-none opacity-20">
          {[100, 75, 50, 25, 0].map((val) => (
            <div key={val} className="flex items-center border-t border-[#4A9FE0] w-full text-[9px] data-mono text-[#4A9FE0]">
              <span className="-mt-3.5 pr-2 bg-[#132A45]">{val}%</span>
            </div>
          ))}
        </div>

        {/* Bars Grid */}
        <div className="relative z-10 flex h-[230px] items-end justify-around gap-2 px-6">
          {displayed.map((candidate, idx) => {
            const badge = getRankBadge(idx);
            const heightPercent = Math.max(candidate.overallScore, 10);
            const isHovered = hoveredCandidate?.id === candidate.id;

            return (
              <div
                key={candidate.id}
                className="group relative flex flex-1 flex-col items-center justify-end h-full cursor-pointer max-w-[80px]"
                onMouseEnter={() => setHoveredCandidate(candidate)}
                onMouseLeave={() => setHoveredCandidate(null)}
                onClick={() => onSelectCandidate?.(candidate)}
              >
                {/* 1st, 2nd, 3rd Rank Badge AT TOP OF BAR */}
                <div
                  className={`mb-2 rounded-full px-2 py-0.5 text-[10px] tracking-tight transition-all duration-200 transform group-hover:scale-110 ${badge.bg}`}
                  data-testid={`badge-rank-${idx + 1}`}
                >
                  {badge.text}
                </div>

                {/* Score Number on Top */}
                <span className="mb-1 text-[11px] font-bold data-mono text-[#DDF0FB]">
                  {candidate.overallScore}
                </span>

                {/* Vertical Bar */}
                <div className="relative w-full overflow-hidden rounded-t-md bg-[#183552] transition-all duration-300 group-hover:brightness-110"
                  style={{ height: `${heightPercent}%` }}
                >
                  <div
                    className={`h-full w-full bg-gradient-to-t ${getBarColor(candidate.overallScore)} transition-all duration-500`}
                  />
                  {isHovered && (
                    <div className="absolute inset-0 bg-white/20 animate-pulse" />
                  )}
                </div>

                {/* Candidate Name below bar */}
                <div className="mt-2 text-center">
                  <div className="w-16 truncate text-[11px] font-semibold text-[#D4E4EC] group-hover:text-[#4A9FE0]">
                    {candidate.name.split(' ')[0]}
                  </div>
                  <div className="text-[9px] text-[#7192A9] font-mono">
                    {candidate.yearsExperience}y exp
                  </div>
                </div>

                {/* Hover Tooltip Card */}
                {isHovered && (
                  <div className="absolute bottom-full mb-3 z-30 w-60 rounded-lg border border-[#3A6B92] bg-[#0E2238] p-3 shadow-2xl backdrop-blur pointer-events-none animate-rise-in">
                    <div className="flex items-center justify-between border-b border-[#24415C] pb-2">
                      <div className="font-bold text-[12px] text-white flex items-center gap-1.5">
                        <Award size={13} className="text-amber-400" />
                        {candidate.name}
                      </div>
                      <span className="data-mono font-bold text-[13px] text-[#62D39D]">
                        {candidate.overallScore}/100
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-[10px] text-[#9EB9CC]">
                      <div className="flex items-center gap-1 text-[#6FB3DF]">
                        <BriefcaseBusiness size={11} />
                        <span>Past: {(candidate.previousCompanies || []).slice(0, 2).join(', ') || 'Tech firm'}</span>
                      </div>
                      <div>Experience: <strong className="text-white">{candidate.yearsExperience} years</strong></div>
                      <div>Semantic Match: <strong className="text-white">{candidate.semanticScore}%</strong></div>
                      <div>Matched Skills: <strong className="text-white">{candidate.skills.filter(s => s.matched).length}</strong></div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer Banner */}
      <div className="mt-4 flex items-center justify-between rounded-md border border-[#24415C] bg-[#10263E] px-4 py-2.5 text-[11px]">
        <span className="text-[#84A4BC]">
          Top ranked candidate: <strong className="text-[#E6F2F8]">{displayed[0]?.name || 'N/A'}</strong> leads the pool with <strong className="text-[#62D39D]">{displayed[0]?.overallScore || 0}% fit score</strong>
        </span>
        <Link
          href="/compare"
          className="flex items-center gap-1 text-[11px] font-bold text-[#4A9FE0] hover:text-[#76BEF0]"
          data-testid="link-compare-from-graph"
        >
          Compare top candidates <ChevronRight size={13} />
        </Link>
      </div>
    </div>
  );
}

