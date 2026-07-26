import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  FileUp,
  ListChecks,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
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
  getNetworkDashboard,
  getNetworkIncident,
  getNetworkIncidents,
  updateNetworkIncidentStatus,
} from "../../api/network.js";
import { useNetworkDataset } from "../../context/NetworkDatasetContext.jsx";
import NetworkIncidentDetail from "./components/NetworkIncidentDetail.jsx";
import NetworkWorkflowColumn from "./components/NetworkWorkflowColumn.jsx";

const WORKFLOW_STATUSES = [
  "open",
  "investigating",
  "resolved",
  "false_positive",
];

const SEVERITY_OPTIONS = [
  { label: "All severities", value: "" },
  { label: "Critical", value: "critical" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
];

const GROUP_LIMIT_OPTIONS = [10, 20, 50];
const COUNT_FORMATTER = new Intl.NumberFormat();

const DATASET_STATUS_STYLES = {
  uploaded: "border-blue-400/40 bg-blue-500/10 text-blue-200",
  processing: "border-amber-400/40 bg-amber-500/10 text-amber-100",
  completed: "border-green-400/40 bg-green-500/10 text-green-200",
  failed: "border-red-400/40 bg-red-500/10 text-red-200",
};

function createStatusState(value) {
  return Object.fromEntries(
    WORKFLOW_STATUSES.map((status) => [status, value])
  );
}

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

function ErrorNotice({ children, onRetry, retryLabel = "Retry request" }) {
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
          {retryLabel}
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
        "The network flows are stored, but no persisted workflow incidents exist yet. Start the frozen-model analysis from Network Overview.",
      icon: Database,
      iconClass: "text-blue-300",
      linkLabel: "Open Network Overview",
    },
    processing: {
      title: "Analysis is in progress",
      message:
        "Workflow totals and groups are withheld until persisted analysis is complete. Use the manual refresh control to read the latest lifecycle state.",
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

function WorkflowGuidance() {
  const stages = [
    {
      status: "Open",
      description: "Newly generated suspicious connection requiring review.",
    },
    {
      status: "Investigating",
      description:
        "An analyst is correlating the connection with other persisted records.",
    },
    {
      status: "Resolved",
      description:
        "Review is complete and no further action is currently needed.",
    },
    {
      status: "False positive",
      description:
        "An analyst determined that the binary model alert was not malicious.",
    },
  ];

  return (
    <Panel>
      <PanelHeader
        icon={ListChecks}
        title="Analyst workflow guidance"
        description="These statuses are persisted analyst decisions, not new ML classes."
      />
      <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
        {stages.map((stage) => (
          <div
            className="rounded border border-[#3b494c] bg-[#111a1b]/80 p-3"
            key={stage.status}
          >
            <p className="text-sm font-semibold text-[#dce4e5]">
              {stage.status}
            </p>
            <p className="mt-1 text-xs leading-5 text-[#849396]">
              {stage.description}
            </p>
          </div>
        ))}
      </div>
      <p className="border-t border-[#3b494c] px-5 py-3 text-xs leading-5 text-[#708083]">
        Changing workflow status does not retrain, tune, or alter the frozen
        detector and does not automatically block or remediate traffic.
      </p>
    </Panel>
  );
}

export default function NetworkWorkflow() {
  const {
    datasets,
    selectedDatasetId,
    selectedDataset,
    isLoadingDatasets,
    datasetsError,
    setSelectedDatasetId,
    refreshDatasets,
  } = useNetworkDataset();
  const [severityFilter, setSeverityFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [groupLimit, setGroupLimit] = useState(20);
  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [groups, setGroups] = useState({});
  const [groupErrors, setGroupErrors] = useState(
    createStatusState("")
  );
  const [groupLoading, setGroupLoading] = useState(
    createStatusState(false)
  );
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [incidentDetail, setIncidentDetail] = useState(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [updateError, setUpdateError] = useState("");
  const [updateSuccess, setUpdateSuccess] = useState("");
  const isMountedRef = useRef(false);
  const selectedDatasetIdRef = useRef(selectedDatasetId);
  const dashboardRequestRef = useRef(0);
  const groupsRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const updateInFlightRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      dashboardRequestRef.current += 1;
      groupsRequestRef.current += 1;
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
    closeDetail();
  }, [closeDetail, selectedDatasetId]);

  const loadDashboard = useCallback(
    async (datasetId, { preserveExisting = false } = {}) => {
      if (!datasetId) {
        dashboardRequestRef.current += 1;
        setDashboard(null);
        setDashboardError("");
        setIsLoadingDashboard(false);
        return null;
      }

      const requestNumber = dashboardRequestRef.current + 1;
      dashboardRequestRef.current = requestNumber;

      if (!preserveExisting) {
        setDashboard(null);
      }

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
              "Could not load persisted workflow totals."
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
    },
    []
  );

  const loadGroups = useCallback(
    async (datasetId, options, { preserveExisting = false } = {}) => {
      if (!datasetId) {
        groupsRequestRef.current += 1;
        setGroups({});
        setGroupErrors(createStatusState(""));
        setGroupLoading(createStatusState(false));
        return [];
      }

      const requestNumber = groupsRequestRef.current + 1;
      groupsRequestRef.current = requestNumber;

      if (!preserveExisting) {
        setGroups({});
      }

      setGroupErrors(createStatusState(""));
      setGroupLoading(createStatusState(true));

      const requests = WORKFLOW_STATUSES.map(async (status) => {
        try {
          const response = await getNetworkIncidents(datasetId, {
            status,
            severity: options.severity,
            search: options.search,
            limit: options.limit,
            offset: 0,
          });

          if (
            isMountedRef.current &&
            groupsRequestRef.current === requestNumber
          ) {
            setGroups((current) => ({
              ...current,
              [status]: {
                ...response,
                items: Array.isArray(response?.items) ? response.items : [],
                total: Number(response?.total || 0),
              },
            }));
          }

          return response;
        } catch (error) {
          if (
            isMountedRef.current &&
            groupsRequestRef.current === requestNumber
          ) {
            setGroupErrors((current) => ({
              ...current,
              [status]: getRequestErrorMessage(
                error,
                `Could not load ${humanizeValue(
                  status
                ).toLowerCase()} incidents.`
              ),
            }));
          }

          return null;
        } finally {
          if (
            isMountedRef.current &&
            groupsRequestRef.current === requestNumber
          ) {
            setGroupLoading((current) => ({
              ...current,
              [status]: false,
            }));
          }
        }
      });

      return Promise.allSettled(requests);
    },
    []
  );

  useEffect(() => {
    if (
      !selectedDatasetId ||
      selectedDataset?.analysis_status !== "completed"
    ) {
      dashboardRequestRef.current += 1;
      setDashboard(null);
      setDashboardError("");
      setIsLoadingDashboard(false);
      return undefined;
    }

    loadDashboard(selectedDatasetId, { preserveExisting: false });

    return () => {
      dashboardRequestRef.current += 1;
    };
  }, [
    loadDashboard,
    selectedDataset?.analysis_status,
    selectedDatasetId,
  ]);

  useEffect(() => {
    if (
      !selectedDatasetId ||
      selectedDataset?.analysis_status !== "completed"
    ) {
      groupsRequestRef.current += 1;
      setGroups({});
      setGroupErrors(createStatusState(""));
      setGroupLoading(createStatusState(false));
      return undefined;
    }

    loadGroups(
      selectedDatasetId,
      {
        severity: severityFilter,
        search: submittedSearch,
        limit: groupLimit,
      },
      { preserveExisting: false }
    );

    return () => {
      groupsRequestRef.current += 1;
    };
  }, [
    groupLimit,
    loadGroups,
    selectedDataset?.analysis_status,
    selectedDatasetId,
    severityFilter,
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

  const refreshCompletedWorkflow = useCallback(
    async (datasetId, { preserveExisting = true } = {}) => {
      return Promise.allSettled([
        loadDashboard(datasetId, { preserveExisting }),
        loadGroups(
          datasetId,
          {
            severity: severityFilter,
            search: submittedSearch,
            limit: groupLimit,
          },
          { preserveExisting }
        ),
      ]);
    },
    [
      groupLimit,
      loadDashboard,
      loadGroups,
      severityFilter,
      submittedSearch,
    ]
  );

  const handleWorkflowRefresh = async () => {
    if (
      !selectedDatasetId ||
      isLoadingDatasets ||
      isLoadingDashboard ||
      Object.values(groupLoading).some(Boolean)
    ) {
      return;
    }

    if (selectedDataset?.analysis_status !== "completed") {
      await refreshDatasets(selectedDatasetId);
      return;
    }

    await refreshCompletedWorkflow(selectedDatasetId, {
      preserveExisting: true,
    });
  };

  const handleSearchSubmit = (event) => {
    event.preventDefault();
    const normalizedSearch = searchInput.trim();
    setSubmittedSearch(normalizedSearch);
    setSearchInput(normalizedSearch);
  };

  const handleSearchClear = () => {
    setSearchInput("");
    setSubmittedSearch("");
  };

  const handleClearFilters = () => {
    setSeverityFilter("");
    setSearchInput("");
    setSubmittedSearch("");
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
      setUpdateSuccess(
        `Workflow status persisted as ${humanizeValue(
          updatedDetail.status
        )}. Refreshing dashboard totals and all four status groups…`
      );

      await refreshCompletedWorkflow(datasetId, {
        preserveExisting: true,
      });

      if (
        isMountedRef.current &&
        selectedDatasetIdRef.current === datasetId
      ) {
        setUpdateSuccess(
          `Workflow status persisted as ${humanizeValue(
            updatedDetail.status
          )}. Dashboard totals and status groups were requested again from the backend.`
        );
      }
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
    severityFilter || submittedSearch
  );
  const isAnyGroupLoading = Object.values(groupLoading).some(Boolean);
  const totalIncidents = Number(
    dashboard?.incident_kpis?.total_incidents || 0
  );
  const shouldShowBoard =
    selectedDataset?.analysis_status === "completed" &&
    (totalIncidents > 0 ||
      !dashboard ||
      WORKFLOW_STATUSES.some(
        (status) => Number(groups[status]?.total || 0) > 0
      ));

  if (!isLoadingDatasets && datasets.length === 0) {
    return (
      <section className="space-y-6">
        <div>
          <p className="muted-label">Analyst triage workspace</p>
          <h1 className="page-title mt-2">Network Analyst Workflow</h1>
          <p className="page-subtitle max-w-3xl">
            Organize persisted binary detector findings through explicit
            analyst workflow decisions.
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
            Upload a supported NSL-KDD-compatible dataset before working with
            persisted analyst incidents.
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
          <p className="muted-label">Analyst triage workspace</p>
          <h1 className="page-title mt-2">Network Analyst Workflow</h1>
          <p className="page-subtitle max-w-3xl">
            Review bounded, risk-ordered incident groups and persist explicit
            analyst workflow decisions.
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
            to="/network/incidents"
          >
            <ListChecks className="h-4 w-4" aria-hidden="true" />
            Incidents
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
          description="The workflow follows the independently persisted Network IDS dataset selection."
          action={
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={
                !selectedDatasetId ||
                isLoadingDatasets ||
                isLoadingDashboard ||
                isAnyGroupLoading
              }
              onClick={handleWorkflowRefresh}
              type="button"
            >
              <RefreshCw
                className={[
                  "h-4 w-4",
                  isLoadingDatasets ||
                  isLoadingDashboard ||
                  isAnyGroupLoading
                    ? "animate-spin"
                    : "",
                ].join(" ")}
                aria-hidden="true"
              />
              {isLoadingDatasets ||
              isLoadingDashboard ||
              isAnyGroupLoading
                ? "Refreshing…"
                : "Refresh workflow"}
            </button>
          }
        />
        <div className="space-y-4 p-5">
          <label
            className="block text-xs font-semibold uppercase tracking-[0.12em] text-[#bac9cc]"
            htmlFor="network-workflow-dataset"
          >
            Network dataset
          </label>
          <select
            className="w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-3 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isLoadingDatasets || isUpdatingStatus}
            id="network-workflow-dataset"
            onChange={(event) =>
              setSelectedDatasetId(event.target.value)
            }
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
            Select a network dataset before requesting persisted workflow data.
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
              title="Shared workflow filters"
              description="Severity and search are applied by the backend to every bounded status group."
              action={
                <button
                  className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!hasActiveFilters}
                  onClick={handleClearFilters}
                  type="button"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                  Clear all filters
                </button>
              }
            />
            <div className="grid gap-4 p-5 xl:grid-cols-[210px_minmax(300px,1fr)_190px] xl:items-end">
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#bac9cc]">
                  Severity
                </span>
                <select
                  className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2.5 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20"
                  onChange={(event) =>
                    setSeverityFilter(event.target.value)
                  }
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
                  htmlFor="network-workflow-search"
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
                    id="network-workflow-search"
                    onChange={(event) => setSearchInput(event.target.value)}
                    placeholder="Type, protocol, service, flag, actual label…"
                    type="search"
                    value={searchInput}
                  />
                  {searchInput || submittedSearch ? (
                    <button
                      aria-label="Clear workflow search"
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
                  Cards per group
                </span>
                <select
                  className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2.5 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20"
                  onChange={(event) =>
                    setGroupLimit(Number(event.target.value))
                  }
                  value={groupLimit}
                >
                  {GROUP_LIMIT_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value} per status
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="border-t border-[#3b494c] px-5 py-3 text-xs leading-5 text-[#708083]">
              Each column is independently bounded to {groupLimit} cards. Its
              filtered total may be larger; complete pagination remains in the
              incident queue.
              {submittedSearch ? (
                <>
                  {" "}
                  Active search:{" "}
                  <span className="font-semibold text-[#dce4e5]">
                    “{submittedSearch}”
                  </span>
                  .
                </>
              ) : null}
            </div>
          </Panel>

          {isLoadingDashboard && !dashboard ? (
            <LoadingNotice>
              Loading complete persisted workflow and severity totals…
            </LoadingNotice>
          ) : null}

          {dashboardError ? (
            <ErrorNotice
              onRetry={() =>
                loadDashboard(selectedDatasetId, {
                  preserveExisting: true,
                })
              }
              retryLabel="Retry totals"
            >
              {dashboardError}
            </ErrorNotice>
          ) : null}

          {dashboard ? (
            <>
              <Panel>
                <PanelHeader
                  icon={ListChecks}
                  title="Complete analyst workflow totals"
                  description="These counts cover the complete dataset and are not limited by the workflow board filters."
                />
                <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
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
              </Panel>

              <Panel>
                <PanelHeader
                  icon={AlertTriangle}
                  title="Complete probability-derived severity totals"
                  description="Severity is an analyst triage band derived from attack probability, not an attack-family prediction."
                />
                <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
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
                </div>
              </Panel>
            </>
          ) : null}

          {dashboard && totalIncidents === 0 ? (
            <Panel className="p-8 text-center">
              <CheckCircle2
                className="mx-auto h-9 w-9 text-green-300"
                aria-hidden="true"
              />
              <h2 className="mt-3 text-lg font-semibold text-[#dce4e5]">
                No network incidents were generated
              </h2>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#849396]">
                The completed frozen binary-detector analysis persisted zero
                incident records for this dataset.
              </p>
            </Panel>
          ) : null}

          {shouldShowBoard ? (
            <>
              <WorkflowGuidance />

              <div>
                <div className="mb-3">
                  <p className="muted-label">Filtered workflow board</p>
                  <h2 className="mt-1 text-xl font-semibold text-[#dce4e5]">
                    Highest-risk persisted incidents by status
                  </h2>
                  <p className="mt-1 max-w-3xl text-sm leading-6 text-[#849396]">
                    Each column retains backend risk ordering and reports its
                    complete filtered total separately from the bounded cards
                    currently displayed.
                  </p>
                </div>
                <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
                  {WORKFLOW_STATUSES.map((status) => (
                    <NetworkWorkflowColumn
                      error={groupErrors[status]}
                      group={groups[status]}
                      hasActiveFilters={hasActiveFilters}
                      isLoading={groupLoading[status]}
                      key={status}
                      onRetry={() =>
                        loadGroups(
                          selectedDatasetId,
                          {
                            severity: severityFilter,
                            search: submittedSearch,
                            limit: groupLimit,
                          },
                          { preserveExisting: true }
                        )
                      }
                      onView={setSelectedIncidentId}
                      selectedIncidentId={selectedIncidentId}
                      status={status}
                    />
                  ))}
                </div>
              </div>
            </>
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
