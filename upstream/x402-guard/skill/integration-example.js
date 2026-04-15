/**
 * x402 Guard - Real x402 Flow Integration Example
 *
 * This file shows the COMPLETE real flow for an AI agent making x402 payments
 * with x402 Guard as the spending policy enforcer.
 *
 * The full flow:
 *   1. Agent tries to fetch a paid API endpoint
 *   2. Server returns HTTP 402 Payment Required
 *   3. We decode the base64 payment payload to get: network, amount, payTo, asset
 *   4. We call x402 Guard FIRST — the guard checks policy limits
 *   5. If BLOCKED → throw error immediately, never sign or send any payment
 *   6. If APPROVE or SOFT_ALERT → call `onchainos payment x402-pay` to sign
 *   7. Get signature + authorization string from onchainos output
 *   8. Assemble the X-PAYMENT-SIGNATURE header
 *   9. Replay the original request with the payment header
 *  10. Return the API response to the agent
 *
 * Drop-in replacement for fetch():
 *   const data = await fetchWithGuard("https://api.example.com/data", "my-agent-001");
 *
 * Install deps:  (none — uses Node built-ins only)
 * Requires: onchainos CLI installed and configured with a funded wallet
 */

"use strict";

const { execSync } = require("child_process");
const https = require("https");
const http = require("http");
const { URL } = require("url");

// ── Configuration ─────────────────────────────────────────────────────────────

const GUARD_API_URL = process.env.GUARD_API_URL || "http://localhost:4402";
const GUARD_TIMEOUT_MS = parseInt(process.env.GUARD_TIMEOUT_MS || "5000", 10);
const ONCHAINOS_CLI = process.env.ONCHAINOS_CLI || "onchainos";

// ── Step 3: Parse the HTTP 402 response ───────────────────────────────────────
//
// When a server returns 402, the body contains a base64-encoded JSON payload
// that describes what payment is required.
//
// x402 spec: https://x402.org/
// The payload tells us: which network, how much, who to pay, which asset.

/**
 * Parse an HTTP 402 Payment Required response.
 *
 * @param {object} response   - The raw response object {status, headers, body}
 * @returns {object}          - Decoded payment requirements
 * @throws {Error}            - If the response is not a valid x402 payload
 */
function parseX402Response(response) {
  if (response.status !== 402) {
    throw new Error(`Expected HTTP 402, got ${response.status}`);
  }

  // The x402 payment payload is base64-encoded in the response body
  let rawBody = response.body;
  if (!rawBody) {
    throw new Error("HTTP 402 response has no body — cannot parse payment requirements");
  }

  // Decode base64 → JSON
  let decoded;
  try {
    const jsonStr = Buffer.from(rawBody, "base64").toString("utf8");
    decoded = JSON.parse(jsonStr);
  } catch (err) {
    // Some implementations send the JSON directly without base64
    try {
      decoded = typeof rawBody === "string" ? JSON.parse(rawBody) : rawBody;
    } catch {
      throw new Error(`Failed to decode x402 payload: ${err.message}`);
    }
  }

  // Normalise field names — different x402 implementations use slightly different keys
  const network = decoded.network || decoded.chain || decoded.chainId || "eip155:196";
  const amount = decoded.amount || decoded.maxAmountRequired || decoded.value || 0;
  const payTo = decoded.payTo || decoded.pay_to || decoded.recipient || decoded.to || "";
  const asset = decoded.asset || decoded.token || decoded.erc20 || "";
  const scheme = decoded.scheme || "exact";
  const resource = decoded.resource || decoded.url || "";

  if (!payTo) {
    throw new Error("x402 payload missing payTo address");
  }

  return { network, amount: Number(amount), payTo, asset, scheme, resource, raw: decoded };
}

// ── Step 4 & 5: Call x402 Guard before paying ────────────────────────────────
//
// The Guard is the FIRST thing we call after parsing the 402.
// It checks the agent's spending policy and decides: approve, soft_alert, or block.
//
// WHY: Without the guard, an agent could be tricked into paying unlimited amounts,
// spending money on blacklisted addresses, or burning through the daily budget.
// The guard is the safety layer between the agent's decision to call an API
// and the actual on-chain signing of a payment.

/**
 * Call x402 Guard to check if this payment is allowed.
 *
 * @param {string} agentId          - The agent's unique identifier
 * @param {object} paymentDetails   - {network, amount, asset, payTo, domain}
 * @returns {object}                - Guard response: {allowed, action, reason, remaining_daily}
 * @throws {Error}                  - If guard is unreachable or blocks the payment
 */
