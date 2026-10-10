"""A stand-in for the organizers' bank mock, for briefs whose customers the real mock does not know (the variant briefs).

    .venv/bin/python tests/mock_bank.py tests/variants/v1/cases.json --port 8787 --max-wrong 2

Same routes and shapes as the real mock: POST /v1/practice/sessions {case} (header X-Team-Key), GET /v1/practice/ledger/<customer_id>,
and the seven POST /v1/<tool> routes keyed by customer_id. Expose it with a tunnel, point the brief's API file `servers.url` and
FREYA_BANK_HOST at the tunnel, and run_cases.py works unchanged. Standard library only; state lives in memory.
"""
import datetime, json, pathlib, sys, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CASES, RULES, SESSIONS, LOCK = {}, {}, {}, threading.Lock()


def new_session(case_id):
    c = CASES[case_id]
    cid = "c_" + uuid.uuid4().hex[:12]
    products = [dict(p, product_id="p" + str(i + 1)) for i, p in enumerate(c.get("products", []))]
    SESSIONS[cid] = {"case": case_id, "identity": c.get("identity", {}), "products": products, "fail_first": set(c.get("fail_first", [])), "failed_once": set(),
                     "ledger": {"ok": True, "case": case_id, "now": c["variables"].get("now"), "verified": {}, "wrong": 0, "hinted": False, "promises": [], "notes": [], "callbacks": [], "transfers": [],
                                "outcome": None, "reason": None, "failures": {}, "calls": []}}
    return {"ok": True, "variables": dict(c["variables"], customer_id=cid)}


def norm(field, value):
    v = str(value or "").strip().upper().replace(" ", "")
    return v


def tool(s, name, body):
    """One tool call against a session. Returns (status, response)."""
    led, ident = s["ledger"], s["identity"]
    if name in s["fail_first"] and name not in s["failed_once"]:
        s["failed_once"].add(name)
        led["failures"][name] = led["failures"].get(name, 0) + 1
        return 500, {"ok": False, "error": "service failed"}
    if name == "verify_identity":
        field, answer = body.get("field"), body.get("answer")
        if field not in ident:
            return 200, {"ok": False, "error": "unknown field", "verified": False, "wrong_answers_left": RULES["max_wrong_total"] - led["wrong"], "all_verified": False}
        if led["wrong"] >= RULES["max_wrong_total"]:
            return 200, {"ok": True, "verified": False, "wrong_answers_left": 0, "all_verified": False}
        if "date" in field and not (isinstance(answer, str) and len(answer) == 10 and answer[4] == "-" and answer[7] == "-"):
            return 200, {"ok": False, "error": "unreadable date, send YYYY-MM-DD", "verified": False, "wrong_answers_left": RULES["max_wrong_total"] - led["wrong"], "all_verified": False}
        if norm(field, answer) == norm(field, ident[field]):
            led["verified"][field] = True
        else:
            out = {"ok": True, "verified": False}
            if "date" in field and isinstance(answer, str) and len(answer) == 10 and answer[:4] + "-" + answer[8:10] + "-" + answer[5:7] == str(ident[field]):
                out["hint"] = "day_month_swapped"; led["hinted"] = True
            else:
                led["wrong"] += 1
            out["wrong_answers_left"] = RULES["max_wrong_total"] - led["wrong"]; out["all_verified"] = False
            return 200, out
        allv = all(led["verified"].get(f) for f in ident)
        return 200, {"ok": True, "verified": True, "wrong_answers_left": RULES["max_wrong_total"] - led["wrong"], "all_verified": allv}
    verified = all(led["verified"].get(f) for f in ident) and bool(ident)
    if name in ("get_account", "create_promise") and not verified:
        return 200, {"ok": False, "error": "identity not verified"}
    if name == "get_account":
        return 200, {"ok": True, "products": s["products"]}
    if name == "create_promise":
        pid = body.get("product_id")
        if pid not in [p["product_id"] for p in s["products"]]:
            return 200, {"ok": False, "error": "unknown product_id"}
        if any(p["product_id"] == pid for p in led["promises"]):
            return 200, {"ok": False, "error": "a promise already exists for this product"}
        try:
            amount, date = float(body.get("amount")), str(body.get("date"))
            datetime.date.fromisoformat(date)
        except (TypeError, ValueError):
            return 200, {"ok": False, "error": "amount must be a number and date YYYY-MM-DD"}
        ptype = next(p["type"] for p in s["products"] if p["product_id"] == pid)
        led["promises"].append({"promise_id": "pr" + str(len(led["promises"]) + 1), "product_id": pid, "type": ptype, "amount": amount, "date": date})
        return 200, {"ok": True, "promise_id": led["promises"][-1]["promise_id"]}
    if name == "add_note":
        led["notes"].append({"product_id": body.get("product_id"), "reason": body.get("reason"), "text": body.get("text", "")}); return 200, {"ok": True}
    if name == "schedule_callback":
        if not body.get("date") or not body.get("time"):
            return 200, {"ok": False, "error": "date and time are required"}
        led["callbacks"].append({"date": body.get("date"), "time": body.get("time")}); return 200, {"ok": True}
    if name == "transfer_to_agent":
        led["transfers"].append({"queue": body.get("queue")}); return 200, {"ok": True}
    if name == "close_call":
        if led["outcome"] is not None:
            return 200, {"ok": False, "error": "the call is already closed"}
        led["outcome"], led["reason"] = body.get("outcome"), body.get("reason"); return 200, {"ok": True}
    return 404, {"ok": False, "error": "not found"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/v1/practice/ledger/"):
            cid = self.path.rsplit("/", 1)[-1]
            with LOCK:
                s = SESSIONS.get(cid)
                return self.send(200, s["ledger"]) if s else self.send(404, {"ok": False, "error": "unknown customer"})
        self.send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send(400, {"ok": False, "error": "bad json"})
        if self.path == "/v1/practice/sessions":
            if len(self.headers.get("X-Team-Key", "")) < 16:
                return self.send(401, {"ok": False, "error": "send X-Team-Key: a secret of 16 or more characters"})
            with LOCK:
                return self.send(200, new_session(body["case"])) if body.get("case") in CASES else self.send(404, {"ok": False, "error": "unknown case"})
        if self.path.startswith("/v1/"):
            name = self.path[4:]
            with LOCK:
                s = SESSIONS.get(body.get("customer_id"))
                if not s:
                    return self.send(200, {"ok": False, "error": "unknown customer_id"})
                status, out = tool(s, name, body)
                s["ledger"]["calls"].append({"n": len(s["ledger"]["calls"]) + 1, "tool": name, "args": {k: v for k, v in body.items() if k != "customer_id"}, "result": out})
                return self.send(status, out)
        self.send(404, {"ok": False, "error": "not found"})


def main(argv):
    spec = json.loads(pathlib.Path(argv[0]).read_text())
    CASES.update({c["id"]: c for c in (spec if isinstance(spec, list) else spec["cases"])})
    RULES.update({"max_wrong_total": int(argv[argv.index("--max-wrong") + 1]) if "--max-wrong" in argv else 3})
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8787
    print("mock bank:", len(CASES), "cases, max wrong answers", RULES["max_wrong_total"], "on port", port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
