// Bank mock on Cloudflare Workers: the same routes and JSON shapes as tests/mock_bank.py.
// All state lives in one Durable Object (SQLite-backed) so it survives requests, isolates and deploys.
import spec from "../openapi.json";
import customersFile from "../customers.json";

const RULES = { max_wrong_total: 3 };
const API_PREFIX = "/v1";                        // the path before each tool name in the contract's servers.url
const SESSIONS_PATH = "/v1/practice/sessions";   // POST {case} -> a fresh customer for one practice call
const LEDGER_PATH = "/v1/practice/ledger/";      // GET <customer_id> -> the bank's records of that customer

// --- customers.json -------------------------------------------------------------------------

function cases() {
  const list = Array.isArray(customersFile) ? customersFile : customersFile.cases || [];
  return list;
}

function rules() {
  return { ...RULES, ...(customersFile.rules || {}) };
}

function newSession(c) {
  const products = (c.products || []).map((p, i) => ({ ...p, product_id: p.product_id || "p" + (i + 1) }));
  const failFirst = (c.fail_first || []).concat((c.faults || []).map((f) => f.tool).filter(Boolean));
  return {
    case: c.id, identity: c.identity || {}, products, fail_first: failFirst, failed_once: [],
    ledger: { ok: true, case: c.id, now: (c.variables || {}).now, verified: {}, wrong: 0, hinted: false,
      promises: [], notes: [], callbacks: [], transfers: [], outcome: null, reason: null, failures: {}, calls: [] },
  };
}

// --- tool semantics --------------------------------------------------------------------------

function norm(value) {
  return String(value ?? "").trim().toUpperCase().replace(/ /g, "");
}

function looksLikeDate(v) {
  return typeof v === "string" && v.length === 10 && v[4] === "-" && v[7] === "-";
}

function isRealDate(v) {
  return looksLikeDate(v) && new Date(v + "T00:00:00Z").toISOString().slice(0, 10) === v;
}

function swapDayMonth(v) {
  return v.slice(0, 4) + "-" + v.slice(8, 10) + "-" + v.slice(5, 7);
}

function allVerified(s) {
  const fields = Object.keys(s.identity);
  return fields.length > 0 && fields.every((f) => s.ledger.verified[f]);
}

function verifyIdentity(s, body) {
  const led = s.ledger, ident = s.identity, max = rules().max_wrong_total;
  const { field, answer } = body;
  const left = () => max - led.wrong;
  if (!(field in ident)) return { ok: false, error: "unknown field", verified: false, wrong_answers_left: left(), all_verified: false };
  if (led.wrong >= max) return { ok: true, verified: false, wrong_answers_left: 0, all_verified: false };
  if (field.includes("date") && !looksLikeDate(answer)) {
    return { ok: false, error: "unreadable date, send YYYY-MM-DD", verified: false, wrong_answers_left: left(), all_verified: false };
  }
  if (norm(answer) === norm(ident[field])) {
    led.verified[field] = true;
    return { ok: true, verified: true, wrong_answers_left: left(), all_verified: allVerified(s) };
  }
  const out = { ok: true, verified: false };
  if (field.includes("date") && swapDayMonth(answer) === String(ident[field])) { out.hint = "day_month_swapped"; led.hinted = true; }
  else led.wrong += 1;
  out.wrong_answers_left = left(); out.all_verified = false;
  return out;
}

function createPromise(s, body) {
  const led = s.ledger, pid = body.product_id;
  const product = s.products.find((p) => p.product_id === pid);
  if (!product) return { ok: false, error: "unknown product_id" };
  if (led.promises.some((p) => p.product_id === pid)) return { ok: false, error: "a promise already exists for this product" };
  const amount = Number(body.amount), date = String(body.date);
  if (body.amount === undefined || body.amount === null || body.amount === "" || Number.isNaN(amount) || !isRealDate(date)) {
    return { ok: false, error: "amount must be a number and date YYYY-MM-DD" };
  }
  led.promises.push({ promise_id: "pr" + (led.promises.length + 1), product_id: pid, type: product.type, amount, date });
  return { ok: true, promise_id: led.promises[led.promises.length - 1].promise_id };
}

function closeCall(s, body) {
  const led = s.ledger;
  if (led.outcome !== null) return { ok: false, error: "the call is already closed" };
  led.outcome = body.outcome ?? null; led.reason = body.reason ?? null;
  return { ok: true };
}

