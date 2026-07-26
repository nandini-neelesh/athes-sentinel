import { useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FileText,
  Info,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { uploadNetworkDataset } from "../../api/network.js";
import { useNetworkDataset } from "../../context/NetworkDatasetContext.jsx";

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = new Set([".txt", ".csv"]);

function getFileExtension(filename) {
  const dotIndex = filename.lastIndexOf(".");

  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : "";
}

function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const kilobytes = bytes / 1024;

  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KiB`;
  }

  return `${(kilobytes / 1024).toFixed(2)} MiB`;
}

function formatCount(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function formatUploadedAt(value) {
  if (!value) {
    return "Unavailable";
  }

  const uploadedAt = new Date(value);

  if (Number.isNaN(uploadedAt.getTime())) {
    return String(value);
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(uploadedAt);
}

function humanizeSourceType(sourceType) {
  if (sourceType === "nsl_kdd_labelled") {
    return "Labelled benchmark dataset";
  }

  if (sourceType === "nsl_kdd_inference") {
    return "Inference-only dataset";
  }

  return sourceType || "Unknown source type";
}

function validateSelectedFile(file) {
  if (!file) {
    return "Choose one NSL-KDD-compatible TXT or CSV file.";
  }

  const extension = getFileExtension(file.name);

  if (!SUPPORTED_EXTENSIONS.has(extension)) {
    return "Unsupported file type. Choose a .txt or .csv file.";
  }

  if (file.size === 0) {
    return "The selected file is empty. Choose a file containing network records.";
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return "The selected file exceeds the 50 MiB upload limit.";
  }

  return "";
}

function formatUploadError(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }

        const location = Array.isArray(item?.loc)
          ? item.loc.filter((part) => part !== "body").join(" → ")
          : "";
        const message = item?.msg || item?.message;

        if (!message) {
          return null;
        }

        return location ? `${location}: ${message}` : message;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  if (detail && typeof detail === "object") {
    const message = detail.message || detail.msg;

    if (typeof message === "string") {
      return message;
    }

    return "The backend rejected the file with a structured validation error.";
  }

  return "Upload failed. Check the file and try again.";
}

function Panel({ children, eyebrow, title }) {
  return (
    <section className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
      <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
        <p className="muted-label">{eyebrow}</p>
        <h2 className="mt-1 text-base font-semibold text-[#dce4e5]">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function ResultField({ label, value }) {
  return (
    <div className="rounded border border-emerald-400/20 bg-[#0d1516]/55 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#849396]">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-semibold text-[#dce4e5]">
        {value}
      </p>
    </div>
  );
}

function DistributionGroup({ items, title }) {
  if (!items?.length) {
    return null;
  }

  return (
    <div className="rounded border border-[#3b494c] bg-[#111a1b]/80 p-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#bac9cc]">
        {title}
      </h3>
      <div className="mt-3 flex max-h-40 flex-wrap gap-2 overflow-y-auto pr-1">
        {items.map((item) => (
          <span
            className="rounded-full border border-[#3b494c] bg-[#0d1516] px-3 py-1.5 text-xs text-[#bac9cc]"
            key={item.value}
          >
            <span className="font-semibold text-[#dce4e5]">{item.value}</span>
            <span className="ml-2 text-[#9cf0ff]">
              {formatCount(item.count)}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function NetworkUpload() {
  const { refreshDatasets, setSelectedDatasetId } = useNetworkDataset();
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileError, setFileError] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef(null);
  const dragDepthRef = useRef(0);
  const uploadInFlightRef = useRef(false);
  const isUploading = uploadState === "uploading";
  const isSuccessful = uploadState === "success";
  const fileExtension = selectedFile
    ? getFileExtension(selectedFile.name)
    : "";

  function clearUploadOutcome() {
    setUploadError("");
    setUploadResult(null);
    setUploadState("idle");
  }

  function selectFile(fileList) {
    if (isUploading || isSuccessful) {
      return;
    }

    clearUploadOutcome();
    setFileError("");

    if (fileList.length !== 1) {
      setSelectedFile(null);
      setFileError("Choose exactly one TXT or CSV file.");
      setUploadState("error");
      return;
    }

    const file = fileList[0];
    const validationError = validateSelectedFile(file);

    if (validationError) {
      setSelectedFile(null);
      setFileError(validationError);
      setUploadState("error");
      return;
    }

    setSelectedFile(file);
    setUploadState("idle");
  }

  function handleFileInputChange(event) {
    selectFile(Array.from(event.target.files || []));
    event.target.value = "";
  }

  function handleDragEnter(event) {
    event.preventDefault();

    if (isUploading || isSuccessful) {
      return;
    }

    dragDepthRef.current += 1;
    setIsDragActive(true);
  }

  function handleDragOver(event) {
    event.preventDefault();

    if (event.dataTransfer) {
      event.dataTransfer.dropEffect =
        isUploading || isSuccessful ? "none" : "copy";
    }
  }

  function handleDragLeave(event) {
    event.preventDefault();
    dragDepthRef.current = Math.max(dragDepthRef.current - 1, 0);

    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDragActive(false);

    if (isUploading || isSuccessful) {
      return;
    }

    selectFile(Array.from(event.dataTransfer.files || []));
  }

  function resetForm() {
    if (isUploading) {
      return;
    }

    setSelectedFile(null);
    setFileError("");
    setUploadError("");
    setUploadResult(null);
    setUploadState("idle");
    setIsDragActive(false);
    dragDepthRef.current = 0;

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleUpload() {
    if (
      !selectedFile ||
      isUploading ||
      isSuccessful ||
      uploadInFlightRef.current
    ) {
      return;
    }

    const validationError = validateSelectedFile(selectedFile);

    if (validationError) {
      setFileError(validationError);
      setUploadState("error");
      return;
    }

    uploadInFlightRef.current = true;
    setFileError("");
    setUploadError("");
    setUploadState("uploading");

    try {
      const result = await uploadNetworkDataset(selectedFile);

      setUploadResult(result);
      setUploadState("success");
      await refreshDatasets(result.id);
      setSelectedDatasetId(result.id, result);
    } catch (error) {
      setUploadError(formatUploadError(error));
      setUploadState("error");
    } finally {
      uploadInFlightRef.current = false;
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <p className="muted-label">Network IDS ingestion</p>
        <h1 className="page-title mt-2">Upload Network Dataset</h1>
        <p className="page-subtitle max-w-3xl">
          Upload NSL-KDD-compatible network connection records for intrusion
          classification. Validation and persistence happen before any model
          analysis.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel eyebrow="Upload area" title="Choose one network dataset">
            <div className="p-5">
              <div
                className={[
                  "rounded-md border-2 border-dashed bg-[#0d1516]/70 px-6 py-10 text-center transition",
                  isDragActive
                    ? "border-[#00e5ff] bg-[#00e5ff]/10"
                    : "border-[#3b494c]",
                  isUploading || isSuccessful
                    ? "opacity-70"
                    : "hover:border-[#00daf3] hover:bg-[#00e5ff]/5",
                ].join(" ")}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
              >
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded border border-[#3b494c] bg-[#242b2d] text-[#9cf0ff]">
                  <UploadCloud className="h-7 w-7" aria-hidden="true" />
                </div>
                <p className="mt-5 text-xl font-semibold text-[#dce4e5]">
                  {isDragActive
                    ? "Drop the file to select it"
                    : "Drag a TXT or CSV file here"}
                </p>
                <p className="mt-2 text-sm text-[#849396]">
                  One UTF-8 NSL-KDD-compatible file, up to 50 MiB.
                </p>

                <label className="sr-only" htmlFor="network-dataset-file">
                  Select a network dataset file
                </label>
                <input
                  accept=".txt,.csv,text/plain,text/csv"
                  className="sr-only"
                  disabled={isUploading || isSuccessful}
                  id="network-dataset-file"
                  onChange={handleFileInputChange}
                  ref={fileInputRef}
                  type="file"
                />
                <button
                  className="mt-5 rounded border border-[#00e5ff]/40 bg-[#00e5ff]/10 px-4 py-2 text-sm font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/70 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isUploading || isSuccessful}
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                >
                  Browse files
                </button>
              </div>

              {fileError ? (
                <div
                  className="mt-4 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200"
                  role="alert"
                >
                  <p className="font-semibold">File selection error</p>
                  <p className="mt-1">{fileError}</p>
                </div>
              ) : null}

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  className="inline-flex items-center gap-2 rounded bg-[#00e5ff] px-5 py-2.5 text-sm font-semibold text-[#00363d] transition hover:bg-[#9cf0ff] focus:outline-none focus:ring-2 focus:ring-[#9cf0ff]/70 disabled:cursor-not-allowed disabled:border disabled:border-[#3b494c] disabled:bg-[#111a1b] disabled:text-[#849396]"
                  disabled={!selectedFile || isUploading || isSuccessful}
                  onClick={handleUpload}
                  type="button"
                >
                  {isUploading ? (
                    <LoaderCircle
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                  ) : (
                    <UploadCloud className="h-4 w-4" aria-hidden="true" />
                  )}
                  {isUploading
                    ? "Uploading and validating..."
                    : isSuccessful
                      ? "Upload complete"
                      : "Upload dataset"}
                </button>

                {isSuccessful ? (
                  <button
                    className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-4 py-2.5 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                    onClick={resetForm}
                    type="button"
                  >
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    Upload another file
                  </button>
                ) : null}
              </div>

              {isUploading ? (
                <div
                  className="mt-4 rounded border border-[#00e5ff]/30 bg-[#00e5ff]/10 px-4 py-3 text-sm text-[#c3f5ff]"
                  role="status"
                >
                  <p className="font-semibold">
                    Uploading the complete file and waiting for backend validation.
                  </p>
                  <p className="mt-1 text-[#bac9cc]">
                    Large official datasets may take several seconds. This is a
                    real indeterminate state; no percentage is estimated.
                  </p>
                </div>
              ) : null}

              {uploadError ? (
                <div
                  className="mt-4 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200"
                  role="alert"
                >
                  <p className="font-semibold">Upload failed</p>
                  <p className="mt-1">{uploadError}</p>
                </div>
              ) : null}
            </div>
          </Panel>

          <Panel eyebrow="Selected file" title="File details">
            <div className="p-5">
              {selectedFile ? (
                <>
                  <div className="flex flex-col gap-4 rounded border border-[#3b494c] bg-[#111a1b]/80 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 items-center gap-3">
                      <FileText
                        className="h-6 w-6 shrink-0 text-[#9cf0ff]"
                        aria-hidden="true"
                      />
                      <div className="min-w-0">
                        <p className="break-all text-sm font-semibold text-[#dce4e5]">
                          {selectedFile.name}
                        </p>
                        <p className="mt-1 text-xs text-[#849396]">
                          {fileExtension === ".txt"
                            ? "NSL-KDD text file"
                            : "CSV dataset"}{" "}
                          · {fileExtension.toUpperCase()} ·{" "}
                          {formatFileSize(selectedFile.size)}
                        </p>
                      </div>
                    </div>

                    {!isSuccessful ? (
                      <div className="flex shrink-0 gap-2">
                        <button
                          className="rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={isUploading}
                          onClick={() => fileInputRef.current?.click()}
                          type="button"
                        >
                          Change
                        </button>
                        <button
                          aria-label="Remove selected file"
                          className="inline-flex items-center gap-1 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-red-400/60 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={isUploading}
                          onClick={resetForm}
                          type="button"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                          Remove
                        </button>
                      </div>
                    ) : null}
                  </div>

                  <div className="mt-4 flex gap-3 rounded border border-[#3b494c] bg-[#0d1516]/70 px-4 py-3 text-sm leading-6 text-[#849396]">
                    <Info
                      className="mt-1 h-4 w-4 shrink-0 text-[#9cf0ff]"
                      aria-hidden="true"
                    />
                    <p>
                      The backend will determine whether this is a labelled
                      43-column dataset or a 41-column inference dataset.
                    </p>
                  </div>
                </>
              ) : (
                <p className="rounded border border-dashed border-[#3b494c] bg-[#111a1b]/80 px-4 py-5 text-sm text-[#849396]">
                  Select one supported file to review its name, format, and size.
                </p>
              )}
            </div>
          </Panel>
        </div>

        <aside>
          <Panel eyebrow="Supported formats" title="NSL-KDD-compatible input">
            <div className="space-y-4 p-5 text-sm leading-6 text-[#bac9cc]">
              <div className="flex gap-3">
                <ShieldCheck
                  className="mt-1 h-4 w-4 shrink-0 text-[#9cf0ff]"
                  aria-hidden="true"
                />
                <p>
                  Official headerless <strong>KDDTrain+.txt</strong> and{" "}
                  <strong>KDDTest+.txt</strong> files are supported.
                </p>
              </div>
              <div className="flex gap-3">
                <Database
                  className="mt-1 h-4 w-4 shrink-0 text-[#9cf0ff]"
                  aria-hidden="true"
                />
                <p>
                  Headered CSV files must contain exactly the official 41 feature
                  columns or all 43 labelled columns.
                </p>
              </div>
              <div className="rounded border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-amber-100">
                42-column partial structures, PCAP files, arbitrary firewall
                logs, and unrelated CSV schemas are not supported.
              </div>
              <p className="text-[#849396]">
                Valid records are stored as their original network-flow fields.
                The model runs only after you explicitly start analysis elsewhere.
              </p>
            </div>
          </Panel>
        </aside>
      </div>

      {uploadResult ? (
        <Panel eyebrow="Upload result" title="Dataset stored successfully">
          <div className="p-5">
            <div
              className="flex gap-3 rounded border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100"
              role="status"
            >
              <CheckCircle2
                className="h-5 w-5 shrink-0"
                aria-hidden="true"
              />
              <div>
                <p className="font-semibold">Upload and persistence completed.</p>
                <p className="mt-1 text-emerald-100/80">
                  The backend validated and stored every reported record.
                </p>
              </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <ResultField label="Dataset ID" value={`#${uploadResult.id}`} />
              <ResultField label="Filename" value={uploadResult.filename} />
              <ResultField
                label="Total records"
                value={formatCount(uploadResult.total_records)}
              />
              <ResultField
                label="Source type"
                value={humanizeSourceType(uploadResult.source_type)}
              />
              <ResultField
                label="Ground truth"
                value={uploadResult.has_ground_truth ? "Available" : "Not supplied"}
              />
              <ResultField
                label="Analysis status"
                value={uploadResult.analysis_status}
              />
              <ResultField
                label="Uploaded"
                value={formatUploadedAt(uploadResult.uploaded_at)}
              />
              <ResultField
                label="Unique services"
                value={formatCount(uploadResult.service_unique_count)}
              />
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <DistributionGroup
                items={uploadResult.protocol_distribution}
                title="Protocol distribution"
              />
              <DistributionGroup
                items={uploadResult.flag_distribution}
                title="Flag distribution"
              />
              {uploadResult.has_ground_truth ? (
                <>
                  <DistributionGroup
                    items={uploadResult.label_distribution}
                    title="Label distribution"
                  />
                  <DistributionGroup
                    items={uploadResult.attack_family_distribution}
                    title="Attack-family distribution"
                  />
                </>
              ) : null}
            </div>
          </div>
        </Panel>
      ) : null}

      {uploadResult ? (
        <section className="rounded-md border border-[#00e5ff]/30 bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
          <p className="muted-label">Next action</p>
          <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-[#dce4e5]">
                Analysis has not run yet
              </h2>
              <p className="mt-1 text-sm text-[#849396]">
                Open Network Overview to review the dataset and start analysis.
              </p>
            </div>
            <Link
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded bg-[#00e5ff] px-5 py-2.5 text-sm font-semibold text-[#00363d] transition hover:bg-[#9cf0ff] focus:outline-none focus:ring-2 focus:ring-[#9cf0ff]/70"
              to="/network"
            >
              Open Network Overview
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </section>
      ) : null}
    </section>
  );
}
