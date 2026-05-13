import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatINR(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Parse <cite:row_id> tags into segments for rendering */
export interface TextSegment {
  type: "text";
  text: string;
}
export interface CiteSegment {
  type: "cite";
  rowId: string;
}
export type Segment = TextSegment | CiteSegment;

export function parseCitations(raw: string): Segment[] {
  const CITE_RE = /<cite:([^>]+)>/g;
  const segments: Segment[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = CITE_RE.exec(raw)) !== null) {
    if (match.index > last) {
      segments.push({ type: "text", text: raw.slice(last, match.index) });
    }
    segments.push({ type: "cite", rowId: match[1] });
    last = match.index + match[0].length;
  }
  if (last < raw.length) {
    segments.push({ type: "text", text: raw.slice(last) });
  }
  return segments;
}
