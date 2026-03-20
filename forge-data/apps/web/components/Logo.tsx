import Link from "next/link";
import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function Logo({ className, size = "md" }: LogoProps) {
  // Map size props to pixel dimensions for the SVG
  // Original viewBox is roughly 400x150 (cropping text)
  // We want to maintain aspect ratio
  const sizeMap = {
    sm: { h: 32, w: 64 },   // h-8
    md: { h: 40, w: 80 },   // h-10
    lg: { h: 64, w: 128 },  // h-16
  };

  const { h, w } = sizeMap[size];
  const orange = "#FF6A00";

  return (
    <Link 
      href="/" 
      className={cn(
        "flex items-center gap-2 hover:opacity-90 transition-opacity", 
        className
      )}
      aria-label="FORGE Data Home"
    >
      <svg
        width={w}
        height={h}
        viewBox="0 0 250 130"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        className="text-foreground"
      >
        <g transform="translate(0,10)">
          {/* Anvil base - stylized geometric shape */}
          <path
            d="M10 110 L40 80 L120 80 L150 110 L140 115 L30 115 Z"
            fill="currentColor"
          />
          {/* Anvil top slanted plate */}
          <path
            d="M30 80 L60 50 L120 50 L140 80 Z"
            fill="currentColor"
          />

          {/* Data bars (ascending) */}
          <rect x="155" y="70" width="12" height="40" rx="1" fill={orange} />
          <rect x="172" y="55" width="12" height="55" rx="1" fill={orange} />
          <rect x="189" y="40" width="12" height="70" rx="1" fill={orange} />
          
          <g>
            <rect x="206" y="20" width="12" height="90" rx="1" fill={orange} />
            {/* Arrow head on top of tallest bar */}
            <polygon
              points="212,12 222,28 202,28"
              fill={orange}
            />
          </g>

          {/* Small spark/flame to the upper right */}
          <path
            d="M232 8 C236 2, 244 2, 248 8 C246 4, 242 6, 240 10 C238 6, 234 4, 232 8 Z"
            fill={orange}
          />
        </g>
      </svg>
      <span className={cn(
        "font-sans font-extrabold tracking-tight text-foreground", 
        size === "sm" ? "text-lg" : size === "lg" ? "text-4xl" : "text-2xl"
      )}>
        FORGE <span className="font-bold">Data</span>
      </span>
    </Link>
  );
}
