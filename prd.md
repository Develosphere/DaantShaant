# DaantShaant — Hackathon Product Requirements Document (PRD)

**Version:** 2.0 — Existing Product Upgrade / Hackathon Edition  
**Product:** DaantShaant Autonomous Dental AI Assistant & Care Marketplace  
**Status:** Living document — update whenever product scope, architecture, or implementation decisions change  
**Primary audience:** Engineering team, hackathon teammates, Qoder/Codex/Antigravity prompt-generation LLMs, designer, technical reviewers, judges  
**Baseline:** Existing `Develosphere/DaantShant` codebase provided by the team, improved rather than rebuilt from scratch

---

# 1. Purpose of This PRD

This PRD replaces the previous "rebuild from scratch" plan.

The hackathon organizers clarified that:

- the project does **not** need to be created from scratch,
- development is **not restricted to Qoder**,
- any IDE, coding assistant, LLM, agentic IDE, or development workflow may be used,
- Alibaba Cloud hosting is **not mandatory**,
- Qoder credits are a development benefit, not a platform lock-in,
- the main judging focus is the **technical quality, sophistication, implementation depth, and usefulness of the project**.

Therefore, DaantShaant will use the **existing mature project as the production baseline** and improve the technically important parts instead of recreating features already present.

This document defines:

1. the product vision,
2. the current implemented baseline,
3. problems in the old implementation,
4. the new architecture,
5. the database migration,
6. Qwen primary AI migration,
7. Gemini fallback,
8. clinical RAG and evidence-based reasoning,
9. LangGraph unification,
10. free/open map replacement,
11. patient/dentist workflows,
12. security improvements,
13. model evaluation,
14. testing,
15. hosting options,
16. phased implementation,
17. Qoder credit/token optimization,
18. collaboration rules,
19. MVP and judging story.

---

# 2. Product Identity

## 2.1 Product Name

**DaantShaant**

## 2.2 Product Category

Autonomous AI-assisted dental screening, triage, patient-memory, dentist-navigation, and dentist-marketplace platform.

## 2.3 One-Line Description

> **DaantShaant is an autonomous AI-assisted dental screening and care-navigation system that analyzes oral images, grounds its reasoning in professional dental knowledge, evaluates urgency, produces an actionable screening report, and connects patients with suitable nearby dentists.**

## 2.4 Core Promise

The system should move the patient through a full care journey:

```text
Scan
↓
Validate
↓
Understand
↓
Ground in Evidence
↓
Triage
↓
Explain
↓
Recommend Specialist
↓
Find Dentist
↓
Take Action
↓
Remember
```

DaantShaant is not intended to be merely:

- an image classifier,
- a one-shot Gemini prompt,
- a generic chatbot,
- a dentist directory,
- or an e-commerce recommendation app.

It is intended to be a **stateful, agentic dental-care orchestration system**.

---

# 3. Medical / Safety Positioning

DaantShaant must not claim to be a licensed human dentist.

It may provide:

- AI-assisted screening,
- visible observations,
- possible concern categories,
- confidence,
- evidence-backed triage,
- urgency,
- recommended next steps,
- recommended dental specialization,
- local dentist navigation.

It must not claim:

- guaranteed diagnosis,
- certainty about conditions that require examination/X-rays,
- that a dental photo replaces a licensed dentist,
- that AI output is treatment authorization.

Preferred terminology:

- AI screening verdict
- observed signs
- possible concern
- evidence-supported triage
- recommended next step
- urgency
- recommended specialist
- licensed dentist confirmation

For high-risk situations the system may use stronger language through **Insist Mode**, but the urgency must come from evidence-backed rules rather than arbitrary model wording.

---

# 4. Why We Are Keeping the Existing Project

The old codebase already contains valuable, working product functionality.

Rebuilding those features would waste hackathon time and reduce technical depth.

The correct strategy is:

```text
Existing DaantShaant
=
working product breadth

+

Hackathon upgrades
=
better architecture
better AI
better persistence
better agent orchestration
better maps
better clinical grounding
better security
tests/evaluation
```

The existing product should therefore remain the main repository.

---

# 5. Existing Implemented Baseline

The provided repository already contains the following.

## 5.1 Next.js Web Application

Existing web experiences include:

- public landing page,
- get-started flow,
- patient portal,
- patient login/register,
- patient dashboard,
- patient scan,
- patient scan history,
- patient chat,
- patient dentist finder,
- dentist portal,
- dentist login/register,
- dentist dashboard,
- products,
- orders,
- admin portal,
- admin login/register/users.

## 5.2 Three Scan Modes

Existing scanning already supports:

1. Snapshot
2. Upload
3. Live WebSocket scan

This functionality should be retained and improved.

## 5.3 Live WebSocket Scanning

The existing orchestrator already supports a true live scanning session.

Current conceptual flow:

```text
Browser camera
↓
WebSocket session
↓
Frames received
↓
Frame throttling
↓
Vision pipeline
↓
Diagnosis pipeline
↓
Partial results
↓
Stability tracking
↓
Best-frame selection
↓
Final result
```

This is a major technical asset and should not be replaced with a fake "live preview only" implementation.

## 5.4 Teeth Analyzer Service

Existing service:

```text
services/teeth_analyzer
```

Responsibilities include:

- image decoding,
- quality evaluation,
- preprocessing,
- Gemini vision,
- structured visual findings.

## 5.5 Diagnosis Service

Existing service:

```text
services/diagnosis
```

Responsibilities include:

- finding-to-condition mapping,
- confidence thresholds,
- severity,
- action triggers.

The service architecture should be retained, while the clinical rule logic is improved.

## 5.6 Orchestrator

Existing:

```text
orchestrator
```

Responsibilities include:

- main API gateway,
- scan pipeline,
- live sessions,
- chat,
- RAG,
- dentist portal,
- product recommendation,
- dentist recommendation,
- session logging.

## 5.7 RAG

Existing RAG already includes:

- sentence-transformers,
- `all-MiniLM-L6-v2`,
- FAISS,
- chunking,
- document ingestion,
- `.md`,
- `.txt`,
- `.pdf`,
- `.docx`,
- semantic retrieval,
- keyword retrieval,
- hybrid scoring,
- active dental issue boosting,
- chat grounding.

## 5.8 LangGraph

Existing real LangGraph workflows include:

### Product Recommendation Graph

```text
START
↓
search_products
↓
similarity router
├── low similarity → terminate
└── continue
    ↓
get_details
↓
rank
↓
log_session
↓
generate_response
↓
END
```

### Dentist Recommendation Graph

```text
START
↓
query_platform
↓
query_places
↓
merge_rank
↓
log_session
↓
END
```

The important missing part is that the **main clinical dental workflow is not yet a unified LangGraph**.

