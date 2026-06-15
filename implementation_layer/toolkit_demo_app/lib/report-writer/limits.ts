function intEnv(name: string, def: number): number {
  const raw = process.env[name];
  if (!raw) return def;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : def;
}

export interface ReportWriterLimits {
  maxReports: number;
  maxTokensPerReport: number;
  maxUploadMb: number;
  maxSections: number;
  maxEvidenceChars: number;
}

/**
 * Read Report Writer abuse limits from env (with safe defaults). Read at call
 * time so container env changes take effect without a rebuild.
 */
export function getReportWriterLimits(): ReportWriterLimits {
  return {
    maxReports: intEnv("REPORT_WRITER_MAX_REPORTS", 5),
    maxTokensPerReport: intEnv("REPORT_WRITER_MAX_TOKENS_PER_REPORT", 32000),
    maxUploadMb: intEnv("REPORT_WRITER_MAX_UPLOAD_MB", 25),
    maxSections: intEnv("REPORT_WRITER_MAX_SECTIONS", 12),
    maxEvidenceChars: intEnv("REPORT_WRITER_MAX_EVIDENCE_CHARS", 200000),
  };
}
