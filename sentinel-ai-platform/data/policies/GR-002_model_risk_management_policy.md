---
id: GR-002
title: Model Risk Management Policy
business_line: group
classification: internal
owner: Head of Model Risk Management
version: 6.0
effective: 2025-12-01
---

## 1 Scope
### 1.1 Models in scope
This policy applies to all models as defined in PRA SS1/23, including AI and machine learning models, vendor models and generative AI systems. For a generative AI system the model is the whole system: the underlying foundation model, prompts, retrieval configuration, tools and guardrails.

## 2 Tiering
### 2.1 Materiality tiers
Every model is assigned a tier from 1, the highest materiality, to 3. Generative AI systems that support credit decisions, client communications or regulatory reporting are Tier 1 or Tier 2.
### 2.2 Validation frequency
Tier 1 models are independently validated before use and revalidated at least annually. Tier 2 models are revalidated at least every two years.

## 3 Change management
### 3.1 Material changes
A change of foundation model version, embedding model, prompt template or retrieval configuration in a Tier 1 or Tier 2 generative AI system is a model change. It must pass the automated evaluation suite and be approved by Model Risk Management before release.
### 3.2 Monitoring
Model owners must monitor performance monthly against thresholds agreed with Model Risk Management and report breaches within 5 business days.
