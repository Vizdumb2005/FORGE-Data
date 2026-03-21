import Link from "next/link";
import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function Logo({ className, size = "md" }: LogoProps) {
  // Size mapping for the container/text
  const sizeClasses = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-4xl",
  };

  const isCollapsed = size === "sm";

  return (
    <Link 
      href="/" 
      className={cn(
        "flex items-center gap-2 hover:opacity-90 transition-opacity select-none", 
        className
      )}
      aria-label="FORGE Data Home"
    >
      <div className={cn("font-sans font-extrabold tracking-tight flex items-baseline", sizeClasses[size])}>
        <span className="text-foreground">{isCollapsed ? "F" : "FORGE"}</span>
        <span className="text-[#FF6A00] font-bold ml-1">{isCollapsed ? "D" : "Data"}</span>
      </div>
    </Link>
  );
}
