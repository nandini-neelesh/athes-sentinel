import { NetworkPageScaffold } from "./NetworkOverview.jsx";

export default function NetworkIncidents() {
  return (
    <NetworkPageScaffold
      eyebrow="Persisted network findings"
      title="Network Incident Queue"
      description="This protected route is connected to the persisted network-incident API foundation and awaits the detailed queue interface."
    >
      <p className="text-sm leading-6 text-[#849396]">
        Incident filters, pagination, evidence detail, and analyst actions will
        be added without fabricating network identities or attack families.
      </p>
    </NetworkPageScaffold>
  );
}
