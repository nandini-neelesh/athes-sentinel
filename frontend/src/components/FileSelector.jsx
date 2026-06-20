import { RefreshCw } from "lucide-react";

import { useFileContext } from "../context/FileContext.jsx";

export default function FileSelector() {
  const {
    fileError,
    isLoadingFiles,
    loadLogFiles,
    logFiles,
    selectedFileId,
    setSelectedFileId,
  } = useFileContext();

  return (
    <div className="panel mt-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="muted-label">Selected dataset</p>
          <h2 className="mt-2 text-lg font-semibold text-slate-50">
            Uploaded log file
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Choose which uploaded file should power the dashboard summary.
          </p>
        </div>

        <button
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-cyan-400 hover:text-cyan-300"
          disabled={isLoadingFiles}
          onClick={loadLogFiles}
          type="button"
        >
          <RefreshCw className={isLoadingFiles ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          Refresh files
        </button>
      </div>

      {fileError ? (
        <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {fileError}
        </div>
      ) : null}

      {logFiles.length > 0 ? (
        <label className="mt-5 block">
          <span className="text-sm font-medium text-slate-300">Log file</span>
          <select
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-50 outline-none transition focus:border-cyan-400"
            onChange={(event) => setSelectedFileId(event.target.value)}
            value={selectedFileId || ""}
          >
            {logFiles.map((file) => (
              <option key={file.id} value={file.id}>
                file_id {file.id} - {file.filename}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="mt-5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-400">
          No uploaded log files found yet.
        </p>
      )}
    </div>
  );
}
