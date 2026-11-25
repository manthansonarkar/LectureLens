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
    title: "PDF Notes",
    subtitle: "Clean study pages, clickable YouTube timestamps & OCR",
    icon: FileText,
  },
  {
    id: "docx",
    title: "Word (.DOCX)",
    subtitle: "Editable in Microsoft Word, Google Docs & Apple Pages",
    icon: FileType2,
  },
  {
    id: "markdown_zip",
    title: "Markdown + PNGs",
    subtitle: "Ready for Notion or Obsidian with relative image links",
    icon: FileCode2,
  },
  {
    id: "images_zip",
    title: "PNG Images (.ZIP)",
    subtitle: "Numbered lossless HD screenshots only",
    icon: Archive,
  },
];

const PDF_LAYOUTS: { id: PdfLayout; name: string; desc: string }[] = [
  { id: "study_full", name: "Full Study", desc: "Large slide + captions + searchable text" },
  { id: "cornell_notes", name: "Cornell Notes", desc: "Slide + lined margin for writing" },
  { id: "handout_2x1", name: "2×1 Handout", desc: "Two slides per page" },
  { id: "grid_2x2", name: "2×2 Grid", desc: "Four slides per page" },
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-xl"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-2xl overflow-hidden rounded-[28px] ${
          dark ? "glass-dark text-white" : "glass-light text-slate-900"
        }`}
      >
        <div className="flex items-center justify-between border-b border-black/10 px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold tracking-tight">Export Notes</h3>
            <p className={`text-xs ${dark ? "text-neutral-400" : "text-slate-500"}`}>
              {slidesCount} curated screenshots ready to package
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`rounded-full p-1.5 ${
              dark ? "bg-white/10 text-neutral-300 hover:bg-white/15" : "bg-black/[0.05] text-slate-600 hover:bg-black/10"
            }`}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[75vh] space-y-5 overflow-y-auto p-6">
          <div>
            <label className={`mb-1.5 block text-xs font-semibold ${dark ? "text-neutral-300" : "text-slate-600"}`}>
              Document Title
            </label>
            <input
              type="text"
              value={titleOverride}
              onChange={(e) => setTitleOverride(e.target.value)}
              className={`w-full rounded-2xl border px-3.5 py-2.5 text-sm outline-none ${
                dark
                  ? "border-white/15 bg-black/30 text-white focus:border-[#0A84FF]"
                  : "border-black/10 bg-white/80 text-slate-900 focus:border-[#007AFF]"
              }`}
            />
          </div>

          <div>
            <label className={`mb-2 block text-xs font-semibold ${dark ? "text-neutral-300" : "text-slate-600"}`}>
              Format
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
                    className={`flex items-start gap-3 rounded-2xl p-3.5 text-left transition-all ${
                      active
                        ? dark
                          ? "bg-[#0A84FF]/20 ring-2 ring-[#0A84FF]"
                          : "bg-[#007AFF]/[0.09] ring-2 ring-[#007AFF]"
                        : dark
                          ? "glass-dark-subtle hover:bg-white/10"
                          : "glass-light-subtle hover:bg-white/85"
                    }`}
                  >
                    <Icon
                      className={`mt-0.5 h-5 w-5 shrink-0 ${
                        active ? "text-[#007AFF]" : dark ? "text-neutral-400" : "text-slate-500"
                      }`}
                    />
                    <div>
                      <div className="text-sm font-semibold">{opt.title}</div>
                      <div className={`text-[11px] ${dark ? "text-neutral-400" : "text-slate-500"}`}>
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
              <label className={`mb-2 block text-xs font-semibold ${dark ? "text-neutral-300" : "text-slate-600"}`}>
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
                      className={`rounded-2xl p-3 text-left transition-all ${
                        active
                          ? dark
                            ? "bg-[#0A84FF]/20 ring-2 ring-[#0A84FF]"
                            : "bg-[#007AFF]/[0.09] ring-2 ring-[#007AFF]"
                          : dark
                            ? "glass-dark-subtle"
                            : "glass-light-subtle"
                      }`}
                    >
                      <div className="text-xs font-semibold">{l.name}</div>
                      <div className={`text-[11px] ${dark ? "text-neutral-400" : "text-slate-500"}`}>
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
                  ["Spoken Captions", includeTranscript, setIncludeTranscript],
                  ["Personal Notes", includeNotes, setIncludeNotes],
                  ["Overview Notes", includeAi, setIncludeAi],
                ] as const
              ).map(([label, checked, setter]) => (
                <label
                  key={label}
                  className={`inline-flex cursor-pointer items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium ${
                    dark ? "glass-dark-subtle text-neutral-200" : "glass-light-subtle text-slate-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => setter(e.target.checked)}
                    className="accent-[#007AFF]"
                  />
                  {label}
                </label>
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-2xl border border-rose-500/35 bg-rose-500/10 p-3 text-xs text-rose-500">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2.5 border-t border-black/10 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className={`rounded-full px-4 py-2 text-xs font-semibold ${
              dark ? "bg-white/10 text-neutral-200 hover:bg-white/15" : "bg-black/[0.05] text-slate-700 hover:bg-black/10"
            }`}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={downloading}
            onClick={handleDownload}
            className="inline-flex items-center gap-2 rounded-full bg-[#007AFF] px-5 py-2.5 text-xs font-semibold text-white shadow-md shadow-[#007AFF]/25 hover:bg-[#0070EB] disabled:opacity-45"
          >
            {downloading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                Download File
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
