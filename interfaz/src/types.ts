export interface Base { codigo: string; nombre: string }
export interface Finding { severidad: 'error' | 'advertencia' | 'info'; mensaje: string; n?: number }
export interface Report {
  base?: string;
  total_registros: number;
  registros_validos: number;
  registros_excluidos: number;
  puntaje: number | null;
  puntajes: Record<string, number>;
  hallazgos: Finding[];
}
export interface AuditResult { reporte: Report; descargas: Record<string, string> }
export interface Turn { speaker: string; start: number; end: number; text: string }
export interface AudioResult { turns: Turn[]; speakers: string[]; warning?: string }
export interface AudioJob {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'error';
  progress: number;
  stage: string;
  error?: string;
  result?: AudioResult | null;
  duration_seconds?: number;
}
