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

function MetricCard({ label, value }) {
  return (
    <div className="panel">
      <p className="muted-label">{label}</p>
      <p className="mt-3 text-3xl font-bold text-cyan-300">
        {formatMetricValue(value)}
      </p>
    </div>
  );
}

function PipelineStep({ isActive, label, description }) {
  return (
    <div className="flex gap-3 rounded-lg border border-slate-700 bg-slate-900/60 p-3">
      <div
        className={[
          "mt-1 h-3 w-3 shrink-0 rounded-full",
          isActive ? "bg-cyan-400 shadow-lg shadow-cyan-400/30" : "bg-slate-600",
        ].join(" ")}
      />
      <div>
        <p className="text-sm font-semibold text-slate-100">{label}</p>
        <p className="mt-1 text-xs text-slate-500">{description}</p>
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
      <h1 className="page-title">Dashboard</h1>
      <p className="page-subtitle">Security monitoring overview</p>

      <FileSelector />

      {!selectedFileId ? (
        <div className="panel mt-6">
          <p className="text-sm text-slate-400">
            Select an uploaded log file to load dashboard metrics.
          </p>
        </div>
      ) : null}

      {isLoadingSummary ? (
        <div className="panel mt-6">
          <p className="text-sm text-slate-300">Loading dashboard summary...</p>
        </div>
      ) : null}

      {summaryError ? (
        <div className="mt-6 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {summaryError}
        </div>
      ) : null}

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
            <div className="flex flex-col gap-1">
              <p className="muted-label">Pipeline status</p>
              <h2 className="text-xl font-semibold text-slate-50">
                Analysis progress for file_id {summary.file_id}
              </h2>
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-5">
              <PipelineStep
                description="Raw log rows are available."
                isActive={hasLogs}
                label="Logs uploaded"
              />
              <PipelineStep
                description="Run feature generation before ML."
                isActive={false}
                label="Features generated"
              />
              <PipelineStep
                description="Run Isolation Forest after features."
                isActive={false}
                label="ML scored"
              />
              <PipelineStep
                description="Incidents exist for this file."
                isActive={hasIncidents}
                label="Incidents generated"
              />
              <PipelineStep
                description="Use status updates during review."
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
