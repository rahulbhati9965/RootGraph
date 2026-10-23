# RUNBOOK-PAY-04: Third-Party Payment Gateway Latency and 504 Timeouts

**Service**: `payment-service`  
**Downstream Dependency**: `bank-gateway` (EU Central)  
**Severity Level**: P0 / P1  
**Owner**: Payments Core Team (`payments-core@company.internal`)

---

## 1. Symptoms & Diagnostic Indicators
- Elevated latency on `checkout-service` (> 1500ms P95).
- Error spikes on `payment-service` with `HTTP 500 Payment gateway timeout`.
- Regional error rate concentration in `eu-central-1` and `eu-west-1`.
- Trace waterfall shows span `bank-gateway > Process Charge` running for > 900ms and returning `504 Gateway Timeout`.

---

## 2. Immediate Mitigation Steps

### Step 1: Verify Upstream Bank Status
Run the synthetic health probe:
```bash
curl -I https://api.centralbank.eu/v2/healthcheck --max-time 2
```
If response time exceeds 1500ms or returns 5xx, the primary bank partner is experiencing an outage.

### Step 2: Trip Circuit Breaker & Reroute to Secondary Gateway (Adyen / Stripe)
To prevent thread starvation in `payment-service`:
1. Execute the emergency traffic shift:
   ```bash
   tracepilot-cli circuit-breaker trip --service payment-service --target bank-gateway
   tracepilot-cli payment-route failover --region eu-central-1 --provider adyen-backup
   ```
2. Verify that `payment-service` error rate drops below 1.0% within 60 seconds.

### Step 3: Inform Stakeholders
Update the `#incident-checkout` Slack channel with:
> *"Primary EU Central bank gateway latency degradation detected. Traffic rerouted to secondary provider. Checkout latency recovering."*

---

## 3. Escalation Contacts
- **Primary On-Call**: Payments SRE Pager (`pagerduty://payments-sre`)
- **Third-Party Partner Support**: CentralBank NOC Hotline (`+49-69-000-1122`, Account #99482)
