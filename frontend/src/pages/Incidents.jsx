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
  return Number(value || 0).toFixed(2);
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

function SummaryCard({ label, value }) {
  return (
    <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-4 shadow-lg shadow-black/20">
      <p className="muted-label">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-[#dce4e5]">
        {value}
      </p>
    </div>
  );
}

function EmptyPanel({ icon, title, message }) {
  return (
    <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
      <div className="flex items-start gap-4">
        <div className="rounded border border-[#00e5ff]/30 bg-[#00e5ff]/10 p-3 text-[#9cf0ff]">
          {icon}
        </div>
        <div>
          <p className="text-base font-semibold text-[#dce4e5]">{title}</p>
          <p className="mt-2 text-sm text-[#849396]">{message}</p>
        </div>
      </div>
    </div>
  );
}

function FilterBar({
  isLoading,
  loadIncidents,
  searchText,
  selectedSeverity,
  selectedStatus,
  setSearchText,
  setSelectedSeverity,
  setSelectedStatus,
}) {
  return (
    <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-3 shadow-lg shadow-black/20">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="flex items-center gap-2 text-[#9cf0ff]">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            <p className="muted-label text-[#9cf0ff]">Operations filter</p>
          </div>
          <p className="mt-1 text-sm text-[#849396]">
            Filter the selected file's incident queue.
          </p>
        </div>

        <button
          type="button"
          onClick={loadIncidents}
          disabled={isLoading}
          className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Refresh
        </button>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_240px]">
        <label className="block">
          <span className="muted-label">Search</span>
          <div className="mt-1.5 flex items-center gap-2 rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 focus-within:border-[#00daf3]">
            <Search className="h-4 w-4 text-[#849396]" aria-hidden="true" />
            <input
              className="w-full bg-transparent text-sm text-[#dce4e5] outline-none placeholder:text-[#849396]"
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search IP address or incident type"
              type="search"
              value={searchText}
            />
          </div>
        </label>

        <label className="block">
          <span className="muted-label">Severity</span>
          <select
            className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm text-[#dce4e5] outline-none transition focus:border-[#00daf3]"
            onChange={(event) => setSelectedSeverity(event.target.value)}
            value={selectedSeverity}
          >
            {SEVERITY_OPTIONS.map((severity) => (
              <option key={severity} value={severity}>
                {severity === "all" ? "All severities" : formatLabel(severity)}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="muted-label">Status</span>
          <select
            className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm text-[#dce4e5] outline-none transition focus:border-[#00daf3]"
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
  );
}

function IncidentQueueTable({ incidents, selectedIncidentId, setSelectedIncidentId }) {
  return (
    <div className="hidden overflow-x-auto lg:block">
      <table className="w-full min-w-[960px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-[#3b494c] bg-[#111a1b] text-[11px] uppercase tracking-[0.16em] text-[#849396]">
            <th className="px-4 py-3 font-semibold">Severity</th>
            <th className="px-4 py-3 font-semibold">Incident Type</th>
            <th className="px-4 py-3 font-semibold">Source IP</th>
            <th className="px-4 py-3 font-semibold">Evidence Summary</th>
            <th className="px-4 py-3 text-center font-semibold">Risk</th>
            <th className="px-4 py-3 font-semibold">Status</th>
            <th className="px-4 py-3 font-semibold">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#3b494c]">
          {incidents.map((incident) => {
            const isSelected = selectedIncidentId === incident.id;

            return (
              <tr
                key={incident.id}
                onClick={() => setSelectedIncidentId(incident.id)}
                className={[
                  "cursor-pointer border-l-2 transition",
                  isSelected
                    ? "border-l-[#00e5ff] bg-[#00e5ff]/10"
                    : "border-l-transparent hover:bg-[#242b2d]/50",
                ].join(" ")}
              >
                <td className="px-4 py-4">
                  <Badge className={getSeverityBadgeClass(incident.severity)}>
                    {formatLabel(incident.severity || "low")}
                  </Badge>
                </td>
                <td className="px-4 py-4 font-semibold text-[#dce4e5]">
                  {formatLabel(incident.incident_type)}
                </td>
                <td className="px-4 py-4 font-medium text-[#bac9cc]">
                  {incident.ip_address || "Unknown"}
                </td>
                <td className="max-w-[280px] truncate px-4 py-4 text-[#849396]">
                  {incident.evidence || "No evidence text available."}
                </td>
                <td className="px-4 py-4 text-center">
                  <span className="rounded bg-[#00e5ff]/10 px-2 py-1 font-semibold text-[#9cf0ff]">
                    {formatRiskScore(incident.risk_score)}
                  </span>
                </td>
                <td className="px-4 py-4">
                  <Badge className={getStatusBadgeClass(incident.status)}>
                    {formatLabel(incident.status || "open")}
                  </Badge>
                </td>
                <td className="px-4 py-4 text-xs text-[#849396]">
                  {incident.created_at || "Not available"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function IncidentMobileList({ incidents, selectedIncidentId, setSelectedIncidentId }) {
  return (
    <div className="divide-y divide-[#3b494c] lg:hidden">
      {incidents.map((incident) => {
        const isSelected = selectedIncidentId === incident.id;

        return (
          <button
            key={incident.id}
            type="button"
            onClick={() => setSelectedIncidentId(incident.id)}
            className={[
              "w-full border-l-2 p-4 text-left transition",
              isSelected
                ? "border-l-[#00e5ff] bg-[#00e5ff]/10"
                : "border-l-transparent hover:bg-[#242b2d]/50",
            ].join(" ")}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-[#dce4e5]">
                  {formatLabel(incident.incident_type)}
                </p>
                <p className="mt-1 text-sm text-[#849396]">
                  {incident.ip_address || "Unknown"}
                </p>
              </div>
              <p className="text-xl font-semibold text-[#9cf0ff]">
                {formatRiskScore(incident.risk_score)}
              </p>
            </div>
            <p className="mt-3 line-clamp-2 text-sm text-[#849396]">
              {incident.evidence || "No evidence text available."}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge className={getSeverityBadgeClass(incident.severity)}>
                {formatLabel(incident.severity || "low")}
              </Badge>
              <Badge className={getStatusBadgeClass(incident.status)}>
                {formatLabel(incident.status || "open")}
              </Badge>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function IncidentDetailPanel({ incident }) {
  if (!incident) {
    return null;
  }

  return (
    <section className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
      <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
        <p className="muted-label">Selected incident detail</p>
        <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[#dce4e5]">
              {formatLabel(incident.incident_type)}
            </h2>
            <p className="mt-1 text-sm text-[#849396]">
              Source IP:{" "}
              <span className="font-semibold text-[#c3f5ff]">
                {incident.ip_address || "Unknown"}
              </span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className={getSeverityBadgeClass(incident.severity)}>
              {formatLabel(incident.severity || "low")}
            </Badge>
            <Badge className={getStatusBadgeClass(incident.status)}>
              {formatLabel(incident.status || "open")}
            </Badge>
            <span className="rounded bg-[#00e5ff]/10 px-2 py-1 text-sm font-semibold text-[#9cf0ff]">
              Risk {formatRiskScore(incident.risk_score)}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-5 xl:grid-cols-2">
        <div>
          <p className="muted-label">Evidence</p>
          <p className="mt-2 rounded border border-[#3b494c] bg-[#0d1516]/70 p-4 text-sm leading-6 text-[#bac9cc]">
            {incident.evidence || "No evidence text available."}
          </p>
        </div>
        <div>
          <p className="muted-label">Recommended action</p>
          <p className="mt-2 rounded border border-[#3b494c] bg-[#0d1516]/70 p-4 text-sm leading-6 text-[#bac9cc]">
            {incident.recommended_action || "No recommendation available."}
          </p>
        </div>
      </div>
    </section>
  );
}

export default function Incidents() {
  const { selectedFileId } = useFileContext();
  const [incidents, setIncidents] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [selectedSeverity, setSelectedSeverity] = useState("all");
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadIncidents() {
    if (!selectedFileId) {
      setIncidents([]);
      setSelectedIncidentId(null);
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
      setSelectedIncidentId(null);
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

  const selectedIncident = useMemo(() => {
    return (
      filteredIncidents.find((incident) => incident.id === selectedIncidentId) ||
      filteredIncidents[0] ||
      null
    );
  }, [filteredIncidents, selectedIncidentId]);

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
    <section className="space-y-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,520px)] xl:items-end">
        <div>
          <p className="muted-label">Security operations</p>
          <h1 className="page-title mt-2">Incident Queue</h1>
          <p className="page-subtitle max-w-3xl">
            Review, prioritize, and investigate suspicious activity detected across
            application logs.
          </p>
        </div>

        <FileSelector />
      </div>

      {!selectedFileId ? (
        <EmptyPanel
          icon={<ShieldAlert className="h-6 w-6" aria-hidden="true" />}
          title="Select a log file"
          message="Choose an uploaded file to review generated incidents."
        />
      ) : null}

      {selectedFileId ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Total Incidents" value={sortedIncidents.length} />
            <SummaryCard label="Open Incidents" value={openIncidentCount} />
            <SummaryCard
              label="High / Critical Incidents"
              value={highCriticalCount}
            />
            <SummaryCard label="Highest Risk Score" value={highestRiskScore} />
          </div>

          <FilterBar
            isLoading={isLoading}
            loadIncidents={loadIncidents}
            searchText={searchText}
            selectedSeverity={selectedSeverity}
            selectedStatus={selectedStatus}
            setSearchText={setSearchText}
            setSelectedSeverity={setSelectedSeverity}
            setSelectedStatus={setSelectedStatus}
          />

          {isLoading ? (
            <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 px-4 py-3 text-sm text-[#849396]">
              Fetching incident records for file_id {selectedFileId}.
            </div>
          ) : null}

          {error ? (
            <div className="rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          {!isLoading && !error && sortedIncidents.length === 0 ? (
            <EmptyPanel
              icon={<ShieldAlert className="h-6 w-6" aria-hidden="true" />}
              title="No incidents found for this file"
              message="No incidents found for this file. Generate incidents after running feature generation and ML scoring."
            />
          ) : null}

          {!isLoading &&
          !error &&
          sortedIncidents.length > 0 &&
          filteredIncidents.length === 0 ? (
            <EmptyPanel
              icon={<Search className="h-6 w-6" aria-hidden="true" />}
              title="No matching incidents"
              message="Adjust the search text, severity, or status filter."
            />
          ) : null}

          {!isLoading && !error && filteredIncidents.length > 0 ? (
            <>
              <section className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
                <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
                  <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
                    <div>
                      <p className="muted-label">Queue</p>
                      <h2 className="text-base font-semibold text-[#dce4e5]">
                        Risk score high to low
                      </h2>
                    </div>
                    <p className="text-xs text-[#849396]">
                      {filteredIncidents.length} visible incident
                      {filteredIncidents.length === 1 ? "" : "s"}
                    </p>
                  </div>
                </div>

                <IncidentQueueTable
                  incidents={filteredIncidents}
                  selectedIncidentId={selectedIncident?.id}
                  setSelectedIncidentId={setSelectedIncidentId}
                />
                <IncidentMobileList
                  incidents={filteredIncidents}
                  selectedIncidentId={selectedIncident?.id}
                  setSelectedIncidentId={setSelectedIncidentId}
                />
              </section>

              <IncidentDetailPanel incident={selectedIncident} />
            </>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
