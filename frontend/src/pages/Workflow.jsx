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
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${className}`}
    >
      {children}
    </span>
  );
}

function EmptyState({ children, icon }) {
  return (
    <div className="panel mt-8">
      <div className="flex items-start gap-4">
        <div className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-3 text-cyan-300">
          {icon}
        </div>
        <div>{children}</div>
      </div>
    </div>
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
        `Incident #${updatedIncident.id} status updated to ${formatLabel(
          updatedIncident.status
        )}.`
      );
    } catch (error) {
      setUpdateError(getErrorMessage(error));
    } finally {
      setIsUpdating(false);
    }
  }

  return (
    <section>
      <h1 className="page-title">Workflow</h1>
      <p className="page-subtitle">
        Triage incidents and record the current analyst investigation status.
      </p>

      <FileSelector />

      {!selectedFileId ? (
        <EmptyState
          icon={<ShieldCheck className="h-6 w-6" aria-hidden="true" />}
        >
          <p className="text-lg font-semibold text-slate-50">
            Select a log file
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Choose an uploaded file to start analyst triage.
          </p>
        </EmptyState>
      ) : null}

      {selectedFileId ? (
        <>
          {loadError ? (
            <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
              {loadError}
            </div>
          ) : null}

          {isLoading ? (
            <div className="panel mt-8">
              <p className="text-lg font-semibold text-slate-50">
                Loading workflow
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Fetching incidents for file_id {selectedFileId}.
              </p>
            </div>
          ) : null}

          {!isLoading && !loadError && incidents.length === 0 ? (
            <EmptyState
              icon={<CircleAlert className="h-6 w-6" aria-hidden="true" />}
            >
              <p className="text-lg font-semibold text-slate-50">
                No incidents to triage
              </p>
              <p className="mt-2 text-sm text-slate-400">
                This file has no incidents yet. Generate incidents first, then
                return here to update analyst status.
              </p>
            </EmptyState>
          ) : null}

          {!isLoading && !loadError && incidents.length > 0 ? (
            <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.2fr)]">
              <aside className="panel">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-slate-50">
                      Incident selection
                    </p>
                    <p className="mt-1 text-sm text-slate-400">
                      Highest-risk incidents appear first.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => loadIncidents(false)}
                    disabled={isLoading}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-400 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <RefreshCw
                      className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
                      aria-hidden="true"
                    />
                    Refresh
                  </button>
                </div>

                <div className="mt-5 space-y-3">
                  {incidents.map((incident) => {
                    const isSelected = incident.id === selectedIncidentId;

                    return (
                      <button
                        key={incident.id}
                        type="button"
                        onClick={() => {
                          setSelectedIncidentId(incident.id);
                          setUpdateError("");
                          setSuccessMessage("");
                        }}
                        className={`w-full rounded-xl border p-4 text-left transition ${
                          isSelected
                            ? "border-cyan-400 bg-cyan-400/10 shadow-lg shadow-cyan-950/20"
                            : "border-slate-700 bg-slate-900/80 hover:border-slate-500"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-50">
                              {formatLabel(incident.incident_type)}
                            </p>
                            <p className="mt-1 text-sm text-slate-400">
                              {incident.ip_address || "Unknown IP"}
                            </p>
                          </div>
                          <p className="text-xl font-bold text-cyan-300">
                            {formatRiskScore(incident.risk_score)}
                          </p>
                        </div>

                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge
                            className={getStatusBadgeClass(
                              incident.status || "open"
                            )}
                          >
                            {formatLabel(incident.status || "open")}
                          </Badge>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </aside>

              <main className="panel">
                {selectedIncident ? (
                  <>
                    <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex items-center gap-3 text-cyan-300">
                          <ShieldCheck className="h-6 w-6" aria-hidden="true" />
                          <p className="text-sm font-semibold uppercase tracking-wide">
                            Analyst review
                          </p>
                        </div>
                        <h2 className="mt-3 text-2xl font-bold text-slate-50">
                          {formatLabel(selectedIncident.incident_type)}
                        </h2>
                        <p className="mt-2 text-sm text-slate-400">
                          IP address:{" "}
                          <span className="font-medium text-cyan-200">
                            {selectedIncident.ip_address || "Unknown"}
                          </span>
                        </p>
                        {selectedIncident.created_at ? (
                          <p className="mt-1 text-xs text-slate-500">
                            Created: {selectedIncident.created_at}
                          </p>
                        ) : null}
                      </div>

                      <div className="rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-5 py-4 text-left lg:text-right">
                        <p className="text-xs font-semibold uppercase tracking-wide text-cyan-200">
                          Risk score
                        </p>
                        <p className="mt-1 text-4xl font-bold text-cyan-300">
                          {formatRiskScore(selectedIncident.risk_score)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-5 flex flex-wrap gap-2">
                      <Badge
                        className={getSeverityBadgeClass(
                          selectedIncident.severity || "low"
                        )}
                      >
                        {formatLabel(selectedIncident.severity || "low")}
                      </Badge>
                      <Badge
                        className={getStatusBadgeClass(
                          selectedIncident.status || "open"
                        )}
                      >
                        {formatLabel(selectedIncident.status || "open")}
                      </Badge>
                    </div>

                    <div className="mt-6 grid gap-5">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Evidence
                        </p>
                        <p className="mt-2 rounded-xl border border-slate-700 bg-slate-950/30 p-4 text-sm leading-6 text-slate-300">
                          {selectedIncident.evidence ||
                            "No evidence text available."}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Recommended action
                        </p>
                        <p className="mt-2 rounded-xl border border-slate-700 bg-slate-950/30 p-4 text-sm leading-6 text-slate-300">
                          {selectedIncident.recommended_action ||
                            "No recommendation available."}
                        </p>
                      </div>
                    </div>

                    <div className="mt-6 rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
                      <div className="flex items-center gap-3">
                        <CheckCircle2
                          className="h-5 w-5 text-cyan-300"
                          aria-hidden="true"
                        />
                        <div>
                          <p className="font-semibold text-slate-50">
                            Update investigation status
                          </p>
                          <p className="mt-1 text-sm text-slate-400">
                            Record the current triage state for this incident.
                          </p>
                        </div>
                      </div>

                      <div className="mt-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                        <label className="block">
                          <span className="text-sm font-medium text-slate-300">
                            Status
                          </span>
                          <select
                            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-50 outline-none transition focus:border-cyan-400"
                            onChange={(event) =>
                              setSelectedStatus(event.target.value)
                            }
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
                          className="inline-flex justify-center rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                        >
                          {isUpdating ? "Updating..." : "Update Status"}
                        </button>
                      </div>

                      {successMessage ? (
                        <div className="mt-4 rounded-xl border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-200">
                          {successMessage}
                        </div>
                      ) : null}

                      {updateError ? (
                        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
                          {updateError}
                        </div>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <div className="rounded-xl border border-slate-700 bg-slate-950/30 p-5 text-sm text-slate-400">
                    Select an incident to review its evidence and update status.
                  </div>
                )}
              </main>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
