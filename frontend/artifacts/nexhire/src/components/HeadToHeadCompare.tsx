import { useState } from 'react';
import type { CandidateProfile } from '@/lib/ai-engine';
import { compareTwoCandidates } from '@/lib/ai-engine';
import {
  GitCompare, Award, Check, X, BriefcaseBusiness, Clock3,
  ArrowRight, Sparkles, ChevronDown, AlertTriangle
} from 'lucide-react';

interface HeadToHeadCompareProps {
  candidates: CandidateProfile[];
}

export function HeadToHeadCompare({ candidates }: HeadToHeadCompareProps) {
  const [candAId, setCandAId] = useState<string>(candidates[0]?.id || '');
  const [candBId, setCandBId] = useState<string>(candidates[1]?.id || candidates[0]?.id || '');

  const candA = candidates.find((c) => c.id === candAId) || candidates[0];
  const candB = candidates.find((c) => c.id === candBId) || candidates[1] || candidates[0];

  if (!candA || !candB) {
    return (
      <div className="p-8 text-center text-[#7F9CB5]">
        Please screen candidates first before running head-to-head comparison.
      </div>
    );
  }

  const comparison = compareTwoCandidates(candA, candB);

  return (
    <div className="space-y-6">
      {/* Selection Control Panel */}
      <div className="rounded-lg border border-[#24415C] bg-[#132A45]/85 p-5 panel-shadow">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded bg-[#4A9FE0]/15 text-[#4A9FE0]">
              <GitCompare size={16} />
            </span>
            <h3 className="text-[15px] font-bold text-[#E5F2F9]">
              Head-to-Head Candidate Comparison
            </h3>
          </div>
          <span className="text-[11px] text-[#7192A9]">
            Select any two candidates to run a direct AI relative evaluation
          </span>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {/* Candidate A Selector */}
          <div>
            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-[.14em] text-[#4A9FE0]">
              Select Candidate A
            </label>
            <div className="relative">
              <select
                value={candAId}
                onChange={(e) => setCandAId(e.target.value)}
                className="w-full appearance-none rounded-md border border-[#315674] bg-[#10263E] px-3 py-2.5 pr-8 text-[12px] font-bold text-[#E6F3FA] outline-none focus:border-[#4A9FE0]"
                data-testid="select-candidate-a"
              >
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    #{c.rank} {c.name} — {c.overallScore}% Fit ({c.yearsExperience} yrs exp)
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-3 top-3.5 text-[#6387A3] pointer-events-none" />
            </div>
          </div>

          {/* Candidate B Selector */}
          <div>
            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-[.14em] text-[#62D39D]">
              Select Candidate B
            </label>
            <div className="relative">
              <select
                value={candBId}
                onChange={(e) => setCandBId(e.target.value)}
                className="w-full appearance-none rounded-md border border-[#315674] bg-[#10263E] px-3 py-2.5 pr-8 text-[12px] font-bold text-[#E6F3FA] outline-none focus:border-[#62D39D]"
                data-testid="select-candidate-b"
              >
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    #{c.rank} {c.name} — {c.overallScore}% Fit ({c.yearsExperience} yrs exp)
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-3 top-3.5 text-[#6387A3] pointer-events-none" />
            </div>
          </div>
        </div>
      </div>

      {/* Side-by-Side Comparison Cards */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Candidate A Card */}
        <div className={`rounded-lg border p-6 panel-shadow transition-all ${
          candA.overallScore >= candB.overallScore
            ? 'border-[#4A9FE0]/60 bg-[#132A45]/95 shadow-[0_0_20px_rgba(74,159,224,0.15)]'
            : 'border-[#24415C] bg-[#10263E]/80'
        }`}>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[#4A9FE0]/50 bg-[#1A3D5E] text-[16px] font-bold text-[#C7E9FB]">
                {candA.initials}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-[16px] font-bold text-white">{candA.name}</h4>
                  {candA.overallScore >= candB.overallScore && (
                    <span className="flex items-center gap-1 rounded bg-[#4A9FE0]/20 px-2 py-0.5 text-[9px] font-extrabold text-[#74C6F4]">
                      <Award size={10} /> LEADING
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-[#86A4BA]">{candA.role}</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-[28px] font-black data-mono text-[#76BFEA]">
                {candA.overallScore}<span className="text-[12px] text-[#698EA5]">%</span>
              </div>
              <div className="text-[10px] text-[#6F90A5]">Rank #{candA.rank} in pool</div>
            </div>
          </div>

          <div className="mt-5 space-y-3.5 border-t border-[#24415C] pt-4 text-[11px]">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[#86A4BA]">
                <Clock3 size={13} /> Total Experience:
              </span>
              <strong className="text-white font-mono">{candA.yearsExperience} Years</strong>
            </div>

            <div>
              <span className="flex items-center gap-1.5 text-[#86A4BA] mb-1.5">
                <BriefcaseBusiness size={13} /> Previous Companies:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(candA.previousCompanies || []).map((comp) => (
                  <span key={comp} className="rounded bg-[#1B3A59] border border-[#2E5579] px-2 py-0.5 text-[10px] text-[#B8DBEE]">
                    {comp}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[#86A4BA]">Semantic Match:</span>
              <span className="data-mono font-bold text-[#4A9FE0]">{candA.semanticScore}%</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[#86A4BA]">Keyword Coverage:</span>
              <span className="data-mono font-bold text-[#62D39D]">{candA.keywordScore}%</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[#86A4BA]">Confidence:</span>
              <span className="data-mono text-[#D2E4EF]">{candA.confidence}%</span>
            </div>
          </div>

          {/* Advantages of A */}
          <div className="mt-5 rounded-md border border-[#265377] bg-[#0F243B] p-3.5">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[.14em] text-[#4A9FE0] flex items-center gap-1.5">
              <Check size={12} /> Where {candA.name} Beats {candB.name}
            </div>
            <ul className="space-y-1.5 text-[11px] text-[#AEC8DA]">
              {comparison.whereABeatsB.map((point, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-[#4A9FE0] mt-0.5">•</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Candidate B Card */}
        <div className={`rounded-lg border p-6 panel-shadow transition-all ${
          candB.overallScore > candA.overallScore
            ? 'border-[#62D39D]/60 bg-[#132A45]/95 shadow-[0_0_20px_rgba(98,211,157,0.15)]'
            : 'border-[#24415C] bg-[#10263E]/80'
        }`}>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[#62D39D]/50 bg-[#163B48] text-[16px] font-bold text-[#BAEEDB]">
                {candB.initials}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-[16px] font-bold text-white">{candB.name}</h4>
                  {candB.overallScore > candA.overallScore && (
                    <span className="flex items-center gap-1 rounded bg-[#62D39D]/20 px-2 py-0.5 text-[9px] font-extrabold text-[#62D39D]">
                      <Award size={10} /> LEADING
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-[#86A4BA]">{candB.role}</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-[28px] font-black data-mono text-[#62D39D]">
                {candB.overallScore}<span className="text-[12px] text-[#698EA5]">%</span>
              </div>
              <div className="text-[10px] text-[#6F90A5]">Rank #{candB.rank} in pool</div>
            </div>
          </div>

          <div className="mt-5 space-y-3.5 border-t border-[#24415C] pt-4 text-[11px]">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[#86A4BA]">
                <Clock3 size={13} /> Total Experience:
              </span>
              <strong className="text-white font-mono">{candB.yearsExperience} Years</strong>
            </div>

            <div>
              <span className="flex items-center gap-1.5 text-[#86A4BA] mb-1.5">
                <BriefcaseBusiness size={13} /> Previous Companies:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(candB.previousCompanies || []).map((comp) => (
                  <span key={comp} className="rounded bg-[#18393F] border border-[#27585F] px-2 py-0.5 text-[10px] text-[#9FDBC9]">
                    {comp}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[#86A4BA]">Semantic Match:</span>
              <span className="data-mono font-bold text-[#4A9FE0]">{candB.semanticScore}%</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[#86A4BA]">Keyword Coverage:</span>
              <span className="data-mono font-bold text-[#62D39D]">{candB.keywordScore}%</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[#86A4BA]">Confidence:</span>
              <span className="data-mono text-[#D2E4EF]">{candB.confidence}%</span>
            </div>
          </div>

          {/* Advantages of B */}
          <div className="mt-5 rounded-md border border-[#27585F] bg-[#0E282F]/70 p-3.5">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[.14em] text-[#62D39D] flex items-center gap-1.5">
              <Check size={12} /> Where {candB.name} Beats {candA.name}
            </div>
            <ul className="space-y-1.5 text-[11px] text-[#A6DDD0]">
              {comparison.whereBBeatsA.map((point, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-[#62D39D] mt-0.5">•</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* AI Recommendation Banner */}
      <div className="rounded-lg border border-[#305E82] bg-gradient-to-r from-[#112942] to-[#15344F] p-5 shadow-lg">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#4A9FE0]/20 text-[#67B8ED]">
            <Sparkles size={18} />
          </div>
          <div>
            <h4 className="text-[13px] font-bold uppercase tracking-[.1em] text-[#55AEEC]">
              AI Decision Recommendation
            </h4>
            <p className="mt-1.5 text-[12px] leading-6 text-[#D7E8F3]">
              {comparison.recommendation}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