async function callGuard(agentId, paymentDetails) {
  const { network, amount, asset, payTo, domain } = paymentDetails;

  const requestBody = JSON.stringify({
    agent_id: agentId,
    network: network || "eip155:196",
    amount: amount,
    asset: asset || "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
    pay_to: payTo,
    domain: domain || "",
  });

  // POST to /guard/check — this is the core guard endpoint
  const guardResponse = await httpPost(`${GUARD_API_URL}/guard/check`, requestBody, {
    "Content-Type": "application/json",
  });

  let guardResult;
  try {
    guardResult = JSON.parse(guardResponse.body);
  } catch {
    throw new Error(`Guard returned invalid JSON: ${guardResponse.body}`);
  }

  if (guardResponse.status !== 200) {
    throw new Error(`Guard API error ${guardResponse.status}: ${guardResult.detail || guardResponse.body}`);
  }

  // Step 5: If guard blocks → abort immediately, never proceed to payment
  if (!guardResult.allowed || guardResult.action === "block") {
    throw new Error(
      `[x402 Guard BLOCKED] ${guardResult.reason} ` +
      `| Remaining daily budget: ${guardResult.remaining_daily} ` +
      `| Agent: ${agentId}`
    );
  }

  // Soft alert: payment is allowed but we warn the agent
  if (guardResult.action === "soft_alert") {
    console.warn(
      `[x402 Guard WARNING] ${guardResult.reason} ` +
      `| Remaining daily budget: ${guardResult.remaining_daily}`
    );
  }

  return guardResult;
}

// ── Step 6 & 7: Sign the payment with onchainos ───────────────────────────────
//
// Only called AFTER the guard approves. Uses the onchainos CLI to create
// an on-chain payment signature without exposing private keys to this code.
//
// The CLI is the standard Onchain OS way to sign x402 payments.
// It handles key management, nonce tracking, and EIP-712 signing internally.
//
// Command format:
//   onchainos payment x402-pay \
//     --network eip155:196 \
//     --amount 1000000 \
//     --pay-to 0xRecipient \
//     --asset 0xTokenAddress \
//     --json

/**
 * Sign an x402 payment using the onchainos CLI.
 *
 * @param {object} paymentDetails - {network, amount, payTo, asset}
 * @returns {object}              - {signature, authorization, transaction_hash}
 * @throws {Error}                - If onchainos CLI fails or output is invalid
 */
