import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw, Upload } from "lucide-react";

import { uploadLogFile } from "../api/logs.js";
import { useFileContext } from "../context/FileContext.jsx";

const REQUIRED_COLUMNS = [
  "timestamp",
  "ip_address",
  "user_id",
  "endpoint",
  "method",
  "status_code",
  "response_time_ms",
  "event_type",
  "user_agent",
];

const PIPELINE_STEPS = [
  "Upload CSV",
  "Generate IP features",
  "Score anomalies",
  "Generate incidents",
];

function formatFileSize(bytes) {
  if (!bytes) {
    return "0 KB";
  }

  const kilobytes = bytes / 1024;

  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KB`;
  }

  return `${(kilobytes / 1024).toFixed(2)} MB`;
}

function formatUploadedAt(value) {
  if (!value) {
    return "Upload time unavailable";
  }

  return value;
}

function getUploadErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(", ");
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "Upload failed. Please check the CSV file and try again.";
}

function PanelHeader({ eyebrow, title }) {
  return (
    <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-4 py-3">
      <p className="muted-label">{eyebrow}</p>
      <h2 className="mt-1 text-base font-semibold text-[#dce4e5]">{title}</h2>
    </div>
  );
}

function PipelinePreview() {
  return (
    <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="muted-label">Ingestion pipeline</p>
          <p className="mt-1 text-sm text-[#849396]">
            Visual guide for the current security analysis flow.
          </p>
        </div>
        <span className="rounded-full border border-[#00e5ff]/30 bg-[#00e5ff]/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#9cf0ff]">
          Start here
        </span>
      </div>

      <div className="mt-5 flex flex-col gap-4 md:flex-row md:items-start">
        {PIPELINE_STEPS.map((step, index) => {
          const isCurrentStep = index === 0;
          const isLastStep = index === PIPELINE_STEPS.length - 1;

          return (
            <div className="flex flex-1 items-center" key={step}>
              <div className="flex min-w-0 flex-col items-center gap-2">
                <div
                  className={[
                    "flex h-9 w-9 items-center justify-center rounded border text-sm font-semibold",
                    isCurrentStep
                      ? "border-[#00e5ff] bg-[#00e5ff] text-[#00363d]"
                      : "border-[#3b494c] bg-[#111a1b] text-[#849396]",
                  ].join(" ")}
                >
                  {index + 1}
                </div>
                <p
                  className={[
                    "text-center text-[11px] font-semibold uppercase tracking-[0.14em]",
                    isCurrentStep ? "text-[#c3f5ff]" : "text-[#849396]",
                  ].join(" ")}
                >
                  {step}
                </p>
              </div>
              {!isLastStep ? (
                <div className="mx-3 hidden h-px flex-1 bg-[#3b494c] md:block" />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function UploadLogs() {
  const navigate = useNavigate();
  const { logFiles, loadLogFiles, setSelectedFileId, isLoadingFiles } =
    useFileContext();
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const latestFiles = [...logFiles]
    .sort((firstFile, secondFile) => secondFile.id - firstFile.id)
    .slice(0, 5);

  function handleFileChange(event) {
    const file = event.target.files?.[0] || null;

    setSelectedFile(file);
    setUploadResult(null);
    setUploadError("");
  }

  async function handleUpload() {
    if (!selectedFile) {
      return;
    }

    setIsUploading(true);
    setUploadError("");
    setUploadResult(null);

    try {
      const result = await uploadLogFile(selectedFile);

      setUploadResult(result);
      await loadLogFiles();
      setSelectedFileId(result.file_id);
    } catch (error) {
      setUploadError(getUploadErrorMessage(error));
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <p className="muted-label">CSV ingestion workspace</p>
        <h1 className="page-title mt-2">Ingest Security Logs</h1>
        <p className="page-subtitle max-w-3xl">
          Upload structured application logs to begin feature generation, anomaly
          detection, and incident analysis.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
            <PanelHeader eyebrow="Upload canvas" title="CSV application log" />

            <div className="p-5">
              <label className="flex min-h-[300px] cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-[#3b494c] bg-[#0d1516]/70 px-6 py-10 text-center transition hover:border-[#00daf3] hover:bg-[#00e5ff]/5">
                <div className="flex h-14 w-14 items-center justify-center rounded border border-[#3b494c] bg-[#242b2d] text-[#9cf0ff]">
                  <Upload className="h-7 w-7" aria-hidden="true" />
                </div>
                <span className="mt-5 text-xl font-semibold text-[#dce4e5]">
                  Drop a CSV file here or browse
                </span>
                <span className="mt-2 text-sm text-[#849396]">
                  Upload one structured application log file.
                </span>
                <input
                  className="sr-only"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileChange}
                />
              </label>

              {selectedFile ? (
                <div className="mt-4 rounded border border-[#3b494c] bg-[#111a1b]/80 p-4">
                  <p className="muted-label">Selected file</p>
                  <div className="mt-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <p className="break-all text-sm font-semibold text-[#dce4e5]">
                      {selectedFile.name}
                    </p>
                    <p className="text-sm text-[#849396]">
                      {formatFileSize(selectedFile.size)}
                    </p>
                  </div>
                </div>
              ) : null}

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleUpload}
                  disabled={!selectedFile || isUploading}
                  className="rounded bg-[#00e5ff] px-5 py-2.5 text-sm font-semibold text-[#00363d] transition hover:bg-[#9cf0ff] disabled:cursor-not-allowed disabled:border disabled:border-[#3b494c] disabled:bg-[#111a1b] disabled:text-[#849396]"
                >
                  {isUploading ? "Uploading..." : "Upload CSV"}
                </button>
              </div>

              {uploadError ? (
                <div className="mt-5 rounded border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-200">
                  {uploadError}
                </div>
              ) : null}

              {uploadResult ? (
                <div className="mt-5 rounded-md border border-emerald-400/30 bg-emerald-500/10 p-5">
                  <p className="text-sm font-semibold uppercase tracking-[0.16em] text-emerald-200">
                    Upload complete
                  </p>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    <div className="rounded border border-emerald-400/20 bg-[#0d1516]/50 p-3">
                      <p className="muted-label">Filename</p>
                      <p className="mt-1 break-all text-sm font-semibold text-[#dce4e5]">
                        {uploadResult.filename}
                      </p>
                    </div>
                    <div className="rounded border border-emerald-400/20 bg-[#0d1516]/50 p-3">
                      <p className="muted-label">File ID</p>
                      <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                        {uploadResult.file_id}
                      </p>
                    </div>
                    <div className="rounded border border-emerald-400/20 bg-[#0d1516]/50 p-3">
                      <p className="muted-label">Rows inserted</p>
                      <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                        {uploadResult.rows_inserted}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate("/")}
                    className="mt-5 rounded border border-[#00daf3]/40 px-4 py-2 text-sm font-semibold text-[#c3f5ff] transition hover:bg-[#00e5ff]/10"
                  >
                    Go to Dashboard
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          <PipelinePreview />
        </div>

        <aside className="space-y-5">
          <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
            <PanelHeader eyebrow="Requirements" title="Required log schema" />
            <div className="p-4">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                {REQUIRED_COLUMNS.map((column) => (
                  <div
                    key={column}
                    className="rounded border border-[#3b494c] bg-[#0d1516]/70 px-3 py-2"
                  >
                    <p className="text-xs font-semibold text-[#dce4e5]">
                      {column}
                    </p>
                  </div>
                ))}
              </div>
              <p className="mt-4 rounded border border-[#3b494c] bg-[#111a1b]/80 px-3 py-2 text-xs leading-5 text-[#849396]">
                Files are validated before records are stored.
              </p>
            </div>
          </div>

          <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
            <div className="flex items-center justify-between gap-3 border-b border-[#3b494c] bg-[#242b2d]/60 px-4 py-3">
              <div>
                <p className="muted-label">Recent uploads</p>
                <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                  {logFiles.length} uploaded file{logFiles.length === 1 ? "" : "s"}
                </p>
              </div>
              <button
                type="button"
                onClick={loadLogFiles}
                disabled={isLoadingFiles}
                className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCw
                  className={`h-4 w-4 ${isLoadingFiles ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                Refresh
              </button>
            </div>

            {latestFiles.length > 0 ? (
              <div className="divide-y divide-[#3b494c]">
                {latestFiles.map((file) => (
                  <div key={file.id} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <p className="break-all text-sm font-semibold text-[#dce4e5]">
                        {file.filename}
                      </p>
                      <span className="shrink-0 rounded bg-[#00e5ff]/10 px-2 py-1 text-xs font-semibold text-[#9cf0ff]">
                        #{file.id}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-[#849396]">
                      {formatUploadedAt(file.uploaded_at)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="p-4 text-sm text-[#849396]">
                No uploaded log files found yet.
              </p>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
