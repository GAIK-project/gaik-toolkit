import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <Loader2 className="h-8 w-8 animate-spin text-white/70" />
      <div className="text-xs tracking-[0.35em] text-white/60 uppercase">
        Loading GAIK Toolkit
      </div>
    </div>
  );
}
