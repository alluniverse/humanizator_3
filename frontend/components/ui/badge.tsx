import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "outline";
}

export function Badge({ children, className, variant = "default" }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variant === "outline" ? "border border-slate-200 text-slate-600" : "bg-indigo-100 text-indigo-800",
        className
      )}
    >
      {children}
    </span>
  );
}
