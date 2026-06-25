import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getHourlyTraffic,
  getStatusCodeDistribution,
  getSummary,
} from "../api/analytics.js";
import { getIncidents } from "../api/incidents.js";
import FileSelector from "../components/FileSelector.jsx";
import { useFileContext } from "../context/FileContext.jsx";

const EMPTY_DASHBOARD_DATA = {
  summary: null,
  hourlyTraffic: [],
  statusCodes: [],
  incidents: [],
};

const TRIAGED_STATUSES = ["investigating", "resolved", "false_positive"];

function formatMetricValue(value) {
  if (value === null || value === undefined) {
    return "--";
  }

  return value;
}

function formatStatusLabel(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value).replaceAll("_", " ");
}

function getApiErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "Could not load dashboard data.";
}

function getMetricBorderClass(label) {
  if (label.includes("Critical")) {
    return "border-l-red-400";
  }

  if (label.includes("Open")) {
    return "border-l-orange-400";
  }

  if (label.includes("ML")) {
    return "border-l-blue-400";
  }

  return "border-l-[#00daf3]";
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

function getStatusCodeColor(statusCode) {
  const code = Number(statusCode);

  if (code >= 500) {
    return "#ef4444";
  }

  if (code >= 400) {
    return "#f97316";
  }

  if (code >= 300) {
    return "#60a5fa";
  }

  return "#00daf3";
}

function MetricCard({ label, value }) {
  return (
    <div
      className={[
        "rounded-md border border-[#3b494c] border-l-2 bg-[#192122]/90 p-4 shadow-lg shadow-black/20",
        getMetricBorderClass(label),
      ].join(" ")}
    >
      <p className="muted-label">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-tight text-[#dce4e5]">
        {formatMetricValue(value)}
      </p>
    </div>
  );
}

function SmallMetric({ label, value }) {
  return (
    <div className="rounded border border-[#3b494c] bg-[#111a1b]/80 px-4 py-3">
      <p className="muted-label">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[#dce4e5]">
        {formatMetricValue(value)}
      </p>
    </div>
  );
}

function NoticePanel({ children }) {
  return (
    <div className="rounded border border-[#3b494c] bg-[#192122]/90 px-4 py-3 text-sm text-[#bac9cc]">
      {children}
    </div>
  );
}

function ErrorPanel({ children }) {
  return (
    <div className="rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      {children}
    </div>
  );
}

function ChartPanel({ children, className = "", isEmpty, isLoading, title }) {
  return (
    <div
      className={[
        "rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20",
        className,
      ].join(" ")}
    >
      <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
        <p className="muted-label text-[#dce4e5]">{title}</p>
      </div>

      {isLoading ? (
        <div className="flex h-[280px] items-center justify-center text-sm text-[#849396]">
          Loading chart data...
        </div>
      ) : isEmpty ? (
        <div className="flex h-[280px] items-center justify-center text-sm text-[#849396]">
          No data available for this file.
        </div>
      ) : (
        <div className="h-[280px] p-5">{children}</div>
      )}
    </div>
  );
}

function DarkTooltip({ active, label, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      {label ? <p className="mb-1 font-semibold text-[#dce4e5]">{label}</p> : null}
      {payload.map((item) => (
        <p key={item.dataKey || item.name} style={{ color: item.color || "#00daf3" }}>
          {item.name || item.dataKey}: {item.value}
        </p>
      ))}
    </div>
  );
}

function DashboardHeader() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,520px)] xl:items-end">
      <div>
        <p className="muted-label">Operational overview</p>
        <h1 className="page-title mt-2">Security Overview</h1>
        <p className="page-subtitle max-w-2xl">
          Monitor application activity, anomaly signals, and analyst triage in one
          place.
        </p>
        <Link
          className="mt-4 inline-flex rounded border border-[#3b494c] bg-[#192122]/80 px-4 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff]"
          to="/upload"
        >
          Upload Logs
        </Link>
      </div>

      <FileSelector />
    </div>
  );
}