## 5.9 Dentist Marketplace

Existing system already includes:

- platform dentists,
- specialty matching,
- partner weighting,
- verification weighting,
- distance,
- Google Places fallback,
- interactive map,
- pins,
- dentist recommendation sessions,
- appointment requests.

This architecture will be retained but Google-specific infrastructure will be replaced.

## 5.10 Dentist Product Marketplace

Existing functionality also includes:

- dentist products,
- product management,
- AI product description,
- recommendation graph,
- orders.

This remains a secondary capability.

It must not distract from the main hackathon story:

> Clinical AI → Triage → Dentist Action.

---

# 6. Main Problems in the Existing Architecture

The existing project is feature-rich but fragmented.

## 6.1 Fragmented AI Providers

Current AI calls are spread across:

- Gemini,
- OpenRouter,
- Gemini-specific vision code,
- Gemini-specific recommendation formatting,
- fallback behavior implemented in different places.

This creates:

- provider coupling,
- inconsistent errors,
- inconsistent structured outputs,
- harder testing,
- harder model replacement.

### New decision

Create one **DaantShaant AI Gateway**.

---

## 6.2 Main Clinical Pipeline Is Not Unified Through LangGraph

Current clinical flow is essentially:

```text
Image
↓
Teeth Analyzer service
↓
Diagnosis service
↓
Response
```

Chat, RAG, marketplace, product agents, and dentist agents remain separate.

The product PRD previously described a shared `DentalGraphState`, but the actual code does not yet have a unified production clinical graph.

### New decision

Build a real master **DaantShaant Clinical LangGraph**.

---

## 6.3 Legacy Persistence Fragmentation — RESOLVED

The pre-Phase-1 implementation stored these concepts in separate document collections:

- users,
- conversations,
- messages,
- analysis history,
- portal users,
- products,
- recommendation sessions,
- orders,
- dentist recommendations,
- appointments.

This creates duplicate identity concepts and weak relational integrity.

### Implemented decision

Persistence is now **Supabase PostgreSQL**, accessed through SQLAlchemy/Alembic rather than tying core code to the Supabase SDK. The legacy runtime and drivers are removed.

---

## 6.4 Patient Identity Was Split — RESOLVED

The old frontend mapped a portal user to a separate random local clinical UUID.

Conceptually:

```text
Portal User ID
↓
localStorage mapping
↓
random clinical UUID
↓
scan/chat APIs
```

This creates fragmented ownership and weak authorization.

### New decision

One authenticated user identity must own:

- patient profile,
- scans,
- reports,
- conversations,
- recommendations,
- appointments.

---

## 6.5 Auth Security Needs Hardening

Current issues include:

- JWT stored in localStorage,
- default JWT secret fallback,
- some APIs accepting raw user IDs,
- public admin registration route,
- weak separation between authentication and object ownership.

### New decision

Port the stronger auth pattern previously developed:

- short-lived access JWT,
- opaque rotating refresh token,
- refresh token hash stored in DB,
- HttpOnly refresh cookie,
- access token memory-only,
- role guards,
- ownership checks,
- no public admin registration.

---

## 6.6 Clinical Rule Mappings Need Evidence

Some old mappings are too aggressive or incorrect.

Example:

```text
broken_teeth
→ ADVANCED_CAVITY
```

A broken tooth is not automatically advanced caries.

Current confidence thresholds are also primarily product-defined rather than linked to explicit professional evidence.

### New decision

Separate:

```text
Visual Observation
↓
Possible Concern Category
↓
Clinical Evidence
↓
Deterministic Triage Rules
```

Do not map every visual abnormality directly into a disease diagnosis.

---

## 6.7 Google Maps / Places Is No Longer Viable

Existing:

- Google Maps JS,
- Places search,
- Place Details,
- Google geocoding.

The previous project credits/API availability are expired.

### New decision

Replace Google maps stack with:

- MapLibre GL JS,
- OpenFreeMap,
- OpenStreetMap,
- Overpass API,
- cached server-side dentist discovery,
- low-volume geocoding where required.

---

## 6.8 Automated Tests Are Insufficient

The old repository lacks a strong automated test foundation.

### New decision

Every meaningful new phase must add focused:

- unit tests,
- integration tests,
- graph routing tests,
- AI schema tests,
- provider-fallback tests,
- data-access tests.

---

# 7. New Target Architecture

```text
                              USER
                                │
                     Next.js Web Application
                                │
                    HTTPS / WebSocket APIs
                                │
                     FastAPI Orchestrator
                                │
                    Master Clinical LangGraph
                                │
 ┌──────────────────────────────┼────────────────────────────────┐
 │                              │                                │
 ▼                              ▼                                ▼
Teeth Analyzer             Clinical RAG                   Marketplace
Service                    / Evidence                     Services
 │                              │                                │
 ▼                              ▼                                ▼
Image Quality             FAISS + Curated                 Supabase DB
Semantic Relevance        Dental Corpus                   OSM / Overpass
Clinical Vision           Rules / Triage                  MapLibre
 │                              │                                │
 └──────────────────────────────┼────────────────────────────────┘
                                │
                        DaantShaant Report
                                │
                                ▼
                         Persistent Memory
                                │
                                ▼
                      Supabase PostgreSQL
```

---

# 8. Technology Stack — Target

## Frontend

- Next.js
- React
- TypeScript
- existing CSS/theme initially
- Phase 3B Figma redesign later
- MapLibre GL JS for maps

## Backend

- FastAPI
- Pydantic
- HTTPX
- SQLAlchemy 2
- asyncpg
- Alembic
- LangGraph
- existing service boundaries retained

## Database

- Supabase PostgreSQL
- direct PostgreSQL access through SQLAlchemy
- provider-neutral `DATABASE_URL`

## Authentication

- custom secure JWT + rotating refresh sessions
- PostgreSQL session table
- HttpOnly refresh cookie
- memory-only access token

## AI

Primary:

- Alibaba Cloud Model Studio
- Qwen
- verified `qwen3.7-plus` default

Fallback:

- Gemini Flash-Lite family
- exact model configured through environment

## RAG

- sentence-transformers
- FAISS
- curated professional dental documents
- hybrid retrieval
- clinical finding driven retrieval

## Maps

- MapLibre GL JS
- OpenFreeMap
- OpenStreetMap
- Overpass API

## Hosting

Preferred:

```text
Vercel
→ Next.js frontend

Office VPS
→ FastAPI services
→ LangGraph
→ FAISS
```

Database:

```text
Supabase PostgreSQL
```

AI:

```text
Alibaba Model Studio
```

Fallback AI:

```text
Gemini API
```

Alternative backend hosting if VPS unavailable:

- Railway
- another Python/Docker host

---

