import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
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
  getErrorRateByEndpoint,
  getHourlyTraffic,
  getSlowestEndpoints,
  getStatusCodeDistribution,
  getTopEndpoints,
  getTopIps,
} from "../api/analytics.js";
import FileSelector from "../components/FileSelector.jsx";
import { useFileContext } from "../context/FileContext.jsx";

const PIE_COLORS = ["#22d3ee", "#3b82f6", "#f97316", "#ef4444", "#a855f7"];
const GRID_COLOR = "#334155";
const TEXT_COLOR = "#cbd5e1";

const EMPTY_ANALYTICS = {
  statusCodes: [],
  topIps: [],
  hourlyTraffic: [],
  topEndpoints: [],
  slowestEndpoints: [],
  errorRates: [],
};

function getErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "Could not load analytics data. Check that the backend is running.";
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function ChartPanel({ children, description, isEmpty, title }) {
  return (
    <div className="panel min-h-[360px]">
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-slate-50">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm text-slate-400">{description}</p>
        ) : null}
      </div>

      {isEmpty ? (
        <div className="flex h-[260px] items-center justify-center rounded-xl border border-slate-700 bg-slate-950/30 text-sm text-slate-400">
          No data available.
        </div>
      ) : (
        <div className="h-[280px]">{children}</div>
      )}
    </div>
  );
}

function DarkTooltip({ active, label, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm shadow-xl">
      {label ? <p className="mb-1 font-medium text-slate-100">{label}</p> : null}
      {payload.map((item) => (
        <p key={item.dataKey} style={{ color: item.color || "#22d3ee" }}>
          {item.name || item.dataKey}: {item.value}
        </p>
      ))}
    </div>
  );
}

function ErrorRateTooltip({ active, label, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const item = payload[0];

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm shadow-xl">
      <p className="mb-1 font-medium text-slate-100">{label}</p>
      <p className="text-red-300">Error rate: {formatPercent(item.value)}</p>
      <p className="text-slate-400">
        Errors: {item.payload.error_count} / {item.payload.total_count}
      </p>
    </div>
  );
}

