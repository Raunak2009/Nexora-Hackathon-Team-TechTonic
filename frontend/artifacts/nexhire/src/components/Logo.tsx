import { Link } from 'wouter';

interface LogoProps {
  showTagline?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function NexHireIcon({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <defs>
        <linearGradient id="nexhire-cyan-blue" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="50%" stopColor="#4A9FE0" />
          <stop offset="100%" stopColor="#3B82F6" />
        </linearGradient>
        <linearGradient id="nexhire-glow" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#60A5FA" />
          <stop offset="100%" stopColor="#6366F1" />
        </linearGradient>
      </defs>
      {/* Humanoid Head */}
      <circle cx="50" cy="20" r="10" fill="url(#nexhire-cyan-blue)" />
      {/* Upper-Left to Lower-Right arm/leg */}
      <path
        d="M24 38 C28 32, 44 46, 50 52 C56 58, 72 72, 76 66 C80 60, 64 46, 50 52"
        fill="url(#nexhire-cyan-blue)"
      />
      {/* Humanoid Body / Stylized X structure */}
      <path
        d="M22 40 L38 52 L18 78 L34 78 L50 58 L66 78 L82 78 L62 52 L78 40 L62 40 L50 50 L38 40 Z"
        fill="url(#nexhire-cyan-blue)"
      />
    </svg>
  );
}

export function Logo({ showTagline = false, size = 'md', className = '' }: LogoProps) {
  const fontSizes = {
    sm: 'text-[15px]',
    md: 'text-[18px]',
    lg: 'text-[26px]',
  };

  return (
    <Link href="/" className={`group flex flex-col justify-center ${className}`} data-testid="link-brand">
      <div className="flex items-center gap-1.5">
        {/* Stylized Logo: NEXHIRE with custom humanoid X in the middle */}
        <span className={`font-black tracking-[0.14em] text-white flex items-center ${fontSizes[size]}`}>
          <span>NE</span>
          {/* Stylized Humanoid X */}
          <span className="relative inline-flex items-center justify-center mx-0.5">
            <svg
              viewBox="0 0 40 40"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className={size === 'lg' ? 'h-7 w-7' : size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'}
            >
              <defs>
                <linearGradient id="logoXGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#38BDF8" />
                  <stop offset="60%" stopColor="#4A9FE0" />
                  <stop offset="100%" stopColor="#6366F1" />
                </linearGradient>
              </defs>
              {/* Head */}
              <circle cx="20" cy="8" r="4.5" fill="url(#logoXGrad)" />
              {/* Dynamic cross legs/arms */}
              <path
                d="M8 17 L17 24 L7 37 L14 37 L20 28 L26 37 L33 37 L23 24 L32 17 L25 17 L20 22 L15 17 Z"
                fill="url(#logoXGrad)"
              />
            </svg>
          </span>
          <span>HIRE</span>
        </span>
      </div>

      {showTagline && (
        <div className="mt-1 flex items-center gap-1.5 text-[9px] font-semibold tracking-[0.12em] text-[#78A4C5]">
          <span className="h-px w-3 bg-[#4A9FE0]/50" />
          <span>Smart Employee Hiring. Powered by AI.</span>
          <span className="h-px w-3 bg-[#4A9FE0]/50" />
        </div>
      )}
    </Link>
  );
}

