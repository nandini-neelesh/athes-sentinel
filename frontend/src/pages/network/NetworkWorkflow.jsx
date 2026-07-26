import { NetworkPageScaffold } from "./NetworkOverview.jsx";

export default function NetworkWorkflow() {
  return (
    <NetworkPageScaffold
      eyebrow="Analyst triage workspace"
      title="Network Analyst Workflow"
      description="The authenticated workflow route is ready for persisted open, investigating, resolved, and false-positive incident states."
    >
      <p className="text-sm leading-6 text-[#849396]">
        Status controls and incident workflow views are intentionally reserved
        for the detailed implementation phase.
      </p>
    </NetworkPageScaffold>
  );
}
