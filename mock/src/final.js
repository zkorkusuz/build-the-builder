// Freya Bank's seven voice services for the final case, on Cloudflare Workers, exactly as the bank's service contract describes them:
// every answer comes from the bank's test customers file (status and body per customer, card and week), an unknown customer, card or
// week gets the contract's 404 or 400 body, and every call is recorded in a ledger kept in one Durable Object.
import spec from "../openapi.json";
import customersFile from "../customers.json";

const API_PREFIX = "/voice/v1";                   // the contract's base path; the service name is the path segment after it
const LEDGER_PATH = "/ledger/";                    // GET <customerNo> -> the bank's record of that customer's calls (ours, not the bank's)

// One row per service: how the recorded answer is found (by customer or by card, then by the requested week), the request fields the
// contract requires in `data`, and the contract's answer when nothing is recorded.
const INVALID = { http: 400, code: "INVALID_ARGUMENTS_ERROR", type: "ERROR" };
export const ROUTES = [
  { service: "cards.list", by: "customerNo", required: ["customerNo"], notFound: { http: 404, code: "FB_IVR_CHANNEL_102", type: "WARNING", message: "Müşteriye ait geçerli kart bilgisi bulunamadı." } },
  { service: "cards.balance", by: "cardNumber", required: ["cardNumber"], notFound: { http: 404, code: "FB_IVR_CHANNEL_120", type: "WARNING", message: "Kart bakiye servisi hatası: kart bulunamadı" } },
  { service: "statement.week.get", by: "cardNumber", required: ["cardNumber"], notFound: { http: 404, code: "FB_IVR_CHANNEL_121", type: "WARNING", message: "Kart bulunamadı" } },
  { service: "statement.week.decide", by: "cardNumber", week: "newStatementWeek", required: ["cardNumber", "newStatementWeek", "statementDay"], notFound: { ...INVALID, message: "no statement week change to preview for this card and week" } },
  { service: "statement.week.change", by: "cardNumber", week: "newStatementWeek", required: ["cardNumber", "newStatementWeek", "statementDay"], notFound: { ...INVALID, message: "no statement week change possible for this card and week" } },
  { service: "contact.email.get", by: "customerNo", required: ["customerNo", "intAddressInfoType"], notFound: { ...INVALID, message: "customer not found" } },
  { service: "statement.pdf.send", by: "customerNo", required: ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"], notFound: { http: 404, code: "FB_IVR_CHANNEL_107", type: "WARNING", message: "Pdf dokümanı bulunamadı" } },
];
const WRITES = new Set(["statement.week.change", "statement.pdf.send"]);   // the calls that change something at the bank

function customers() {
  return Array.isArray(customersFile) ? customersFile : customersFile.customers || [];
}

function norm(v) {
  return v === undefined || v === null ? "" : String(v).trim();
}

function guid() {
  return "mock" + crypto.randomUUID().replace(/-/g, "").slice(0, 28);
}

// The contract's error envelope: no data, only result; returnCode/code and messageText/message carry the same values.
function error(http, code, type, message) {
  const g = guid();
  return [http, { result: { guid: g, returnCode: code, messageText: message, code, message, type, details: { guid: g, rootCause: type === "ERROR" ? "TechnicalError" : "NotFoundException", errorOrigin: "bank-mock" } } }, 0];
}

// The recorded entry for a service: under the customer (by customer number) or under whichever customer holds the card.
function entry(route, data) {
  const key = norm(data[route.by]);
  if (route.by === "customerNo") {
    const cust = customers().find((c) => norm(c.customerNo) === key);
    return cust ? (cust.services || {})[route.service] : undefined;
  }
  for (const cust of customers()) {
    const node = ((cust.services || {})[route.service] || {})[key];
    if (node) return node;
  }
  return undefined;
}

// [status, body, delay seconds] for one request, exactly as the test environment records it.
function answer(route, data) {
  for (const field of route.required) {
    if (norm(data[field]) === "") return error(400, "INVALID_ARGUMENTS_ERROR", "ERROR", field + " cannot be empty");
  }
  let node = entry(route, data);
  if (node && route.week) node = node[norm(data[route.week])];
  if (!node || node.http === undefined) {
    const nf = route.notFound;
    return error(nf.http, nf.code, nf.type, nf.message);
  }
  return [Number(node.http), node.response ?? node.yanit ?? null, Number(node.delaySeconds ?? 0)];
}

function sleep(seconds) {
  return new Promise((resolve) => setTimeout(resolve, Math.min(seconds, 60) * 1000));
}

function json(status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}

// The customer a call belongs to, for the ledger: the customer number sent, else the holder of the card sent.
function owner(route, data) {
  if (norm(data.customerNo)) return norm(data.customerNo);
  const card = norm(data.cardNumber);
  const cust = customers().find((c) => ((c.services || {})["cards.list"]?.response?.data?.cards || []).some((k) => norm(k.cardNumber) === card)
    || Object.keys((c.services || {})[route.service] || {}).includes(card));
  return cust ? norm(cust.customerNo) : "unknown";
}

export class BankState {
  constructor(state) {
    this.storage = state.storage;
  }

  async ledger(customerNo) {
    return (await this.storage.get("l:" + customerNo)) || { customerNo, calls: [], changes: [], sent: [] };
  }

  async call(route, data) {
    const customerNo = owner(route, data);
    const [status, body, delay] = answer(route, data);
    if (delay > 0) await sleep(delay);                 // the test data says how slow this answer is
    const led = await this.ledger(customerNo);
    const returnCode = body?.result?.returnCode ?? "";
    led.calls.push({ n: led.calls.length + 1, service: route.service, data, http: status, returnCode });
    if (WRITES.has(route.service) && status === 200 && returnCode === "1") {
      (route.service === "statement.pdf.send" ? led.sent : led.changes).push({ ...data, n: led.calls.length });
    }
    await this.storage.put("l:" + customerNo, led);
    return json(status, body);
  }

  async fetch(request) {
    const url = new URL(request.url), path = url.pathname;
    if (request.method === "GET" && path.startsWith(LEDGER_PATH)) return json(200, await this.ledger(path.slice(LEDGER_PATH.length)));
    if (request.method === "GET" && path === "/ledgers") {
      const all = await this.storage.list({ prefix: "l:" });
      return json(200, { customers: [...all.values()] });
    }
    const route = ROUTES.find((r) => path === API_PREFIX + "/" + r.service);
    if (!route) return json(404, { error: "not found" });
    if (request.method !== "POST") return json(405, { error: "POST only" });
    let body;
    try { body = await request.json(); } catch { return json(400, { error: "bad json" }); }
    const data = body && typeof body === "object" ? (body.data && typeof body.data === "object" ? body.data : body) : {};   // the contract's envelope; a bare body still answers
    return this.call(route, data);
  }
}

function openapiFor(origin) {
  return { ...spec, servers: [{ url: origin + API_PREFIX }] };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/openapi.json") return json(200, openapiFor(url.origin));
    if (url.pathname === "/" || url.pathname === "/health") return json(200, { ok: true, service: "freya-bank-voice-mock", openapi: url.origin + "/openapi.json", customers: customers().length, ledger_epoch: env.LEDGER_EPOCH });
    if (url.pathname === "/customers") return json(200, { customers: customers().map((c) => ({ customerNo: c.customerNo, firstName: c.firstName, lastName: c.lastName })) });
    const stub = env.BANK.get(env.BANK.idFromName("final-" + (env.LEDGER_EPOCH || "1")));
    return stub.fetch(request);
  },
};
