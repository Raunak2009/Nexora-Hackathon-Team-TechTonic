/**
 * Utilities for exporting candidate data, comparison reports, and skill gap analyses.
 * Provides real browser downloads for CSV, JSON, and printable reports.
 */

export interface ExportCandidateData {
  id: string;
  name: string;
  email: string;
  role: string;
  yearsExperience: number;
  previousCompanies?: string[];
  overallScore: number;
  semanticScore: number;
  keywordScore: number;
  confidence: number;
  status: string;
  skills: { name: string; matched: boolean }[];
  strengths?: string[];
  weaknesses?: string[];
  summary?: string;
}

/**
 * Triggers a file download in the browser
 */
export function downloadFile(filename: string, content: string, mimeType: string = 'text/plain') {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Generates and downloads a ranked candidate CSV file
 */
export function exportRankedCandidatesCSV(candidates: ExportCandidateData[], jobTitle: string = 'Role'): string {
  const headers = [
    'Rank',
    'Candidate Name',
    'Email',
    'Role',
    'Years Experience',
    'Previous Companies',
    'Overall Fit Score (%)',
    'Semantic Alignment (%)',
    'Keyword Coverage (%)',
    'Model Confidence (%)',
    'Status',
    'Relative Strengths (vs Cohort)',
    'Relative Weaknesses (vs Cohort)',
    'Matched Skills',
    'AI Recruiter Summary',
  ];

  const rows = candidates.map((c, index) => {
    const rank = index + 1;
    const name = `"${(c.name || '').replace(/"/g, '""')}"`;
    const email = `"${(c.email || '').replace(/"/g, '""')}"`;
    const role = `"${(c.role || '').replace(/"/g, '""')}"`;
    const yearsExp = c.yearsExperience ?? 0;
    const companies = `"${(c.previousCompanies || []).join(', ').replace(/"/g, '""')}"`;
    const overallScore = c.overallScore ?? 0;
    const semanticScore = c.semanticScore ?? 0;
    const keywordScore = c.keywordScore ?? 0;
    const confidence = c.confidence ?? 0;
    const status = c.status || 'review';
    const strengths = `"${(c.strengths || []).join('; ').replace(/"/g, '""')}"`;
    const weaknesses = `"${(c.weaknesses || []).join('; ').replace(/"/g, '""')}"`;
    const matchedSkills = `"${c.skills.filter(s => s.matched).map(s => s.name).join(', ').replace(/"/g, '""')}"`;
    const summary = `"${(c.summary || '').replace(/"/g, '""')}"`;

    return [
      rank,
      name,
      email,
      role,
      yearsExp,
      companies,
      overallScore,
      semanticScore,
      keywordScore,
      confidence,
      status,
      strengths,
      weaknesses,
      matchedSkills,
      summary,
    ].join(',');
  });

  const csvContent = [headers.join(','), ...rows].join('\n');
  const filename = `NexHire_${jobTitle.replace(/[^a-zA-Z0-9_-]/g, '_')}_Ranked_List_${new Date().toISOString().slice(0, 10)}.csv`;
  downloadFile(filename, csvContent, 'text/csv');
  return filename;
}

/**
 * Generates and downloads a printable HTML / PDF-ready candidate comparison report
 */
export function exportComparisonReportHTML(
  candidates: ExportCandidateData[],
  jobTitle: string = 'Active Role',
  company: string = 'NexHire Labs'
): string {
  const top = candidates.slice(0, 3);
  const dateStr = new Date().toLocaleDateString('en-US', { dateStyle: 'full' });

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>NexHire Top Candidate Decision Report - ${jobTitle}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b1b2e; color: #d9e6f0; padding: 40px; margin: 0; }
    .header { border-bottom: 2px solid #24415c; padding-bottom: 20px; margin-bottom: 30px; }
    .title { font-size: 26px; font-weight: 800; color: #ffffff; }
    .subtitle { font-size: 14px; color: #7f9cb5; margin-top: 6px; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; background: #4a9fe020; color: #4a9fe0; border: 1px solid #4a9fe050; }
    .grid { display: grid; grid-template-columns: repeat(${Math.max(top.length, 1)}, 1fr); gap: 20px; margin-top: 25px; }
    .card { background: #132a45; border: 1px solid #24415c; border-radius: 8px; padding: 20px; }
    .score { font-size: 38px; font-weight: 800; color: #62d39d; font-family: monospace; }
    .candidate-name { font-size: 18px; font-weight: 700; color: #ffffff; margin-top: 10px; }
    .meta { font-size: 12px; color: #8fa8bd; margin-bottom: 15px; }
    .companies { margin: 10px 0; }
    .company-pill { display: inline-block; background: #1a3a56; color: #9bc5e0; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; }
    .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #668ba8; font-weight: bold; margin-top: 15px; }
    .strengths { color: #62d39d; font-size: 12px; margin: 6px 0; }
    .weaknesses { color: #f47d80; font-size: 12px; margin: 6px 0; }
    .footer { margin-top: 50px; font-size: 11px; color: #5f7e97; text-align: center; border-top: 1px solid #24415c; padding-top: 20px; }
    @media print { body { background: white; color: black; } .card { border-color: #ccc; background: #f9f9f9; } .score { color: #007744; } }
  </style>
</head>
<body>
  <div class="header">
    <span class="badge">NEXHIRE DECISION REPORT</span>
    <h1 class="title">${jobTitle} — Top Candidates Comparison</h1>
    <p class="subtitle">${company} · Generated on ${dateStr} · AI-Assisted Candidate Screening</p>
  </div>

  <div class="grid">
    ${top.map((c, i) => `
      <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span class="badge">#${i + 1} Ranked</span>
          <span class="score">${c.overallScore}%</span>
        </div>
        <div class="candidate-name">${c.name}</div>
        <div class="meta">${c.role} · ${c.yearsExperience} Years Experience</div>
        
        <div class="section-title">Previous Companies</div>
        <div class="companies">
          ${(c.previousCompanies || ['Independent Contributor']).map(co => `<span class="company-pill">${co}</span>`).join(' ')}
        </div>

        <div class="section-title">Relative Strengths</div>
        <div class="strengths">
          ${(c.strengths || ['High skill alignment with role expectations']).map(s => `<div>✓ ${s}</div>`).join('')}
        </div>

        <div class="section-title">Areas to Probe</div>
        <div class="weaknesses">
          ${(c.weaknesses || ['Verify specific tooling in interview']).map(w => `<div>⚠ ${w}</div>`).join('')}
        </div>

        <div class="section-title">AI Recruiter Summary</div>
        <p style="font-size:12px; line-height:1.5; color:#bed5e6;">${c.summary || 'Strong candidate with clear evidence of relevant technical competencies.'}</p>
      </div>
    `).join('')}
  </div>

  <div class="footer">
    NexHire Intelligent Screening Engine · "AI does the judging, you do the selection."
  </div>
</body>
</html>`;

  const filename = `NexHire_${jobTitle.replace(/[^a-zA-Z0-9_-]/g, '_')}_Comparison_Report.html`;
  downloadFile(filename, html, 'text/html');
  return filename;
}

/**
 * Generates and downloads a skill gap analysis report
 */
export function exportSkillGapCSV(candidates: ExportCandidateData[], jobTitle: string = 'Role'): string {
  // Aggregate all skills
  const skillCounts: Record<string, { matched: number; total: number }> = {};

  candidates.forEach(c => {
    c.skills.forEach(s => {
      if (!skillCounts[s.name]) skillCounts[s.name] = { matched: 0, total: 0 };
      skillCounts[s.name].total += 1;
      if (s.matched) skillCounts[s.name].matched += 1;
    });
  });

  const headers = ['Required Skill', 'Candidates with Skill', 'Total Candidates Screened', 'Cohort Coverage (%)', 'Shortage Indicator'];
  const rows = Object.entries(skillCounts)
    .sort((a, b) => (b[1].matched / b[1].total) - (a[1].matched / a[1].total))
    .map(([skill, data]) => {
      const coveragePct = Math.round((data.matched / Math.max(data.total, 1)) * 100);
      const shortage = coveragePct < 40 ? 'CRITICAL GAP (<40%)' : coveragePct < 70 ? 'MODERATE SHORTAGE' : 'WELL SATISFIED';
      return [`"${skill}"`, data.matched, data.total, `${coveragePct}%`, `"${shortage}"`].join(',');
    });

  const csvContent = [headers.join(','), ...rows].join('\n');
  const filename = `NexHire_${jobTitle.replace(/[^a-zA-Z0-9_-]/g, '_')}_Skill_Gap_Analysis.csv`;
  downloadFile(filename, csvContent, 'text/csv');
  return filename;
}
