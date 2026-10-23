import data from "@/content/example-report.json";

import { parseAnalysisResult, type AnalysisResult } from "./analysis";

export const EXAMPLE_REPORT_DATA: unknown = data;

export const EXAMPLE_REPORT: AnalysisResult | null = parseAnalysisResult(EXAMPLE_REPORT_DATA);
