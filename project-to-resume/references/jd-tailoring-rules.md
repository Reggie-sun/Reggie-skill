# JD Tailoring Rules

## Tailoring Boundary

JD tailoring may change:

- ordering of already-supported claims
- vocabulary where it remains technically equivalent
- compression or expansion
- which eligible facts receive emphasis
- technology-stack ordering

It may not change:

- project facts
- personal responsibility
- implementation or deployment status
- metrics class or value
- evidence confidence
- time period
- product scope

## Capability Mapping

1. Group the JD into concrete capability families such as RAG, Agent Runtime, Python backend, evaluation, automation, deployment, data, security, or collaboration.
2. Map each family to `claim_id` values: `Direct`, `Adjacent`, or `Gap`.
3. Use only `Direct` evidence as an explicit experience claim.
4. Use `Adjacent` evidence as transferable context without saying the missing capability was performed.
5. List `Gap` items honestly.

## Keyword Rules

- Add a keyword only when the underlying fact already exists.
- Preserve precise project terminology; do not replace a narrower implementation with a broader fashionable label.
- Do not call ordinary orchestration “Agent Runtime”, keyword search “RAG”, scripts “AI Native”, or a local prototype “enterprise deployment” without evidence.
- Keep JD language secondary to repository truth.

## Output Review

Before finalizing, compare tailored and untailored versions claim by claim. Any new noun, verb, number, status, scale, or responsibility term requires an existing ledger source. Put uncovered JD requirements in `Capability Gaps`, not in the resume text.
