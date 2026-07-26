import { ArrowRight, Database, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { useNetworkDataset } from "../../context/NetworkDatasetContext.jsx";

export function NetworkPageScaffold({
  children,
  description,
  eyebrow,
  title,
}) {
  const {
    selectedDataset,
    isLoadingDatasets,
    datasetsError,
  } = useNetworkDataset();

  return (
    <section className="space-y-5">
      <div>
        <p className="muted-label">{eyebrow}</p>
        <h1 className="page-title mt-2">{title}</h1>
        <p className="page-subtitle max-w-3xl">{description}</p>
      </div>

      <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20">
        <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
          <div className="flex items-center gap-2">
            <ShieldCheck
              className="h-4 w-4 text-[#00e5ff]"
              aria-hidden="true"
            />
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#dce4e5]">
              Persisted network workspace
            </h2>
          </div>
          <p className="mt-1 text-xs text-[#849396]">
            NSL-KDD network mode is connected to the authenticated persisted backend.
          </p>
        </div>

        <div className="space-y-4 p-5">
          {isLoadingDatasets ? (
            <div className="rounded border border-[#3b494c] bg-[#111a1b] px-4 py-3 text-sm text-[#bac9cc]">
              Loading uploaded network datasets...
            </div>
          ) : null}

          {datasetsError ? (
            <div className="rounded border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {datasetsError}
            </div>
          ) : null}

          {!isLoadingDatasets && selectedDataset ? (
            <div className="flex flex-col gap-3 rounded border border-[#00e5ff]/25 bg-[#00e5ff]/5 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <Database
                  className="h-5 w-5 shrink-0 text-[#9cf0ff]"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[#849396]">
                    Selected network dataset
                  </p>
                  <p className="mt-1 truncate font-semibold text-[#dce4e5]">
                    {selectedDataset.filename}
                  </p>
                </div>
              </div>
              <span className="shrink-0 rounded-full border border-[#3b494c] bg-[#0d1516] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9cf0ff]">
                {selectedDataset.analysis_status}
              </span>
            </div>
          ) : null}

          {!isLoadingDatasets && !selectedDataset ? (
            <div className="rounded border border-dashed border-[#3b494c] bg-[#111a1b] px-4 py-5 text-sm text-[#849396]">
              No network datasets have been uploaded yet.
            </div>
          ) : null}

          {children}
        </div>
      </div>
    </section>
  );
}

export default function NetworkOverview() {
  return (
    <NetworkPageScaffold
      eyebrow="Network IDS workspace"
      title="Network Intrusion Overview"
      description="The foundation for reviewing persisted NSL-KDD-compatible datasets, frozen-model results, and analyst workflow."
    >
      <div className="flex flex-wrap gap-3">
        <Link
          className="inline-flex items-center gap-2 rounded border border-[#00e5ff]/40 bg-[#00e5ff]/10 px-4 py-2 text-sm font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff]"
          to="/network/upload"
        >
          Upload workspace
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
        <Link
          className="inline-flex items-center gap-2 rounded border border-[#3b494c] px-4 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff]"
          to="/network/analytics"
        >
          Analytics foundation
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </NetworkPageScaffold>
  );
}