function signWithOnchainos(paymentDetails) {
  const { network, amount, payTo, asset } = paymentDetails;

  // Build the onchainos payment command
  // --json flag ensures machine-readable output we can parse
  const cmd = [
    ONCHAINOS_CLI,
    "payment",
    "x402-pay",
    "--network", network || "eip155:196",
    "--amount", String(Math.round(amount)),       // onchainos expects integer micro-units
    "--pay-to", payTo,
    "--asset", asset || "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
    "--json",                                     // output JSON for parsing
  ].join(" ");

  console.log(`[x402 Guard] Calling onchainos: ${cmd}`);

  let output;
  try {
    output = execSync(cmd, {
      encoding: "utf8",
      timeout: 30000,       // 30s timeout for on-chain signing
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (err) {
    // execSync throws on non-zero exit code
    const stderr = err.stderr || "";
    const stdout = err.stdout || "";
    throw new Error(
      `onchainos payment x402-pay failed (exit ${err.status}):\n` +
      `stdout: ${stdout}\nstderr: ${stderr}`
    );
  }

  // Parse the JSON output from onchainos
  let result;
  try {
    result = JSON.parse(output.trim());
  } catch {
    throw new Error(`onchainos returned non-JSON output: ${output}`);
  }

  // Validate we got the required fields
  if (!result.signature && !result.authorization) {
    throw new Error(
      `onchainos output missing signature/authorization fields. Got: ${JSON.stringify(result)}`
    );
  }

  return {
    signature: result.signature || "",
    authorization: result.authorization || result.auth || "",
    transactionHash: result.transaction_hash || result.txHash || result.hash || "",
    from: result.from || result.payer || "",
    raw: result,
  };
}

// ── Step 8: Assemble the payment header ──────────────────────────────────────
//
// The x402 protocol requires a specific header format to prove payment.
// The header value is a base64-encoded JSON object combining:
//   - The original payment requirements (from the 402 response)
//   - The signature produced by our wallet
//   - The authorization string
//
// The server uses this to verify the payment was signed by the expected payer
// and that the amount/recipient matches what was requested.

/**
 * Assemble the X-PAYMENT-SIGNATURE header value.
 *
 * @param {object} decoded       - Parsed x402 payment requirements
 * @param {string} signature     - EIP-712 signature from onchainos
 * @param {string} authorization - Authorization string from onchainos
 * @returns {string}             - base64-encoded header value
 */
function assemblePaymentHeader(decoded, signature, authorization) {
  // The payment header combines the original requirements with our signature
  const paymentProof = {
    // Original requirements from the 402 response (server needs these back)
    ...decoded.raw,

    // Our payment proof
    signature: signature,
    authorization: authorization,

    // Timestamp to prevent replay attacks
    timestamp: Date.now(),
  };

  // base64-encode the JSON as required by the x402 spec
  return Buffer.from(JSON.stringify(paymentProof)).toString("base64");
}

// ── Step 9 & 10: The main function ────────────────────────────────────────────
//
// fetchWithGuard is a drop-in replacement for fetch().
// It handles the entire x402 flow transparently:
//   - Makes the original request
//   - If 402: runs the guard check, signs, retries
//   - Returns the final response to the caller
//
// The agent code doesn't need to know anything about x402 internals.

/**
 * Drop-in fetch replacement with x402 Guard integration.
 *
 * @param {string} url      - URL to fetch
 * @param {string} agentId  - Agent identifier for guard policy lookup
 * @param {object} options  - Standard fetch options (method, headers, body, etc.)
 * @returns {object}        - {status, headers, body, json} of the final response
 *
 * @example
 *   const res = await fetchWithGuard(
 *     "https://api.xlayer.example.com/premium-data",
 *     "research-agent-001"
 *   );
 *   console.log(res.json);
 */
async function fetchWithGuard(url, agentId, options = {}) {
  if (!agentId) throw new Error("agentId is required for fetchWithGuard");

  const domain = new URL(url).hostname;

  // ── Step 1: Make the original HTTP request ──────────────────────────────────
  console.log(`[x402 Guard] Requesting: ${url}`);
  const initialResponse = await httpGet(url, options.headers || {}, options);

  // Happy path: no payment required
  if (initialResponse.status !== 402) {
    return initialResponse;
  }

  // ── Step 2: Got HTTP 402 — payment required ─────────────────────────────────
  console.log(`[x402 Guard] Got HTTP 402 from ${domain}, parsing payment requirements...`);

  // ── Step 3: Parse the base64 payload ───────────────────────────────────────
  let decoded;
  try {
    decoded = parseX402Response(initialResponse);
  } catch (err) {
    throw new Error(`Failed to parse x402 payment requirements: ${err.message}`);
  }

  console.log(
    `[x402 Guard] Payment required: ${decoded.amount} of ${decoded.asset} ` +
    `on ${decoded.network} to ${decoded.payTo}`
  );

  // ── Step 4 & 5: Call guard BEFORE signing anything ─────────────────────────
  // This is where the policy engine runs. If blocked, we throw and stop here.
  console.log(`[x402 Guard] Checking policy for agent ${agentId}...`);
  let guardResult;
  try {
    guardResult = await callGuard(agentId, { ...decoded, domain });
  } catch (err) {
    // Guard blocked or unreachable — never proceed to payment
    throw new Error(`[x402 Guard] Payment blocked: ${err.message}`);
  }

  console.log(
    `[x402 Guard] Approved (action=${guardResult.action}). ` +
    `Remaining daily budget: ${guardResult.remaining_daily}`
  );

  // ── Step 6 & 7: Sign with onchainos ────────────────────────────────────────
  // Guard approved — now we can sign the payment
  console.log("[x402 Guard] Signing payment with onchainos...");
  let signed;
  try {
    signed = signWithOnchainos(decoded);
  } catch (err) {
    throw new Error(`Failed to sign payment with onchainos: ${err.message}`);
  }

  // ── Step 8: Assemble payment header ────────────────────────────────────────
  const paymentHeader = assemblePaymentHeader(decoded, signed.signature, signed.authorization);

  // ── Step 9: Replay original request with payment header ────────────────────
  console.log("[x402 Guard] Replaying request with payment signature...");
  const paidResponse = await httpGet(url, {
    ...(options.headers || {}),
    "X-PAYMENT-SIGNATURE": paymentHeader,
    "X-Payment-Payer": signed.from,
  }, options);

  // ── Step 10: Return response to agent ──────────────────────────────────────
  if (paidResponse.status === 200 || paidResponse.status === 201) {
    console.log(`[x402 Guard] Payment successful. Response: ${paidResponse.status}`);
  } else if (paidResponse.status === 402) {
    throw new Error(
      `Payment was made but server still returned 402. ` +
      `Signature may be invalid or payment amount insufficient.`
    );
  } else if (paidResponse.status >= 400) {
    throw new Error(
      `Request failed after payment: HTTP ${paidResponse.status} — ${paidResponse.body}`
    );
  }

  return paidResponse;
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────
// Simple Node.js http/https wrappers so this file has zero npm dependencies.

function httpGet(url, headers = {}, options = {}) {
  return new Promise((resolve, reject) => {
    const parsedUrl = new URL(url);
    const lib = parsedUrl.protocol === "https:" ? https : http;
    const method = options.method || "GET";

    const reqOptions = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port || (parsedUrl.protocol === "https:" ? 443 : 80),
      path: parsedUrl.pathname + parsedUrl.search,
      method,
      headers: {
        "User-Agent": "x402-guard-agent/1.0",
        ...headers,
      },
      timeout: GUARD_TIMEOUT_MS,
    };

    const req = lib.request(reqOptions, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8");
        let json = null;
        try {
          json = JSON.parse(body);
        } catch {
          // Not JSON
        }
        resolve({ status: res.statusCode, headers: res.headers, body, json });
      });
    });

    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request timed out: ${url}`));
    });

    if (options.body) req.write(options.body);
    req.end();
  });
}

function httpPost(url, body, headers = {}) {
  return httpGet(url, {
    "Content-Length": Buffer.byteLength(body),
    ...headers,
  }, { method: "POST", body });
}

// ── Demo / smoke test ─────────────────────────────────────────────────────────
// Run this file directly to see a simulated flow without a live server.

async function runDemo() {
  console.log("=== x402 Guard Integration Demo ===\n");

  const agentId = "demo-agent-001";
  const guardUrl = GUARD_API_URL;

  console.log(`Guard API: ${guardUrl}`);
  console.log(`Agent ID: ${agentId}\n`);

  // Step 0: Create a policy for the demo agent
  console.log("--- Step 0: Create spending policy ---");
  try {
    const policyResponse = await httpPost(
      `${guardUrl}/policies`,
      JSON.stringify({
        agent_id: agentId,
        name: "Demo Policy",
        daily_limit: 50.0,
        hourly_limit: 10.0,
        per_tx_limit: 5.0,
        auto_approve_under: 0.01,
      }),
      { "Content-Type": "application/json" }
    );
    console.log(`Policy created: HTTP ${policyResponse.status}`);
    if (policyResponse.json) {
      console.log(`  Policy ID: ${policyResponse.json.id}`);
      console.log(`  Daily limit: ${policyResponse.json.daily_limit}`);
    }
  } catch (err) {
    console.warn(`  Policy creation skipped: ${err.message}`);
  }

  // Step 1: Simulate receiving a 402 response
  console.log("\n--- Step 1: Simulate HTTP 402 response ---");
  const simulatedX402Payload = {
    network: "eip155:196",
    amount: 1000000,   // 1 USDC in micro-units
    payTo: "0xabcdef1234567890abcdef1234567890abcdef12",
    asset: "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
    scheme: "exact",
    resource: "https://api.example.com/premium-data",
  };
  const simulatedBase64Body = Buffer.from(JSON.stringify(simulatedX402Payload)).toString("base64");
  const mock402Response = { status: 402, headers: {}, body: simulatedBase64Body };

  // Step 2: Parse the 402
  console.log("--- Step 2: Parse x402 payload ---");
  let decoded;
  try {
    decoded = parseX402Response(mock402Response);
    console.log(`  Network: ${decoded.network}`);
    console.log(`  Amount:  ${decoded.amount} micro-units`);
    console.log(`  Pay to:  ${decoded.payTo}`);
    console.log(`  Asset:   ${decoded.asset}`);
  } catch (err) {
    console.error(`  Failed: ${err.message}`);
    return;
  }

  // Step 3: Call the guard
  console.log("\n--- Step 3: Call x402 Guard ---");
  try {
    const guardResult = await callGuard(agentId, decoded);
    console.log(`  Action: ${guardResult.action}`);
    console.log(`  Allowed: ${guardResult.allowed}`);
    console.log(`  Reason: ${guardResult.reason}`);
    console.log(`  Remaining daily: ${guardResult.remaining_daily}`);
  } catch (err) {
    console.log(`  Guard decision: ${err.message}`);
    return;
  }

  // Step 4: Show the onchainos command that would be run
  console.log("\n--- Step 4: onchainos payment command (would run) ---");
  const onchainosCmd = [
    ONCHAINOS_CLI, "payment", "x402-pay",
    "--network", decoded.network,
    "--amount", String(Math.round(decoded.amount)),
    "--pay-to", decoded.payTo,
    "--asset", decoded.asset,
    "--json",
  ].join(" ");
  console.log(`  $ ${onchainosCmd}`);

  console.log("\n=== Demo complete ===");
  console.log("In production, fetchWithGuard() handles this entire flow automatically.");
  console.log("Example usage:");
  console.log('  const data = await fetchWithGuard("https://api.example.com/data", "agent-001");');
}

// ── Exports ───────────────────────────────────────────────────────────────────

module.exports = {
  fetchWithGuard,
  parseX402Response,
  callGuard,
  signWithOnchainos,
  assemblePaymentHeader,
};

// Run demo if called directly
if (require.main === module) {
  runDemo().catch((err) => {
    console.error("Demo error:", err.message);
    process.exit(1);
  });
}
