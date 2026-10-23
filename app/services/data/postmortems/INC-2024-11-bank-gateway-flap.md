# Post-Mortem: Incident INC-2024-11 (EU Central Bank Route Flap)

**Date**: 2024-11-14  
**Impact**: 18 minutes of checkout timeouts across European users  
**Root Cause**: Transit BGP route flap at upstream clearing house datacenter in Frankfurt (`eu-central-1`)

---

## Executive Summary
On November 14, 2024 at 16:20 UTC, `checkout-service` experienced elevated P95 latency (spiking to 3.2s) with 31% of requests failing with 504 status codes. 

The incident investigation revealed that `payment-service` was synchronously waiting on responses from `bank-gateway`. The external bank was experiencing severe packet loss due to an upstream ISP route flap, causing HTTP requests to hang until the 900ms read timeout triggered. Because the circuit breaker was set to manual, `payment-service` exhausted its worker threads, causing cascading latency back to `checkout-service`.

---

## Lessons Learned
1. **Circuit Breakers Must Be Automatic**: Manual circuit breakers allowed cascading thread pool exhaustion. We configured bounded retries and an automatic circuit trip after 5 consecutive 504 errors.
2. **Correlation ID Chains**: Preserving correlation IDs (`a1b2c3d4 > b2c3d4e5 > c3d4e5f6 > d4e5f607`) allowed us to trace the root cause directly from the user's cart request to the external bank IP in Frankfurt.
3. **Multi-Region Failover**: When `eu-central-1` bank gateways degrade, routing rules should immediately switch payment processing to the secondary processor.
