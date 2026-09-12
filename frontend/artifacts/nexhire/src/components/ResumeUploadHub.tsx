import { useState, useRef } from 'react';
import {
  Upload, FileText, Check, Sparkles, X, Loader2,
  BriefcaseBusiness, Plus, ShieldCheck, ArrowRight
} from 'lucide-react';
import { analyzeResumeText, computeRelativeStrengthsAndWeaknesses, type CandidateProfile, type JobProfile } from '@/lib/ai-engine';

interface ResumeUploadHubProps {
  currentJob: JobProfile;
  onScreenComplete: (newCandidates: CandidateProfile[], updatedJob: JobProfile) => void;
}

export function ResumeUploadHub({ currentJob, onScreenComplete }: ResumeUploadHubProps) {
  const [jobTitle, setJobTitle] = useState(currentJob.title || 'Full-Stack Software Employee');
  const [jobDescription, setJobDescription] = useState(
    currentJob.description ||
      'Looking for an experienced software employee proficient in React, TypeScript, Node.js, REST APIs, Next.js, and cloud services (AWS/Docker).'
  );
  const [skills, setSkills] = useState<string[]>(
    currentJob.skills?.length
      ? currentJob.skills
      : ['React', 'TypeScript', 'Node.js', 'REST APIs', 'Next.js', 'Tailwind CSS', 'AWS', 'Docker']
  );
  const [newSkill, setNewSkill] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanStatusMessage, setScanStatusMessage] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addSkill = () => {
    const trimmed = newSkill.trim();
    if (trimmed && !skills.includes(trimmed)) {
      setSkills([...skills, trimmed]);
      setNewSkill('');
    }
  };

  const removeSkill = (skillToRemove: string) => {
    setSkills(skills.filter((s) => s !== skillToRemove));
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files) {
      const droppedFiles = Array.from(e.dataTransfer.files).filter((f) =>
        /\.(pdf|docx|doc|txt)$/i.test(f.name)
      );
      setFiles((prev) => [...prev, ...droppedFiles]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selected = Array.from(e.target.files);
      setFiles((prev) => [...prev, ...selected]);
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // Pre-load realistic candidate resume files for 1-click test
  const loadSampleResumes = () => {
    const sampleNames = [
      'Aarav_Mehta_Sr_Frontend_Resume.pdf',
      'Priya_Sharma_FullStack_AWS_Resume.docx',
      'Rohan_Deshmukh_UI_Engineer_Resume.pdf',
      'Ananya_Iyer_Fintech_FullStack.pdf',
      'Vikramaditya_Rao_Systems_Developer.docx',
      'Neha_Kapoor_Senior_Software_Engineer.pdf',
      'Kavita_Nair_React_NextJS_Resume.pdf',
      'Siddharth_Verma_Cloud_Backend_Resume.docx',
    ];

    const dummyFiles = sampleNames.map((name) => {
      return new File(
        [
          `Resume of candidate with skills in React, TypeScript, Node.js, AWS. Worked at Microsoft, Amazon, Swiggy, and Flipkart over 3-5 years. Built microservices and UI design systems.`
        ],
        name,
        { type: name.endsWith('.pdf') ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }
      );
    });

    setFiles(dummyFiles);
  };

  const runAiScreening = async () => {
    if (files.length === 0) return;

    setIsScanning(true);
    setScanProgress(15);
    setScanStatusMessage('Parsing uploaded resume files and extracting text...');

    await new Promise((r) => setTimeout(r, 600));
    setScanProgress(45);
    setScanStatusMessage('Extracting previous companies, years of exp, and technology stacks...');

    await new Promise((r) => setTimeout(r, 700));
    setScanProgress(75);
    setScanStatusMessage('Running multi-vector semantic scoring & relative cohort comparison...');

    // Process files into Candidate Profiles
    const parsedCandidates: CandidateProfile[] = [];

    for (const file of files) {
      let fileText = '';
      try {
        fileText = await file.text();
      } catch {
        fileText = file.name;
      }
      const candidate = analyzeResumeText(file.name, fileText, skills, jobTitle);
      parsedCandidates.push(candidate);
    }

    // Sort by overall score descending
    parsedCandidates.sort((a, b) => b.overallScore - a.overallScore);

    // Compute relative strengths and weaknesses across the cohort
    const enrichedCandidates = computeRelativeStrengthsAndWeaknesses(parsedCandidates);

    await new Promise((r) => setTimeout(r, 500));
    setScanProgress(100);
    setScanStatusMessage('AI Screening complete! Rendering ranked evidence table...');

    await new Promise((r) => setTimeout(r, 400));
    setIsScanning(false);

    const updatedJob: JobProfile = {
      ...currentJob,
      title: jobTitle,
      description: jobDescription,
      skills,
      candidateCount: enrichedCandidates.length,
      updatedAt: new Date().toISOString(),
    };

    onScreenComplete(enrichedCandidates, updatedJob);
  };

  return (
    <div className="rounded-lg border border-[#2B4E6F] bg-[#122740]/90 p-6 panel-shadow">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between border-b border-[#24415C] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#4A9FE0]/20 text-[#4A9FE0]">
              <Sparkles size={16} />
            </span>
            <h2 className="text-[17px] font-extrabold text-[#E6F2F8]">
              AI Resume Screening Hub
            </h2>
          </div>
          <p className="mt-1 text-[11px] text-[#84A2B8]">
            Enter your specific Job Description and upload candidate resumes. AI extracts previous companies, years of exp, calculates relative strengths/weaknesses, and ranks the candidates.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadSampleResumes}
            className="flex items-center gap-1.5 rounded-md border border-[#376288] bg-[#10263E] px-3 py-2 text-[11px] font-bold text-[#8CC5EB] hover:border-[#4A9FE0] hover:text-white transition-colors"
            data-testid="button-load-samples"
          >
            <Sparkles size={13} className="text-amber-400" />
            Quick Load Sample Resumes
          </button>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Left Column: Job Description Specification */}
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 flex items-center justify-between text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
              <span>Role Title</span>
              <span className="text-[9px] text-[#4A9FE0] normal-case">Target Role</span>
            </label>
            <div className="relative">
              <input
                type="text"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="e.g. Senior Frontend Software Employee"
                className="w-full rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2.5 text-[12px] font-semibold text-[#DDEBF3] outline-none focus:border-[#4A9FE0]"
                data-testid="input-hub-job-title"
              />
              <BriefcaseBusiness size={14} className="absolute right-3 top-3 text-[#5A7C96]" />
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
              Required Skills & Technologies (Evaluated by AI)
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={newSkill}
                onChange={(e) => setNewSkill(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                placeholder="Add skill (e.g. Next.js, Docker, Python)..."
                className="flex-1 rounded-md border border-[#315674] bg-[#0E2238] px-3 py-2 text-[11px] text-[#DDEBF3] outline-none focus:border-[#4A9FE0]"
                data-testid="input-hub-skill"
              />
              <button
                type="button"
                onClick={addSkill}
                className="flex items-center gap-1 rounded-md bg-[#244C69] px-3 text-[11px] font-bold text-[#C7E5F7] hover:bg-[#316489]"
                data-testid="button-hub-add-skill"
              >
                <Plus size={14} /> Add
              </button>
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {skills.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-1.5 rounded border border-[#315674] bg-[#0E2238] px-2.5 py-1 text-[10px] font-semibold text-[#9EC4DB]"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => removeSkill(skill)}
                    className="text-[#64849B] hover:text-[#F87171]"
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
              Job Description Context & Requirements
            </label>
            <textarea
              rows={3}
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder="Paste or write the full job description here..."
              className="w-full resize-none rounded-md border border-[#315674] bg-[#0E2238] p-3 text-[11px] leading-5 text-[#DDEBF3] outline-none focus:border-[#4A9FE0]"
              data-testid="textarea-hub-jd"
            />
          </div>
        </div>

        {/* Right Column: Resume Dropzone & File List */}
        <div className="flex flex-col">
          <label className="mb-1.5 flex items-center justify-between text-[10px] font-bold uppercase tracking-[.14em] text-[#7192A9]">
            <span>Upload Candidate Resumes</span>
            <span className="text-[10px] text-[#8EAABE] normal-case">
              {files.length} {files.length === 1 ? 'file' : 'files'} selected
            </span>
          </label>

          {/* Dropzone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex flex-1 flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center cursor-pointer transition-all ${
              isDragOver
                ? 'border-[#4A9FE0] bg-[#4A9FE0]/10'
                : 'border-[#2D4D6B] bg-[#0E2238]/80 hover:border-[#4A9FE0]/60 hover:bg-[#10273F]'
            }`}
            data-testid="dropzone-resumes"
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.txt"
              onChange={handleFileSelect}
              className="hidden"
            />
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#4A9FE0]/15 text-[#4A9FE0]">
              <Upload size={24} />
            </div>
            <p className="text-[13px] font-bold text-[#E2EEF5]">
              Drop candidate resumes here or <span className="text-[#4A9FE0] underline">browse files</span>
            </p>
            <p className="mt-1 text-[10px] text-[#7693A8]">
              Supports PDF, DOCX, DOC, and TXT (multi-file bulk upload)
            </p>
          </div>

          {/* Uploaded Files Chips */}
          {files.length > 0 && (
            <div className="mt-3 max-h-32 overflow-y-auto space-y-1.5 rounded-md border border-[#24415C] bg-[#0E2238] p-2.5">
              {files.map((file, i) => (
                <div
                  key={`${file.name}-${i}`}
                  className="flex items-center justify-between rounded bg-[#132A45] px-2.5 py-1.5 text-[11px] text-[#CBE1EE]"
                >
                  <div className="flex items-center gap-2 truncate pr-2">
                    <FileText size={13} className="shrink-0 text-[#4A9FE0]" />
                    <span className="truncate font-medium">{file.name}</span>
                    <span className="text-[9px] text-[#69889E] font-mono">
                      ({(file.size / 1024).toFixed(1)} KB)
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(i);
                    }}
                    className="text-[#7292A9] hover:text-[#F87171]"
                  >
                    <X size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Scanning Progress Banner */}
      {isScanning && (
        <div className="mt-5 rounded-lg border border-[#3E749F] bg-[#0F263F] p-4 animate-pulse">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-[12px] font-bold text-[#62D39D]">
              <Loader2 size={15} className="animate-spin" />
              <span>{scanStatusMessage}</span>
            </div>
            <span className="data-mono text-[12px] font-bold text-white">{scanProgress}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-[#183652]">
            <div
              className="h-full bg-gradient-to-r from-[#4A9FE0] via-[#3FB27F] to-[#62D39D] transition-all duration-300"
              style={{ width: `${scanProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Action Bar */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#24415C] pt-5">
        <div className="flex items-center gap-2 text-[11px] text-[#7896AA]">
          <ShieldCheck size={15} className="text-[#3FB27F]" />
          <span>Semantic matching, company extraction, and relative cohort scoring enabled</span>
        </div>

        <button
          type="button"
          onClick={runAiScreening}
          disabled={isScanning || files.length === 0}
          className="flex items-center gap-2 rounded-md bg-[#4A9FE0] px-5 py-2.5 text-[12px] font-extrabold text-[#0B1B2E] shadow-md hover:bg-[#68B7EE] disabled:opacity-50 transition-all"
          data-testid="button-run-screening"
        >
          {isScanning ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              AI Analyzing Resumes...
            </>
          ) : (
            <>
              <Sparkles size={15} />
              Analyze & Rank Resumes with AI ({files.length})
              <ArrowRight size={14} />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

