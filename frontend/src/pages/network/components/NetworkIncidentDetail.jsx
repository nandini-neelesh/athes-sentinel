import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  SeverityBadge,
  WorkflowBadge,
} from "./NetworkIncidentTable.jsx";

const STATUS_OPTIONS = [
  { label: "Open", value: "open" },
  { label: "Investigating", value: "investigating" },
  { label: "Resolved", value: "resolved" },
  { label: "False positive", value: "false_positive" },
];

const CONNECTION_RATE_FIELDS = [
  ["SYN error rate", "serror_rate"],
  ["Service SYN error rate", "srv_serror_rate"],
  ["REJ error rate", "rerror_rate"],
  ["Service REJ error rate", "srv_rerror_rate"],
  ["Same service rate", "same_srv_rate"],
  ["Different service rate", "diff_srv_rate"],
  ["Service different host rate", "srv_diff_host_rate"],
];

const DESTINATION_HOST_FIELDS = [
  ["Destination host count", "dst_host_count"],
  ["Destination host service count", "dst_host_srv_count"],
  ["Destination host same service rate", "dst_host_same_srv_rate"],
  ["Destination host different service rate", "dst_host_diff_srv_rate"],
  [
    "Destination host same source-port rate",
    "dst_host_same_src_port_rate",
  ],
  [
    "Destination host service different-host rate",
    "dst_host_srv_diff_host_rate",
  ],
  ["Destination host SYN error rate", "dst_host_serror_rate"],
  [
    "Destination host service SYN error rate",
    "dst_host_srv_serror_rate",
  ],
  ["Destination host REJ error rate", "dst_host_rerror_rate"],
  [
    "Destination host service REJ error rate",
    "dst_host_srv_rerror_rate",
  ],
];

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

function formatFlowValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Not supplied";
  }

  return String(value);
}

function shortenVersion(value) {
  if (!value) {
    return "Not recorded";
  }

  const version = String(value);

  return version.length > 24
    ? `${version.slice(0, 12)}…${version.slice(-8)}`
    : version;
}

function DetailField({ label, title, value }) {
  return (
    <div className="min-w-0 rounded border border-[#3b494c] bg-[#111a1b]/80 px-3 py-3">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#708083]">
        {label}
      </dt>
      <dd
        className="mt-1 break-words text-sm text-[#dce4e5]"
        title={title || ""}
      >
        {value}
      </dd>
    </div>
  );
}

function ErrorNotice({ children }) {
  return (
    <div
      className="flex items-start gap-3 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-100"
      role="alert"
    >
      <AlertTriangle
        className="mt-0.5 h-4 w-4 shrink-0 text-red-300"
        aria-hidden="true"
      />
      <span className="leading-6">{children}</span>
    </div>
  );
}

function FlowFieldGroup({ fields, flow, title }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-[#dce4e5]">{title}</h3>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {fields.map(([label, key]) => (
          <DetailField
            key={key}
            label={label}
            value={formatFlowValue(flow?.[key])}
          />
        ))}
      </dl>
    </section>
  );
}

