import type { VerdictState } from "../shared/verdict";

/** The verdict as a day shape, the way a port hoists its warning signal: a shape
 * that still reads when the colour does not (glare, a cracked screen, colour
 * blindness). Circle safe, triangle caution, diamond unsafe, octagon blocked by
 * an official warning, dashed square no data. */
export function VerdictSign({ state, size = 104 }: { state: VerdictState; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 100 100", "aria-hidden": true };
  switch (state) {
    case "safe":
      return (
        <svg {...common}>
          <circle cx="50" cy="50" r="44" fill="#fff" />
          <path d="M29 51 L44 66 L72 36" fill="none" stroke="var(--color-safe)" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "caution":
      return (
        <svg {...common}>
          <path d="M50 7 L95 88 L5 88 Z" fill="var(--color-ink)" strokeLinejoin="round" />
          <rect x="45" y="36" width="10" height="28" rx="4" fill="var(--color-caution)" />
          <circle cx="50" cy="75" r="6" fill="var(--color-caution)" />
        </svg>
      );
    case "unsafe":
      return (
        <svg {...common}>
          <path d="M50 4 L96 50 L50 96 L4 50 Z" fill="#fff" />
          <path d="M35 35 L65 65 M65 35 L35 65" stroke="var(--color-danger)" strokeWidth="10" strokeLinecap="round" />
        </svg>
      );
    case "blocked":
      return (
        <svg {...common}>
          <path d="M31 4 H69 L96 31 V69 L69 96 H31 L4 69 V31 Z" fill="#fff" />
          <rect x="22" y="43" width="56" height="14" rx="3" fill="var(--color-blocked)" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <rect x="8" y="8" width="84" height="84" rx="6" fill="none" stroke="#fff" strokeWidth="6" strokeDasharray="12 9" />
          <text x="50" y="66" textAnchor="middle" fontSize="48" fontWeight="800" fill="#fff" fontFamily="var(--font-sans)">?</text>
        </svg>
      );
  }
}

/** Background and text colours per state. Caution is dark text on buoy yellow;
 * the rest are white on colour. */
export const SIGN_THEME: Record<VerdictState, { bg: string; fg: string; soft: string }> = {
  safe: { bg: "bg-safe", fg: "text-white", soft: "text-white/85" },
  caution: { bg: "bg-caution", fg: "text-ink", soft: "text-ink/80" },
  unsafe: { bg: "bg-danger", fg: "text-white", soft: "text-white/85" },
  blocked: { bg: "bg-blocked", fg: "text-white", soft: "text-white/85" },
  unavailable: { bg: "bg-unknown", fg: "text-white", soft: "text-white/85" },
};
