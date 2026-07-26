import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  FileUp,
  ListChecks,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";

import {
  analyzeNetworkDataset,
  getNetworkDashboard,
} from "../../api/network.js";
import { useNetworkDataset } from "../../context/NetworkDatasetContext.jsx";

const COUNT_FORMATTER = new Intl.NumberFormat();

const DATASET_STATUS_STYLES = {
  uploaded: "border-blue-400/40 bg-blue-500/10 text-blue-200",
  processing: "border-amber-400/40 bg-amber-500/10 text-amber-100",
  completed: "border-green-400/40 bg-green-500/10 text-green-200",
  failed: "border-red-400/40 bg-red-500/10 text-red-200",
};

const SEVERITY_STYLES = {
  critical: "border-red-400/40 bg-red-500/15 text-red-200",
  high: "border-orange-400/40 bg-orange-500/15 text-orange-200",
  medium: "border-yellow-400/40 bg-yellow-500/15 text-yellow-100",
  low: "border-blue-400/40 bg-blue-500/15 text-blue-200",
};

const WORKFLOW_STYLES = {
  open: "border-cyan-400/40 bg-cyan-500/15 text-cyan-100",
  investigating: "border-amber-400/40 bg-amber-500/15 text-amber-100",
  resolved: "border-green-400/40 bg-green-500/15 text-green-200",
  false_positive: "border-slate-500 bg-slate-700/50 text-slate-200",
};

