import { useEffect, useMemo, useState } from "react";

import { getSummary } from "../api/analytics.js";
import FileSelector from "../components/FileSelector.jsx";
import { useFileContext } from "../context/FileContext.jsx";

function formatMetricValue(value) {
  if (value === null || value === undefined) {
    return "--";
  }

  return value;
}

function getMetricBorderClass(label) {
  if (label.includes("Critical")) {
    return "border-l-red-400";
  }

  if (label.includes("High") || label.includes("Risk")) {
    return "border-l-orange-400";
  }

  if (label.includes("ML")) {
    return "border-l-blue-400";
  }

  return "border-l-[#00daf3]";
}

function MetricCard({ label, value }) {
  return (
    <div
      className={[
        "rounded-md border border-[#3b494c] border-l-2 bg-[#192122]/90 p-5 shadow-lg shadow-black/20",
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

function PipelineStep({ isActive, label, description }) {
  return (
    <div className="min-w-[150px] flex-1 rounded border border-[#3b494c] bg-[#0d1516]/70 p-4">
      <div className="flex items-center gap-3">
        <div
          className={[
            "h-2.5 w-2.5 shrink-0 rounded-full",
            isActive
              ? "bg-[#00e5ff] shadow-[0_0_10px_rgba(0,229,255,0.45)]"
              : "bg-[#3b494c]",
          ].join(" ")}
        />
        <p
          className={[
            "text-sm font-semibold",
            isActive ? "text-[#c3f5ff]" : "text-[#bac9cc]",
          ].join(" ")}
        >
          {label}
        </p>
      </div>
      <p className="mt-3 text-xs leading-5 text-[#849396]">{description}</p>
    </div>
  );
}

function NoticePanel({ children }) {
  return (
    <div className="mt-6 rounded border border-[#3b494c] bg-[#192122]/90 px-4 py-3 text-sm text-[#bac9cc]">
      {children}
    </div>
  );
}

function ErrorPanel({ children }) {
  return (
    <div className="mt-6 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      {children}
    </div>
  );
}

function DashboardHeader() {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p className="muted-label">Operational overview</p>
        <h1 className="page-title mt-2">Security Overview</h1>
        <p className="page-subtitle">
          Monitor application activity, anomaly signals, and analyst triage in one
          place.
        </p>
      </div>

      <div className="rounded border border-[#3b494c] bg-[#192122]/80 px-4 py-3">
        <p className="muted-label">Current mode</p>
        <p className="mt-1 text-sm font-semibold text-[#c3f5ff]">
          Live API data
        </p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { selectedFileId } = useFileContext();
  const [summary, setSummary] = useState(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState("");

  useEffect(() => {
    async function loadSummary() {
      if (!selectedFileId) {
        setSummary(null);
        return;
      }

      setIsLoadingSummary(true);
      setSummaryError("");

      try {
        const summaryData = await getSummary(selectedFileId);
        setSummary(summaryData);
      } catch (error) {
        const detail = error.response?.data?.detail;
        setSummaryError(detail || "Could not load dashboard summary.");
      } finally {
        setIsLoadingSummary(false);
      }
    }

    loadSummary();
  }, [selectedFileId]);

  const metrics = useMemo(
    () => [
      { label: "Total Logs", value: summary?.total_logs },
      { label: "Unique IPs", value: summary?.unique_ips },
      { label: "Total Incidents", value: summary?.total_incidents },
      { label: "Open Incidents", value: summary?.open_incidents },
      { label: "High Incidents", value: summary?.high_incidents },
      { label: "Critical Incidents", value: summary?.critical_incidents },
      { label: "Max Risk Score", value: summary?.max_risk_score },
      { label: "Avg ML Score", value: summary?.avg_ml_anomaly_score },
    ],
    [summary]
  );

  const hasLogs = Number(summary?.total_logs || 0) > 0;
  const hasIncidents = Number(summary?.total_incidents || 0) > 0;

  return (
    <section>
      <DashboardHeader />

      <FileSelector />

      {!selectedFileId ? (
        <NoticePanel>
          Select an uploaded log file to load dashboard metrics.
        </NoticePanel>
      ) : null}

      {isLoadingSummary ? (
        <NoticePanel>Loading dashboard summary...</NoticePanel>
      ) : null}

      {summaryError ? <ErrorPanel>{summaryError}</ErrorPanel> : null}

      {summary ? (
        <>
          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => (
              <MetricCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
              />
            ))}
          </div>

          <div className="panel mt-8">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="muted-label">Pipeline status</p>
                <h2 className="mt-2 text-xl font-semibold text-[#dce4e5]">
                  Analysis progress for file_id {summary.file_id}
                </h2>
              </div>
              <p className="text-sm text-[#849396]">
                Active steps are based only on available summary data.
              </p>
            </div>

            <div className="mt-5 flex flex-col gap-3 xl:flex-row">
              <PipelineStep
                description="Raw log rows are available."
                isActive={hasLogs}
                label="Logs uploaded"
              />
              <PipelineStep
                description="Awaiting feature evidence in this summary."
                isActive={false}
                label="Features generated"
              />
              <PipelineStep
                description="Awaiting ML score evidence in this summary."
                isActive={false}
                label="ML scored"
              />
              <PipelineStep
                description="Incidents exist for this file."
                isActive={hasIncidents}
                label="Incidents generated"
              />
              <PipelineStep
                description="Status review is tracked in Workflow."
                isActive={false}
                label="Analyst triage"
              />
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