# 9. Database Migration — Supabase PostgreSQL

Database migration is the **first engineering phase**.

## 9.1 Design Principle

Supabase is used primarily as a managed PostgreSQL host.

Core code should depend on:

```text
SQLAlchemy
+
asyncpg
+
DATABASE_URL
```

not on vendor-specific Supabase database APIs.

This preserves portability.

---

# 10. Proposed Relational Schema

The final exact schema may be refined during migration.

## 10.1 `users`

Purpose:

Unified account identity.

Suggested fields:

```text
id UUID PK
email CITEXT/unique
password_hash
role patient|dentist|admin
status active|disabled
first_name
last_name
phone
profile_image_url
created_at
updated_at
```

---

## 10.2 `auth_sessions`

```text
id UUID PK
user_id FK users
refresh_token_hash
expires_at
revoked_at
created_at
last_used_at
user_agent optional
ip_hash optional
```

Raw refresh tokens must never be stored.

---

## 10.3 `patient_profiles`

```text
user_id PK/FK users
city
country
location_text
latitude
longitude
preferences JSONB
created_at
updated_at
```

---

## 10.4 `dentists`

Supports:

- registered DaantShaant dentists,
- verified partners,
- OSM/community dentists.

Suggested fields:

```text
id UUID PK
owner_user_id nullable FK users
source platform|osm|curated
external_id nullable
name
clinic_name
email
phone
address
city
country
latitude
longitude
specialties JSONB
degree
degree_year
institution
specialized_training
qualifications JSONB
rating nullable
review_count nullable
is_verified
is_partner
is_active
commission_rate
source_metadata JSONB
last_refreshed_at
created_at
updated_at
```

Important:

A newly registered dentist defaults:

```text
is_verified = false
is_partner = false
```

---

## 10.5 `scans`

```text
id UUID PK
patient_user_id FK users
input_mode snapshot|upload|live
status
media_object_key nullable
mechanical_quality_score nullable
mechanical_quality_issues JSONB
relevance_score nullable
relevance_result JSONB
ai_provider nullable
ai_model nullable
created_at
updated_at
```

Suggested statuses:

```text
received
quality_pending
quality_rejected
quality_passed
relevance_pending
relevance_rejected
relevance_passed
clinical_pending
clinical_complete
clinical_failed
```

---

## 10.6 `scan_findings`

One row per normalized visible finding.

```text
id UUID PK
scan_id FK scans
finding_code
region
tooth_reference nullable
observation
confidence
visibility
raw_ai_metadata JSONB
created_at
```

No finding should automatically equal a confirmed disease.

---

## 10.7 `clinical_reports`

```text
id UUID PK
scan_id FK scans
patient_user_id FK users
verdict
urgency_level
summary
possible_concerns JSONB
recommended_actions JSONB
recommended_specialist
limitations JSONB
evidence_refs JSONB
agent_trace_summary JSONB
created_at
updated_at
```

---

## 10.8 `conversations`

```text
id UUID PK
patient_user_id FK users
title
active_scan_id nullable
active_report_id nullable
created_at
updated_at
```

---

## 10.9 `messages`

```text
id UUID PK
conversation_id FK conversations
user_id nullable
role user|assistant|system
content
provider nullable
model nullable
evidence_refs JSONB
created_at
```

---

## 10.10 `products`

Existing dentist product capability.

```text
id UUID PK
dentist_id FK dentists
name
category
price
raw_description
ai_description
problems_solved JSONB
images JSONB
status
view_count
recommendation_count
created_at
updated_at
```

---

## 10.11 `product_recommendations`

```text
id UUID PK
session_id UUID
patient_user_id FK users
scan_id nullable
issue
recommendations JSONB
created_at
```

---

## 10.12 `orders`

Existing dentist product orders.

```text
id UUID PK
dentist_id FK dentists
patient_user_id nullable FK users
items JSONB
total
status
created_at
updated_at
```

---

## 10.13 `dentist_recommendations`

```text
id UUID PK
session_id UUID
patient_user_id FK users
scan_id nullable
report_id nullable
specialist
severity
patient_lat
patient_lng
results JSONB
created_at
```

---

## 10.14 `appointment_requests`

```text
id UUID PK
patient_user_id FK users
dentist_id FK dentists
scan_id nullable
report_id nullable
message nullable
preferred_time nullable
status requested|accepted|declined|completed|cancelled
created_at
updated_at
```

---

## 10.15 `commission_records`

```text
id UUID PK
appointment_id FK appointment_requests
dentist_id FK dentists
commission_rate
commission_amount nullable
status pending|earned|settled|waived
created_at
```

Actual payment integration is not required for the hackathon.

---

## 10.16 `live_scan_sessions`

Optional but useful for technical traceability.

```text
id UUID PK
patient_user_id FK users
started_at
ended_at
frames_received
frames_analyzed
best_scan_id nullable
final_report_id nullable
status
metadata JSONB
```

---

# 11. Legacy-to-PostgreSQL Migration — COMPLETE

The legacy concepts now map into PostgreSQL as follows.

| Existing Mongo concept | New PostgreSQL target |
|---|---|
| users | users / patient_profiles |
| portal_users | users + patient_profiles/dentists |
| conversations | conversations |
| messages | messages |
| analysis_history | scans + scan_findings + clinical_reports |
| portal_products | products |
| portal_sessions | product_recommendations / agent sessions |
| portal_recommendations | product_recommendations |
| portal_orders | orders |
| portal_dentist_recommendations | dentist_recommendations |
| portal_appointments | appointment_requests |

The old local datastore was not reachable and no accessible demo dataset required import. Schema creation, persistence cutover, dependency removal, and Supabase verification completed in Phase 1B.

---

# 12. Authentication Upgrade

The database phase must also remove the split patient identity.

## Target Flow

```text
Register/Login
↓
users.id UUID
↓
same identity used for:
    scan ownership
    report ownership
    conversation ownership
    appointment ownership
    recommendations
```

## Access Token

Short-lived JWT.

## Refresh Token

Opaque random token.

Browser:

```text
HttpOnly cookie
```

Database:

```text
SHA-256 hash only
```

## Frontend

Access token:

```text
memory only
```

No localStorage access token.

## Security Requirements

- remove insecure fallback JWT secret,
- disable public admin registration,
- patient APIs use authenticated user identity,
- never accept trusted `user_id` from the browser where auth identity already exists,
- object ownership checks required,
- dentist role cannot read arbitrary patient scans.

---

# 13. AI Provider Architecture

After DB migration, AI migration is the next highest priority.

## 13.1 DaantShaant AI Gateway

```text
Business/Agent Module
↓
DaantShaant AIGateway
├── Qwen provider — PRIMARY
└── Gemini provider — FALLBACK
```

