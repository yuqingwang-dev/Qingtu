export default function BrandMark({ className = "" }: { className?: string }) {
  return <svg className={className} width="42" height="42" viewBox="0 0 48 48" fill="none" aria-hidden="true">
    <rect width="48" height="48" rx="15" fill="#155E53" />
    <circle cx="32" cy="15" r="5" fill="#FFC778" />
    <path d="M10 34C13 23 24 34 27 26C31 16 15 26 18 15" stroke="#FFFDF6" strokeWidth="3.5" strokeLinecap="round" />
    <path d="m13 17 5-4 4 5" stroke="#FFFDF6" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M31 34h7" stroke="#8FC4AC" strokeWidth="3" strokeLinecap="round" />
  </svg>;
}