export default function NetworkIncidentDetail({
  detail,
  detailError,
  incidentId,
  isLoading,
  isUpdating,
  onClose,
  onRetry,
  onUpdateStatus,
  updateError,
  updateSuccess,
}) {
  const [pendingStatus, setPendingStatus] = useState("");
  const closeButtonRef = useRef(null);

  useEffect(() => {
    setPendingStatus(detail?.status || "");
  }, [detail?.status, incidentId]);

  useEffect(() => {
    if (!incidentId) {
      return undefined;
    }

    closeButtonRef.current?.focus();

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleEscape);

    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [incidentId, onClose]);

  if (!incidentId) {
    return null;
  }

  const prediction = detail?.prediction;
  const flow = detail?.flow_context;
  const hasBenchmarkPrediction =
    prediction?.actual_binary !== null &&
    prediction?.actual_binary !== undefined;
  const hasBenchmarkFlow = Boolean(
    flow?.actual_label ||
      flow?.actual_family ||
      (flow?.difficulty_level !== null &&
        flow?.difficulty_level !== undefined)
  );
  const statusUnchanged = pendingStatus === detail?.status;

  return (
    <div
      aria-labelledby="network-incident-detail-title"
      aria-modal="true"
      className="fixed inset-0 z-50 flex justify-end bg-black/70"
      role="dialog"
    >
      <button
        aria-label="Close incident details"
        className="absolute inset-0 cursor-default disabled:cursor-wait"
        disabled={isUpdating}
        onClick={onClose}
        type="button"
      />

      <aside className="relative flex h-full w-full max-w-3xl flex-col border-l border-[#3b494c] bg-[#111a1b] shadow-2xl shadow-black">
        <header className="flex items-start justify-between gap-4 border-b border-[#3b494c] bg-[#192122] px-5 py-4">
          <div className="min-w-0">
            <p className="muted-label">Persisted network incident</p>
            <h2
              className="mt-1 truncate text-xl font-semibold text-[#dce4e5]"
              id="network-incident-detail-title"
            >
              Incident #{incidentId}
            </h2>
          </div>
          <button
            aria-label="Close incident details"
            className="rounded border border-[#3b494c] p-2 text-[#bac9cc] transition hover:border-[#00daf3] hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-wait disabled:opacity-50"
            disabled={isUpdating}
            onClick={onClose}
            ref={closeButtonRef}
            type="button"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {isLoading ? (
            <div
              className="flex min-h-[320px] items-center justify-center gap-3 p-6 text-sm text-[#bac9cc]"
              role="status"
            >
              <Loader2
                className="h-5 w-5 animate-spin text-[#9cf0ff]"
                aria-hidden="true"
              />
              Loading persisted incident details…
            </div>
          ) : null}

          {detailError && !isLoading ? (
            <div className="space-y-4 p-5">
              <ErrorNotice>{detailError}</ErrorNotice>
              <button
                className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                onClick={onRetry}
                type="button"
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Retry detail
              </button>
            </div>
          ) : null}

          {detail && !isLoading ? (
            <div className="space-y-6 p-5">
              <section>
                <div className="flex flex-col gap-4 rounded border border-[#3b494c] bg-[#192122]/80 p-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-lg font-semibold text-[#dce4e5]">
                      {detail.incident_type}
                    </p>
                    <p className="mt-1 text-xs text-[#849396]">
                      Created {formatDate(detail.created_at)}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <SeverityBadge severity={detail.severity} />
                      <WorkflowBadge status={detail.status} />
                    </div>
                  </div>
                  <div className="shrink-0 rounded border border-[#00e5ff]/30 bg-[#00e5ff]/5 px-4 py-3 sm:text-right">
                    <p className="muted-label">Analyst risk score</p>
                    <p className="mt-1 text-2xl font-semibold text-[#9cf0ff]">
                      {formatRisk(detail.risk_score)}
                    </p>
                  </div>
                </div>

                <dl className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <DetailField label="Incident ID" value={detail.incident_id} />
                  <DetailField label="Dataset ID" value={detail.dataset_id} />
                  <DetailField label="Source row" value={detail.row_number} />
                  <DetailField label="Flow ID" value={detail.flow_id} />
                  <DetailField
                    label="Prediction ID"
                    value={detail.prediction_id}
                  />
                  <DetailField
                    label="Attack probability"
                    value={`${formatProbability(
                      detail.rf_attack_probability
                    )} (0–1)`}
                  />
                </dl>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-[#dce4e5]">
                  Model evidence
                </h3>
                <p className="mt-2 whitespace-pre-wrap rounded border border-[#3b494c] bg-[#0d1516] p-4 text-sm leading-6 text-[#bac9cc]">
                  {detail.evidence}
                </p>
                <p className="mt-3 text-xs leading-5 text-[#708083]">
                  This is persisted binary model-triage evidence, not proof that
                  the connection is malicious and not a predicted attack family.
                </p>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-[#dce4e5]">
                  Recommended analyst action
                </h3>
                <p className="mt-2 whitespace-pre-wrap rounded border border-[#3b494c] bg-[#0d1516] p-4 text-sm leading-6 text-[#bac9cc]">
                  {detail.recommended_action}
                </p>
              </section>

              <section>
                <div className="flex items-center gap-2">
                  <ShieldCheck
                    className="h-4 w-4 text-[#9cf0ff]"
                    aria-hidden="true"
                  />
                  <h3 className="text-sm font-semibold text-[#dce4e5]">
                    Frozen binary prediction
                  </h3>
                </div>
                <dl className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <DetailField
                    label="Predicted class"
                    value={prediction?.predicted_class || "Not supplied"}
                  />
                  <DetailField
                    label="Attack probability"
                    value={`${formatProbability(
                      prediction?.rf_attack_probability
                    )} (0–1)`}
                  />
                  <DetailField
                    label="Threshold used"
                    value={`${formatProbability(
                      prediction?.threshold_used_probability
                    )} (0–1)`}
                  />
                  <DetailField
                    label="Model name"
                    value={prediction?.model_name || "Not supplied"}
                  />
                  <DetailField
                    label="Model version"
                    title={prediction?.model_version}
                    value={shortenVersion(prediction?.model_version)}
                  />
                  {hasBenchmarkPrediction ? (
                    <DetailField
                      label="Benchmark actual binary"
                      value={
                        prediction.actual_binary === 1
                          ? "1 (attack)"
                          : "0 (normal)"
                      }
                    />
                  ) : null}
                  {prediction?.is_correct !== null &&
                  prediction?.is_correct !== undefined ? (
                    <DetailField
                      label="Benchmark correctness"
                      value={prediction.is_correct ? "Correct" : "Incorrect"}
                    />
                  ) : null}
                </dl>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-[#dce4e5]">
                  Original network flow context
                </h3>
                <p className="mt-1 text-xs leading-5 text-[#708083]">
                  Original stored values are shown without one-hot encoded
                  features or fabricated network identities.
                </p>
                <dl className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <DetailField
                    label="Source row"
                    value={formatFlowValue(flow?.row_number)}
                  />
                  <DetailField
                    label="Duration"
                    value={formatFlowValue(flow?.duration)}
                  />
                  <DetailField
                    label="Protocol"
                    value={formatFlowValue(flow?.protocol_type)}
                  />
                  <DetailField
                    label="Service"
                    title={flow?.service}
                    value={formatFlowValue(flow?.service)}
                  />
                  <DetailField
                    label="Connection flag"
                    value={formatFlowValue(flow?.flag)}
                  />
                  <DetailField
                    label="Source bytes"
                    value={formatFlowValue(flow?.src_bytes)}
                  />
                  <DetailField
                    label="Destination bytes"
                    value={formatFlowValue(flow?.dst_bytes)}
                  />
                  <DetailField
                    label="Failed login count"
                    value={formatFlowValue(flow?.num_failed_logins)}
                  />
                  <DetailField
                    label="Logged-in indicator"
                    value={formatFlowValue(flow?.logged_in)}
                  />
                  <DetailField
                    label="Connection count"
                    value={formatFlowValue(flow?.count)}
                  />
                  <DetailField
                    label="Service count"
                    value={formatFlowValue(flow?.srv_count)}
                  />
                </dl>
              </section>

              <FlowFieldGroup
                fields={CONNECTION_RATE_FIELDS}
                flow={flow}
                title="Connection and error-rate features"
              />

              <FlowFieldGroup
                fields={DESTINATION_HOST_FIELDS}
                flow={flow}
                title="Destination-host context"
              />

              {hasBenchmarkFlow ? (
                <section>
                  <h3 className="text-sm font-semibold text-[#dce4e5]">
                    Supplied benchmark context
                  </h3>
                  <p className="mt-1 text-xs leading-5 text-[#708083]">
                    These fields are actual benchmark truth, not predicted
                    attack families.
                  </p>
                  <dl className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {flow?.actual_label ? (
                      <DetailField
                        label="Benchmark actual label"
                        value={flow.actual_label}
                      />
                    ) : null}
                    {flow?.actual_family ? (
                      <DetailField
                        label="Benchmark family"
                        value={flow.actual_family}
                      />
                    ) : null}
                    {flow?.difficulty_level !== null &&
                    flow?.difficulty_level !== undefined ? (
                      <DetailField
                        label="Benchmark difficulty level"
                        value={flow.difficulty_level}
                      />
                    ) : null}
                  </dl>
                </section>
              ) : null}

              <section className="rounded border border-[#3b494c] bg-[#192122]/80 p-4">
                <h3 className="text-sm font-semibold text-[#dce4e5]">
                  Analyst workflow status
                </h3>
                <p className="mt-1 text-xs leading-5 text-[#708083]">
                  This changes only the persisted workflow status. It does not
                  retrain the model, block traffic, or alter evidence.
                </p>

                <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                  <label className="block">
                    <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#bac9cc]">
                      Status
                    </span>
                    <select
                      className="mt-1.5 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2.5 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={isUpdating}
                      onChange={(event) =>
                        setPendingStatus(event.target.value)
                      }
                      value={pendingStatus}
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="inline-flex items-center justify-center gap-2 rounded border border-[#00e5ff]/45 bg-[#00e5ff]/10 px-4 py-2.5 text-sm font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={
                      isUpdating || !pendingStatus || statusUnchanged
                    }
                    onClick={() => onUpdateStatus(pendingStatus)}
                    type="button"
                  >
                    {isUpdating ? (
                      <Loader2
                        className="h-4 w-4 animate-spin"
                        aria-hidden="true"
                      />
                    ) : (
                      <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                    )}
                    {isUpdating ? "Saving status…" : "Save status"}
                  </button>
                </div>

                {statusUnchanged && !isUpdating ? (
                  <p className="mt-2 text-xs text-[#708083]">
                    Choose a different status to enable the update.
                  </p>
                ) : null}

                {updateError ? (
                  <div className="mt-3">
                    <ErrorNotice>{updateError}</ErrorNotice>
                  </div>
                ) : null}

                {updateSuccess ? (
                  <div
                    className="mt-3 flex items-start gap-3 rounded border border-green-400/35 bg-green-500/10 px-4 py-3 text-sm text-green-100"
                    role="status"
                  >
                    <CheckCircle2
                      className="mt-0.5 h-4 w-4 shrink-0 text-green-300"
                      aria-hidden="true"
                    />
                    {updateSuccess}
                  </div>
                ) : null}
              </section>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