All provider-specific HTTP logic belongs inside provider adapters.

---

# 14. Qwen Strategy

Alibaba Qwen becomes the main intelligence provider.

The team already verified:

```text
qwen3.7-plus
```

for:

- text requests,
- multimodal image requests,
- real Singapore Model Studio workspace endpoint.

## Runtime Strategy

Use task-based model configuration.

Example configuration design:

```text
QWEN_DEFAULT_MODEL=qwen3.7-plus
QWEN_VISION_MODEL=qwen3.7-plus
QWEN_REASONING_MODEL=qwen3.7-plus
QWEN_CHAT_MODEL=qwen3.7-plus
```

Initially these may all point to the verified model.

Later, if different Qwen models are selected from available Model Studio quotas, the IDs can change without modifying business code.

This gives the architecture "multiple task models" without inventing unsupported model names.

---

# 15. Gemini Strategy

Gemini remains a fallback.

Use cases:

- Qwen outage,
- quota exhaustion,
- retryable provider error,
- optional second opinion later.

Gemini should not remain the default primary model.

Technical fallback must remain different from clinical disagreement.

Future concept:

```text
Qwen finding confidence low
↓
optional Gemini second opinion
↓
model agreement/disagreement recorded
```

This is not required for first MVP.

---

# 16. Remove OpenRouter From Primary Architecture

OpenRouter should be retired from the core new implementation.

Reasons:

- unnecessary third provider layer,
- less transparent provider behavior,
- Qwen now has working direct Model Studio access,
- Gemini remains enough as fallback,
- simplified observability,
- simplified testing.

Legacy code may remain temporarily during migration but should not be used by the final primary clinical workflow.

---

# 17. Semantic Image Relevance

Mechanical quality and semantic relevance are separate.

## Mechanical Question

> Are the pixels technically usable?

Examples:

- dimensions,
- brightness,
- overexposure,
- contrast,
- blur.

## Semantic Question

> Does the image actually show useful dental/oral content?

Qwen handles semantic relevance.

Relevant:

- teeth,
- gums,
- intraoral tissue,
- mouth region,
- localized jaw/oral swelling where appropriate.

Reject:

- random object,
- scenery,
- unrelated body part,
- closed-mouth selfie with no useful evidence,
- image where oral region cannot be evaluated.

This step must **not perform diagnosis**.

---

# 18. Clinical Vision Architecture

Qwen Clinical Vision should output structured observations.

Do not ask:

> "What disease is this?"

Ask:

> "What is visibly observable?"

Suggested structured fields:

```text
finding_code
observation
region
tooth_reference optional
confidence
visibility
limitations
```

Examples:

- dark occlusal area,
- visible plaque-like deposit,
- gingival redness,
- visible swelling,
- chipped tooth structure,
- discoloration,
- missing tooth space.

Disease interpretation occurs later.

---

# 19. Clinical RAG Upgrade

The current FAISS implementation should be retained.

The important change:

RAG must become part of the **clinical pipeline**, not only chat.

## New Flow

```text
Structured visual finding
↓
Clinical retrieval query
↓
FAISS
↓
professional dental evidence
↓
rule engine / triage
```

Example:

```text
Finding:
localized gingival redness + swelling

↓ retrieval

Professional evidence about:
gingival inflammation
red flags
recommended dental evaluation
limitations of visual-only assessment
```

---

# 20. RAG Data Categories

Keep three datasets separate.

## 20.1 Clinical Knowledge Corpus

Used for RAG.

Examples:

- professional guidelines,
- dental textbooks/reference material,
- papers,
- public clinical guidance,
- structured condition summaries.

## 20.2 Image Evaluation Dataset

Used for evaluation.

Not RAG.

Purpose:

- Qwen vs Gemini comparison,
- relevance accuracy,
- structured-output validity,
- model agreement.

## 20.3 Dentist Directory Dataset

Used by marketplace.

Not RAG.

Includes:

- DaantShaant partners,
- platform dentists,
- OSM/community dentists.

---

# 21. Evidence / Rule Engine

The diagnosis service should evolve into an evidence-backed triage engine.

## Old Pattern

```text
vision label
↓
hard-coded disease mapping
↓
severity
```

## New Pattern

```text
visible finding
↓
possible concern categories
↓
retrieved evidence
↓
deterministic rules
↓
triage / urgency / action
```

Rules must retain references/metadata showing why they exist.

Do not use arbitrary thresholds without documentation.

---

# 22. Clinical Output

The final report should contain:

## Main Verdict

Examples:

- routine monitoring,
- dental visit recommended,
- visit soon,
- urgent dental consultation.

## Visible Findings

## Possible Concerns

Not guaranteed diagnoses.

## Confidence

Finding-level confidence preferred.

## Urgency

## Recommended Visit Timeframe

## Recommended Specialist

Examples:

- general dentist,
- periodontist,
- endodontist,
- restorative dentist,
- oral surgeon.

## Next Steps

## Limitations

## Evidence

Short references, not raw RAG chunks.

---

# 23. Insist Mode

If deterministic/evidence-based red flags are present:

```text
normal report
↓
Insist Mode
↓
stronger action wording
↓
automatic dentist marketplace
↓
nearest appropriate specialist
```

The AI model should not independently decide "critical" merely from prose.

Insist Mode is triggered by the triage layer.

---

# 24. Master LangGraph — Primary Technical Upgrade

The main technical showcase should be a unified LangGraph workflow.

## Proposed `DentalGraphState`

Concept:

```python
class DentalGraphState(TypedDict):
    user_id: str
    scan_id: str
    input_mode: str

    image_ref: str | None

    mechanical_quality: dict | None
    relevance_result: dict | None
    visual_findings: list[dict]

    rag_evidence: list[dict]
    rule_result: dict | None
    clinical_report: dict | None

    recommended_specialist: str | None
    patient_location: dict | None
    recommended_dentists: list[dict]

    conversation_id: str | None

    current_node: str
    errors: list[dict]
```

Exact state fields may be optimized.

---

# 25. Proposed Clinical Graph

```text
START
↓
IntakeNode
↓
MechanicalQualityNode
├── fail → RescanNode → END/Wait
└── pass
    ↓
SemanticRelevanceNode
├── unrelated → RescanNode
└── relevant
    ↓
ClinicalVisionNode
↓
ClinicalRAGNode
↓
EvidenceRuleNode
↓
TriageNode
↓
ReportNode
↓
ShouldRecommendDentist?
├── no → PersistNode
└── yes
    ↓
SpecialistSelectionNode
↓
DentistMarketplaceNode
↓
PersistNode
↓
END
```

The chat agent can later re-enter the case state.

---

# 26. Existing LangGraphs

Do not delete existing product and dentist graphs immediately.

Instead:

