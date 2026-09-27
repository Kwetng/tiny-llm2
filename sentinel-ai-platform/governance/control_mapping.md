# Control mapping: one control, many frameworks

Each control is built once in the platform and produces evidence automatically. The columns show which regulatory expectation each control helps meet.

| Control | Where it lives | EU AI Act | PRA SS1/23 | UK/EU GDPR | ISO/IEC 42001 | NIST AI RMF |
|---|---|---|---|---|---|---|
| Use-case register and risk tiering | `governance/use_case_register.yaml` | Risk classification (Art. 6, Annex III) | P1 identification and classification | Records of processing (Art. 30) | 6.1 risk assessment; 8.4 impact assessment | Map |
| Single AI gateway, identity-bound calls | `sentinel/gateway.py`, `sentinel/identity.py` | Record-keeping (Art. 12) | P3 implementation and use | Accountability (Art. 5(2)) | 8.1 operational control | Govern / Manage |
| Entitlement pre-filter and information barriers | `sentinel/rag.py`, `sentinel/identity.py` | Data governance (Art. 10) | P3 data quality and use | Security (Art. 32), minimisation (Art. 5(1)(c)) | A.7 data for AI systems | Map / Manage |
| PII redaction before model and log | `sentinel/pii.py` | Data governance | P3 | Minimisation, security | A.7 | Manage |
| Prompt-injection guard and context quarantine | `sentinel/guard.py`, gateway | Robustness and cybersecurity (Art. 15) | P3, P5 mitigants | Security (Art. 32) | A.6 system life cycle | Measure / Manage |
| Grounding check and abstention | `sentinel/gateway.py`, `sentinel/providers.py` | Accuracy (Art. 15) | P4 outcomes analysis; P5 | Accuracy (Art. 5(1)(d)) | 9.1 monitoring and measurement | Measure |
| Pinned model versions and routing with fallback | `sentinel/config.py`, `infra/` | Accuracy and robustness | P3 change management; SS2/21 resilience | - | 8.1 | Manage |
| Evaluation gate in CI | `evals/`, `.github/workflows/sentinel-ci.yml` | Testing (Art. 9(6)-(8)) | P4 independent validation (evidence) | Accuracy | 9.1, A.6.2.4 verification and validation | Measure |
| Tamper-evident audit log + immutable storage | `sentinel/audit.py`, `infra/` | Logging (Art. 12, 19) | P2 governance evidence | Accountability | 7.5 documented information | Govern |
| Human approval and segregation of duties for actions | `sentinel/agent.py` | Human oversight (Art. 14) | P5 risk mitigants | Art. 22 safeguards | A.9 use of AI systems | Manage |
| Confidence routing to human review | `sentinel/extract.py` | Human oversight | P5 | - | A.9 | Manage |
| Monitoring and drift alerts | `sentinel/monitoring.py` | Post-market monitoring (Art. 72) | P4 ongoing monitoring | Integrity | 9.1, 10 improvement | Measure / Manage |
| Private networking, CMK, least-privilege identities | `infra/terraform/` | Cybersecurity (Art. 15) | SS2/21 outsourcing, operational resilience | Security (Art. 32), transfers (Ch. V) | Relies on ISO/IEC 27001 controls | Manage |
| Model cards and evidence pack | `governance/build_evidence_pack.py` | Technical documentation (Art. 11, Annex IV) | P2, P4 | Transparency | 7.5 | Govern |

Notes:
- The EU AI Act's Annex III high-risk obligations now apply from 2 December 2027 (Digital Omnibus on AI, in force July 2026). None of the three live use cases is high-risk; the rejected retail-scoring example shows where the line is.
- Under SS1/23 a generative AI system is validated as a *system*: foundation model, prompts, retrieval configuration, tools and guardrails (see `data/policies/GR-002` §1.1).
