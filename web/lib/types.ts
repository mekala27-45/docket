export type Box = [number, number, number, number];
export interface Field { value: string | number | null; confidence: number | null; reviewed?: boolean; model_confidence?: number; calibration_sentence?: string; box?: Box; trace?: {step: string; detail: string}[] }
export interface LineItem { description: string; quantity: number; unit_price: number; amount: number }
export interface Rule { id: string; name: string; status: 'pass' | 'fail' | 'not_applicable'; message: string }
export interface DocumentItem {
  id: string; type: string; vendor: string; number: string; date: string; due_date?: string; currency: string;
  subtotal: number; tax: number; total: number; po_number?: string; line_items: LineItem[];
  image?: string; source: string; split: string; defects?: string[]; created_at?: string;
  tokens?: {text: string; box: Box; confidence: number; label?: string}[];
  extraction: { fields: Record<string, Field>; line_items: LineItem[]; backend: string; ocr_engine: string };
  rules: Rule[]; status: 'needs_review' | 'auto_approved' | 'accepted' | 'rejected'; risk?: number;
}
export interface Metric {value?: number | null; estimate?: number | null; lower?: number; upper?: number; ci_low?: number; ci_high?: number; n?: number; reason?: string}
export interface Bundle {documents: DocumentItem[]; evaluation: Record<string, unknown>}
export interface Connection {url: string; token: string}
export type PageName = 'inbox' | 'review' | 'evaluation' | 'lab' | 'rules' | 'models' | 'explore' | 'report';
export const BASE = '/docket';
export const FIELD_COLORS: Record<string, string> = {vendor:'#4F46C8', date:'#B4561E', due_date:'#B4561E', total:'#0C9174', subtotal:'#0C9174', tax:'#95561F', line_items:'#2457A6', number:'#A8780A', po_number:'#A8780A', address:'#B8306E', currency:'#5E8A1A'};
export function asset(path: string) { return path.startsWith('http') || path.startsWith('blob:') || path.startsWith('data:') ? path : `${BASE}/${path.replace(/^\//, '')}`; }
export function money(value: number, currency = 'USD') { if(typeof value !== 'number' || !Number.isFinite(value))return 'Unavailable';try { return new Intl.NumberFormat('en-US', {style:'currency',currency, maximumFractionDigits: 2}).format(value); } catch {return `${value.toFixed(2)} ${currency}`;} }
export function label(value: string) {return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());}
export function pct(value: number) {return `${(value * 100).toFixed(1)}%`;}
export function lowest(doc: DocumentItem) {const values = Object.values(doc.extraction?.fields || {}).filter(f => !f.reviewed).map(f => f.confidence).filter((c):c is number=>typeof c==='number'); return values.length ? Math.min(...values) : 0;}