## Product Recommendation Graph

Keep as secondary agent tool.

It may be invoked from the main graph for low-risk hygiene/product guidance.

## Dentist Recommendation Graph

Upgrade and call from:

```text
DentistMarketplaceNode
```

This creates graph composition rather than duplicated logic.

---

# 27. Patient Chat / Persistent Case Memory

Current RAG chat should become scan-aware.

## Desired Context

DaantShaant chat should have access to:

- active scan,
- current report,
- previous reports,
- latest findings,
- recommended specialist,
- dentist recommendations,
- patient conversation history.

Example questions:

- "How urgent is this?"
- "Why did you recommend a periodontist?"
- "What should I do until the appointment?"
- "Was my last scan better?"
- "Explain my report simply."

---

# 28. Free/Open Map Replacement

Google Maps and Google Places will be removed.

## Target Stack

### Map Rendering

**MapLibre GL JS**

### Base Map / Style

**OpenFreeMap**

### Geographic Data

**OpenStreetMap**

### Dentist Search

**Overpass API**

### Browser Location

Native:

```text
navigator.geolocation
```

---

# 29. Community Dentist Discovery

Do not perform expensive third-party discovery every time the user opens the map if avoidable.

Preferred architecture:

```text
User city/coordinates
↓
Check cached dentists in PostgreSQL
↓
enough recent results?
├── yes → use DB
└── no
    ↓
Overpass discovery
↓
normalize
↓
cache/upsert into dentists table
↓
rank
```

Possible OSM tag:

```text
amenity=dentist
```

Additional useful tags may be captured if available.

---

# 30. Geocoding Strategy

Preferred:

1. browser GPS when user allows location,
2. stored patient coordinates,
3. manual city/address geocoding when necessary.

Avoid continuous public geocoder autocomplete on every keystroke.

If using a public Nominatim endpoint:

- server-side,
- low frequency,
- identify application,
- cache results,
- respect usage policies.

If later a stronger free geocoder is selected, the geocoder interface can be replaced.

---

# 31. Dentist Recommendation Ranking

Candidate sources:

```text
Platform / Partner
+
OSM / Community
```

Ranking inputs:

- specialist match,
- distance,
- verification,
- partner status,
- location quality,
- available contact data,
- optional ratings where trustworthy.

## Partner Rule

Partners receive ranking preference only when clinically appropriate.

A mismatched partner must not outrank a clinically suitable specialist solely because of commercial status.

---

# 32. Dentist Map UI

The map should display:

- patient location,
- verified partner pins,
- community pins.

Pin interaction opens:

- dentist/clinic name,
- partner badge,
- verification,
- specialty,
- why recommended,
- distance,
- address,
- phone,
- email if available,
- directions,
- call,
- request appointment.

---

# 33. Dentist Verification

New dentist registration means:

```text
registered
≠
verified
≠
partner
```

Default:

```text
is_verified = false
is_partner = false
```

Admin can later approve.

Partner pins and cards should be visually distinct.

---

# 34. Product Recommendation

Keep existing product recommendation agent as a secondary capability.

Use for:

- plaque/hygiene guidance,
- toothbrush,
- toothpaste,
- mouthwash,
- floss,
- other dentist products.

Do not make products the main outcome for potentially serious dental concerns.

Clinical care routing has priority.

---

# 35. User Sitemap

```text
DaantShaant
│
├── Public
│   ├── /
│   ├── /get-started
│   └── role selection
│
├── Patient
│   ├── /patient/login
│   ├── /patient/register
│   ├── /patient/dashboard
│   ├── /patient/scan
│   │   ├── Snapshot
│   │   ├── Upload
│   │   └── Live
│   ├── /patient/scans
│   ├── /patient/chat
│   └── /patient/dentists
│
├── Dentist
│   ├── /dentist/login
│   ├── /dentist/register
│   ├── /dentist/dashboard
│   ├── /dentist/products
│   └── /dentist/orders
│
├── Products
│   └── /products/[id]
│
└── Admin
    ├── /admin/login
    ├── /admin/dashboard
    └── /admin/users
```

Existing legacy/general routes may remain temporarily during migration.

Final route cleanup should remove duplicate experiences.

---

# 36. Patient Primary Use Case

```text
1. Register/Login
2. Open Patient Dashboard
3. Start Dental Scan
4. Choose Snapshot / Upload / Live
5. Mechanical quality validation
6. Retake if technically poor
7. Qwen semantic dental relevance
8. Retake if unrelated
9. Qwen clinical vision
10. Structured visible findings
11. Clinical RAG retrieval
12. Evidence/rule evaluation
13. LangGraph triage
14. Report generated
15. Urgency displayed
16. Specialist recommended
17. Dentist marketplace opens
18. Platform + community dentists ranked
19. Map displayed
20. User opens dentist
21. Call / Directions / Appointment Request
22. User asks DaantShaant follow-up
23. Case remains in history
```

---

# 37. Dentist Use Case

```text
1. Dentist registers
2. Profile created
3. Verification Pending
4. Dentist logs in
5. Manage profile/products
6. Admin verifies
7. Optional partner status
8. Dentist becomes eligible for patient recommendations
9. Appointment requests appear
10. Future commission status available
```

---

# 38. Admin Use Case

Hackathon minimum:

- login,
- list users,
- verify dentist,
- set partner status,
- disable abusive accounts.

Public admin signup should be removed.

Advanced admin analytics are optional.

---

# 39. Model Evaluation Harness — Proposed High-Value Improvement

Technical judges should be able to see that models were evaluated, not blindly trusted.

Create a small evaluation harness.

Dataset:

approximately 30–50 curated test images where legally/licensing-wise appropriate.

Evaluate:

- semantic dental relevance accuracy,
- structured output validity,
- latency,
- Qwen/Gemini agreement,
- model errors,
- fallback frequency,
- confidence calibration.

Possible report:

```text
Qwen
vs
Gemini
```

This is a strong technical differentiator.

Do not put private patient images into Git.

---

# 40. Observability / Agent Trace

For demo and debugging, persist safe agent execution metadata.

Possible events:

```text
quality_check
relevance_check
clinical_vision
rag_retrieval
rule_evaluation
triage
specialist_selection
dentist_search
report_complete
```

Store:

- node,
- duration,
- provider,
- model,
- status,
- fallback used.

Do not store:

- API keys,
- raw image base64,
- sensitive provider payloads unnecessarily.

A simple visual "AI reasoning progress" UI may consume this trace.

---

# 41. Testing Requirements

Each new phase must add relevant tests.

## Database

- schema
- repositories
- ownership
- role access
- transaction handling

## AI Gateway

- Qwen normalization
- fallback
- timeouts
- malformed JSON
- no real provider calls in tests

