/**
 * Bridge from this Express server to the Python scoring engine.
 *
 * The engine (repo root `ai/`, served by `backend/server.py`) does all the
 * parsing, matching and ranking. Nothing in this file scores anything - it
 * forwards requests and reshapes the responses into the `Candidate` /
 * `Dashboard` types the React app already expects, so the UI needs no changes.
 *
 * Start the Python side first:
 *     cd backend && uvicorn server:app --port 8000
 *
 * Point this at it with ENGINE_URL if it is not on localhost:8000.
 *
 * If the engine is unreachable, every call throws `EngineUnavailableError` and
 * the routes return 503 with a clear message. The previous version of this file
 * served hardcoded candidates, which meant a broken backend looked exactly like
 * a working one - the worst possible failure mode during a judged demo.
 */

const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";
const TIMEOUT_MS = Number(process.env.ENGINE_TIMEOUT_MS ?? 120_000);

export class EngineUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EngineUnavailableError";
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${ENGINE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init?.body && !(init.body instanceof FormData)
          ? { "content-type": "application/json" }
          : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new EngineUnavailableError(
        `Engine returned ${res.status} for ${path}. ${body.slice(0, 300)}`,
      );
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof EngineUnavailableError) throw err;
    const reason = err instanceof Error ? err.message : String(err);
    throw new EngineUnavailableError(
      `Could not reach the scoring engine at ${ENGINE_URL}. ` +
        `Start it with: cd backend && uvicorn server:app --port 8000  (${reason})`,
    );
  } finally {
    clearTimeout(timer);
  }
}

