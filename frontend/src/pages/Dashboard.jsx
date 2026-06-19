const metrics = [
  { label: "Total Logs", value: "--" },
  { label: "Unique IPs", value: "--" },
  { label: "Total Incidents", value: "--" },
  { label: "Open Incidents", value: "--" },
];

export default function Dashboard() {
  return (
    <section>
      <h1 className="page-title">Dashboard</h1>
      <p className="page-subtitle">Security monitoring overview</p>

      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="panel">
            <p className="muted-label">{metric.label}</p>
            <p className="mt-3 text-3xl font-bold text-slate-50">{metric.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
