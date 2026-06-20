import { useEffect, useMemo, useState } from "react";
import {
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";

import { getIncidents } from "../api/incidents.js";
import FileSelector from "../components/FileSelector.jsx";
import { useFileContext } from "../context/FileContext.jsx";

const SEVERITY_OPTIONS = ["all", "low", "medium", "high", "critical"];
const STATUS_OPTIONS = [
  "all",
  "open",
  "investigating",
  "resolved",
  "false_positive",
];

function getErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "Could not load incidents. Check that the backend is running.";
}

function formatLabel(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value).replaceAll("_", " ");
}

function formatRiskScore(value) {
  const score = Number(value || 0);

  return score.toFixed(2);
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

function getIncidentAccentClass(severity) {
  const normalizedSeverity = String(severity || "").toLowerCase();

  if (normalizedSeverity === "critical") {
    return "border-l-red-500";
  }

  if (normalizedSeverity === "high") {
    return "border-l-orange-500";
  }

  if (normalizedSeverity === "medium") {
    return "border-l-yellow-500";
  }

  return "border-l-blue-500";
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

function SummaryCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/80 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold text-slate-50">{value}</p>
    </div>
  );
}

function IncidentCard({ incident }) {
  const severity = incident.severity || "low";
  const status = incident.status || "open";

  return (
    <article
      className={`rounded-2xl border border-slate-700 border-l-4 bg-slate-900/80 p-5 shadow-lg shadow-slate-950/20 ${getIncidentAccentClass(
        severity
      )}`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-lg font-semibold text-slate-50">
            {formatLabel(incident.incident_type)}
          </p>
          <p className="mt-1 text-sm text-slate-400">
            IP address:{" "}
            <span className="font-medium text-cyan-200">
              {incident.ip_address || "Unknown"}
            </span>
          </p>
          {incident.created_at ? (
            <p className="mt-1 text-xs text-slate-500">
              Created: {incident.created_at}
            </p>
          ) : null}
        </div>

        <div className="text-left sm:text-right">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Risk score
          </p>
          <p className="mt-1 text-3xl font-bold text-cyan-300">
            {formatRiskScore(incident.risk_score)}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Badge className={getSeverityBadgeClass(severity)}>
          {formatLabel(severity)}
        </Badge>
        <Badge className={getStatusBadgeClass(status)}>{formatLabel(status)}</Badge>
        <Badge className="border-slate-600 bg-slate-800 text-slate-300">
          Rule + ML
        </Badge>
      </div>

      <div className="mt-5 space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Evidence
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            {incident.evidence || "No evidence text available."}
          </p>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recommended action
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            {incident.recommended_action || "No recommendation available."}
          </p>
        </div>
      </div>
    </article>
  );
}

export default function Incidents() {
  const { selectedFileId } = useFileContext();
  const [incidents, setIncidents] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [selectedSeverity, setSelectedSeverity] = useState("all");
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadIncidents() {
    if (!selectedFileId) {
      setIncidents([]);
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      const data = await getIncidents(selectedFileId);
      setIncidents(Array.isArray(data) ? data : []);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
      setIncidents([]);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadIncidents();
  }, [selectedFileId]);

  const sortedIncidents = useMemo(() => {
    return [...incidents].sort((firstIncident, secondIncident) => {
      return (
        Number(secondIncident.risk_score || 0) -
        Number(firstIncident.risk_score || 0)
      );
    });
  }, [incidents]);

  const filteredIncidents = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();

    return sortedIncidents.filter((incident) => {
      const ipAddress = String(incident.ip_address || "").toLowerCase();
      const incidentType = String(incident.incident_type || "").toLowerCase();
      const severity = String(incident.severity || "").toLowerCase();
      const status = String(incident.status || "").toLowerCase();

      const matchesSearch =
        !normalizedSearch ||
        ipAddress.includes(normalizedSearch) ||
        incidentType.includes(normalizedSearch);
      const matchesSeverity =
        selectedSeverity === "all" || severity === selectedSeverity;
      const matchesStatus = selectedStatus === "all" || status === selectedStatus;

      return matchesSearch && matchesSeverity && matchesStatus;
    });
  }, [searchText, selectedSeverity, selectedStatus, sortedIncidents]);

  const openIncidentCount = sortedIncidents.filter((incident) => {
    return String(incident.status || "").toLowerCase() === "open";
  }).length;
  const highCriticalCount = sortedIncidents.filter((incident) => {
    const severity = String(incident.severity || "").toLowerCase();
    return severity === "high" || severity === "critical";
  }).length;
  const highestRiskScore =
    sortedIncidents.length > 0
      ? formatRiskScore(sortedIncidents[0].risk_score)
      : "0.00";

  return (
    <section>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">
        Review, prioritize, and investigate suspicious activity detected across
        application logs.
      </p>

      <FileSelector />

      {!selectedFileId ? (
        <div className="panel mt-8">
          <div className="flex items-start gap-4">
            <div className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-3 text-cyan-300">
              <ShieldAlert className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-50">
                Select a log file
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Choose an uploaded file to review generated incidents.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {selectedFileId ? (
        <>
          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Total Incidents" value={sortedIncidents.length} />
            <SummaryCard label="Open Incidents" value={openIncidentCount} />
            <SummaryCard
              label="High / Critical Incidents"
              value={highCriticalCount}
            />
            <SummaryCard label="Highest Risk Score" value={highestRiskScore} />
          </div>

          <div className="panel mt-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div>
                <div className="flex items-center gap-2 text-cyan-300">
                  <SlidersHorizontal className="h-5 w-5" aria-hidden="true" />
                  <p className="text-sm font-semibold uppercase tracking-wide">
                    Filters
                  </p>
                </div>
                <p className="mt-2 text-sm text-slate-400">
                  Search and filter the current file's incident queue.
                </p>
              </div>

              <button
                type="button"
                onClick={loadIncidents}
                disabled={isLoading}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-400 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCw
                  className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                Refresh
              </button>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px_240px]">
              <label className="block">
                <span className="text-sm font-medium text-slate-300">Search</span>
                <div className="mt-2 flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 focus-within:border-cyan-400">
                  <Search className="h-4 w-4 text-slate-500" aria-hidden="true" />
                  <input
                    className="w-full bg-transparent text-sm text-slate-50 outline-none placeholder:text-slate-500"
                    onChange={(event) => setSearchText(event.target.value)}
                    placeholder="Search IP or incident type"
                    type="search"
                    value={searchText}
                  />
                </div>
              </label>

              <label className="block">
                <span className="text-sm font-medium text-slate-300">
                  Severity
                </span>
                <select
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-50 outline-none transition focus:border-cyan-400"
                  onChange={(event) => setSelectedSeverity(event.target.value)}
                  value={selectedSeverity}
                >
                  {SEVERITY_OPTIONS.map((severity) => (
                    <option key={severity} value={severity}>
                      {severity === "all"
                        ? "All severities"
                        : formatLabel(severity)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-sm font-medium text-slate-300">Status</span>
                <select
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-50 outline-none transition focus:border-cyan-400"
                  onChange={(event) => setSelectedStatus(event.target.value)}
                  value={selectedStatus}
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status === "all" ? "All statuses" : formatLabel(status)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <div className="mt-6 rounded-xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
            Incident risk scores combine configurable rule signals with Isolation
            Forest anomaly scoring when ML scores are available.
          </div>

          {isLoading ? (
            <div className="panel mt-6">
              <p className="text-lg font-semibold text-slate-50">
                Loading incidents
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Fetching incident records for file_id {selectedFileId}.
              </p>
            </div>
          ) : null}

          {error ? (
            <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          {!isLoading && !error && sortedIncidents.length === 0 ? (
            <div className="panel mt-6">
              <p className="text-lg font-semibold text-slate-50">
                No incidents found for this file
              </p>
              <p className="mt-2 text-sm text-slate-400">
                No incidents found for this file. Generate incidents after running
                feature generation and ML scoring.
              </p>
            </div>
          ) : null}

          {!isLoading &&
          !error &&
          sortedIncidents.length > 0 &&
          filteredIncidents.length === 0 ? (
            <div className="panel mt-6">
              <p className="text-lg font-semibold text-slate-50">
                No matching incidents
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Adjust the search text, severity, or status filter.
              </p>
            </div>
          ) : null}

          {!isLoading && !error && filteredIncidents.length > 0 ? (
            <div className="mt-6 grid gap-5 xl:grid-cols-2">
              {filteredIncidents.map((incident) => (
                <IncidentCard key={incident.id} incident={incident} />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
