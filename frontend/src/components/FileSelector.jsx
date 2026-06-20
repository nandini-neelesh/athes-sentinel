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
    <div className="panel mt-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="muted-label">Selected dataset</p>
          <h2 className="mt-2 text-base font-semibold text-[#dce4e5]">
            Uploaded log file
          </h2>
          <p className="mt-1 text-sm text-[#849396]">
            Choose the active evidence set for dashboard metrics.
          </p>
        </div>

        <button
          className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff]"
          disabled={isLoadingFiles}
          onClick={loadLogFiles}
          type="button"
        >
          <RefreshCw className={isLoadingFiles ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          Refresh files
        </button>
      </div>

      {fileError ? (
        <div className="mt-4 rounded border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {fileError}
        </div>
      ) : null}

      {logFiles.length > 0 ? (
        <label className="mt-4 block">
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#849396]">
            Log file
          </span>
          <select
            className="mt-2 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm text-[#dce4e5] outline-none transition focus:border-[#00daf3]"
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
        <p className="mt-4 rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm text-[#849396]">
          No uploaded log files found yet.
        </p>
      )}
    </div>
  );
}
