import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { getIncidents, updateIncidentStatus } from "../api/incidents.js";
import FileSelector from "../components/FileSelector.jsx";
import { useFileContext } from "../context/FileContext.jsx";

const STATUS_OPTIONS = ["open", "investigating", "resolved", "false_positive"];

function getErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "The workflow request failed. Check that the backend is running.";
}

function formatLabel(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value).replaceAll("_", " ");
}

function formatRiskScore(value) {
  return Number(value || 0).toFixed(2);
}

function sortIncidentsByRisk(incidentList) {
  return [...incidentList].sort((firstIncident, secondIncident) => {
    return (
      Number(secondIncident.risk_score || 0) -
      Number(firstIncident.risk_score || 0)
    );
  });
}

function getSeverityBadgeClass(severity) {
  const normalizedSeverity = String(severity || "").toLowerCase();

  if (normalizedSeverity === "critical") {
    return "border-red-400/40 bg-red-500/15 text-red-200";
  }

  if (normalizedSeverity === "high") {
    return "border-orange-400/40 bg-orange-500/15 text-orange-200";
  }

  if (normalizedSeverity === "medium") {
    return "border-yellow-400/40 bg-yellow-500/15 text-yellow-100";
  }

  return "border-blue-400/40 bg-blue-500/15 text-blue-200";
}

function getStatusBadgeClass(status) {
  const normalizedStatus = String(status || "").toLowerCase();

  if (normalizedStatus === "investigating") {
    return "border-amber-400/40 bg-amber-500/15 text-amber-200";
  }

  if (normalizedStatus === "resolved") {
    return "border-green-400/40 bg-green-500/15 text-green-200";
  }

  if (normalizedStatus === "false_positive") {
    return "border-slate-500 bg-slate-700/50 text-slate-200";
  }

  return "border-cyan-400/40 bg-cyan-500/15 text-cyan-200";
}

