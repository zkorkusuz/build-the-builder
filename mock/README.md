# Bank mock on Cloudflare Workers

The bank's services that the phone agent's tools call, hosted by us. It mirrors `tests/mock_bank.py` (same routes,
same JSON shapes, same ledger) so the agent built on the practice works against it unchanged. State lives in one
Durable Object with SQLite storage, so it survives requests, isolates and redeploys. No secrets anywhere.

Files: `src/index.js` (the Worker), `customers.json` (the bank's customers), `openapi.json` (the tool API the mock
serves at `/openapi.json`), `wrangler.toml` (name, Durable Object binding and migration).

## Deploy (three commands, once)

```
cd mock && npm install
npx wrangler login        # opens the browser; any Cloudflare account, free plan is enough
npx wrangler deploy       # prints https://bank-mock.<account>.workers.dev
```

Redeploy with `npx wrangler deploy` after every change to `customers.json` or `src/index.js`; the ledger is kept.
Check it is up: `curl https://bank-mock.<account>.workers.dev/` and `.../v1/practice/customers`.
Then put `https://bank-mock.<account>.workers.dev/v1` into the tool API file's `servers.url` and
`export FREYA_BANK_HOST=https://bank-mock.<account>.workers.dev` for `tools/run_cases.py`.

## Local

```
cd mock && npx wrangler dev --port 8787      # http://localhost:8787, state in .wrangler/state (ignored by git)
```

## Routes

| Route | Body / answer |
|---|---|
| `GET /` | liveness, the OpenAPI URL and the ledger epoch |
| `GET /openapi.json` | `openapi.json` with `servers.url` set to this host + `/v1` |
| `GET /v1/practice/customers` | the customers loaded from `customers.json` and the rules |
| `POST /v1/practice/sessions` `{"case": "PUB-01"}`, header `X-Team-Key` (16+ chars) | `{"ok": true, "variables": {..., "customer_id": "c_..."}}`, a fresh copy of that customer |
| `POST /v1/<tool>` `{"customer_id": ..., ...}` | the seven tools; validation answers are HTTP 200 with `ok: false`; a `fail_first` tool answers 500 once |
| `GET /v1/practice/ledger/<customer_id>` | the bank's records of one customer (shape below) |
| `GET /v1/practice/ledgers` | every customer's records, each with its `customer_id` |

Ledger shape (identical to `tests/mock_bank.py`):
`{ok, case, now, verified: {field: true}, wrong, hinted, promises: [{promise_id, product_id, type, amount, date}],
notes: [{product_id, reason, text}], callbacks: [{date, time}], transfers: [{queue}], outcome, reason,
failures: {tool: n}, calls: [{n, tool, args, result}]}`. `calls` is every tool call in order, so "close_call is
last" and "one promise per product" can be read off it.

## customers.json

`{"rules": {"max_wrong_total": 3}, "cases": [...]}` (a bare list also works). Each case: `id`, `title`,
`variables` (`first_name`, `last_name`, `title`, `now`, anything else the agent gets), `identity` (the security
answers, field name to value; dates as `YYYY-MM-DD`), `products` (each gets `product_id` `p1`, `p2`, ... unless it
carries one), `fail_first` (tools that answer 500 on their first call). An optional `customer_id` makes the
customer reachable by that fixed id without opening a session, for test customers the organizers address directly.

Reload: edit the file, `npx wrangler deploy`. Sessions already opened keep their old copy of the customer.
Fresh ledger: bump `LEDGER_EPOCH` in `wrangler.toml` and deploy (old records stay readable by switching it back).

Reading the ledger: `curl https://bank-mock.<account>.workers.dev/v1/practice/ledger/<customer_id>` or
`.../v1/practice/ledgers` for all; `npx wrangler tail` streams the live request log.

## At 20:00: reshape from the service contract

Work through the contract against `src/index.js` top to bottom; every item names its function.

1. **Customers**: regenerate `customers.json` from the zip's test customers (ids, variables, identity answers,
   products, faults). If the organizers address customers by a fixed id, put it in `customer_id` (`session()`).
   Identity rule (`max_wrong_total`) goes in `rules`.
2. **Paths**: `API_PREFIX`, `SESSIONS_PATH`, `LEDGER_PATH` at the top; the tool names in `tool()` are the path
   segments after the prefix. A tool with a different method or a path parameter: change `BankState.fetch`.
3. **Field names**: request fields are read in `verifyIdentity` (`field`, `answer`), `createPromise`
   (`product_id`, `amount`, `date`), and `tool()` (`add_note`, `schedule_callback`, `transfer_to_agent`,
   `close_call`). `customer_id` is stripped from the logged args in `stripCustomerId`.
4. **Enum values**: the mock does not enforce enums (same as the practice); the scorer compares the ledger with the
   expectations, so record what the contract names (`outcome`, `reason`, `queue`, `type`). Rename the product
   id scheme (`p1`...) in `newSession` if the contract fixes ids.
5. **Response shapes**: each function returns the exact JSON of its route; `wrong_answers_left`, `all_verified`,
   the `day_month_swapped` hint and the "identity not verified" gate live in `verifyIdentity` and `tool()`.
   Validation stays HTTP 200 with `ok: false`; the once-only 500 is the first branch of `tool()`.
6. **Ledger route and shape**: `LEDGER_PATH`, the ledger object in `newSession`, the per-call record in
   `callTool`, the list in `allLedgers`.
7. **OpenAPI**: replace `openapi.json` with the contract's tool API (the servers url is overwritten per request in
   `openapiFor`), then `npx wrangler deploy` and re-check with the curl sequence below.

Smoke test after a change (any host):
```
H=https://bank-mock.<account>.workers.dev
CID=$(curl -s -X POST $H/v1/practice/sessions -H 'X-Team-Key: a-local-key-of-16-chars' -H 'content-type: application/json' -d '{"case":"PUB-01"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["variables"]["customer_id"])')
curl -s -X POST $H/v1/verify_identity -H 'content-type: application/json' -d "{\"customer_id\":\"$CID\",\"field\":\"date_of_birth\",\"answer\":\"1988-03-14\"}"
curl -s $H/v1/practice/ledger/$CID
```
