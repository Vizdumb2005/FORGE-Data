import Link from "next/link";
import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function Logo({ className, size = "md" }: LogoProps) {
  const sizeClasses = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-4xl",
  };

  return (
    <Link 
      href="/" 
      className={cn(
        "flex items-center gap-2 font-sans tracking-tight hover:opacity-90 transition-opacity", 
        sizeClasses[size], 
        className
      )}
    >
      <div className="relative flex items-center justify-center">
        {/* Simple geometric logo mark */}
        <div className="h-[1.2em] w-[1.2em] bg-gradient-to-br from-forge-accent to-blue-600 rounded-md flex items-center justify-center shadow-lg shadow-forge-accent/20">
          <div className="h-[40%] w-[40%] bg-forge-bg rounded-sm" />
        </div>
      </div>
      <span className="font-bold text-foreground">
        FORGE <span className="font-normal text-muted-foreground">Data</span>
      </span>
    </Link>
  );
}
