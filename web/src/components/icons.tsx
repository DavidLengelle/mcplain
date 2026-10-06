import type { LampId } from "@/lib/analysis";
import { cn } from "@/lib/utils";

type IconProps = { className?: string };

const STROKE = {
  fill: "none",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function LampIcon({ lamp, className }: IconProps & { lamp: LampId }) {
  const common = { viewBox: "0 0 24 24", strokeWidth: 2.2, "aria-hidden": true, className, ...STROKE };
  if (lamp === "files_read") {
    return (
      <svg {...common}>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
        <path d="M9 13h6M9 17h4" />
      </svg>
    );
  }
  if (lamp === "files_write") {
    return (
      <svg {...common}>
        <path d="M4 20h4L19 9l-4-4L4 16z" />
        <path d="M13.5 6.5l4 4" />
      </svg>
    );
  }
  if (lamp === "internet") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18" />
        <path d="M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
      </svg>
    );
  }
  if (lamp === "commands") {
    return (
      <svg {...common}>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M7 9l3 3-3 3M13 15h4" />
      </svg>
    );
  }
  if (lamp === "secrets") {
    return (
      <svg {...common}>
        <circle cx="8" cy="15" r="4" />
        <path d="M11 12l9-9M17 6l3 3M15 8l2 2" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M3 3l18 18" />
      <path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 9 6 9 6a17 17 0 0 1-3.2 3.8M6.6 7.6A17 17 0 0 0 3 12s4 6 9 6a9 9 0 0 0 4.4-1.2" />
    </svg>
  );
}

export function CheckCircleIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" strokeWidth={2.4} aria-hidden="true" className={className} {...STROKE}>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M7.5 12.5l3 3 6-6.5" />
    </svg>
  );
}

export function ArrowUpIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" strokeWidth={2.6} aria-hidden="true" className={className} {...STROKE}>
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

export function CheckIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" strokeWidth={2.6} aria-hidden="true" className={className} {...STROKE}>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

export function CircleIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" strokeWidth={2.2} aria-hidden="true" className={className} {...STROKE}>
      <circle cx="12" cy="12" r="8" />
    </svg>
  );
}

export function SpinnerIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      strokeWidth={2.6}
      aria-hidden="true"
      className={cn("animate-spin motion-reduce:animate-none", className)}
      {...STROKE}
    >
      <path d="M21 12a9 9 0 1 1-9-9" />
    </svg>
  );
}

export function ShieldIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" strokeWidth={2.2} aria-hidden="true" className={className} {...STROKE}>
      <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </svg>
  );
}