function humanizeValue(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function humanizeSourceType(sourceType) {
  if (sourceType === "nsl_kdd_labelled") {
    return "Labelled benchmark dataset";
  }

  if (sourceType === "nsl_kdd_inference") {
    return "Inference-only dataset";
  }

  return humanizeValue(sourceType);
}

function formatCount(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return COUNT_FORMATTER.format(value);
}

function formatDate(value) {
  if (!value) {
    return "Not recorded";
  }

  const parsedDate = new Date(value);

  if (Number.isNaN(parsedDate.getTime())) {
    return String(value);
  }

  return parsedDate.toLocaleString();
}

function formatProbability(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return Number(value).toFixed(4);
}

function formatHumanPercentage(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${Number(value).toFixed(2)}%`;
}

function formatRateAsPercentage(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${(Number(value) * 100).toFixed(2)}%`;
}

function formatRiskScore(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${Number(value).toFixed(1)} / 100`;
}

function shortenVersion(value) {
  if (!value) {
    return "Not recorded";
  }

  const version = String(value);

  if (version.length <= 24) {
    return version;
  }

  return `${version.slice(0, 12)}…${version.slice(-8)}`;
}

function getRequestErrorMessage(error, fallbackMessage) {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        const message = item?.msg || item?.message;
        const location = Array.isArray(item?.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";

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

  if (error?.code === "ECONNABORTED") {
    return "The request timed out. The backend may still be processing the dataset.";
  }

  if (!error?.response && error?.message) {
    return `The backend could not be reached: ${error.message}`;
  }

  return fallbackMessage;
}

function Badge({ children, className = "" }) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em]",
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}

function DatasetStatusBadge({ status }) {
  const normalizedStatus = String(status || "unknown").toLowerCase();

  return (
    <Badge
      className={
        DATASET_STATUS_STYLES[normalizedStatus] ||
        "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]"
      }
    >
      {humanizeValue(normalizedStatus)}
    </Badge>
  );
}

function SeverityBadge({ severity }) {
  const normalizedSeverity = String(severity || "unknown").toLowerCase();

  return (
    <Badge
      className={
        SEVERITY_STYLES[normalizedSeverity] ||
        "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]"
      }
    >
      {humanizeValue(normalizedSeverity)}
    </Badge>
  );
}

function WorkflowBadge({ status }) {
  const normalizedStatus = String(status || "unknown").toLowerCase();

  return (
    <Badge
      className={
        WORKFLOW_STYLES[normalizedStatus] ||
        "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]"
      }
    >
      {humanizeValue(normalizedStatus)}
    </Badge>
  );
}

function Panel({ children, className = "" }) {
  return (
    <section
      className={[
        "rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20",
        className,
      ].join(" ")}
    >
      {children}
    </section>
  );
}

function PanelHeader({ action, description, icon: Icon, title }) {
  return (
    <div className="flex flex-col gap-3 border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex items-center gap-2">
          {Icon ? (
            <Icon className="h-4 w-4 text-[#00e5ff]" aria-hidden="true" />
          ) : null}
          <h2 className="text-sm font-semibold text-[#dce4e5]">{title}</h2>
        </div>
        {description ? (
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[#849396]">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

function MetricCard({ helper, label, value }) {
  return (
    <div className="min-w-0 rounded border border-[#3b494c] border-l-2 border-l-[#00daf3] bg-[#111a1b]/85 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-[#849396]">
        {label}
      </p>
      <p className="mt-2 break-words text-2xl font-semibold tracking-tight text-[#dce4e5]">
        {value}
      </p>
      {helper ? (
        <p className="mt-1 text-xs leading-5 text-[#708083]">{helper}</p>
      ) : null}
    </div>
  );
}

function ErrorNotice({ children }) {
  return (
    <div
      className="flex items-start gap-3 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-100"
      role="alert"
    >
      <AlertTriangle
        className="mt-0.5 h-4 w-4 shrink-0 text-red-300"
        aria-hidden="true"
      />
      <div className="min-w-0 leading-6">{children}</div>
    </div>
  );
}

function LoadingNotice({ children }) {
  return (
    <div
      className="flex items-center gap-3 rounded border border-[#00e5ff]/25 bg-[#00e5ff]/5 px-4 py-4 text-sm text-[#bac9cc]"
      role="status"
    >
      <Loader2
        className="h-4 w-4 shrink-0 animate-spin text-[#9cf0ff]"
        aria-hidden="true"
      />
      {children}
    </div>
  );
}

// The remaining temporary network pages reuse this lightweight shell until
// their dedicated implementations replace it in later phases.
export function NetworkPageScaffold({
  children,
  description,
  eyebrow,
  title,
}) {
  const {
    selectedDataset,
    isLoadingDatasets,
    datasetsError,
  } = useNetworkDataset();

  return (
    <section className="space-y-5">
      <div>
        <p className="muted-label">{eyebrow}</p>
        <h1 className="page-title mt-2">{title}</h1>
        <p className="page-subtitle max-w-3xl">{description}</p>
      </div>

      <Panel>
        <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
          <div className="flex items-center gap-2">
            <ShieldCheck
              className="h-4 w-4 text-[#00e5ff]"
              aria-hidden="true"
            />
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#dce4e5]">
              Persisted network workspace
            </h2>
          </div>
          <p className="mt-1 text-xs text-[#849396]">
            NSL-KDD network mode is connected to the authenticated persisted backend.
          </p>
        </div>

        <div className="space-y-4 p-5">
          {isLoadingDatasets ? (
            <div className="rounded border border-[#3b494c] bg-[#111a1b] px-4 py-3 text-sm text-[#bac9cc]">
              Loading uploaded network datasets...
            </div>
          ) : null}

          {datasetsError ? <ErrorNotice>{datasetsError}</ErrorNotice> : null}

          {!isLoadingDatasets && selectedDataset ? (
            <div className="flex flex-col gap-3 rounded border border-[#00e5ff]/25 bg-[#00e5ff]/5 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <Database
                  className="h-5 w-5 shrink-0 text-[#9cf0ff]"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[#849396]">
                    Selected network dataset
                  </p>
                  <p className="mt-1 truncate font-semibold text-[#dce4e5]">
                    {selectedDataset.filename}
                  </p>
                </div>
              </div>
              <DatasetStatusBadge status={selectedDataset.analysis_status} />
            </div>
          ) : null}

          {!isLoadingDatasets && !selectedDataset ? (
            <div className="rounded border border-dashed border-[#3b494c] bg-[#111a1b] px-4 py-5 text-sm text-[#849396]">
              No network datasets have been uploaded yet.
            </div>
          ) : null}

          {children}
        </div>
      </Panel>
    </section>
  );
}

export default function NetworkOverview() {
  const {
    datasets,
    selectedDatasetId,
    selectedDataset,
    isLoadingDatasets,
    datasetsError,
    setSelectedDatasetId,
    refreshDatasets,
  } = useNetworkDataset();
  const [dashboard, setDashboard] = useState(null);
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [analysisNotice, setAnalysisNotice] = useState("");
  const isMountedRef = useRef(false);
  const dashboardRequestRef = useRef(0);
  const analysisInFlightRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      dashboardRequestRef.current += 1;
    };
  }, []);

  const loadDashboard = useCallback(async (datasetId) => {
    if (!datasetId) {
      dashboardRequestRef.current += 1;
      setDashboard(null);
      setDashboardError("");
      setIsLoadingDashboard(false);
      return null;
    }

    const requestNumber = dashboardRequestRef.current + 1;
    dashboardRequestRef.current = requestNumber;
    setDashboard(null);
    setDashboardError("");
    setIsLoadingDashboard(true);

    try {
      const response = await getNetworkDashboard(datasetId);

      if (
        isMountedRef.current &&
        dashboardRequestRef.current === requestNumber
      ) {
        setDashboard(response);
      }

      return response;
    } catch (error) {
      if (
        isMountedRef.current &&
        dashboardRequestRef.current === requestNumber
      ) {
        setDashboardError(
          getRequestErrorMessage(
            error,
            "Could not load the persisted network dashboard."
          )
        );
      }

      return null;
    } finally {
      if (
        isMountedRef.current &&
        dashboardRequestRef.current === requestNumber
      ) {
        setIsLoadingDashboard(false);
      }
    }
  }, []);

  useEffect(() => {
    setAnalysisError("");
    setAnalysisNotice("");
    setDashboard(null);
    setDashboardError("");

    if (!selectedDatasetId) {
      dashboardRequestRef.current += 1;
      setIsLoadingDashboard(false);
      return undefined;
    }

    loadDashboard(selectedDatasetId);

    return () => {
      dashboardRequestRef.current += 1;
    };
  }, [loadDashboard, selectedDatasetId]);

  const handleDatasetRefresh = async () => {
    if (isLoadingDatasets || isAnalyzing) {
      return;
    }

    await refreshDatasets(selectedDatasetId);
  };

  const handleAnalysis = async () => {
    if (
      !selectedDatasetId ||
      isAnalyzing ||
      analysisInFlightRef.current
    ) {
      return;
    }

    const datasetId = selectedDatasetId;
    analysisInFlightRef.current = true;
    setIsAnalyzing(true);
    setAnalysisError("");
    setAnalysisNotice("");

    try {
      const response = await analyzeNetworkDataset(datasetId);

      if (!isMountedRef.current) {
        return;
      }

      setAnalysisNotice(
        response?.reused_existing
          ? "The backend reused the complete persisted analysis; the frozen model was not run again."
          : "Analysis completed and the persisted dashboard has been refreshed."
      );

      await refreshDatasets(datasetId);

      if (!isMountedRef.current) {
        return;
      }

      await loadDashboard(datasetId);
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }

      setAnalysisError(
        getRequestErrorMessage(
          error,
          "Intrusion analysis failed. The backend did not return a readable error."
        )
      );

      // A failed backend run persists a safe failed status after rolling back
      // child writes, so refresh both context and dashboard to show that state.
      await refreshDatasets(datasetId);

      if (!isMountedRef.current) {
        return;
      }

      await loadDashboard(datasetId);
    } finally {
      analysisInFlightRef.current = false;

      if (isMountedRef.current) {
        setIsAnalyzing(false);
      }
    }
  };

  const datasetInfo = dashboard?.dataset || null;
  const analysisStatus =
    datasetInfo?.analysis_status ||
    selectedDataset?.analysis_status ||
    "uploaded";
  const isCompleted = analysisStatus === "completed";
  const hasPersistedPredictions =
    isCompleted && (dashboard?.prediction_kpis?.total_predictions ?? 0) > 0;
  const priorityIncidents = Array.isArray(dashboard?.priority_incidents)
    ? dashboard.priority_incidents.slice(0, 5)
    : [];

  if (!isLoadingDatasets && datasets.length === 0) {
    return (
      <section className="space-y-6">
        <div>
          <p className="muted-label">Network IDS workspace</p>
          <h1 className="page-title mt-2">Network Intrusion Overview</h1>
          <p className="page-subtitle max-w-3xl">
            Review uploaded NSL-KDD-compatible network datasets and explicitly
            run the frozen binary intrusion detector.
          </p>
        </div>

        {datasetsError ? <ErrorNotice>{datasetsError}</ErrorNotice> : null}

        <Panel className="p-8 text-center">
          <Database
            className="mx-auto h-10 w-10 text-[#00e5ff]"
            aria-hidden="true"
          />
          <h2 className="mt-4 text-xl font-semibold text-[#dce4e5]">
            No network datasets have been uploaded yet.
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#849396]">
            Upload a supported NSL-KDD-compatible TXT or CSV file before
            reviewing persisted flow data or starting analysis.
          </p>
          <Link
            className="mt-5 inline-flex items-center gap-2 rounded border border-[#00e5ff]/50 bg-[#00e5ff]/10 px-4 py-2.5 text-sm font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network/upload"
          >
            <FileUp className="h-4 w-4" aria-hidden="true" />
            Upload Network Dataset
          </Link>
        </Panel>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="muted-label">Network IDS workspace</p>
          <h1 className="page-title mt-2">Network Intrusion Overview</h1>
          <p className="page-subtitle max-w-3xl">
            Select a persisted NSL-KDD-compatible dataset, review its lifecycle,
            and explicitly run the frozen binary intrusion detector.
          </p>
        </div>
        <Link
          className="inline-flex w-fit items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-4 py-2.5 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
          to="/network/upload"
        >
          <FileUp className="h-4 w-4" aria-hidden="true" />
          Upload Dataset
        </Link>
      </div>

      <Panel>
        <PanelHeader
          icon={Database}
          title="Dataset workspace"
          description="Selection is stored independently from the application-log workspace."
          action={
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isLoadingDatasets || isAnalyzing}
              onClick={handleDatasetRefresh}
              type="button"
            >
              <RefreshCw
                className={[
                  "h-4 w-4",
                  isLoadingDatasets ? "animate-spin" : "",
                ].join(" ")}
                aria-hidden="true"
              />
              {isLoadingDatasets ? "Refreshing…" : "Refresh datasets"}
            </button>
          }
        />
        <div className="space-y-4 p-5">
          <label
            className="block text-xs font-semibold uppercase tracking-[0.12em] text-[#bac9cc]"
            htmlFor="network-dataset-selector"
          >
            Selected network dataset
          </label>
          <select
            className="w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-3 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isLoadingDatasets || isAnalyzing}
            id="network-dataset-selector"
            onChange={(event) => setSelectedDatasetId(event.target.value)}
            value={selectedDatasetId ?? ""}
          >
            <option value="" disabled>
              Select an uploaded dataset
            </option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.filename} · ID {dataset.id} ·{" "}
                {humanizeValue(dataset.analysis_status)}
              </option>
            ))}
          </select>

          {datasetsError ? <ErrorNotice>{datasetsError}</ErrorNotice> : null}
        </div>
      </Panel>

      {!selectedDatasetId ? (
        <Panel className="p-6">
          <p className="text-sm text-[#849396]">
            Select a dataset to load its persisted dashboard. No analysis will
            start automatically.
          </p>
        </Panel>
      ) : null}

      {isLoadingDashboard ? (
        <LoadingNotice>
          Loading the selected dataset&apos;s persisted dashboard…
        </LoadingNotice>
      ) : null}

      {dashboardError ? (
        <ErrorNotice>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{dashboardError}</span>
            <button
              className="shrink-0 rounded border border-red-300/40 px-3 py-1.5 text-xs font-semibold text-red-100 transition hover:border-red-200 focus:outline-none focus:ring-2 focus:ring-red-300/50"
              onClick={() => loadDashboard(selectedDatasetId)}
              type="button"
            >
              Retry dashboard
            </button>
          </div>
        </ErrorNotice>
      ) : null}

      {datasetInfo ? (
        <Panel>
          <PanelHeader
            icon={Database}
            title="Dataset and lifecycle"
            description="Persisted source metadata and the current analysis state."
            action={<DatasetStatusBadge status={datasetInfo.analysis_status} />}
          />
          <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
            <div className="min-w-0 sm:col-span-2">
              <p className="muted-label">Filename</p>
              <p
                className="mt-1 break-all text-sm font-semibold text-[#dce4e5]"
                title={datasetInfo.filename}
              >
                {datasetInfo.filename}
              </p>
            </div>
            <div>
              <p className="muted-label">Dataset ID</p>
              <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                {datasetInfo.dataset_id}
              </p>
            </div>
            <div>
              <p className="muted-label">Total flows</p>
              <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                {formatCount(datasetInfo.total_flows)}
              </p>
            </div>
            <div>
              <p className="muted-label">Source type</p>
              <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                {humanizeSourceType(datasetInfo.source_type)}
              </p>
            </div>
            <div>
              <p className="muted-label">Ground truth</p>
              <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                {datasetInfo.has_ground_truth ? "Available" : "Not supplied"}
              </p>
            </div>
            <div>
              <p className="muted-label">Uploaded</p>
              <p className="mt-1 text-sm text-[#bac9cc]">
                {formatDate(datasetInfo.uploaded_at)}
              </p>
            </div>
            <div>
              <p className="muted-label">Analysis started</p>
              <p className="mt-1 text-sm text-[#bac9cc]">
                {formatDate(datasetInfo.analysis_started_at)}
              </p>
            </div>
            <div>
              <p className="muted-label">Analysis completed</p>
              <p className="mt-1 text-sm text-[#bac9cc]">
                {formatDate(datasetInfo.analysis_completed_at)}
              </p>
            </div>
          </div>

          {datasetInfo.analysis_status === "failed" &&
          datasetInfo.analysis_error ? (
            <div className="px-5 pb-5">
              <ErrorNotice>
                <div>
                  <p className="font-semibold">Last analysis failed</p>
                  <p className="mt-1">{datasetInfo.analysis_error}</p>
                </div>
              </ErrorNotice>
            </div>
          ) : null}
        </Panel>
      ) : null}

      {dashboard ? (
        <Panel>
          <PanelHeader
            icon={ShieldCheck}
            title="Frozen-model analysis"
            description="Analysis is user-initiated and uses the stored network connections in source order."
          />
          <div className="space-y-5 p-5">
            <div className="grid gap-3 text-sm leading-6 text-[#bac9cc] lg:grid-cols-2">
              <div className="rounded border border-[#3b494c] bg-[#111a1b]/80 p-4">
                <p className="font-semibold text-[#dce4e5]">
                  What this action does
                </p>
                <p className="mt-1">
                  The frozen Random Forest trained on complete KDDTrain+ assigns
                  a normal or attack classification at the fixed 0.38
                  probability threshold. Predicted attacks create persisted
                  analyst incidents.
                </p>
              </div>
              <div className="rounded border border-[#3b494c] bg-[#111a1b]/80 p-4">
                <p className="font-semibold text-[#dce4e5]">
                  What it does not do
                </p>
                <p className="mt-1">
                  It does not train, tune, or predict attack families. Supplied
                  benchmark labels are used only for evaluation, never as model
                  features. Results are signals for review, not guaranteed
                  detection or a claim of modern production coverage.
                </p>
              </div>
            </div>

            {analysisError ? <ErrorNotice>{analysisError}</ErrorNotice> : null}

            {analysisNotice ? (
              <div
                className="flex items-start gap-3 rounded border border-green-400/35 bg-green-500/10 px-4 py-3 text-sm text-green-100"
                role="status"
              >
                <CheckCircle2
                  className="mt-0.5 h-4 w-4 shrink-0 text-green-300"
                  aria-hidden="true"
                />
                {analysisNotice}
              </div>
            ) : null}

            {isAnalyzing ? (
              <LoadingNotice>
                Running frozen-model analysis and persisting predictions and
                incidents. Complete datasets may take several seconds; no
                percentage is estimated.
              </LoadingNotice>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              {analysisStatus === "uploaded" ||
              analysisStatus === "failed" ? (
                <button
                  className="inline-flex items-center gap-2 rounded border border-[#00e5ff]/50 bg-[#00e5ff]/10 px-4 py-2.5 text-sm font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isAnalyzing}
                  onClick={handleAnalysis}
                  type="button"
                >
                  {isAnalyzing ? (
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                  ) : (
                    <Play className="h-4 w-4" aria-hidden="true" />
                  )}
                  {isAnalyzing
                    ? "Analysis in progress…"
                    : analysisStatus === "failed"
                      ? "Retry Analysis"
                      : "Run Intrusion Analysis"}
                </button>
              ) : null}

              {analysisStatus === "processing" ? (
                <div className="inline-flex items-center gap-2 rounded border border-amber-400/35 bg-amber-500/10 px-4 py-2.5 text-sm font-semibold text-amber-100">
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                  Analysis is processing
                </div>
              ) : null}

              {isCompleted ? (
                <div className="flex flex-wrap items-center gap-3">
                  <span className="inline-flex items-center gap-2 text-sm text-green-200">
                    <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                    Persisted analysis is complete and reused on repeat requests.
                  </span>
                  <button
                    className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isLoadingDashboard || isAnalyzing}
                    onClick={() => loadDashboard(selectedDatasetId)}
                    type="button"
                  >
                    <RefreshCw
                      className={[
                        "h-4 w-4",
                        isLoadingDashboard ? "animate-spin" : "",
                      ].join(" ")}
                      aria-hidden="true"
                    />
                    Refresh Dashboard
                  </button>
                </div>
              ) : null}

              {analysisStatus === "processing" ? (
                <button
                  className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                  onClick={() => loadDashboard(selectedDatasetId)}
                  type="button"
                >
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Refresh status
                </button>
              ) : null}
            </div>
          </div>
        </Panel>
      ) : null}

      {hasPersistedPredictions ? (
        <>
          <Panel>
            <PanelHeader
              icon={Activity}
              title="Persisted prediction KPIs"
              description="Counts come from stored predictions. Probability values remain on the model's 0–1 scale."
            />
            <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Total predictions"
                value={formatCount(dashboard.prediction_kpis.total_predictions)}
              />
              <MetricCard
                label="Predicted normal"
                value={formatCount(dashboard.prediction_kpis.predicted_normal)}
              />
              <MetricCard
                label="Predicted attack"
                value={formatCount(dashboard.prediction_kpis.predicted_attack)}
              />
              <MetricCard
                label="Predicted attack share"
                value={formatHumanPercentage(
                  dashboard.prediction_kpis.predicted_attack_percentage
                )}
                helper="Human-facing percentage (0–100%)"
              />
              <MetricCard
                label="Minimum attack probability"
                value={formatProbability(
                  dashboard.prediction_kpis.minimum_attack_probability
                )}
                helper="Model probability (0–1)"
              />
              <MetricCard
                label="Maximum attack probability"
                value={formatProbability(
                  dashboard.prediction_kpis.maximum_attack_probability
                )}
                helper="Model probability (0–1)"
              />
              <MetricCard
                label="Mean attack probability"
                value={formatProbability(
                  dashboard.prediction_kpis.mean_attack_probability
                )}
                helper="Model probability (0–1)"
              />
            </div>
          </Panel>

          <Panel>
            <PanelHeader
              icon={ListChecks}
              title="Incident workflow"
              description="Workflow status and triage severity are separate persisted analyst views."
              action={
                <Link
                  className="inline-flex items-center gap-2 text-xs font-semibold text-[#9cf0ff] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                  to="/network/incidents"
                >
                  Open incident queue
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              }
            />
            <div className="space-y-5 p-5">
              <div>
                <p className="muted-label">Workflow status counts</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                  <MetricCard
                    label="Total incidents"
                    value={formatCount(
                      dashboard.incident_kpis.total_incidents
                    )}
                  />
                  <MetricCard
                    label="Open"
                    value={formatCount(
                      dashboard.incident_kpis.open_incidents
                    )}
                  />
                  <MetricCard
                    label="Investigating"
                    value={formatCount(
                      dashboard.incident_kpis.investigating_incidents
                    )}
                  />
                  <MetricCard
                    label="Resolved"
                    value={formatCount(
                      dashboard.incident_kpis.resolved_incidents
                    )}
                  />
                  <MetricCard
                    label="False positive"
                    value={formatCount(
                      dashboard.incident_kpis
                        .false_positive_status_incidents
                    )}
                  />
                </div>
              </div>

              <div>
                <p className="muted-label">Triage severity counts</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                  <MetricCard
                    label="Critical"
                    value={formatCount(
                      dashboard.incident_kpis.critical_incidents
                    )}
                  />
                  <MetricCard
                    label="High"
                    value={formatCount(
                      dashboard.incident_kpis.high_incidents
                    )}
                  />
                  <MetricCard
                    label="Medium"
                    value={formatCount(
                      dashboard.incident_kpis.medium_incidents
                    )}
                  />
                  <MetricCard
                    label="Low"
                    value={formatCount(
                      dashboard.incident_kpis.low_incidents
                    )}
                  />
                  <MetricCard
                    label="Highest risk score"
                    value={formatRiskScore(
                      dashboard.incident_kpis.highest_risk_score
                    )}
                    helper="Analyst-facing risk scale (0–100)"
                  />
                </div>
              </div>
            </div>
          </Panel>

          {dashboard.model ? (
            <Panel>
              <PanelHeader
                icon={ShieldCheck}
                title="Binary detector"
                description="Frozen fitted preprocessing plus Random Forest classifier."
              />
              <div className="grid gap-4 p-5 md:grid-cols-3">
                <div>
                  <p className="muted-label">Model name</p>
                  <p className="mt-1 break-words text-sm font-semibold text-[#dce4e5]">
                    {dashboard.model.model_name}
                  </p>
                </div>
                <div className="min-w-0">
                  <p className="muted-label">Artifact / model version</p>
                  <p
                    className="mt-1 break-all font-mono text-sm text-[#bac9cc]"
                    title={dashboard.model.model_version}
                  >
                    {shortenVersion(dashboard.model.model_version)}
                  </p>
                </div>
                <div>
                  <p className="muted-label">Attack threshold</p>
                  <p className="mt-1 text-sm font-semibold text-[#dce4e5]">
                    {formatProbability(
                      dashboard.model.threshold_probability
                    )}
                  </p>
                  <p className="mt-1 text-xs text-[#708083]">
                    Probability scale (0–1)
                  </p>
                </div>
              </div>
            </Panel>
          ) : null}

          {datasetInfo.has_ground_truth &&
          dashboard.benchmark_metrics ? (
            <Panel>
              <PanelHeader
                icon={BarChart3}
                title="Benchmark evaluation"
                description="Supplied labels evaluate the binary predictions; they were not used as inference features."
              />
              <div className="space-y-5 p-5">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                  <MetricCard
                    label="Actual normal"
                    value={formatCount(
                      dashboard.benchmark_metrics.actual_normal
                    )}
                  />
                  <MetricCard
                    label="Actual attack"
                    value={formatCount(
                      dashboard.benchmark_metrics.actual_attack
                    )}
                  />
                  <MetricCard
                    label="True negatives"
                    value={formatCount(
                      dashboard.benchmark_metrics.true_negatives
                    )}
                  />
                  <MetricCard
                    label="False positives"
                    value={formatCount(
                      dashboard.benchmark_metrics.false_positives
                    )}
                  />
                  <MetricCard
                    label="False negatives"
                    value={formatCount(
                      dashboard.benchmark_metrics.false_negatives
                    )}
                  />
                  <MetricCard
                    label="True positives"
                    value={formatCount(
                      dashboard.benchmark_metrics.true_positives
                    )}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {[
                    ["Accuracy", "accuracy"],
                    ["Precision", "precision"],
                    ["Recall", "recall"],
                    ["F1 score", "f1"],
                    ["F2 score", "f2"],
                    ["False-positive rate", "false_positive_rate"],
                    ["False-negative rate", "false_negative_rate"],
                  ].map(([label, key]) => (
                    <MetricCard
                      helper="Backend metric formatted as a percentage"
                      key={key}
                      label={label}
                      value={formatRateAsPercentage(
                        dashboard.benchmark_metrics[key]
                      )}
                    />
                  ))}
                </div>
              </div>
            </Panel>
          ) : datasetInfo.has_ground_truth ? (
            <Panel className="p-5">
              <p className="text-sm text-[#849396]">
                This labelled dataset does not currently have persisted
                benchmark metrics to display.
              </p>
            </Panel>
          ) : (
            <Panel className="p-5">
              <p className="text-sm text-[#849396]">
                No benchmark labels were supplied with this inference-only
                dataset, so evaluation metrics are not available.
              </p>
            </Panel>
          )}

          <Panel>
            <PanelHeader
              icon={AlertTriangle}
              title="Priority incidents"
              description="Up to five persisted incidents, ordered by risk score by the backend."
              action={
                <Link
                  className="inline-flex items-center gap-2 text-xs font-semibold text-[#9cf0ff] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                  to="/network/incidents"
                >
                  View complete queue
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              }
            />
            <div className="space-y-3 p-5">
              {priorityIncidents.length > 0 ? (
                priorityIncidents.map((incident) => (
                  <article
                    className="rounded border border-[#3b494c] bg-[#111a1b]/85 p-4"
                    key={incident.incident_id}
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-[#dce4e5]">
                            Incident #{incident.incident_id}
                          </p>
                          <SeverityBadge severity={incident.severity} />
                          <WorkflowBadge status={incident.status} />
                        </div>
                        <p className="mt-2 text-xs text-[#849396]">
                          Flow row {formatCount(incident.row_number)} ·{" "}
                          {incident.protocol_type || "Unknown protocol"} ·{" "}
                          {incident.service || "Unknown service"} ·{" "}
                          {incident.flag || "Unknown flag"}
                        </p>
                      </div>
                      <div className="shrink-0 text-left lg:text-right">
                        <p className="text-sm font-semibold text-[#dce4e5]">
                          Risk {formatRiskScore(incident.risk_score)}
                        </p>
                        <p className="mt-1 text-xs text-[#849396]">
                          Attack probability{" "}
                          {formatProbability(
                            incident.rf_attack_probability
                          )}
                        </p>
                      </div>
                    </div>
                    {incident.evidence_preview ? (
                      <p className="mt-3 line-clamp-2 text-sm leading-6 text-[#bac9cc]">
                        {incident.evidence_preview}
                      </p>
                    ) : null}
                  </article>
                ))
              ) : (
                <div className="rounded border border-dashed border-[#3b494c] bg-[#111a1b]/70 px-4 py-6 text-center">
                  <CheckCircle2
                    className="mx-auto h-7 w-7 text-green-300"
                    aria-hidden="true"
                  />
                  <p className="mt-2 text-sm font-semibold text-[#dce4e5]">
                    No predicted-attack incidents were persisted.
                  </p>
                  <p className="mt-1 text-xs text-[#849396]">
                    The completed analysis contains zero network incidents.
                  </p>
                </div>
              )}
            </div>
          </Panel>
        </>
      ) : null}

      {dashboard ? (
        <Panel>
          <PanelHeader
            icon={ArrowRight}
            title="Continue in Network IDS"
            description="Open the persisted-data workspace that matches your next task."
          />
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
            {[
              {
                description: "Add another supported network dataset.",
                icon: FileUp,
                label: "Upload",
                to: "/network/upload",
                requiresAnalysis: false,
              },
              {
                description: "Explore persisted detector distributions.",
                icon: BarChart3,
                label: "Analytics",
                to: "/network/analytics",
                requiresAnalysis: true,
              },
              {
                description: "Review persisted predicted-attack incidents.",
                icon: AlertTriangle,
                label: "Incidents",
                to: "/network/incidents",
                requiresAnalysis: true,
              },
              {
                description: "Continue analyst incident triage.",
                icon: ListChecks,
                label: "Workflow",
                to: "/network/workflow",
                requiresAnalysis: true,
              },
            ].map((item) => {
              const Icon = item.icon;
              const isDeemphasized = item.requiresAnalysis && !isCompleted;

              return (
                <Link
                  className={[
                    "group rounded border border-[#3b494c] bg-[#111a1b]/80 p-4 transition hover:border-[#00daf3] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60",
                    isDeemphasized ? "opacity-50" : "",
                  ].join(" ")}
                  key={item.to}
                  to={item.to}
                >
                  <div className="flex items-center justify-between">
                    <Icon
                      className="h-5 w-5 text-[#9cf0ff]"
                      aria-hidden="true"
                    />
                    <ArrowRight
                      className="h-4 w-4 text-[#708083] transition group-hover:translate-x-0.5 group-hover:text-[#9cf0ff]"
                      aria-hidden="true"
                    />
                  </div>
                  <p className="mt-3 text-sm font-semibold text-[#dce4e5]">
                    {item.label}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[#849396]">
                    {item.description}
                  </p>
                  {isDeemphasized ? (
                    <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-amber-200">
                      Analysis not completed
                    </p>
                  ) : null}
                </Link>
              );
            })}
          </div>
        </Panel>
      ) : null}
    </section>
  );
}
