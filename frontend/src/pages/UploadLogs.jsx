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
    <section>
      <h1 className="page-title">Upload Logs</h1>
      <p className="page-subtitle">
        Import CSV application logs for feature generation and detection.
      </p>

      <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <div className="panel">
          <div className="flex items-start gap-4">
            <div className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-3 text-cyan-300">
              <Upload className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-slate-50">CSV upload</h2>
              <p className="mt-1 text-sm text-slate-400">
                Upload raw application logs using the backend CSV schema.
              </p>
            </div>
          </div>

          <label className="mt-6 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-600 bg-slate-950/30 px-6 py-12 text-center transition hover:border-cyan-400/70 hover:bg-cyan-400/5">
            <Upload className="h-10 w-10 text-cyan-300" aria-hidden="true" />
            <span className="mt-4 text-base font-semibold text-slate-50">
              Choose a CSV file
            </span>
            <span className="mt-2 text-sm text-slate-400">
              Use the file picker to select an application log export.
            </span>
            <input
              className="sr-only"
              type="file"
              accept=".csv,text/csv"
              onChange={handleFileChange}
            />
          </label>

          {selectedFile && (
            <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/30 p-4">
              <p className="text-sm font-medium text-slate-200">
                {selectedFile.name}
              </p>
              <p className="mt-1 text-sm text-slate-500">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleUpload}
              disabled={!selectedFile || isUploading}
              className="rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {isUploading ? "Uploading..." : "Upload CSV"}
            </button>
          </div>

          {uploadError && (
            <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
              {uploadError}
            </div>
          )}

          {uploadResult && (
            <div className="mt-5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-5">
              <p className="text-sm font-semibold uppercase tracking-wide text-emerald-300">
                Upload complete
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div>
                  <p className="text-xs uppercase text-slate-500">Filename</p>
                  <p className="mt-1 break-all text-sm font-medium text-slate-100">
                    {uploadResult.filename}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-500">File ID</p>
                  <p className="mt-1 text-sm font-medium text-slate-100">
                    {uploadResult.file_id}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-500">Rows inserted</p>
                  <p className="mt-1 text-sm font-medium text-slate-100">
                    {uploadResult.rows_inserted}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => navigate("/")}
                className="mt-5 rounded-lg border border-cyan-400/40 px-4 py-2 text-sm font-medium text-cyan-200 transition hover:border-cyan-300 hover:bg-cyan-400/10"
              >
                Go to Dashboard
              </button>
            </div>
          )}
        </div>

        <aside className="space-y-6">
          <div className="panel">
            <h2 className="text-lg font-semibold text-slate-50">Required schema</h2>
            <p className="mt-2 text-sm text-slate-400">
              CSV files must include these columns:
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {REQUIRED_COLUMNS.map((column) => (
                <span
                  key={column}
                  className="rounded-full border border-slate-700 bg-slate-950/40 px-3 py-1 text-xs text-slate-300"
                >
                  {column}
                </span>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-50">
                  Existing files
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  {logFiles.length} uploaded file{logFiles.length === 1 ? "" : "s"}
                </p>
              </div>
              <button
                type="button"
                onClick={loadLogFiles}
                disabled={isLoadingFiles}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-400 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCw
                  className={`h-4 w-4 ${isLoadingFiles ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                Refresh
              </button>
            </div>

            {latestFiles.length > 0 ? (
              <div className="mt-5 space-y-3">
                {latestFiles.map((file) => (
                  <div
                    key={file.id}
                    className="rounded-xl border border-slate-700 bg-slate-950/30 p-3"
                  >
                    <p className="text-sm font-semibold text-slate-100">
                      File #{file.id}
                    </p>
                    <p className="mt-1 break-all text-sm text-slate-400">
                      {file.filename}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-5 rounded-xl border border-slate-700 bg-slate-950/30 p-4 text-sm text-slate-400">
                No uploaded log files found yet.
              </p>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