function PriorityIncidentsTable({ incidents, isLoading }) {
  if (isLoading) {
    return (
      <div className="p-5 text-sm text-[#849396]">Loading priority incidents...</div>
    );
  }

  if (incidents.length === 0) {
    return (
      <div className="p-5 text-sm text-[#849396]">
        No incidents exist for this file yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-[#3b494c] bg-[#111a1b] text-[11px] uppercase tracking-[0.16em] text-[#849396]">
            <th className="px-5 py-3 font-semibold">Incident Type</th>
            <th className="px-5 py-3 font-semibold">IP Address</th>
            <th className="px-5 py-3 text-center font-semibold">Risk Score</th>
            <th className="px-5 py-3 font-semibold">Status</th>
            <th className="px-5 py-3 font-semibold">Severity</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#3b494c]">
          {incidents.map((incident) => (
            <tr key={incident.id} className="transition hover:bg-[#242b2d]/50">
              <td className="px-5 py-4 font-semibold text-[#dce4e5]">
                {formatStatusLabel(incident.incident_type)}
              </td>
              <td className="px-5 py-4 text-[#bac9cc]">
                {incident.ip_address || "Unknown"}
              </td>
              <td className="px-5 py-4 text-center">
                <span className="rounded bg-[#00e5ff]/10 px-2 py-1 font-semibold text-[#9cf0ff]">
                  {formatMetricValue(incident.risk_score)}
                </span>
              </td>
              <td className="px-5 py-4">
                <span
                  className={[
                    "inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
                    getStatusBadgeClass(incident.status),
                  ].join(" ")}
                >
                  {formatStatusLabel(incident.status || "open")}
                </span>
              </td>
              <td className="px-5 py-4">
                <span
                  className={[
                    "inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
                    getSeverityBadgeClass(incident.severity),
                  ].join(" ")}
                >
                  {formatStatusLabel(incident.severity || "low")}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PipelineStep({ isActive, isLast, label }) {
  return (
    <div className="flex flex-1 items-center">
      <div className="flex min-w-0 flex-col items-center gap-2">
        <div
          className={[
            "h-3 w-3 rounded-full border",
            isActive
              ? "border-[#00e5ff] bg-[#00e5ff]"
              : "border-[#3b494c] bg-[#111a1b]",
          ].join(" ")}
        />
        <p
          className={[
            "text-center text-[11px] font-semibold uppercase tracking-[0.14em]",
            isActive ? "text-[#c3f5ff]" : "text-[#849396]",
          ].join(" ")}
        >
          {label}
        </p>
      </div>
      {!isLast ? (
        <div
          className={[
            "mx-3 hidden h-px flex-1 md:block",
            isActive ? "bg-[#00daf3]/60" : "bg-[#3b494c]",
          ].join(" ")}
        />
      ) : null}
    </div>
  );
}

export default function Dashboard() {
  const { selectedFileId } = useFileContext();
  const [dashboardData, setDashboardData] = useState(EMPTY_DASHBOARD_DATA);
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState("");

  useEffect(() => {
    if (!selectedFileId) {
      setDashboardData(EMPTY_DASHBOARD_DATA);
      setDashboardError("");
      return;
    }

    let shouldIgnoreResult = false;

    async function loadDashboardData() {
      setIsLoadingDashboard(true);
      setDashboardError("");

      try {
        const [summary, hourlyTraffic, statusCodes, incidents] =
          await Promise.all([
            getSummary(selectedFileId),
            getHourlyTraffic(selectedFileId),
            getStatusCodeDistribution(selectedFileId),
            getIncidents(selectedFileId),
          ]);

        if (!shouldIgnoreResult) {
          setDashboardData({
            summary,
            hourlyTraffic: Array.isArray(hourlyTraffic) ? hourlyTraffic : [],
            statusCodes: Array.isArray(statusCodes) ? statusCodes : [],
            incidents: Array.isArray(incidents) ? incidents : [],
          });
        }
      } catch (error) {
        if (!shouldIgnoreResult) {
          setDashboardData(EMPTY_DASHBOARD_DATA);
          setDashboardError(getApiErrorMessage(error));
        }
      } finally {
        if (!shouldIgnoreResult) {
          setIsLoadingDashboard(false);
        }
      }
    }

    loadDashboardData();

    return () => {
      shouldIgnoreResult = true;
    };
  }, [selectedFileId]);

  const { summary, hourlyTraffic, statusCodes, incidents } = dashboardData;

  const primaryMetrics = useMemo(
    () => [
      { label: "Total Logs", value: summary?.total_logs },
      { label: "Unique IPs", value: summary?.unique_ips },
      { label: "Open Incidents", value: summary?.open_incidents },
      { label: "Critical Incidents", value: summary?.critical_incidents },
      { label: "Avg ML Score", value: summary?.avg_ml_anomaly_score },
    ],
    [summary]
  );

  const secondaryMetrics = useMemo(
    () => [
      { label: "Total Incidents", value: summary?.total_incidents },
      { label: "High Incidents", value: summary?.high_incidents },
      { label: "Max Risk Score", value: summary?.max_risk_score },
    ],
    [summary]
  );

  const priorityIncidents = useMemo(() => {
    return [...incidents]
      .sort((firstIncident, secondIncident) => {
        return (
          Number(secondIncident.risk_score || 0) -
          Number(firstIncident.risk_score || 0)
        );
      })
      .slice(0, 4);
  }, [incidents]);

  const hasLogs = Number(summary?.total_logs || 0) > 0;
  const hasMlScore =
    summary?.avg_ml_anomaly_score !== null &&
    summary?.avg_ml_anomaly_score !== undefined;
  const hasIncidents = Number(summary?.total_incidents || 0) > 0;
  const hasAnalystTriage = incidents.some((incident) => {
    return TRIAGED_STATUSES.includes(String(incident.status || "").toLowerCase());
  });

  const pipelineSteps = [
    { label: "Logs uploaded", isActive: hasLogs },
    { label: "Features generated", isActive: hasMlScore },
    { label: "ML scored", isActive: hasMlScore },
    { label: "Incidents generated", isActive: hasIncidents },
    { label: "Analyst triage", isActive: hasAnalystTriage },
  ];

  return (
    <section className="space-y-5">
      <DashboardHeader />

      {!selectedFileId ? (
        <NoticePanel>
          Select an uploaded log file to load dashboard metrics.
        </NoticePanel>
      ) : null}

      {dashboardError ? <ErrorPanel>{dashboardError}</ErrorPanel> : null}

      {selectedFileId && isLoadingDashboard ? (
        <NoticePanel>Loading dashboard data...</NoticePanel>
      ) : null}

      {summary ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {primaryMetrics.map((metric) => (
              <MetricCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
              />
            ))}
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            {secondaryMetrics.map((metric) => (
              <SmallMetric
                key={metric.label}
                label={metric.label}
                value={metric.value}
              />
            ))}
          </div>
        </>
      ) : null}

      {selectedFileId && !dashboardError ? (
        <div className="grid gap-5 xl:grid-cols-12">
          <ChartPanel
            className="xl:col-span-8"
            isEmpty={hourlyTraffic.length === 0}
            isLoading={isLoadingDashboard}
            title="Traffic Volume Over Time"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hourlyTraffic}>
                <CartesianGrid stroke="#3b494c" strokeDasharray="3 3" />
                <XAxis
                  dataKey="hour"
                  stroke="#849396"
                  tick={{ fill: "#849396", fontSize: 11 }}
                  tickFormatter={(value) => String(value).split(" ")[1] || value}
                />
                <YAxis stroke="#849396" tick={{ fill: "#849396", fontSize: 11 }} />
                <Tooltip content={<DarkTooltip />} />
                <Line
                  dataKey="request_count"
                  dot={{ fill: "#00e5ff", r: 3 }}
                  name="Requests"
                  stroke="#00e5ff"
                  strokeWidth={2}
                  type="monotone"
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            className="xl:col-span-4"
            isEmpty={statusCodes.length === 0}
            isLoading={isLoadingDashboard}
            title="Status Code Distribution"
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusCodes}
                  dataKey="count"
                  innerRadius={58}
                  nameKey="status_code"
                  outerRadius={92}
                  paddingAngle={3}
                >
                  {statusCodes.map((entry) => (
                    <Cell
                      fill={getStatusCodeColor(entry.status_code)}
                      key={entry.status_code}
                    />
                  ))}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </ChartPanel>
        </div>
      ) : null}

      {selectedFileId && !dashboardError ? (
        <section className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
          <div className="flex flex-col gap-3 border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="muted-label text-[#dce4e5]">Priority Incidents</p>
              <p className="mt-1 text-sm text-[#849396]">
                Highest-risk incidents for the selected file.
              </p>
            </div>
            <Link
              className="text-sm font-semibold text-[#9cf0ff] transition hover:text-[#c3f5ff]"
              to="/incidents"
            >
              View all incidents
            </Link>
          </div>

          <PriorityIncidentsTable
            incidents={priorityIncidents}
            isLoading={isLoadingDashboard}
          />
        </section>
      ) : null}

      {summary ? (
        <section className="rounded-md border border-[#3b494c] bg-[#192122]/90 p-5 shadow-lg shadow-black/20">
          <div className="flex flex-col gap-1">
            <p className="muted-label">Pipeline Status</p>
            <h2 className="text-lg font-semibold text-[#dce4e5]">
              Analysis progress for file_id {summary.file_id}
            </h2>
          </div>

          <div className="mt-5 flex flex-col gap-4 md:flex-row md:items-start">
            {pipelineSteps.map((step, index) => (
              <PipelineStep
                isActive={step.isActive}
                isLast={index === pipelineSteps.length - 1}
                key={step.label}
                label={step.label}
              />
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