## Clinical Vision

- schema validation
- disease claims prohibited where needed
- persistence

## Graph

- branch routing
- quality rejection
- relevance rejection
- urgent route
- marketplace route
- failure recovery

## Maps

- Overpass normalization
- ranking
- distance
- cache

## Auth

- login
- refresh rotation
- logout
- role guards
- ownership

---

# 42. Third-Party / Hackathon Documentation

The team should clearly distinguish:

## Alibaba-Native

- Model Studio
- Qwen

## Third-Party / Open Source

- Next.js
- FastAPI
- Supabase PostgreSQL hosting
- SQLAlchemy
- LangGraph
- FAISS
- sentence-transformers
- Gemini fallback
- MapLibre
- OpenFreeMap
- OpenStreetMap
- Overpass

Maintain a document such as:

```text
docs/third-party-usage.md
```

with purpose and usage boundaries.

---

# 43. Hosting Strategy

Alibaba hosting is no longer mandatory.

## Preferred Architecture

```text
Vercel
└── Next.js

Office VPS
└── Docker Compose
    ├── Orchestrator
    ├── Teeth Analyzer
    └── Diagnosis

Supabase
└── PostgreSQL

Alibaba Model Studio
└── Qwen

Gemini
└── fallback
```

## Alternative

If office VPS unavailable:

```text
Vercel
+
Railway / similar Python host
+
Supabase
```

---

# 44. Deployment Principles

Do not over-engineer hackathon deployment.

Avoid:

- Kubernetes,
- multi-region DB,
- service mesh,
- complicated queues,
- distributed tracing stack.

Use:

- Docker,
- health endpoints,
- environment variables,
- simple reverse proxy if VPS,
- HTTPS,
- stable demo configuration.

---

# 45. Secrets

Never commit:

- Supabase DB password,
- JWT secret,
- Qwen/DashScope key,
- Gemini key,
- VPS credentials,
- private test images.

All secrets must remain in environment files / deployment secret stores.

---

# 46. Development Tools

Hackathon rules allow any tools.

The team may use:

- Qoder Enterprise/Premium,
- Codex,
- ChatGPT,
- Gemini Pro,
- Antigravity,
- other IDE assistants where helpful.

Qoder remains a major development tool but is not mandatory for every task.

---

# 47. Qoder Token / Credit Optimization Strategy

Qoder work must remain phase-based.

## Rule

```text
One bounded phase
=
one fresh Qoder chat
```

Do not run one giant chat for the entire project.

---

# 48. Qoder Context Strategy

Create/maintain at repository root:

```text
context.md
```

Purpose:

Compact current implementation state.

Every Qoder prompt begins:

```text
Read /context.md FIRST.
Treat it as canonical CURRENT state.
Do not scan the whole repository.
Inspect only files needed for this phase.
```

At completion:

```text
Update context.md.
Replace obsolete current-state information.
Put history in docs/phase-log.md.
```

---

# 49. Qoder Model Selection

Use the cheapest model capable of the job.

Known useful Qoder tiers from the team account:

| Task | Recommended Qoder Model | Approx Multiplier |
|---|---|---:|
| Documentation-only patch | Lite | 0.0x |
| Deterministic backend/frontend | Qwen3.7-Plus | 0.04x |
| Moderate integration | Qwen3.8-Flash | 0.1x |
| Moderate alternative | Qwen3.7-Max | 0.1x |
| Complex AI/graph/refactor | Qwen3.8-Max | 0.25x |
| Difficult coding fallback | Kimi-K2.7-Code | 0.3x |

Avoid by default:

- Auto,
- Performance,
- Ultimate,
- expensive multi-agent Experts mode.

---

# 50. Qoder Prompt Rules

Every phase prompt should include:

1. execution profile,
2. recommended Qoder model,
3. context-first protocol,
4. exact relevant files,
5. current verified state,
6. exact objective,
7. implementation requirements,
8. explicit non-goals,
9. testing,
10. third-party documentation,
11. context.md update,
12. final response format.

Never ask Qoder:

> "Build the entire DaantShaant upgrade."

---

# 51. Recovery Strategy When Qoder Partially Completes a Phase

Do not rerun the full large prompt.

Instead:

```text
fresh chat
+
context.md
+
current Git diff
+
exact incomplete tasks
```

Use a stronger Qoder model only for the isolated blocker.

---

# 52. Multi-IDE Allocation Strategy

Recommended:

## Qoder

- scoped backend modules,
- database migration,
- API contracts,
- repeatable phase work.

## Codex

- deep repository-wide reasoning,
- LangGraph architecture,
- complex refactor,
- hard debugging.

## Antigravity / Gemini

- frontend iteration,
- design implementation,
- quick visual work,
- debugging where it performs well.

## ChatGPT

- architecture,
- PRD,
- prompt planning,
- code review,
- cross-module reasoning,
- technical audit.

No judge-facing claim should imply that one IDE built the project.

The technical implementation matters.

---

# 53. New Phase Roadmap

The phase order reflects the project lead's current priority:

> **Database first → Qwen AI → clinical agent → maps → final hardening.**

---

# 54. Phase 0 — Hackathon Rebaseline & Qoder Context

**Status:** PRD being created now.

Goals:

- adopt existing repo as baseline,
- create/update `context.md`,
- create `docs/phase-log.md`,
- create/update `docs/third-party-usage.md`,
- add Qoder rules,
- document current architecture,
- prevent old PRD from becoming implementation truth.

Recommended Qoder:

**Lite** if documentation only.

---

# 55. Phase 1A — Supabase PostgreSQL Foundation (COMPLETE)

Goals:

- add SQLAlchemy 2,
- add asyncpg,
- add Alembic,
- configure `DATABASE_URL`,
- create Supabase-compatible DB engine/session,
- create initial relational models,
- generate baseline migration,
- preserve current endpoints.

Do not yet rewrite every business module.

Recommended Qoder:

**Qwen3.7-Plus — 0.04x**

---

# 56. Phase 1B — Full Supabase PostgreSQL Cutover (COMPLETE)

Goals:

- merge the former identity/auth and domain-migration scopes,
- create users/auth_sessions,
- patient/dentist/admin roles,
- migrate registration/login,
- short access JWT,
- rotating refresh cookie,
- eliminate localStorage JWT,
- eliminate random clinical UUID mapping,
- authenticated ownership,
- remove public admin registration.

Also completed in this phase:

- conversations and messages,
- scans, findings, and reports,
- products, orders, and recommendation history,
- dentist records and appointment requests,
- complete runtime MongoDB/driver/configuration removal.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

Reason:

Touches backend + frontend + security.

---

# 57. Phase 1C — REMOVED / MERGED INTO PHASE 1B

Historical goals (completed as part of Phase 1B):