function Badge({ children, className }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] ${className}`}
    >
      {children}
    </span>
  );
}

function EmptyState({ children, icon }) {
  return (
    <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
      <div className="flex items-start gap-4">
        <div className="rounded border border-[#00e5ff]/30 bg-[#00e5ff]/10 p-3 text-[#9cf0ff]">
          {icon}
        </div>
        <div>{children}</div>
      </div>
    </div>
  );
}

function IncidentSelectionRow({ incident, isSelected, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        "w-full border-l-2 px-4 py-3 text-left transition",
        isSelected
          ? "border-l-[#00e5ff] bg-[#00e5ff]/10"
          : "border-l-transparent hover:bg-[#242b2d]/60",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[#dce4e5]">
            {formatLabel(incident.incident_type)}
          </p>
          <p className="mt-1 text-xs text-[#849396]">
            {incident.ip_address || "Unknown IP"}
          </p>
        </div>

        <div className="text-right">
          <p className="text-lg font-semibold leading-none text-[#9cf0ff]">
            {formatRiskScore(incident.risk_score)}
          </p>
          <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#849396]">
            Risk
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Badge className={getStatusBadgeClass(incident.status || "open")}>
          {formatLabel(incident.status || "open")}
        </Badge>
      </div>
    </button>
  );
}

function IncidentSelectionPanel({
  incidents,
  selectedIncidentId,
  setSelectedIncidentId,
  setSuccessMessage,
  setUpdateError,
}) {
  return (
    <aside className="overflow-hidden rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
      <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
        <p className="muted-label">Incident Selection</p>
        <div className="mt-1 flex items-end justify-between gap-3">
          <h2 className="text-base font-semibold text-[#dce4e5]">
            Highest-risk queue
          </h2>
          <p className="text-xs text-[#849396]">{incidents.length} records</p>
        </div>
      </div>

      <div className="max-h-[620px] divide-y divide-[#3b494c] overflow-y-auto">
        {incidents.map((incident) => {
          const isSelected = incident.id === selectedIncidentId;

          return (
            <IncidentSelectionRow
              incident={incident}
              isSelected={isSelected}
              key={incident.id}
              onSelect={() => {
                setSelectedIncidentId(incident.id);
                setUpdateError("");
                setSuccessMessage("");
              }}
            />
          );
        })}
      </div>
    </aside>
  );
}

function IncidentReviewPanel({ incident }) {
  if (!incident) {
    return (
      <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 text-sm text-[#849396] shadow-lg shadow-black/20">
        Select an incident to review its evidence and update status.
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
      <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-4">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-[#9cf0ff]">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
              <p className="muted-label text-[#9cf0ff]">Incident Review</p>
            </div>

            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-[#dce4e5]">
              {formatLabel(incident.incident_type)}
            </h2>
            <p className="mt-2 text-sm text-[#849396]">
              Source IP{" "}
              <span className="font-semibold text-[#c3f5ff]">
                {incident.ip_address || "Unknown"}
              </span>
            </p>

            {incident.created_at ? (
              <p className="mt-1 text-xs text-[#849396]">
                Created {incident.created_at}
              </p>
            ) : null}
          </div>

          <div className="rounded border border-[#00e5ff]/30 bg-[#00e5ff]/10 px-5 py-4 lg:text-right">
            <p className="muted-label text-[#9cf0ff]">Risk score</p>
            <p className="mt-1 text-4xl font-semibold text-[#9cf0ff]">
              {formatRiskScore(incident.risk_score)}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Badge className={getSeverityBadgeClass(incident.severity || "low")}>
            {formatLabel(incident.severity || "low")}
          </Badge>
          <Badge className={getStatusBadgeClass(incident.status || "open")}>
            {formatLabel(incident.status || "open")}
          </Badge>
        </div>
      </div>

      <div className="grid gap-4 p-5">
        <div>
          <p className="muted-label">Evidence</p>
          <pre className="mt-2 whitespace-pre-wrap rounded border border-[#3b494c] bg-[#0d1516]/80 p-4 font-mono text-xs leading-6 text-[#bac9cc]">
            {incident.evidence || "No evidence text available."}
          </pre>
        </div>

        <div>
          <p className="muted-label">Recommended Action</p>
          <p className="mt-2 rounded border border-[#3b494c] bg-[#0d1516]/60 p-4 text-sm leading-6 text-[#bac9cc]">
            {incident.recommended_action || "No recommendation available."}
          </p>
        </div>

        <div className="rounded border border-[#3b494c] bg-[#0d1516]/60 p-4">
          <p className="muted-label text-[#9cf0ff]">Detection Context</p>
          <p className="mt-2 text-sm leading-6 text-[#bac9cc]">
            Risk score combines configurable detection rules with Isolation
            Forest anomaly scoring when available.
          </p>
        </div>
      </div>
    </section>
  );
}

function StatusUpdatePanel({
  handleStatusUpdate,
  isUpdating,
  selectedIncident,
  selectedStatus,
  setSelectedStatus,
  successMessage,
  updateError,
}) {
  if (!selectedIncident) {
    return null;
  }

  return (
    <section className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
      <div className="flex items-start gap-3">
        <div className="rounded border border-[#00e5ff]/30 bg-[#00e5ff]/10 p-2 text-[#9cf0ff]">
          <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <p className="text-base font-semibold text-[#dce4e5]">
            Update investigation status
          </p>
          <p className="mt-1 text-sm text-[#849396]">
            Record the current triage state for this incident.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <label className="block">
          <span className="muted-label">Status</span>
          <select
            className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm text-[#dce4e5] outline-none transition focus:border-[#00daf3]"
            onChange={(event) => setSelectedStatus(event.target.value)}
            value={selectedStatus}
          >
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {formatLabel(status)}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={handleStatusUpdate}
          disabled={isUpdating}
          className="inline-flex justify-center rounded border border-[#00daf3]/50 bg-[#00e5ff] px-5 py-2.5 text-sm font-semibold text-[#00363d] transition hover:bg-[#9cf0ff] disabled:cursor-not-allowed disabled:border-[#3b494c] disabled:bg-[#242b2d] disabled:text-[#849396]"
        >
          {isUpdating ? "Updating..." : "Update Status"}
        </button>
      </div>

      {successMessage ? (
        <div className="mt-4 rounded border border-green-400/40 bg-green-500/10 px-4 py-3 text-sm text-green-200">
          {successMessage}
        </div>
      ) : null}

      {updateError ? (
        <div className="mt-4 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {updateError}
        </div>
      ) : null}
    </section>
  );
}

export default function Workflow() {
  const { selectedFileId } = useFileContext();
  const [incidents, setIncidents] = useState([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [selectedStatus, setSelectedStatus] = useState("open");
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [updateError, setUpdateError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  async function loadIncidents(shouldResetSelection = false) {
    if (!selectedFileId) {
      setIncidents([]);
      setSelectedIncidentId(null);
      return;
    }

    setIsLoading(true);
    setLoadError("");
    setUpdateError("");
    setSuccessMessage("");

    try {
      const data = await getIncidents(selectedFileId);
      const sortedIncidents = sortIncidentsByRisk(Array.isArray(data) ? data : []);

      setIncidents(sortedIncidents);
      setSelectedIncidentId((currentIncidentId) => {
        if (!shouldResetSelection) {
          const currentIncidentStillExists = sortedIncidents.some((incident) => {
            return incident.id === currentIncidentId;
          });

          if (currentIncidentStillExists) {
            return currentIncidentId;
          }
        }

        return sortedIncidents[0]?.id || null;
      });
    } catch (error) {
      setLoadError(getErrorMessage(error));
      setIncidents([]);
      setSelectedIncidentId(null);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadIncidents(true);
  }, [selectedFileId]);

  const selectedIncident = useMemo(() => {
    return (
      incidents.find((incident) => incident.id === selectedIncidentId) || null
    );
  }, [incidents, selectedIncidentId]);

  useEffect(() => {
    if (selectedIncident?.status) {
      setSelectedStatus(selectedIncident.status);
    } else {
      setSelectedStatus("open");
    }
  }, [selectedIncident]);

  async function handleStatusUpdate() {
    if (!selectedIncident) {
      return;
    }

    setIsUpdating(true);
    setUpdateError("");
    setSuccessMessage("");

    try {
      const updatedIncident = await updateIncidentStatus(
        selectedIncident.id,
        selectedStatus
      );

      setIncidents((currentIncidents) => {
        const nextIncidents = currentIncidents.map((incident) => {
          if (incident.id === updatedIncident.id) {
            return updatedIncident;
          }

          return incident;
        });

        return sortIncidentsByRisk(nextIncidents);
      });
      setSelectedIncidentId(updatedIncident.id);
      setSuccessMessage(
        `Status updated to ${formatLabel(updatedIncident.status)}.`
      );
    } catch (error) {
      setUpdateError(getErrorMessage(error));
    } finally {
      setIsUpdating(false);
    }
  }

  return (
    <section className="space-y-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,520px)] xl:items-end">
        <div>
          <p className="muted-label">Security operations</p>
          <h1 className="page-title mt-2">Analyst Workflow</h1>
          <p className="page-subtitle max-w-3xl">
            Review incident evidence and record the current investigation status.
          </p>
        </div>

        <FileSelector />
      </div>

      <div className="flex flex-col gap-3 rounded-md border border-[#3b494c] bg-[#192122]/90 p-3 shadow-lg shadow-black/20 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="muted-label">Review desk</p>
          <p className="mt-1 text-sm text-[#849396]">
            Selected file_id {selectedFileId || "none"}
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadIncidents(false)}
          disabled={!selectedFileId || isLoading}
          className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Refresh incidents
        </button>
      </div>

      {!selectedFileId ? (
        <EmptyState
          icon={<ShieldCheck className="h-6 w-6" aria-hidden="true" />}
        >
          <p className="text-base font-semibold text-[#dce4e5]">
            Select a log file
          </p>
          <p className="mt-2 text-sm text-[#849396]">
            Choose an uploaded file to start analyst triage.
          </p>
        </EmptyState>
      ) : null}

      {selectedFileId ? (
        <>
          {loadError ? (
            <div className="rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {loadError}
            </div>
          ) : null}

          {isLoading ? (
            <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
              <p className="text-base font-semibold text-[#dce4e5]">
                Loading workflow
              </p>
              <p className="mt-2 text-sm text-[#849396]">
                Fetching incidents for file_id {selectedFileId}.
              </p>
            </div>
          ) : null}

          {!isLoading && !loadError && incidents.length === 0 ? (
            <EmptyState
              icon={<CircleAlert className="h-6 w-6" aria-hidden="true" />}
            >
              <p className="text-base font-semibold text-[#dce4e5]">
                No incidents to triage
              </p>
              <p className="mt-2 text-sm text-[#849396]">
                This file has no incidents yet. Generate incidents first, then
                return here to update analyst status.
              </p>
            </EmptyState>
          ) : null}

          {!isLoading && !loadError && incidents.length > 0 ? (
            <div className="grid gap-5 xl:grid-cols-[minmax(300px,0.72fr)_minmax(0,1.28fr)]">
              <IncidentSelectionPanel
                incidents={incidents}
                selectedIncidentId={selectedIncidentId}
                setSelectedIncidentId={setSelectedIncidentId}
                setSuccessMessage={setSuccessMessage}
                setUpdateError={setUpdateError}
              />

              <div className="space-y-5">
                <IncidentReviewPanel incident={selectedIncident} />
                <StatusUpdatePanel
                  handleStatusUpdate={handleStatusUpdate}
                  isUpdating={isUpdating}
                  selectedIncident={selectedIncident}
                  selectedStatus={selectedStatus}
                  setSelectedStatus={setSelectedStatus}
                  successMessage={successMessage}
                  updateError={updateError}
                />
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