// One tool call against a session. Returns [status, response]; the caller logs it and saves the session.
function tool(s, name, body) {
  const led = s.ledger;
  if (s.fail_first.includes(name) && !s.failed_once.includes(name)) {
    s.failed_once.push(name);
    led.failures[name] = (led.failures[name] || 0) + 1;
    return [500, { ok: false, error: "service failed" }];
  }
  if (name === "verify_identity") return [200, verifyIdentity(s, body)];
  if ((name === "get_account" || name === "create_promise") && !allVerified(s)) return [200, { ok: false, error: "identity not verified" }];
  if (name === "get_account") return [200, { ok: true, products: s.products }];
  if (name === "create_promise") return [200, createPromise(s, body)];
  if (name === "add_note") { led.notes.push({ product_id: body.product_id ?? null, reason: body.reason ?? null, text: body.text ?? "" }); return [200, { ok: true }]; }
  if (name === "schedule_callback") {
    if (!body.date || !body.time) return [200, { ok: false, error: "date and time are required" }];
    led.callbacks.push({ date: body.date, time: body.time }); return [200, { ok: true }];
  }
  if (name === "transfer_to_agent") { led.transfers.push({ queue: body.queue ?? null }); return [200, { ok: true }]; }
  if (name === "close_call") return [200, closeCall(s, body)];
  return [404, { ok: false, error: "not found" }];
}

// --- HTTP ------------------------------------------------------------------------------------

function json(status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}

function randomId() {
  return "c_" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
}

function stripCustomerId(body) {
  const { customer_id, ...args } = body;
  return args;
}

export class BankState {
  constructor(state) {
    this.storage = state.storage;
  }

  // A customer the zip ships with a fixed customer_id exists before any session is opened for it.
  async session(cid) {
    if (!cid) return null;
    const stored = await this.storage.get("s:" + cid);
    if (stored) return stored;
    const c = cases().find((x) => x.customer_id === cid);
    if (!c) return null;
    const s = newSession(c);
    await this.storage.put("s:" + cid, s);
    return s;
  }

  async openSession(body) {
    const c = cases().find((x) => x.id === body.case);
    if (!c) return json(404, { ok: false, error: "unknown case" });
    const cid = randomId();
    await this.storage.put("s:" + cid, newSession(c));
    return json(200, { ok: true, variables: { ...(c.variables || {}), customer_id: cid } });
  }

  async callTool(name, body) {
    const cid = body.customer_id, s = await this.session(cid);
    if (!s) return json(200, { ok: false, error: "unknown customer_id" });
    const [status, out] = tool(s, name, body);
    s.ledger.calls.push({ n: s.ledger.calls.length + 1, tool: name, args: stripCustomerId(body), result: out });
    await this.storage.put("s:" + cid, s);
    return json(status, out);
  }

  async allLedgers() {
    const all = await this.storage.list({ prefix: "s:" });
    return json(200, { ok: true, customers: [...all].map(([k, s]) => ({ customer_id: k.slice(2), ...s.ledger })) });
  }

  async fetch(request) {
    const path = new URL(request.url).pathname;
    if (request.method === "GET" && path.startsWith(LEDGER_PATH)) {
      const s = await this.session(path.slice(LEDGER_PATH.length));
      return s ? json(200, s.ledger) : json(404, { ok: false, error: "unknown customer" });
    }
    if (request.method === "GET" && path === LEDGER_PATH.slice(0, -1) + "s") return this.allLedgers();
    if (request.method !== "POST") return json(404, { ok: false, error: "not found" });
    let body;
    try { body = await request.json(); } catch { return json(400, { ok: false, error: "bad json" }); }
    if (typeof body !== "object" || body === null) return json(400, { ok: false, error: "bad json" });
    if (path === SESSIONS_PATH) {
      if ((request.headers.get("x-team-key") || "").length < 16) return json(401, { ok: false, error: "send X-Team-Key: a secret of 16 or more characters" });
      return this.openSession(body);
    }
    if (path.startsWith(API_PREFIX + "/")) return this.callTool(path.slice(API_PREFIX.length + 1), body);
    return json(404, { ok: false, error: "not found" });
  }
}

function openapiFor(origin) {
  return { ...spec, servers: [{ url: origin + API_PREFIX }] };
}

function customerList() {
  return cases().map((c) => ({ id: c.id, customer_id: c.customer_id, title: c.title, products: (c.products || []).length }));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/openapi.json") return json(200, openapiFor(url.origin));
    if (url.pathname === "/v1/practice/customers") return json(200, { ok: true, rules: rules(), customers: customerList() });
    if (url.pathname === "/") return json(200, { ok: true, service: "bank-mock", openapi: url.origin + "/openapi.json", ledger_epoch: env.LEDGER_EPOCH });
    // One object holds every customer: bump LEDGER_EPOCH in wrangler.toml to start with an empty ledger.
    const stub = env.BANK.get(env.BANK.idFromName("bank-" + (env.LEDGER_EPOCH || "1")));
    return stub.fetch(request);
  },
};
