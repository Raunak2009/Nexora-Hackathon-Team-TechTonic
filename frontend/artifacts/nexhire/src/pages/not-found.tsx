import { ArrowUpRight, Compass } from 'lucide-react';
import { Link } from 'wouter';

export default function NotFound() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[#0B1B2E] p-6 text-[#D9E6F0]">
      <div className="w-full max-w-md rounded-lg border border-[#24415C] bg-[#132A45] p-8 text-center shadow-[0_20px_60px_rgba(4,16,29,.35)]">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-md border border-[#4A9FE0]/30 bg-[#4A9FE0]/10 text-[#70C4F1]"><Compass size={22} /></div>
        <div className="mb-2 text-[10px] font-bold uppercase tracking-[.22em] text-[#4A9FE0]">NexHire / 404</div>
        <h1 className="text-[23px] font-extrabold tracking-[-.04em] text-[#E5F1F7]">This view is off the shortlist.</h1>
        <p className="mt-3 text-[12px] leading-5 text-[#89A5BA]">The page you requested is not part of this recruiting workspace.</p>
        <Link href="/" className="mx-auto mt-6 inline-flex items-center gap-2 rounded-md bg-[#4A9FE0] px-4 py-2.5 text-[11px] font-extrabold text-[#0B1B2E]" data-testid="link-return-overview">Return to overview <ArrowUpRight size={13} /></Link>
      </div>
    </div>
  );
}