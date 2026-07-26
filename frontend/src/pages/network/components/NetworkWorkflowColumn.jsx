import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  Search,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import {
  SeverityBadge,
  WorkflowBadge,
} from "./NetworkIncidentTable.jsx";

const COUNT_FORMATTER = new Intl.NumberFormat();

const STATUS_PRESENTATION = {
  open: {
    accent: "border-t-cyan-400",
    icon: AlertTriangle,
    iconClass: "text-cyan-300",
    title: "Open",
  },
  investigating: {
    accent: "border-t-amber-400",
    icon: Search,
    iconClass: "text-amber-300",
    title: "Investigating",
  },
  resolved: {
    accent: "border-t-green-400",
    icon: CheckCircle2,
    iconClass: "text-green-300",
    title: "Resolved",
  },
  false_positive: {
    accent: "border-t-slate-400",
    icon: X,
    iconClass: "text-slate-300",
    title: "False positive",
  },
};

function formatCount(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return COUNT_FORMATTER.format(value);
}

function formatProbability(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return Number(value).toFixed(4);
}

function formatRisk(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${Number(value).toFixed(1)} / 100`;
}

function humanizeBenchmarkFamily(value) {
  const normalized = String(value || "").toLowerCase();
  const labels = {
    normal: "Normal",
    dos: "DoS",
    probe: "Probe",
    r2l: "R2L",
    u2r: "U2R",
  };

  return labels[normalized] || value;
}

function WorkflowCard({ incident, isSelected, onView }) {
  return (
    <article
      className={[
        "rounded border p-3 transition",
        isSelected
          ? "border-[#00e5ff] bg-[#00e5ff]/10"
          : "border-[#3b494c] bg-[#111a1b]/80 hover:border-[#536164]",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[#dce4e5]">
            Incident #{incident.incident_id}
          </p>
          <p className="mt-1 text-xs text-[#849396]">
            Source row {formatCount(incident.row_number)}
          </p>
        </div>
        <p className="shrink-0 text-right text-xs font-semibold text-[#9cf0ff]">
          Risk {formatRisk(incident.risk_score)}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <SeverityBadge severity={incident.severity} />
        <WorkflowBadge status={incident.status} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-[#708083]">Protocol</dt>
          <dd className="mt-0.5 break-all text-[#bac9cc]">
            {incident.protocol_type || "Not supplied"}
          </dd>
        </div>
        <div>
          <dt className="text-[#708083]">Service</dt>
          <dd
            className="mt-0.5 truncate text-[#bac9cc]"
            title={incident.service || ""}
          >
            {incident.service || "Not supplied"}
          </dd>
        </div>
        <div>
          <dt className="text-[#708083]">Flag</dt>
          <dd className="mt-0.5 text-[#bac9cc]">
            {incident.flag || "Not supplied"}
          </dd>
        </div>
        <div>
          <dt className="text-[#708083]">Attack probability</dt>
          <dd className="mt-0.5 text-[#bac9cc]">
            {formatProbability(incident.rf_attack_probability)}
          </dd>
        </div>
      </dl>

      <p
        className="mt-3 line-clamp-3 text-xs leading-5 text-[#849396]"
        title={incident.evidence_preview}
      >
        {incident.evidence_preview || "No evidence preview was supplied."}
      </p>

      {incident.actual_label || incident.actual_family ? (
        <div className="mt-3 rounded border border-[#3b494c] bg-[#0d1516]/70 px-2.5 py-2 text-[11px] leading-5 text-[#849396]">
          {incident.actual_label ? (
            <p>
              Benchmark actual label:{" "}
              <span className="text-[#bac9cc]">{incident.actual_label}</span>
            </p>
          ) : null}
          {incident.actual_family ? (
            <p>
              Benchmark family:{" "}
              <span className="text-[#bac9cc]">
                {humanizeBenchmarkFamily(incident.actual_family)}
              </span>
            </p>
          ) : null}
        </div>
      ) : null}

      <button
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
        onClick={() => onView(incident.incident_id)}
        type="button"
      >
        <Eye className="h-4 w-4" aria-hidden="true" />
        View and update
      </button>
    </article>
  );
}

export default function NetworkWorkflowColumn({
  error,
  group,
  hasActiveFilters,
  isLoading,
  onRetry,
  onView,
  selectedIncidentId,
  status,
}) {
  const presentation = STATUS_PRESENTATION[status];
  const Icon = presentation.icon;
  const incidents = Array.isArray(group?.items) ? group.items : [];
  const total = Number(group?.total || 0);
  const hasMore = total > incidents.length;

  return (
    <section
      className={[
        "flex min-w-0 flex-col overflow-hidden rounded-md border border-t-2 border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20",
        presentation.accent,
      ].join(" ")}
    >
      <header className="border-b border-[#3b494c] bg-[#242b2d]/60 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Icon
              className={`h-4 w-4 ${presentation.iconClass}`}
              aria-hidden="true"
            />
            <h2 className="text-sm font-semibold text-[#dce4e5]">
              {presentation.title}
            </h2>
          </div>
          <span className="rounded-full border border-[#3b494c] bg-[#111a1b] px-2.5 py-1 text-xs font-semibold text-[#bac9cc]">
            {formatCount(total)}
          </span>
        </div>
        <p className="mt-2 text-xs text-[#849396]">
          Showing {formatCount(incidents.length)} of {formatCount(total)}{" "}
          filtered incidents
        </p>
      </header>

      {isLoading ? (
        <div
          className="flex min-h-[180px] items-center justify-center px-4 text-sm text-[#849396]"
          role="status"
        >
          Loading {presentation.title.toLowerCase()} incidents…
        </div>
      ) : null}

      {error && !isLoading ? (
        <div className="space-y-3 p-4">
          <div
            className="rounded border border-red-400/40 bg-red-500/10 px-3 py-3 text-xs leading-5 text-red-100"
            role="alert"
          >
            {error}
          </div>
          <button
            className="rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            onClick={onRetry}
            type="button"
          >
            Retry workflow groups
          </button>
        </div>
      ) : null}

      {!isLoading && (!error || incidents.length > 0) ? (
        incidents.length > 0 ? (
          <div className="max-h-[720px] space-y-3 overflow-y-auto p-3">
            {incidents.map((incident) => (
              <WorkflowCard
                incident={incident}
                isSelected={incident.incident_id === selectedIncidentId}
                key={incident.incident_id}
                onView={onView}
              />
            ))}
          </div>
        ) : (
          <div className="flex min-h-[180px] flex-col items-center justify-center px-4 py-6 text-center">
            <Icon
              className={`h-7 w-7 ${presentation.iconClass}`}
              aria-hidden="true"
            />
            <p className="mt-2 text-sm font-semibold text-[#dce4e5]">
              {hasActiveFilters
                ? "No matching incidents"
                : `No ${presentation.title.toLowerCase()} incidents`}
            </p>
            <p className="mt-1 text-xs leading-5 text-[#849396]">
              {hasActiveFilters
                ? "No persisted incidents in this status match the active backend filters."
                : "This workflow status currently has no persisted incidents."}
            </p>
          </div>
        )
      ) : null}

      <footer className="mt-auto border-t border-[#3b494c] px-4 py-3">
        {hasMore ? (
          <p className="mb-2 text-xs leading-5 text-amber-100">
            {formatCount(total - incidents.length)} more matching incidents are
            available in the complete paginated queue.
          </p>
        ) : null}
        <Link
          className="inline-flex items-center gap-2 text-xs font-semibold text-[#9cf0ff] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
          to="/network/incidents"
        >
          Open complete incident queue
        </Link>
      </footer>
    </section>
  );
}
