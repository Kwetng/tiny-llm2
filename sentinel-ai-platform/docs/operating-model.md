# Operating model: how the AI Engineering function runs this platform

## Team (first 12 months, 10–15 people)

| Role | Number | Owns in this repository |
|---|---|---|
| Head of AI Engineering | 1 | Standards, roadmap, design authority for ADRs |
| Platform lead | 1 | Gateway, router, audit, infrastructure (`sentinel/gateway.py`, `infra/`) |
| Applications lead | 1 | Use cases: policy assistant, extraction, agent |
| AI / LLM engineers | 3–4 | Retrieval, prompts, evaluation sets, guard |
| Platform / MLOps engineers | 2–3 | CI/CD, Terraform, monitoring, on-call |
| Full-stack engineers | 2–3 | User interfaces and integrations (Teams, credit and collateral systems) |
| Data engineer | 1–2 | Ingestion and labelling of policy and contract sources |
| AI security and quality engineer | 1 | Red-team suite, guard patterns, penetration-test liaison |

**Hub and spoke:** the hub (platform lead and platform engineers) owns the shared services; spokes (small squads under the applications lead) build use cases on them.

## Who does what

| Activity | AI Innovation & Transformation | AI Engineering | Architecture & Engineering | Risk / Compliance / Cyber | Business owner |
|---|---|---|---|---|---|
| Use-case idea and value case | A | C | I | C | R |
| Intake and risk tiering (`use_case_register.yaml`) | R | R | C | A | C |
| Solution design and ADRs | C | A | C (design authority) | C | I |
| Build, evaluation gate, deployment | I | A | C | C | I |
| Independent validation and approval | I | R (evidence pack) | I | A | C |
| Monitoring and incidents | I | A | I | C | R |
| Business outcome | C | C | I | I | A |

A = accountable, R = responsible, C = consulted, I = informed.

## First 90 days

| Days | Focus | Output in this repository |
|---|---|---|
| 1–30 | Listen and map: stakeholders, existing pilots, shadow AI, group policy from Tokyo | Use-case register first draft; control mapping agreed with Model Risk |
| 31–60 | Design and decide: platform blueprint, RACI, thresholds with Model Risk, two lighthouse use cases | ADRs 0001–0005; `thresholds.yaml` signed off |
| 61–90 | Deliver: landing zone, gateway, evaluation gate in CI, lighthouse use cases in test | Terraform applied in dev; CI green; first evidence pack to the AI governance forum |

## How a new use case gets to production

1. **Intake:** register the use case, then the risk tier and accountable SMF are agreed with Risk.
2. **Design:** reuse the shared services; write an ADR for anything new.
3. **Build** on the golden path; business experts add golden questions and red-team cases.
4. **Gate:** CI passes and the evidence pack is generated.
5. **Validation:** Model Risk reviews the evidence pack and adds independent tests. Tier 1 needs approval before use.
6. **Pilot:** a limited user group, with monitoring alerts owned by named people.
7. **Scale**, with monthly monitoring reports and re-validation on any model change.

## Measures reported monthly

- **Engineering:** deployment frequency, lead time for changes, change failure rate and time to restore (the DORA metrics).
- **Quality and risk:** evaluation scores, abstention rate, grounding failures, blocked requests, incidents.
- **Value:** hours saved, cycle time (for example CSA onboarding), adoption.
- **Cost:** cost per use case and per business line.
- **Platform leverage:** time to onboard a new use case.
