import { useState } from "react";
import { Archive, Download, FileCode2, FileText, FileType2, Loader2, X } from "lucide-react";
import { downloadExport } from "../api";
import type { ExportFormat, ExportRequest, PdfLayout } from "../types";

interface ExportDialogProps {
  dark: boolean;
  open: boolean;
  onClose: () => void;
  jobId: string;
  defaultTitle: string;
  slidesCount: number;
}

const FORMAT_OPTIONS: {
  id: ExportFormat;
  title: string;
  subtitle: string;
  icon: typeof FileText;
}[] = [
  {
    id: "pdf",
    title: "PDF Study Document",
    subtitle: "Vector cover, clickable YouTube links, OCR & study layouts",
    icon: FileText,
  },
  {
    id: "docx",
    title: "Word Document (.DOCX)",
    subtitle: "Fully editable in MS Word, Google Docs & Apple Pages",
    icon: FileType2,
  },
  {
    id: "markdown_zip",
    title: "Markdown + PNGs (.ZIP)",
    subtitle: "Drop straight into Obsidian or Notion with embedded images",
    icon: FileCode2,
  },
  {
    id: "images_zip",
    title: "Raw HD PNGs (.ZIP)",
    subtitle: "Cleanly numbered lossless screenshots only",
    icon: Archive,
  },
];

const PDF_LAYOUTS: { id: PdfLayout; name: string; desc: string }[] = [
  { id: "study_full", name: "Full Study Mode", desc: "Large slide + spoken notes + searchable OCR" },
  { id: "cornell_notes", name: "Cornell Notes", desc: "Slide + lined margin box for iPad / print writing" },
  { id: "handout_2x1", name: "2x1 Handout", desc: "Two slides per page for compact reading" },
  { id: "grid_2x2", name: "2x2 Revision Grid", desc: "Four slides per page cheat-sheet view" },
];

export function ExportDialog({
  dark,
  open,
  onClose,
  jobId,
  defaultTitle,
  slidesCount,
}: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [pdfLayout, setPdfLayout] = useState<PdfLayout>("study_full");
  const [includeOcr, setIncludeOcr] = useState(true);
  const [includeTranscript, setIncludeTranscript] = useState(true);
  const [includeNotes, setIncludeNotes] = useState(true);
  const [includeAi, setIncludeAi] = useState(true);
  const [titleOverride, setTitleOverride] = useState(defaultTitle);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      const req: ExportRequest = {
        format,
        pdf_layout: pdfLayout,
        include_ocr: includeOcr,
        include_transcript: includeTranscript,
        include_ai_summary: includeAi,
        include_user_notes: includeNotes,
        title_override: titleOverride.trim() || null,
      };
      await downloadExport(jobId, req);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-2xl overflow-hidden rounded-2xl border shadow-2xl ${
          dark
            ? "border-slate-700 bg-slate-900 text-slate-100"
            : "border-slate-200 bg-white text-slate-900"
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-700/30 px-6 py-4">
          <div>
            <h3 className="text-lg font-bold">Export Lecture Notes</h3>
            <p className={`text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
              Packaging {slidesCount} curated screenshots into your selected format
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`rounded-lg p-1.5 ${
              dark ? "hover:bg-slate-800 text-slate-400" : "hover:bg-slate-100 text-slate-500"
            }`}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[75vh] space-y-5 overflow-y-auto p-6">
          <div>
            <label className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-indigo-400">
              Document Title
            </label>
            <input
              type="text"
              value={titleOverride}
              onChange={(e) => setTitleOverride(e.target.value)}
              className={`w-full rounded-xl border px-3.5 py-2.5 text-sm outline-none ${
                dark
                  ? "border-slate-700 bg-slate-950 text-slate-100 focus:border-indigo-500"
                  : "border-slate-300 bg-slate-50 text-slate-900 focus:border-indigo-500"
              }`}
            />
          </div>

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-indigo-400">
              Output Format
            </label>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {FORMAT_OPTIONS.map((opt) => {
                const Icon = opt.icon;
                const active = format === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setFormat(opt.id)}
                    className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                      active
                        ? dark
                          ? "border-indigo-500 bg-indigo-500/15"
                          : "border-indigo-600 bg-indigo-50"
                        : dark
                          ? "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                          : "border-slate-200 bg-slate-50 hover:border-slate-300"
                    }`}
                  >
                    <Icon
                      className={`mt-0.5 h-5 w-5 shrink-0 ${
                        active ? "text-indigo-400" : "text-slate-400"
                      }`}
                    />
                    <div>
                      <div className="text-sm font-bold">{opt.title}</div>
                      <div className={`text-[11px] ${dark ? "text-slate-400" : "text-slate-500"}`}>
                        {opt.subtitle}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {format === "pdf" && (
            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-indigo-400">
                PDF Page Layout
              </label>
              <div className="grid grid-cols-2 gap-2">
                {PDF_LAYOUTS.map((l) => {
                  const active = pdfLayout === l.id;
                  return (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => setPdfLayout(l.id)}
                      className={`rounded-xl border p-2.5 text-left transition-all ${
                        active
                          ? dark
                            ? "border-cyan-500 bg-cyan-500/15"
                            : "border-cyan-600 bg-cyan-50"
                          : dark
                            ? "border-slate-800 bg-slate-950/60"
                            : "border-slate-200 bg-slate-50"
                      }`}
                    >
                      <div className="text-xs font-bold">{l.name}</div>
                      <div className={`text-[11px] ${dark ? "text-slate-400" : "text-slate-500"}`}>
                        {l.desc}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {format !== "images_zip" && (
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["OCR Slide Text", includeOcr, setIncludeOcr],
                  ["Spoken Lecture Transcript", includeTranscript, setIncludeTranscript],
                  ["My Study Notes", includeNotes, setIncludeNotes],
                  ["AI Takeaways", includeAi, setIncludeAi],
                ] as const
              ).map(([label, checked, setter]) => (
                <label
                  key={label}
                  className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                    dark
                      ? "border-slate-800 bg-slate-950 text-slate-300"
                      : "border-slate-200 bg-slate-50 text-slate-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => setter(e.target.checked)}
                    className="accent-indigo-500"
                  />
                  {label}
                </label>
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-400">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-slate-700/30 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className={`rounded-xl px-4 py-2 text-xs font-semibold ${
              dark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-700"
            }`}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={downloading}
            onClick={handleDownload}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 px-5 py-2.5 text-xs font-bold text-white shadow-lg shadow-indigo-600/25 hover:from-indigo-500 hover:to-cyan-500 disabled:opacity-50"
          >
            {downloading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating File...
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                Download Notes
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
