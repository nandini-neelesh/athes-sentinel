import { NetworkPageScaffold } from "./NetworkOverview.jsx";

export default function NetworkAnalytics() {
  return (
    <NetworkPageScaffold
      eyebrow="Persisted detector analytics"
      title="Network Analytics"
      description="This route is ready for persisted prediction, protocol, service, severity, and benchmark visualizations in a later phase."
    >
      <p className="text-sm leading-6 text-[#849396]">
        Detailed charts are intentionally deferred. No placeholder metrics or
        synthetic network results are shown.
      </p>
    </NetworkPageScaffold>
  );
}
