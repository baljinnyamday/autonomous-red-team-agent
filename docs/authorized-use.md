# Authorized use policy

This software is for **defensive security research and authorized red team exercises only**.

## Requirements before running

1. **Written authorization** from the system owner for every target.
2. **Defined scope** in `ALLOWED_TARGETS` — no broad internet scanning.
3. **`AUTHORIZED_ENGAGEMENT=true`** only inside isolated lab or customer-approved windows.
4. **`ENGAGEMENT_ID`** set for every run (audit trail).
5. **Operator identity** recorded (`ENGAGEMENT_OPERATOR` or CLI `--operator`).

## Prohibited use

- Testing systems you do not own or lack permission to assess.
- Denial-of-service, data destruction, or exfiltration beyond agreed rules of engagement.
- Disabling guardrails to bypass scope checks.

## Guardrails in code

- `guardrails/authorization.py` — blocks runs without explicit opt-in.
- `guardrails/scope.py` — rejects targets outside the allowlist.

Violations should abort the engagement and be logged for review.
