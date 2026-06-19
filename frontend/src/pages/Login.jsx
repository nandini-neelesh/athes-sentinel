export default function Login() {
  return (
    <section className="flex min-h-[70vh] items-center justify-center">
      <div className="panel w-full max-w-md">
        <h1 className="text-2xl font-bold text-slate-50">Login</h1>
        <p className="mt-2 text-sm text-slate-400">
          Sign in to access the Athes Sentinel workspace.
        </p>

        <form className="mt-6 space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-300">Username</span>
            <input
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-50 outline-none transition focus:border-cyan-400"
              name="username"
              placeholder="admin"
              type="text"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-300">Password</span>
            <input
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-50 outline-none transition focus:border-cyan-400"
              name="password"
              placeholder="admin123"
              type="password"
            />
          </label>

          <button className="primary-button w-full" type="button">
            Sign in
          </button>
        </form>
      </div>
    </section>
  );
}
