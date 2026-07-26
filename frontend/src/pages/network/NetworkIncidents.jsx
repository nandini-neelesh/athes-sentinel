import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Database,
  FileUp,
  ListChecks,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";

import {
  getNetworkIncident,
  getNetworkIncidents,
  updateNetworkIncidentStatus,
} from "../../api/network.js";
import { useNetworkDataset } from "../../context/NetworkDatasetContext.jsx";
import NetworkIncidentDetail from "./components/NetworkIncidentDetail.jsx";
import NetworkIncidentTable from "./components/NetworkIncidentTable.jsx";

const STATUS_OPTIONS = [
  { label: "All statuses", value: "" },
  { label: "Open", value: "open" },
  { label: "Investigating", value: "investigating" },
  { label: "Resolved", value: "resolved" },
  { label: "False positive", value: "false_positive" },
];

const SEVERITY_OPTIONS = [
  { label: "All severities", value: "" },
  { label: "Critical", value: "critical" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
];

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];
const COUNT_FORMATTER = new Intl.NumberFormat();

const DATASET_STATUS_STYLES = {
  uploaded: "border-blue-400/40 bg-blue-500/10 text-blue-200",
  processing: "border-amber-400/40 bg-amber-500/10 text-amber-100",
  completed: "border-green-400/40 bg-green-500/10 text-green-200",
  failed: "border-red-400/40 bg-red-500/10 text-red-200",
};