Migrate repositories/services for:

- conversations,
- messages,
- scans/analysis history,
- products,
- recommendation sessions,
- orders,
- dentist recommendations,
- appointments.

Add optional migration/seed script if old development records matter.

After verification:

- remove Motor/PyMongo from active runtime,
- remove Mongo env variables.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

This is not a future phase.

---

# 58. Phase 2A — Shared DaantShaant AI Gateway

Port the already validated gateway concept into this existing repo.

Goals:

- Qwen primary,
- Gemini fallback,
- HTTPX,
- normalized AI result,
- structured output,
- text/image support,
- provider metadata,
- timeout/fallback,
- no OpenRouter in new calls,
- tests with fake providers.

Runtime Qwen default:

```text
qwen3.7-plus
```

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

---

# 59. Phase 2B — Semantic Dental Relevance Gate

Goals:

- Qwen validates oral/dental relevance,
- typed structured output,
- no diagnosis,
- irrelevant image retake,
- external oral-region handling,
- persistence,
- integration into snapshot/upload/live pipeline.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

---

# 60. Phase 2C — Qwen Clinical Vision Upgrade

Replace Gemini-first dental vision with Qwen-first clinical observation extraction.

Goals:

- Qwen primary through shared gateway,
- Gemini fallback,
- structured observations,
- regions,
- optional tooth localization where defensible,
- visible findings,
- confidence,
- limitations,
- no direct disease certainty,
- store `scan_findings`.

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

---

# 61. Phase 3A — Clinical RAG Upgrade

Goals:

- keep FAISS,
- improve corpus metadata,
- connect findings to retrieval,
- evidence snippets/references,
- retrieval service usable by graph,
- no model calls in ingestion tests.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

---

# 62. Phase 3B — Evidence / Rule Engine Rewrite

Goals:

- remove incorrect one-to-one disease mappings,
- define evidence-backed triage rules,
- possible concern categories,
- urgency,
- specialist,
- Insist Mode,
- link rules to evidence references.

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

Because this is clinically sensitive and central.

---

# 63. Phase 4 — Unified Clinical LangGraph

Goals:

Create production master graph:

```text
quality
→ relevance
→ vision
→ RAG
→ rules
→ triage
→ report
→ specialist
→ marketplace
→ persist
```

Reuse existing subgraphs where appropriate.

Add:

- conditional routing,
- retryable provider errors,
- rescan branches,
- graph state persistence,
- agent trace.

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

Codex can be used for architecture review/debugging.

---

# 64. Phase 5A — Clinical Report & History

Goals:

- persist reports,
- report detail,
- scan history,
- evidence,
- limitations,
- urgency,
- specialist,
- agent progress UI.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

---

# 65. Phase 5B — Persistent Case Chat

Goals:

- PostgreSQL conversations,
- report-aware chat,
- scan-aware RAG,
- patient history,
- Qwen primary,
- Gemini fallback,
- identity-based ownership.

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

---

# 66. Phase 6A — Google Maps Removal

Goals:

Remove:

- Google Maps loader,
- Google Places,
- Google geocoder,
- Google API key dependencies.

Preserve frontend route/UX behavior where possible.

Recommended Qoder:

**Qwen3.7-Plus — 0.04x**

---

# 67. Phase 6B — OSM Dentist Discovery Backend

Goals:

- Overpass client,
- normalize OSM dentist entities,
- DB caching/upsert,
- source metadata,
- distance,
- specialist/platform merge,
- TTL refresh,
- resilient API failure handling.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

---

# 68. Phase 6C — MapLibre / OpenFreeMap Frontend

Goals:

- MapLibre rendering,
- OpenFreeMap style,
- patient pin,
- partner pins,
- community pins,
- dentist popup/card,
- map/list layout,
- directions action,
- remove Google types/package.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

Antigravity may be used for visual polish.

---

# 69. Phase 6D — Dentist Ranking / Marketplace Agent Upgrade

Goals:

- appropriate specialist match,
- platform partner priority,
- verification,
- distance,
- OSM community alternatives,
- no commercial override of clinical relevance,
- reuse existing LangGraph dentist agent.

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

---

# 70. Phase 7 — Live Scan Intelligence Upgrade

Existing live scan is preserved.

Goals:

- semantic relevance before repeated clinical calls,
- better frame selection,
- agent progress,
- duplicate finding stability,
- lower unnecessary model usage,
- optional Qwen live/realtime experiments if time permits.

Do not rewrite WebSocket foundation.

Recommended Qoder:

**Qwen3.8-Max — 0.25x**

---

# 71. Phase 8 — Evaluation Harness

Goals:

- curated test manifest,
- Qwen/Gemini comparison,
- relevance evaluation,
- schema validity,
- latency,
- provider agreement,
- graph outcomes,
- exportable benchmark report.

Recommended Qoder:

**Qwen3.8-Flash — 0.1x**

---

# 72. Phase 9 — Automated Testing / Security Hardening

Goals:

- full integration tests,
- ownership,
- auth,
- graph routing,
- DB transactions,
- provider failure,
- map fallback,
- remove secret fallbacks,
- input limits,
- public admin signup removal,
- security checklist.

Recommended Qoder:

**Qwen3.8-Max** for audit,
then cheaper targeted repair chats.

---

# 73. Phase 10 — Final UI/UX Integration

Use final designer Figma from the parallel design phase.

Goals:

- preserve working APIs,
- replace old visual layer,
- responsive UI,
- scan states,
- agent progress,
- report,
- map,
- chat,
- dentist portal.

Recommended:

Antigravity for visual implementation plus targeted Qoder/Codex fixes.

---

# 74. Phase 11 — Deployment

Preferred:

```text
Frontend → Vercel
Backend → office VPS Docker Compose
DB → Supabase
AI → Alibaba Model Studio
Fallback → Gemini
```

Goals:

- production env,
- HTTPS,
- CORS,
- secure cookies,
- DB migration,
- FAISS persistence,
- health checks,
- demo seeding.

Recommended Qoder:

**Qwen3.8-Flash/Max depending infrastructure complexity**

---

# 75. Phase 12 — Demo Hardening

Goals:

- reliable demo dataset,
- partner dentists,
- patient account,
- sample dental scans,
- provider failure fallback,
- stable map,
- stable reports,
- demo script,
- screenshots/video fallback,
- final technical architecture diagram.

Use cheapest capable tool per issue.

---

# 76. Parallel Design Phase

Final UI/UX design remains a parallel track.

Designer should work from the separate:

```text
DaantShaant_Phase_3B_Design_Instructions.md
```

Engineering should not wait for the final design to complete technical phases.

---

# 77. Phase Splitting Rule

If any Qoder phase looks likely to:

- touch more than 2–3 major subsystems,
- require >10–15 significant files,
- involve DB + backend + frontend + AI simultaneously,

split it into A/B phases.

Token savings are less important than avoiding failed giant executions.

---

# 78. Partial Submission Strategy

Because the old project is already functional, the partial submission can truthfully demonstrate:

- existing UI,
- three scan modes,
- live WebSocket scanning,
- Gemini vision baseline,
- diagnosis service baseline,
- RAG,
- chat,
- LangGraph product agent,
- LangGraph dentist agent,
- marketplace/map baseline,
- dentist portal.

The submission should explain completed and active hackathon upgrades:

```text
Legacy document persistence
→ Supabase PostgreSQL (complete)

Gemini/OpenRouter fragmented AI
→ Qwen-primary gateway

fragmented agents
→ unified clinical LangGraph

Google Maps
→ MapLibre/OpenStreetMap

hard-coded diagnosis
→ evidence-backed triage
```

This makes the partial submission look like a mature product under technical upgrade rather than an unfinished prototype.

---

# 79. MVP Success Criteria

DaantShaant hackathon MVP is considered complete when:

- [ ] Supabase PostgreSQL is the active persistent DB.
- [ ] User identity is unified.
- [ ] Authentication is secure and ownership-enforced.
- [ ] Snapshot works.
- [ ] Upload works.
- [ ] Live WebSocket scan works.
- [ ] Mechanical quality gate works.
- [ ] Qwen semantic relevance works.
- [ ] Qwen clinical vision works.
- [ ] Gemini fallback works.
- [ ] FAISS clinical RAG is integrated into the clinical path.
- [ ] Evidence/rule triage works.
- [ ] Master LangGraph orchestrates the clinical flow.
- [ ] Report is persisted.
- [ ] Urgency and specialist are displayed.
- [ ] Google Maps is removed.
- [ ] MapLibre map works.
- [ ] OSM/Overpass community dentists work.
- [ ] Partner dentists are appropriately prioritized.
- [ ] Interactive dentist pin/card works.
- [ ] Appointment request works.
- [ ] Persistent patient chat knows the report.
- [ ] Automated tests cover critical flows.
- [ ] Evaluation harness produces model metrics.
- [ ] App is deployed reliably.

---

# 80. Primary Judge Demonstration Flow

The ideal live demonstration:

```text
1. Patient logs in
2. Opens live dental scan
3. Camera quality guidance appears
4. DaantShaant confirms dental relevance
5. Qwen clinical vision analyzes best frame
6. UI shows agent workflow progress
7. RAG retrieves clinical evidence
8. Triage engine produces urgency
9. Report appears
10. Recommended specialist appears
11. Dentist map automatically opens
12. Partner + community dentists appear
13. User opens a dentist pin
14. User requests consultation
15. User opens AI chat
16. Asks "Why did you recommend this specialist?"
17. DaantShaant answers using the same persisted case and evidence
```

This single flow demonstrates:

- multimodal AI,
- real-time WebSocket engineering,
- agent orchestration,
- RAG,
- deterministic reasoning,
- relational persistence,
- geospatial marketplace,
- business model,
- memory,
- end-to-end action.

---

# 81. Technical Judging Story

The team should emphasize:

> DaantShaant is not a wrapper around one LLM call.

It contains:

- computer-vision preprocessing,
- multimodal Qwen,
- provider abstraction,
- technical failover,
- structured AI contracts,
- semantic media gating,
- FAISS RAG,
- evidence-backed deterministic logic,
- LangGraph orchestration,
- persistent patient state,
- WebSocket live scanning,
- PostgreSQL relational state,
- geospatial dentist matching,
- open mapping stack,
- appointment/marketplace workflow,
- evaluation/testing.

---

# 82. What Not to Prioritize

Do not delay core MVP for:

- native mobile app,
- WhatsApp,
- direct payments,
- Kubernetes,
- custom model fine-tuning,
- massive admin analytics,
- perfect product e-commerce,
- complex clinic SaaS billing,
- continuous production-grade real-time video model streaming,
- microservice decomposition beyond the existing useful service boundaries.

---

# 83. Living PRD Rule

This PRD is intentionally editable.

If the project lead changes:

- DB,
- model,
- workflow,
- phase ordering,
- maps,
- product features,
- deployment,
- designer scope,

update this document and `context.md`.

Do not let an obsolete plan silently remain active.

---

# 84. Source-of-Truth Order

During implementation:

```text
1. Current source code
2. context.md
3. this PRD
4. docs/architecture and API docs
5. docs/phase-log.md
6. old PRDs / old documentation
```

If old documentation conflicts with current code and this new plan, the old documentation should be treated as historical reference only.

---

# 85. Immediate Next Step

Phase 0, Phase 1A, and the merged Phase 1B cutover are complete.

> **Start Phase 2A — Shared DaantShaant AI Gateway in a new chat.**

The PostgreSQL database, unified identity, authentication, ownership, and domain repositories are stable prerequisites for that work.

---

# 86. Current Roadmap Snapshot

```text
[x] Existing DaantShaant baseline
[x] Snapshot scan
[x] Upload scan
[x] Live WebSocket scan
[x] Gemini vision baseline
[x] Diagnosis service baseline
[x] FAISS RAG baseline
[x] Chat baseline
[x] Product LangGraph
[x] Dentist LangGraph
[x] Google marketplace/map baseline
[x] Dentist portal
[x] Product/order capabilities

[x] Phase 0  — Hackathon rebaseline + context/Qoder rules
[x] Phase 1A — Supabase PostgreSQL foundation
[x] Phase 1B — Full Supabase PostgreSQL cutover (identity/auth/domain)
[x] Phase 1C — removed; scope merged into Phase 1B
[ ] Phase 2A — Qwen-primary AI gateway
[ ] Phase 2B — Semantic dental relevance
[ ] Phase 2C — Qwen clinical vision
[ ] Phase 3A — Clinical RAG upgrade
[ ] Phase 3B — Evidence/rule engine
[ ] Phase 4  — Unified Clinical LangGraph
[ ] Phase 5A — Clinical report/history
[ ] Phase 5B — Persistent case chat
[ ] Phase 6A — Remove Google Maps
[ ] Phase 6B — OSM/Overpass dentist discovery
[ ] Phase 6C — MapLibre/OpenFreeMap frontend
[ ] Phase 6D — Marketplace ranking agent upgrade
[ ] Phase 7  — Live scan intelligence upgrade
[ ] Phase 8  — Model evaluation harness
[ ] Phase 9  — Testing/security hardening
[ ] Phase 10 — Final designer UI integration
[ ] Phase 11 — Deployment
[ ] Phase 12 — Demo hardening
```

---

**End of DaantShaant Hackathon PRD v2.0**
