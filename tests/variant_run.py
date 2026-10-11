"""End-to-end test of a variant brief against our own bank mock: start the mock, open a tunnel, build the agent, run the cases.

    .venv/bin/python tests/variant_run.py tests/variants/v1 [--reps 1] [--only NW-01,NW-02]

Needs `cloudflared` on the PATH (a quick tunnel, no account) and the usual env (FREYA_API_KEY, FREYA_BANK_TEAM_KEY). The brief's
API file is rewritten with the tunnel URL as `servers.url` into openapi.tunnel.json, and run_cases.py is pointed at the tunnel
with FREYA_BANK_HOST. The mock's wrong-answer limit comes from the folder's rules.json (max_wrong_total), default 3.
"""
import json, os, pathlib, re, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


def start_tunnel(port):
    proc = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://localhost:" + str(port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 60
    while time.time() < deadline:
        line = proc.stdout.readline()
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line or "")
        if m:
            return proc, m.group(0)
    proc.terminate(); raise SystemExit("no tunnel URL within 60 s")


def main(argv):
    folder = pathlib.Path(argv[0]).resolve()
    extra = argv[1:]
    rules = json.loads((folder / "rules.json").read_text()) if (folder / "rules.json").exists() else {}
    port = 8787
    mock = subprocess.Popen([PY, str(ROOT / "tests" / "mock_bank.py"), str(folder / "cases.json"), "--port", str(port), "--max-wrong", str(rules.get("max_wrong_total", 3))])
    tunnel = None
    try:
        time.sleep(1)
        tunnel, url = start_tunnel(port)
        print("tunnel:", url, flush=True)
        spec = json.loads((folder / "openapi.json").read_text())
        spec["servers"] = [{"url": url + "/v1"}]
        (folder / "openapi.tunnel.json").write_text(json.dumps(spec, indent=1))
        briefs = [str(p) for p in sorted(folder.glob("*.md"))]
        env = dict(os.environ, FREYA_BANK_HOST=url); env.pop("CLAUDECODE", None)
        out = subprocess.run([PY, str(ROOT / "builder" / "build.py")] + briefs + [str(folder / "openapi.tunnel.json")], env=env, capture_output=True, text=True)
        print("\n".join(l for l in out.stdout.splitlines() if l.startswith(("{", "0", "1", "2")))[-1200:], flush=True)
        if not out.stdout.strip().endswith("}"):                      # the build died before its summary line: show why
            print(out.stderr[-2000:], flush=True); raise SystemExit("build failed, no agent to run")
        agent = json.loads(out.stdout.strip().splitlines()[-1])["agent_id"]
        subprocess.run([PY, str(ROOT / "tools" / "run_cases.py"), agent, "--cases", str(folder / "cases.json"), "--out", str(ROOT / "results" / (folder.name + "-variant.json"))] + extra, env=env)
    finally:
        if tunnel:
            tunnel.terminate()
        mock.terminate()


if __name__ == "__main__":
    main(sys.argv[1:])