function humanizeValue(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatCount(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return COUNT_FORMATTER.format(value);
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
    return "The request timed out. Retry when the backend is available.";
  }

  if (!error?.response && error?.message) {
    return `The backend could not be reached: ${error.message}`;
  }

  return fallbackMessage;
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

function DatasetStatusBadge({ status }) {
  const normalized = String(status || "unknown").toLowerCase();

  return (
    <span
      className={[
        "inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em]",
        DATASET_STATUS_STYLES[normalized] ||
          "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]",
      ].join(" ")}
    >
      {humanizeValue(normalized)}
    </span>
  );
}

function ErrorNotice({ children, onRetry }) {
  return (
    <div
      className="flex flex-col gap-3 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-100 sm:flex-row sm:items-center sm:justify-between"
      role="alert"
    >
      <div className="flex min-w-0 items-start gap-3">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-red-300"
          aria-hidden="true"
        />
        <span className="leading-6">{children}</span>
      </div>
      {onRetry ? (
        <button
          className="shrink-0 rounded border border-red-300/40 px-3 py-1.5 text-xs font-semibold text-red-100 transition hover:border-red-200 focus:outline-none focus:ring-2 focus:ring-red-300/50"
          onClick={onRetry}
          type="button"
        >
          Retry request
        </button>
      ) : null}
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

function LifecyclePanel({ dataset }) {
  const status = dataset?.analysis_status;
  const content = {
    uploaded: {
      title: "Dataset uploaded, analysis not started",
      message:
        "The source flows are stored, but no persisted incident results exist yet. Start the frozen-model analysis from Network Overview.",
      icon: Database,
      iconClass: "text-blue-300",
      linkLabel: "Open Network Overview",
    },
    processing: {
      title: "Analysis is in progress",
      message:
        "The queue is withheld until persisted predictions and incidents are complete. Refresh the page state manually; this page will not start analysis.",
      icon: Loader2,
      iconClass: "animate-spin text-amber-300",
      linkLabel: null,
    },
    failed: {
      title: "Analysis failed",
      message:
        dataset?.analysis_error ||
        "The backend recorded a failed analysis without an additional safe error message.",
      icon: AlertTriangle,
      iconClass: "text-red-300",
      linkLabel: "Open Network Overview to retry",
    },
  }[status];

  if (!content) {
    return null;
  }

  const Icon = content.icon;

  return (
    <Panel className="p-6">
      <div className="flex items-start gap-3">
        <Icon
          className={`mt-0.5 h-5 w-5 shrink-0 ${content.iconClass}`}
          aria-hidden="true"
        />
        <div>
          <h2 className="font-semibold text-[#dce4e5]">{content.title}</h2>
          <p
            className={[
              "mt-1 text-sm leading-6",
              status === "failed" ? "text-red-100" : "text-[#849396]",
            ].join(" ")}
          >
            {content.message}
          </p>
          {content.linkLabel ? (
            <Link
              className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-[#9cf0ff] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
              to="/network"
            >
              {content.linkLabel}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          ) : null}
        </div>
      </div>
    </Panel>
  );
}

export default function NetworkIncidents() {
  const {
    datasets,
    selectedDatasetId,
    selectedDataset,
    isLoadingDatasets,
    datasetsError,
    setSelectedDatasetId,
    refreshDatasets,
  } = useNetworkDataset();
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState(null);
  const [isLoadingQueue, setIsLoadingQueue] = useState(false);
  const [queueError, setQueueError] = useState("");
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [incidentDetail, setIncidentDetail] = useState(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [updateError, setUpdateError] = useState("");
  const [updateSuccess, setUpdateSuccess] = useState("");
  const isMountedRef = useRef(false);
  const selectedDatasetIdRef = useRef(selectedDatasetId);
  const queueRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const updateInFlightRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      queueRequestRef.current += 1;
      detailRequestRef.current += 1;
    };
  }, []);

  useEffect(() => {
    selectedDatasetIdRef.current = selectedDatasetId;
  }, [selectedDatasetId]);

  const closeDetail = useCallback(() => {
    if (updateInFlightRef.current) {
      return;
    }

    detailRequestRef.current += 1;
    setSelectedIncidentId(null);
    setIncidentDetail(null);
    setDetailError("");
    setIsLoadingDetail(false);
    setUpdateError("");
    setUpdateSuccess("");
  }, []);

  useEffect(() => {
    setOffset(0);
    closeDetail();
  }, [closeDetail, selectedDatasetId]);

  const loadQueue = useCallback(
    async (datasetId, options, { clearExisting = true } = {}) => {
      if (!datasetId) {
        queueRequestRef.current += 1;
        setQueue(null);
        setQueueError("");
        setIsLoadingQueue(false);
        return null;
      }

      const requestNumber = queueRequestRef.current + 1;
      queueRequestRef.current = requestNumber;

      if (clearExisting) {
        setQueue(null);
      }

      setQueueError("");
      setIsLoadingQueue(true);

      try {
        const response = await getNetworkIncidents(datasetId, options);

        if (
          !isMountedRef.current ||
          queueRequestRef.current !== requestNumber
        ) {
          return response;
        }

        const responseItems = Array.isArray(response?.items)
          ? response.items
          : [];
        const responseTotal = Number(response?.total || 0);
        const responseLimit = Number(response?.limit || options.limit);
        const responseOffset = Number(response?.offset || 0);

        if (
          responseItems.length === 0 &&
          responseTotal > 0 &&
          responseOffset >= responseTotal
        ) {
          const lastPageOffset =
            Math.floor((responseTotal - 1) / responseLimit) * responseLimit;
          setOffset(lastPageOffset);
          return response;
        }

        setQueue({
          ...response,
          items: responseItems,
          total: responseTotal,
          limit: responseLimit,
          offset: responseOffset,
        });
        return response;
      } catch (error) {
        if (
          isMountedRef.current &&
          queueRequestRef.current === requestNumber
        ) {
          setQueueError(
            getRequestErrorMessage(
              error,
              "Could not load the persisted network incident queue."
            )
          );
        }

        return null;
      } finally {
        if (
          isMountedRef.current &&
          queueRequestRef.current === requestNumber
        ) {
          setIsLoadingQueue(false);
        }
      }
    },
    []
  );

  useEffect(() => {
    if (
      !selectedDatasetId ||
      selectedDataset?.analysis_status !== "completed"
    ) {
      queueRequestRef.current += 1;
      setQueue(null);
      setQueueError("");
      setIsLoadingQueue(false);
      return undefined;
    }

    loadQueue(
      selectedDatasetId,
      {
        limit,
        offset,
        status: statusFilter,
        severity: severityFilter,
        search: submittedSearch,
      },
      { clearExisting: true }
    );

    return () => {
      queueRequestRef.current += 1;
    };
  }, [
    limit,
    loadQueue,
    offset,
    selectedDataset?.analysis_status,
    selectedDatasetId,
    severityFilter,
    statusFilter,
    submittedSearch,
  ]);

  const loadDetail = useCallback(async (incidentId) => {
    if (!incidentId) {
      return null;
    }

    const requestNumber = detailRequestRef.current + 1;
    detailRequestRef.current = requestNumber;
    setIncidentDetail(null);
    setDetailError("");
    setUpdateError("");
    setUpdateSuccess("");
    setIsLoadingDetail(true);

    try {
      const response = await getNetworkIncident(incidentId);

      if (
        isMountedRef.current &&
        detailRequestRef.current === requestNumber
      ) {
        setIncidentDetail(response);
      }

      return response;
    } catch (error) {
      if (
        isMountedRef.current &&
        detailRequestRef.current === requestNumber
      ) {
        setDetailError(
          getRequestErrorMessage(
            error,
            "Could not load the persisted network incident detail."
          )
        );
      }

      return null;
    } finally {
      if (
        isMountedRef.current &&
        detailRequestRef.current === requestNumber
      ) {
        setIsLoadingDetail(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!selectedIncidentId) {
      return undefined;
    }

    loadDetail(selectedIncidentId);

    return () => {
      detailRequestRef.current += 1;
    };
  }, [loadDetail, selectedIncidentId]);

  const handleQueueRefresh = async () => {
    if (!selectedDatasetId || isLoadingQueue || isLoadingDatasets) {
      return;
    }

    if (selectedDataset?.analysis_status !== "completed") {
      await refreshDatasets(selectedDatasetId);
      return;
    }

    await loadQueue(
      selectedDatasetId,
      {
        limit,
        offset,
        status: statusFilter,
        severity: severityFilter,
        search: submittedSearch,
      },
      { clearExisting: false }
    );
  };

  const handleSearchSubmit = (event) => {
    event.preventDefault();
    const normalizedSearch = searchInput.trim();
    setOffset(0);
    setSubmittedSearch(normalizedSearch);
    setSearchInput(normalizedSearch);
  };

  const handleSearchClear = () => {
    setSearchInput("");
    setSubmittedSearch("");
    setOffset(0);
  };

  const handleClearFilters = () => {
    setStatusFilter("");
    setSeverityFilter("");
    setSearchInput("");
    setSubmittedSearch("");
    setOffset(0);
  };

  const handleStatusUpdate = async (nextStatus) => {
    if (
      !incidentDetail ||
      nextStatus === incidentDetail.status ||
      updateInFlightRef.current
    ) {
      return;
    }

    const incidentId = incidentDetail.incident_id;
    const datasetId = incidentDetail.dataset_id;
    updateInFlightRef.current = true;
    setIsUpdatingStatus(true);
    setUpdateError("");
    setUpdateSuccess("");

    try {
      const updatedDetail = await updateNetworkIncidentStatus(
        incidentId,
        nextStatus
      );

      if (
        !isMountedRef.current ||
        selectedDatasetIdRef.current !== datasetId
      ) {
        return;
      }

      setIncidentDetail(updatedDetail);
      setQueue((currentQueue) => {
        if (!currentQueue) {
          return currentQueue;
        }

        const stillMatchesStatus =
          !statusFilter || updatedDetail.status === statusFilter;
        const rowExists = currentQueue.items.some(
          (item) => item.incident_id === incidentId
        );

        if (!stillMatchesStatus) {
          return {
            ...currentQueue,
            items: currentQueue.items.filter(
              (item) => item.incident_id !== incidentId
            ),
            total: rowExists
              ? Math.max(0, currentQueue.total - 1)
              : currentQueue.total,
          };
        }

        return {
          ...currentQueue,
          items: currentQueue.items.map((item) =>
            item.incident_id === incidentId
              ? { ...item, status: updatedDetail.status }
              : item
          ),
        };
      });
      setUpdateSuccess(
        `Workflow status persisted as ${humanizeValue(
          updatedDetail.status
        )}.`
      );

      await loadQueue(
        datasetId,
        {
          limit,
          offset,
          status: statusFilter,
          severity: severityFilter,
          search: submittedSearch,
        },
        { clearExisting: false }
      );
    } catch (error) {
      if (
        isMountedRef.current &&
        selectedDatasetIdRef.current === datasetId
      ) {
        setUpdateError(
          getRequestErrorMessage(
            error,
            "The incident workflow status could not be updated."
          )
        );
      }
    } finally {
      updateInFlightRef.current = false;

      if (isMountedRef.current) {
        setIsUpdatingStatus(false);
      }
    }
  };

  const hasActiveFilters = Boolean(
    statusFilter || severityFilter || submittedSearch
  );
  const queueItems = Array.isArray(queue?.items) ? queue.items : [];
  const queueTotal = Number(queue?.total || 0);
  const queueOffset = Number(queue?.offset ?? offset);
  const queueLimit = Number(queue?.limit || limit);
  const firstResult = queueTotal > 0 ? queueOffset + 1 : 0;
  const lastResult =
    queueTotal > 0
      ? Math.min(queueOffset + queueItems.length, queueTotal)
      : 0;
  const currentPage =
    queueTotal > 0 ? Math.floor(queueOffset / queueLimit) + 1 : 1;
  const totalPages =
    queueTotal > 0 ? Math.ceil(queueTotal / queueLimit) : 1;
  const canGoPrevious = queueOffset > 0 && !isLoadingQueue;
  const canGoNext =
    queueOffset + queueLimit < queueTotal && !isLoadingQueue;

  if (!isLoadingDatasets && datasets.length === 0) {
    return (
      <section className="space-y-6">
        <div>
          <p className="muted-label">Persisted network findings</p>
          <h1 className="page-title mt-2">Network Incident Queue</h1>
          <p className="page-subtitle max-w-3xl">
            Review persisted binary detector findings and analyst workflow
            status without rerunning model analysis.
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
            Upload a supported NSL-KDD-compatible dataset before reviewing
            persisted incident results.
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
        <div className="min-w-0">
          <p className="muted-label">Persisted network findings</p>
          <h1 className="page-title mt-2">Network Incident Queue</h1>
          <p className="page-subtitle max-w-3xl">
            Search, filter, review, and update persisted analyst workflow status
            for binary intrusion findings.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Overview
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network/analytics"
          >
            <BarChart3 className="h-4 w-4" aria-hidden="true" />
            Analytics
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network/workflow"
          >
            <ListChecks className="h-4 w-4" aria-hidden="true" />
            Workflow
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network/upload"
          >
            <FileUp className="h-4 w-4" aria-hidden="true" />
            Upload
          </Link>
        </div>
      </div>

      <Panel>
        <PanelHeader
          icon={Database}
          title="Dataset workspace"
          description="The queue follows the independently persisted Network IDS dataset selection."
          action={
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={
                !selectedDatasetId ||
                isLoadingQueue ||
                isLoadingDatasets
              }
              onClick={handleQueueRefresh}
              type="button"
            >
              <RefreshCw
                className={[
                  "h-4 w-4",
                  isLoadingQueue || isLoadingDatasets ? "animate-spin" : "",
                ].join(" ")}
                aria-hidden="true"
              />
              {isLoadingQueue || isLoadingDatasets
                ? "Refreshing…"
                : "Refresh queue"}
            </button>
          }
        />
        <div className="space-y-4 p-5">
          <label
            className="block text-xs font-semibold uppercase tracking-[0.12em] text-[#bac9cc]"
            htmlFor="network-incident-dataset"
          >
            Network dataset
          </label>
          <select
            className="w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-3 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isLoadingDatasets || isUpdatingStatus}
            id="network-incident-dataset"
            onChange={(event) => {
              setOffset(0);
              setSelectedDatasetId(event.target.value);
            }}
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

          <div className="flex flex-wrap items-center gap-3 rounded border border-[#3b494c] bg-[#111a1b]/80 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p
                className="truncate text-sm font-semibold text-[#dce4e5]"
                title={selectedDataset?.filename}
              >
                {selectedDataset?.filename || "No dataset selected"}
              </p>
              {selectedDatasetId ? (
                <p className="mt-1 text-xs text-[#849396]">
                  Dataset ID {selectedDatasetId}
                </p>
              ) : null}
            </div>
            {selectedDataset ? (
              <DatasetStatusBadge status={selectedDataset.analysis_status} />
            ) : null}
          </div>
        </div>
      </Panel>

      {datasetsError ? <ErrorNotice>{datasetsError}</ErrorNotice> : null}

      {!selectedDatasetId ? (
        <Panel className="p-6">
          <p className="text-sm text-[#849396]">
            Select a network dataset before requesting persisted incidents.
          </p>
        </Panel>
      ) : null}

      {selectedDataset &&
      selectedDataset.analysis_status !== "completed" ? (
        <LifecyclePanel dataset={selectedDataset} />
      ) : null}

      {selectedDataset?.analysis_status === "completed" ? (
        <>
          <Panel>
            <PanelHeader
              icon={SlidersHorizontal}
              title="Queue filters"
              description="Filtering, searching, and pagination are applied by the backend to persisted fields."
              action={
                <button
                  className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!hasActiveFilters}
                  onClick={handleClearFilters}
                  type="button"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                  Clear filters
                </button>
              }
            />
            <div className="grid gap-4 p-5 xl:grid-cols-[190px_190px_minmax(280px,1fr)_150px] xl:items-end">
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#bac9cc]">
                  Workflow status
                </span>
                <select
                  className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2.5 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20"
                  onChange={(event) => {
                    setStatusFilter(event.target.value);
                    setOffset(0);
                  }}
                  value={statusFilter}
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value || "all"} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#bac9cc]">
                  Severity
                </span>
                <select
                  className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2.5 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20"
                  onChange={(event) => {
                    setSeverityFilter(event.target.value);
                    setOffset(0);
                  }}
                  value={severityFilter}
                >
                  {SEVERITY_OPTIONS.map((option) => (
                    <option key={option.value || "all"} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <form
                className="min-w-0"
                onSubmit={handleSearchSubmit}
                role="search"
              >
                <label
                  className="text-xs font-semibold uppercase tracking-[0.1em] text-[#bac9cc]"
                  htmlFor="network-incident-search"
                >
                  Search persisted fields
                </label>
                <div className="mt-1.5 flex min-w-0 items-center rounded border border-[#3b494c] bg-[#0d1516] focus-within:border-[#00e5ff] focus-within:ring-2 focus-within:ring-[#00e5ff]/20">
                  <Search
                    className="ml-3 h-4 w-4 shrink-0 text-[#849396]"
                    aria-hidden="true"
                  />
                  <input
                    className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm text-[#dce4e5] outline-none placeholder:text-[#708083]"
                    id="network-incident-search"
                    onChange={(event) => setSearchInput(event.target.value)}
                    placeholder="Type, protocol, service, flag, actual label…"
                    type="search"
                    value={searchInput}
                  />
                  {searchInput || submittedSearch ? (
                    <button
                      aria-label="Clear incident search"
                      className="mr-1 rounded p-2 text-[#849396] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                      onClick={handleSearchClear}
                      type="button"
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                  ) : null}
                  <button
                    className="m-1 inline-flex items-center gap-2 rounded border border-[#00e5ff]/35 bg-[#00e5ff]/5 px-3 py-2 text-xs font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                    type="submit"
                  >
                    Search
                  </button>
                </div>
              </form>

              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#bac9cc]">
                  Page size
                </span>
                <select
                  className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2.5 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20"
                  onChange={(event) => {
                    setLimit(Number(event.target.value));
                    setOffset(0);
                  }}
                  value={limit}
                >
                  {PAGE_SIZE_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value} per page
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {submittedSearch ? (
              <div className="border-t border-[#3b494c] px-5 py-3 text-xs text-[#849396]">
                Active search:{" "}
                <span className="font-semibold text-[#dce4e5]">
                  “{submittedSearch}”
                </span>
              </div>
            ) : null}
          </Panel>

          {isLoadingQueue ? (
            <LoadingNotice>
              Loading the matching persisted incident page…
            </LoadingNotice>
          ) : null}

          {queueError ? (
            <ErrorNotice
              onRetry={() =>
                loadQueue(
                  selectedDatasetId,
                  {
                    limit,
                    offset,
                    status: statusFilter,
                    severity: severityFilter,
                    search: submittedSearch,
                  },
                  { clearExisting: false }
                )
              }
            >
              {queueError}
            </ErrorNotice>
          ) : null}

          {queue && !queueError ? (
            <Panel>
              <PanelHeader
                icon={ShieldAlert}
                title="Persisted incident queue"
                description="Backend order: highest risk score, then earliest creation time, then incident ID."
                action={
                  <p
                    className="text-xs text-[#849396]"
                    aria-live="polite"
                  >
                    {queueTotal > 0
                      ? `${formatCount(firstResult)}–${formatCount(
                          lastResult
                        )} of ${formatCount(queueTotal)}`
                      : "0 matching incidents"}
                  </p>
                }
              />

              {queueItems.length > 0 ? (
                <NetworkIncidentTable
                  incidents={queueItems}
                  onView={setSelectedIncidentId}
                  selectedIncidentId={selectedIncidentId}
                />
              ) : (
                <div className="p-8 text-center">
                  <ShieldAlert
                    className="mx-auto h-9 w-9 text-[#849396]"
                    aria-hidden="true"
                  />
                  <h3 className="mt-3 text-lg font-semibold text-[#dce4e5]">
                    {hasActiveFilters
                      ? "No incidents match these filters."
                      : "No incidents were generated."}
                  </h3>
                  <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#849396]">
                    {hasActiveFilters
                      ? "Change or clear the backend filters to review other persisted incidents."
                      : "The completed analysis produced no predicted-attack incidents for this dataset."}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-3 border-t border-[#3b494c] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-[#849396]">
                  Page {formatCount(currentPage)} of{" "}
                  {formatCount(totalPages)} · {formatCount(queueTotal)} matching
                </p>
                <div className="flex gap-2">
                  <button
                    className="rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!canGoPrevious}
                    onClick={() =>
                      setOffset(Math.max(0, queueOffset - queueLimit))
                    }
                    type="button"
                  >
                    Previous
                  </button>
                  <button
                    className="rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!canGoNext}
                    onClick={() => setOffset(queueOffset + queueLimit)}
                    type="button"
                  >
                    Next
                  </button>
                </div>
              </div>
            </Panel>
          ) : null}
        </>
      ) : null}

      <NetworkIncidentDetail
        detail={incidentDetail}
        detailError={detailError}
        incidentId={selectedIncidentId}
        isLoading={isLoadingDetail}
        isUpdating={isUpdatingStatus}
        onClose={closeDetail}
        onRetry={() => loadDetail(selectedIncidentId)}
        onUpdateStatus={handleStatusUpdate}
        updateError={updateError}
        updateSuccess={updateSuccess}
      />
    </section>
  );
}