export default function Analytics() {
  const { selectedFileId } = useFileContext();
  const [analyticsData, setAnalyticsData] = useState(EMPTY_ANALYTICS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selectedFileId) {
      setAnalyticsData(EMPTY_ANALYTICS);
      return;
    }

    let shouldIgnoreResult = false;

    async function loadAnalytics() {
      setIsLoading(true);
      setError("");

      try {
        const [
          statusCodes,
          topIps,
          hourlyTraffic,
          topEndpoints,
          slowestEndpoints,
          errorRates,
        ] = await Promise.all([
          getStatusCodeDistribution(selectedFileId),
          getTopIps(selectedFileId),
          getHourlyTraffic(selectedFileId),
          getTopEndpoints(selectedFileId),
          getSlowestEndpoints(selectedFileId),
          getErrorRateByEndpoint(selectedFileId),
        ]);

        if (!shouldIgnoreResult) {
          setAnalyticsData({
            statusCodes,
            topIps,
            hourlyTraffic,
            topEndpoints,
            slowestEndpoints,
            errorRates,
          });
        }
      } catch (requestError) {
        if (!shouldIgnoreResult) {
          setError(getErrorMessage(requestError));
          setAnalyticsData(EMPTY_ANALYTICS);
        }
      } finally {
        if (!shouldIgnoreResult) {
          setIsLoading(false);
        }
      }
    }

    loadAnalytics();

    return () => {
      shouldIgnoreResult = true;
    };
  }, [selectedFileId]);

  return (
    <section>
      <h1 className="page-title">Analytics</h1>
      <p className="page-subtitle">
        Traffic patterns, endpoint behavior, and security performance metrics.
      </p>

      <FileSelector />

      {!selectedFileId ? (
        <div className="panel mt-8">
          <p className="text-lg font-semibold text-slate-50">
            Select a log file
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Choose an uploaded file to load traffic and endpoint analytics.
          </p>
        </div>
      ) : null}

      {isLoading ? (
        <div className="panel mt-8">
          <p className="text-lg font-semibold text-slate-50">
            Loading analytics
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Fetching chart datasets for file_id {selectedFileId}.
          </p>
        </div>
      ) : null}

      {error ? (
        <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {selectedFileId && !isLoading && !error ? (
        <div className="mt-8 grid gap-6 xl:grid-cols-2">
          <ChartPanel
            description="Counts grouped by HTTP response code."
            isEmpty={analyticsData.statusCodes.length === 0}
            title="Status Code Distribution"
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={analyticsData.statusCodes}
                  dataKey="count"
                  nameKey="status_code"
                  innerRadius={55}
                  outerRadius={95}
                  paddingAngle={3}
                >
                  {analyticsData.statusCodes.map((entry, index) => (
                    <Cell
                      key={entry.status_code}
                      fill={PIE_COLORS[index % PIE_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend wrapperStyle={{ color: TEXT_COLOR }} />
              </PieChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            description="Most active source IP addresses."
            isEmpty={analyticsData.topIps.length === 0}
            title="Top IPs by Request Count"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analyticsData.topIps}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis
                  dataKey="ip_address"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                  interval={0}
                  angle={-25}
                  textAnchor="end"
                  height={70}
                />
                <YAxis stroke={TEXT_COLOR} tick={{ fill: TEXT_COLOR }} />
                <Tooltip content={<DarkTooltip />} />
                <Bar
                  dataKey="request_count"
                  fill="#22d3ee"
                  name="Requests"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            description="Request volume grouped by hour."
            isEmpty={analyticsData.hourlyTraffic.length === 0}
            title="Hourly Traffic Volume"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={analyticsData.hourlyTraffic}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis
                  dataKey="hour"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                />
                <YAxis stroke={TEXT_COLOR} tick={{ fill: TEXT_COLOR }} />
                <Tooltip content={<DarkTooltip />} />
                <Line
                  type="monotone"
                  dataKey="request_count"
                  stroke="#22d3ee"
                  strokeWidth={3}
                  dot={{ fill: "#22d3ee", r: 4 }}
                  name="Requests"
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            description="Endpoints with the highest request counts."
            isEmpty={analyticsData.topEndpoints.length === 0}
            title="Most Accessed Endpoints"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analyticsData.topEndpoints}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis
                  dataKey="endpoint"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                  interval={0}
                  angle={-25}
                  textAnchor="end"
                  height={80}
                />
                <YAxis stroke={TEXT_COLOR} tick={{ fill: TEXT_COLOR }} />
                <Tooltip content={<DarkTooltip />} />
                <Bar
                  dataKey="request_count"
                  fill="#3b82f6"
                  name="Requests"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            description="Average response time by endpoint."
            isEmpty={analyticsData.slowestEndpoints.length === 0}
            title="Slowest Endpoints"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={analyticsData.slowestEndpoints}
                layout="vertical"
                margin={{ left: 32 }}
              >
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR }}
                  tickFormatter={(value) => `${value} ms`}
                />
                <YAxis
                  dataKey="endpoint"
                  type="category"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                  width={105}
                />
                <Tooltip content={<DarkTooltip />} />
                <Bar
                  dataKey="avg_response_time_ms"
                  fill="#f97316"
                  name="Avg response time ms"
                  radius={[0, 6, 6, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            description="Endpoints sorted by error rate."
            isEmpty={analyticsData.errorRates.length === 0}
            title="Error Rate by Endpoint"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analyticsData.errorRates}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis
                  dataKey="endpoint"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                  interval={0}
                  angle={-25}
                  textAnchor="end"
                  height={80}
                />
                <YAxis
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR }}
                  tickFormatter={formatPercent}
                />
                <Tooltip content={<ErrorRateTooltip />} />
                <Bar
                  dataKey="error_rate"
                  fill="#ef4444"
                  name="Error rate"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>
        </div>
      ) : null}
    </section>
  );
}
