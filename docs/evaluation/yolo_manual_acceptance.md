# DaantShaant YOLO Manual Acceptance Test Plan (Phase 11B-1)

> This document defines the protocol and test categories for Nathan's manual acceptance testing of the YOLO dental pathology perception model (`best.pt` and upcoming `best_v2.pt`).
> 
> **Testing Principle**: The engineering agent does not perform live patient image tests or browser runs. Nathan performs all live acceptance testing against these standardized categories.

---

## Acceptance Test Matrix

| Category | Description | Image Characteristics | Expected Clinical Code | Expected Screening Outcome | Failure Mode to Watch |
|---|---|---|---|---|---|
| **A** | **Generalized True Discoloration** | Widespread extrinsic/intrinsic staining or yellowing across front teeth. | `discoloration` | High confidence (>=0.70), `distribution: "generalized"`, non-definitive limitation attached. | Must NOT be called calculus / tartar. |
| **B** | **True Tartar / Calculus** | Visible supra- or sub-gingival calcified deposits along gingival margins. | `tartar` | `distribution: "localized"` or `"multiple"`, urgency `routine` or `soon`. | Must NOT confuse with generalized staining. |
| **C** | **True Caries / Cavity** | Dark cavitation, pit/fissure decay, or distinct demineralized lesions. | `cavity_suspect` | Urgent / soon evaluation recommendation. | Must NOT confuse with dark interdental shadow. |
| **D** | **Visible Gingivitis** | Erythematous (red), swollen, or bleeding gingival margins. | `gingivitis_signs` | Recommends periodontal evaluation and hygiene check. | Must NOT falsely trigger on normal pink gum pigmentation. |
| **E** | **Visible Oral Ulcer** | Aphthous lesion, canker sore, or mucous membrane erosion. | `oral_ulcer` | Recommends dental check if persistent > 10–14 days. | Must NOT diagnose malignancy or systemic disease. |
| **F** | **Clean Recently Treated Teeth** | Teeth with recent professional prophylaxis, clean enamel, normal restorations. | *None* | **"No supported visible pathology was detected by this screening model."** | Must NOT produce false positive discoloration (~0.60). |
| **G** | **Naturally Off-White / Mild Yellow Teeth** | Healthy adult dentition with natural enamel yellow shade (A3, A3.5, B3 shades). | *None* | Ideally no unsupported pathology; no tartar misattribution. | Moderate confidence threshold must suppress spurious discoloration boxes. |
| **H** | **Dark Interdental Shadows** | Spaces between teeth with lighting shadows or minor crowding. | *None* | Normal background; not reported as caries. | Must NOT trigger false cavity_suspect. |
| **I** | **Irrelevant Selfie / Non-Dental Object** | Face selfie without teeth, food, pet, document, or room photo. | *None* | **Semantic relevance rejection BEFORE YOLO** (`status: "rejected"`). | YOLO perception must NEVER be invoked. |
| **J** | **Low-Quality / Blurry Dental Image** | Severe motion blur, out of focus, or extreme underexposure. | *None* | **Mechanical quality gate / retake behavior** (`status: "retake"`). | Must NOT display detector-driven "moderate confidence" — must state image clarity retake. |

---

## Step-by-Step Acceptance Protocol

1. **Verify Baseline Model Configuration**:
   ```bash
   # In .env or shell:
   YOLO_DENTAL_CONFIDENCE_THRESHOLD=0.50
   YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/best.pt
   ```
2. **Execute Categories A–E (Pathology Positive Controls)**:
   - Verify each positive condition is detected with its appropriate normalized finding code.
   - Verify discoloration and tartar remain strictly separate even when concurrent.
3. **Execute Categories F–H (Negative Controls & Natural Variations)**:
   - Verify Category F (clean treated teeth) yields no unsupported findings.
   - If discoloration still triggers around 0.60 on Category F/G under `best.pt`:
     - Test setting `YOLO_DISCOLORATION_CONFIDENCE_THRESHOLD=0.65` in `.env` without modifying code.
     - Document whether false positives disappear while Category A remains detected.
4. **Execute Categories I & J (Gating Controls)**:
   - Confirm non-dental photos are rejected by semantic relevance without calling YOLO.
   - Confirm blurry photos trigger the retake prompt with visual clarity instructions.
5. **Log Manual Observations**:
   - Record findings in `docs/evaluation/yolo_manual_acceptance_results.md`.