export const engine = {
  health: () => call<EngineHealth>("/health"),
  listJobs: () => call<{ jobs: EngineJob[] }>("/jobs"),
  getJob: (id: string) => call<EngineJob>(`/jobs/${id}`),
  createJob: (title: string, jdText: string) =>
    call<EngineJob>("/jobs", {
      method: "POST",
      body: JSON.stringify({ title, jd_text: jdText }),
    }),
  deleteJob: (id: string) =>
    call<{ deleted: string }>(`/jobs/${id}`, { method: "DELETE" }),
  auditJd: (jdText: string) =>
    call<{ audit: BiasAudit }>("/jd/audit", {
      method: "POST",
      body: JSON.stringify({ jd_text: jdText }),
    }),

  getRun: (runId: string, collapse = true) =>
    call<EngineRun>(`/runs/${runId}?collapse_duplicates=${collapse}`),
  matrix: (runId: string) => call<EngineMatrix>(`/runs/${runId}/matrix`),
  candidate: (runId: string, who: string) =>
    call<EngineCandidateDetail>(
      `/runs/${runId}/candidates/${encodeURIComponent(who)}`,
    ),
  timeline: (runId: string, who: string) =>
    call<EngineTimeline>(
      `/runs/${runId}/candidates/${encodeURIComponent(who)}/timeline`,
    ),
  top: (runId: string, n = 3) => call<EngineTop>(`/runs/${runId}/top?n=${n}`),
  charts: (runId: string) => call<Record<string, unknown>>(`/runs/${runId}/charts`),
  flags: (runId: string) => call<EngineFlags>(`/runs/${runId}/flags`),
  duplicates: (runId: string) => call<EngineDuplicates>(`/runs/${runId}/duplicates`),

  setWeights: (runId: string, w: { keyword?: number; semantic?: number; experience?: number }) =>
    call<EngineRun>(`/runs/${runId}/weights`, {
      method: "POST",
      body: JSON.stringify(w),
    }),
  filter: (runId: string, filters: Record<string, unknown>) =>
    call<{ results: EngineCandidate[]; matched: number; filters: string[] }>(
      `/runs/${runId}/filter`,
      { method: "POST", body: JSON.stringify(filters) },
    ),
  chat: (runId: string, message: string) =>
    call<EngineChatReply>(`/runs/${runId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  reportUrl: (runId: string, kind: string) =>
    `${ENGINE_URL}/runs/${runId}/report/${kind}.pdf`,

  async rankUpload(jobId: string, files: { name: string; buffer: Buffer; type?: string }[]) {
    const form = new FormData();
    for (const f of files) {
      form.append(
        "resumes",
        new Blob([new Uint8Array(f.buffer)], {
          type: f.type ?? "application/octet-stream",
        }),
        f.name,
      );
    }
    form.append("explain_top", "3");
    return call<EngineRun>(`/jobs/${jobId}/rank/upload`, {
      method: "POST",
      body: form,
    });
  },
};

/* -------------------------------------------------------------------------
 * Engine response shapes (only the fields this server reads)
 * ---------------------------------------------------------------------- */
export interface EngineHealth {
  status: string;
  encoder: string;
  default_weights: Record<string, number>;
}

export interface BiasAudit {
  flag_count: number;
  high_severity: number;
  summary: string;
  flags: {
    category: string;
    severity: string;
    phrase: string;
    why: string;
    suggestion: string;
  }[];
}

export interface EngineJob {
  job_id: string;
  title: string;
  created_at: string;
  jd_text?: string;
  parsed: {
    title: string;
    seniority: string;
    min_years: number;
    required_skills: string[];
    preferred_skills: string[];
  };
  bias_audit: BiasAudit;
}

export interface EngineConfidence {
  score: number;
  band: string;
  reasons: string[];
}

export interface EngineFlag {
  code: string;
  severity: string;
  title: string;
  detail: string;
  evidence: string;
}

export interface EngineCandidate {
  rank: number;
  doc_id: string;
  candidate: string;
  file: string;
  email: string | null;
  score: number;
  keyword_score: number;
  semantic_score: number;
  skill_score: number;
  years_experience: number;
  education: string;
  matched_required_skills: string[];
  missing_required_skills: string[];
  matched_preferred_skills: string[];
  explanation: string;
  confidence: EngineConfidence | null;
  integrity_flags: EngineFlag[];
  flag_level: string | null;
  is_duplicate: boolean;
  duplicate_files: string[];
}

export interface EngineRun {
  run_id: string;
  job_id: string | null;
  pool_size: number;
  engine: {
    semantic_encoder: string;
    slider_weights: Record<string, number>;
    notes: string[];
    elapsed_seconds: number | null;
  };
  job_description: EngineJob["parsed"];
  ranking: EngineCandidate[];
  top_explanations: {
    rank: number;
    candidate: string;
    explanation: string;
    matched_skills: string[];
    missing_skills: string[];
  }[];
  jd_bias_audit?: BiasAudit;
  duplicate_summary?: EngineDuplicates;
  collapsed_duplicates?: number;
  failed_files?: { file: string; reason: string }[];
  movements?: { candidate: string; from: number; to: number; delta: number }[];
}

export interface EngineMatrixCell {
  skill: string;
  key: string;
  kind: string;
  status: "exact" | "related" | "semantic" | "missing";
  colour: "green" | "amber" | "red";
  symbol: "check" | "tilde" | "cross";
  evidence: string;
  reason: string;
}

export interface EngineMatrix {
  columns: { key: string; label: string; kind: string }[];
  rows: {
    rank: number;
    doc_id: string;
    candidate: string;
    score: number;
    keyword_score: number;
    semantic_score: number;
    confidence: number | null;
    flag_level: string | null;
    required_met: number;
    required_total: number;
    cells: EngineMatrixCell[];
  }[];
  pool_coverage: {
    skill: string;
    candidates_with_skill: number;
    pool_coverage_pct: number;
  }[];
  scarcest_skills: string[];
}

export interface EngineCandidateDetail {
  rank: number;
  candidate: string;
  scores: Record<string, number>;
  confidence: EngineConfidence | null;
  integrity_flags: EngineFlag[];
  required_skills: Record<string, unknown>[];
  semantic_evidence: Record<string, unknown>[];
  explanation: string;
  timeline?: EngineTimeline;
}

export interface EngineTimeline {
  entries: {
    start_label: string;
    end_label: string;
    months: number;
    kind: string;
    label: string;
  }[];
  overlaps: { overlap_months: number; fully_contained: boolean }[];
  total_work_months: number;
  calendar_span_months: number;
  flags: EngineFlag[];
}

export interface EngineTop {
  candidates: Record<string, unknown>[];
  pairwise: {
    a: string;
    b: string;
    score_gap: number;
    only_a_has: string[];
    only_b_has: string[];
    explanation: string;
  }[];
}

export interface EngineFlags {
  flagged_count: number;
  candidates: {
    rank: number;
    candidate: string;
    file: string;
    flag_level: string;
    flags: EngineFlag[];
  }[];
}

export interface EngineDuplicates {
  files: number;
  unique_candidates: number;
  duplicate_groups: number;
  files_removed_by_collapsing: number;
  groups: {
    candidate: string;
    primary_file: string;
    duplicate_files: string[];
    copies: number;
    reason: string;
  }[];
}

export interface EngineChatReply {
  intent: string;
  answer: string;
  candidates: string[];
  data: Record<string, unknown>;
  reranked: boolean;
}
