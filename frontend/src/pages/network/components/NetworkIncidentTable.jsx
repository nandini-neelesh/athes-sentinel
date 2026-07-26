import { AlertTriangle, Eye, Workflow } from "lucide-react";

const COUNT_FORMATTER = new Intl.NumberFormat();

const SEVERITY_STYLES = {
  critical: "border-red-400/40 bg-red-500/15 text-red-200",
  high: "border-orange-400/40 bg-orange-500/15 text-orange-200",
  medium: "border-yellow-400/40 bg-yellow-500/15 text-yellow-100",
  low: "border-blue-400/40 bg-blue-500/15 text-blue-200",
};

const STATUS_STYLES = {
  open: "border-cyan-400/40 bg-cyan-500/15 text-cyan-100",
  investigating: "border-amber-400/40 bg-amber-500/15 text-amber-100",
  resolved: "border-green-400/40 bg-green-500/15 text-green-200",
  false_positive: "border-slate-500 bg-slate-700/50 text-slate-200",
};

function humanizeValue(value) {
  if (!value) {
    return "Unknown";
  }

  const normalized = String(value).toLowerCase();
  const benchmarkAcronyms = {
    dos: "DoS",
    r2l: "R2L",
    u2r: "U2R",
  };

  if (benchmarkAcronyms[normalized]) {
    return benchmarkAcronyms[normalized];
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

function formatDate(value) {
  if (!value) {
    return "Not recorded";
  }

  const parsed = new Date(value);

  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleString();
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

function Badge({ children, icon: Icon, style }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        style,
      ].join(" ")}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }) {
  const normalized = String(severity || "unknown").toLowerCase();

  return (
    <Badge
      icon={AlertTriangle}
      style={
        SEVERITY_STYLES[normalized] ||
        "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]"
      }
    >
      {humanizeValue(normalized)}
    </Badge>
  );
}

export function WorkflowBadge({ status }) {
  const normalized = String(status || "unknown").toLowerCase();

  return (
    <Badge
      icon={Workflow}
      style={
        STATUS_STYLES[normalized] ||
        "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]"
      }
    >
      {humanizeValue(normalized)}
    </Badge>
  );
}

function BenchmarkContext({ incident }) {
  if (!incident.actual_label && !incident.actual_family) {
    return null;
  }

  return (
    <div className="mt-2 space-y-0.5 text-xs text-[#849396]">
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
            {humanizeValue(incident.actual_family)}
          </span>
        </p>
      ) : null}
    </div>
  );
}

function MobileIncidentCard({ incident, isSelected, onView }) {
  return (
    <article
      className={[
        "border-l-2 p-4",
        isSelected
          ? "border-l-[#00e5ff] bg-[#00e5ff]/5"
          : "border-l-transparent bg-[#111a1b]/50",
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
        <p className="shrink-0 text-right text-sm font-semibold text-[#9cf0ff]">
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
            className="mt-0.5 break-all text-[#bac9cc]"
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
        className="mt-3 line-clamp-3 text-sm leading-6 text-[#849396]"
        title={incident.evidence_preview}
      >
        {incident.evidence_preview || "No evidence preview was supplied."}
      </p>

      <BenchmarkContext incident={incident} />

      <div className="mt-4 flex items-center justify-between gap-3">
        <p className="text-xs text-[#708083]">
          {formatDate(incident.created_at)}
        </p>
        <button
          className="inline-flex shrink-0 items-center gap-2 rounded border border-[#00e5ff]/35 bg-[#00e5ff]/5 px-3 py-2 text-xs font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
          onClick={() => onView(incident.incident_id)}
          type="button"
        >
          <Eye className="h-4 w-4" aria-hidden="true" />
          View details
        </button>
      </div>
    </article>
  );
}

export default function NetworkIncidentTable({
  incidents,
  onView,
  selectedIncidentId,
}) {
  return (
    <>
      <div className="divide-y divide-[#3b494c] lg:hidden">
        {incidents.map((incident) => (
          <MobileIncidentCard
            incident={incident}
            isSelected={incident.incident_id === selectedIncidentId}
            key={incident.incident_id}
            onView={onView}
          />
        ))}
      </div>

      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full min-w-[1280px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-[#3b494c] bg-[#111a1b] text-[11px] uppercase tracking-[0.12em] text-[#849396]">
              <th className="px-4 py-3 font-semibold" scope="col">
                Incident
              </th>
              <th className="px-4 py-3 font-semibold" scope="col">
                Severity / workflow
              </th>
              <th className="px-4 py-3 font-semibold" scope="col">
                Network context
              </th>
              <th className="px-4 py-3 font-semibold" scope="col">
                Evidence preview
              </th>
              <th className="px-4 py-3 text-right font-semibold" scope="col">
                Risk / probability
              </th>
              <th className="px-4 py-3 font-semibold" scope="col">
                Created
              </th>
              <th className="px-4 py-3 text-right font-semibold" scope="col">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#3b494c]">
            {incidents.map((incident) => (
              <tr
                className={[
                  "border-l-2 transition",
                  incident.incident_id === selectedIncidentId
                    ? "border-l-[#00e5ff] bg-[#00e5ff]/5"
                    : "border-l-transparent hover:bg-[#242b2d]/40",
                ].join(" ")}
                key={incident.incident_id}
              >
                <th className="px-4 py-4 align-top" scope="row">
                  <p className="font-semibold text-[#dce4e5]">
                    #{incident.incident_id}
                  </p>
                  <p className="mt-1 text-xs font-normal text-[#849396]">
                    Source row {formatCount(incident.row_number)}
                  </p>
                  <p
                    className="mt-2 max-w-[180px] truncate text-xs font-normal text-[#708083]"
                    title={incident.incident_type}
                  >
                    {incident.incident_type}
                  </p>
                </th>
                <td className="space-y-2 px-4 py-4 align-top">
                  <SeverityBadge severity={incident.severity} />
                  <div>
                    <WorkflowBadge status={incident.status} />
                  </div>
                </td>
                <td className="max-w-[190px] px-4 py-4 align-top text-xs text-[#bac9cc]">
                  <p>Protocol: {incident.protocol_type || "Not supplied"}</p>
                  <p
                    className="mt-1 truncate"
                    title={incident.service || ""}
                  >
                    Service: {incident.service || "Not supplied"}
                  </p>
                  <p className="mt-1">Flag: {incident.flag || "Not supplied"}</p>
                  <BenchmarkContext incident={incident} />
                </td>
                <td className="max-w-[300px] px-4 py-4 align-top">
                  <p
                    className="line-clamp-3 text-xs leading-5 text-[#849396]"
                    title={incident.evidence_preview}
                  >
                    {incident.evidence_preview ||
                      "No evidence preview was supplied."}
                  </p>
                </td>
                <td className="px-4 py-4 text-right align-top">
                  <p className="font-semibold text-[#9cf0ff]">
                    {formatRisk(incident.risk_score)}
                  </p>
                  <p className="mt-1 text-xs text-[#849396]">
                    Probability{" "}
                    {formatProbability(incident.rf_attack_probability)}
                  </p>
                </td>
                <td className="max-w-[150px] px-4 py-4 align-top text-xs text-[#849396]">
                  {formatDate(incident.created_at)}
                </td>
                <td className="px-4 py-4 text-right align-top">
                  <button
                    className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                    onClick={() => onView(incident.incident_id)}
                    type="button"
                  >
                    <Eye className="h-4 w-4" aria-hidden="true" />
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
