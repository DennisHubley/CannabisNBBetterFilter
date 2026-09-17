// Triggers a Netlify rebuild (which re-scrapes stock data) via a build hook.
// Set the BUILD_HOOK_URL environment variable in the Netlify dashboard.
export default async (req) => {
  if (req.method !== "POST") {
    return new Response("POST only", { status: 405 });
  }
  const hook = process.env.BUILD_HOOK_URL;
  if (!hook) {
    return Response.json(
      { started: false, error: "BUILD_HOOK_URL is not set in this site's environment variables." },
      { status: 500 }
    );
  }
  const r = await fetch(hook, { method: "POST" });
  return Response.json({ started: r.ok }, { status: r.ok ? 200 : 502 });
};
