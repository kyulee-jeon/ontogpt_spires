# Experiment A: SPIRES Attribute Extraction Analysis

**Date**: 2026-03-25  
**Model**: gpt-4o-mini  
**Dataset**: SNUH local radiology order names (`snuh_250926.xlsx`)  
**Gold standard**: LOINC/RSNA Radiology Playbook  

---

## 1. Method Description

### 1.1 SPIRES (Structured Prompt Interrogation and Recursive Extraction from Schemas)

SPIRES is the core extraction engine of [OntoGPT](https://github.com/monarch-initiative/ontogpt).
It uses zero-shot LLM prompting guided by a **LinkML schema** to extract structured
knowledge from free text. The pipeline consists of four stages:

| Stage | Description |
|-------|-------------|
| **GeneratePrompt** | Converts the LinkML schema into a pseudo-YAML template prompt. Each attribute becomes a named field with a natural-language description as the prompt cue. |
| **CompletePrompt** | Sends the prompt + input text to the LLM (gpt-4o-mini). The LLM fills in the pseudo-YAML template. |
| **ParseCompletion** | Parses the LLM's YAML-formatted response field by field. For nested/complex types, SPIRES calls itself recursively. |
| **Ground** | Maps extracted text values to ontology identifiers (e.g., RadLex RIDs). *(Not applied in this experiment — text-level comparison only.)* |

### 1.2 Schema Design

A custom LinkML schema (`radiology_procedure.yaml`) was created with the following attributes:

| Attribute | Description | Example values |
|-----------|-------------|----------------|
| `modality` | Imaging modality abbreviation | CT, MR, US, XR, RF, NM, PET, MG |
| `anatomy_focus` | Most specific anatomic target | brain, knee, ureter |
| `anatomy_region` | Broader anatomic region | chest, abdomen, lower extremity |
| `laterality` | Body side | left, right, bilateral, unspecified |
| `contrast` | Contrast administration | W, WO, W_WO |
| `view` | View type / count | AP, Lateral, 2 views |
| `guidance_action` | Interventional action | biopsy, injection, placement |
| `guidance_object` | Target of intervention | nerve, stent, mass |
| `timing` | Temporal context | pre-procedure, dynamic |
| `reason` | Clinical indication | trauma, metastasis |

### 1.3 Gold Standard Derivation

Gold-standard attributes were derived from the **LOINC/RSNA Radiology Playbook CSV**
(`LoincRsnaRadiologyPlaybook.csv`) by joining each labeled LOINC code with its
structured `PartTypeName` / `PartName` rows:

- `Rad.Modality.Modality Type` -> `modality`
- `Rad.Anatomic Location.Imaging Focus` -> `anatomy_focus` (most specific)
- `Rad.Anatomic Location.Region Imaged` -> `anatomy_region`
- `Rad.Anatomic Location.Laterality` -> `laterality`
- Contrast (`W`/`WO`/`W_WO`) was inferred from the LOINC Long Common Name via regex
  (e.g., `W contrast IV` -> W, `WO contrast` -> WO, `W and WO` -> W_WO)
- `Rad.Guidance for.Action` -> `guidance_action`
- `Rad.Guidance for.Object` -> `guidance_object`

For samples labeled **없음** (no LOINC match), all gold attributes are null.
SPIRES is expected to return all-null for these cases (abstain correctly).

### 1.4 Evaluation Setup

- **Normalization**: both gold and predicted values were lowercased and synonym-mapped
  before comparison (e.g., `MRI` -> `MR`, `Rt` -> `right`, `thyroid` ~ `thyroid gland`).
- **Exact match**: predicted value == gold value after normalization (both null = match).
- **Core attributes**: modality, anatomy_focus, laterality, contrast
  (used for the all-core-correct rate and sample-level binary verdict).

---

## 2. Dataset

| Split | Count |
|-------|-------|
| Total samples | 285 |
| Has valid LOINC label | 242 |
| Label = 없음 (no LOINC) | 43 |
| Missing SPIRES results | 5 |

---

## 3. Overall Results

### 3.1 Sample-level Binary Metrics

A sample is **correct** if:
- Has-LOINC case: ALL 10 evaluated attributes exactly match gold
- No-LOINC case: SPIRES returns all-null (correctly abstains)

| Metric | Value |
|--------|-------|
| Overall sample accuracy | **3.9%** (11/285) |
| Has-LOINC: all-attr-correct rate | 1.2% (3/242) |
| No-LOINC: abstain-correct rate | 18.6% (8/43) |

**Detection-level metrics** (does SPIRES extract vs. abstain correctly?)

| Metric | Value |
|--------|-------|
| Accuracy | 0.8772 |
| Precision | 0.8736 |
| Recall | 1.0000 |
| F1 | 0.9326 |
| TP (correctly extracted) | 242 |
| FP (extracted for no-LOINC) | 35 |
| FN (failed to extract for has-LOINC) | 0 |
| TN (correctly abstained) | 8 |

### 3.2 Attribute-level Metrics: Text vs Grounded (All 285 Samples)

Two evaluations are reported:
- **Text**: normalized string comparison (e.g., `thyroid` vs `thyroid gland` = mismatch)
- **Grounded**: RadLex RID comparison via Playbook lookup (e.g., both `thyroid` and `thyroid gland` -> RID7578 = match)

#### Text-level


| Attribute | #Gold | #Pred | TP | FP | FN | TN | Prec | Rec | F1 | Acc |
|-----------|------:|------:|---:|---:|---:|---:|-----:|----:|---:|----:|
| `modality` * | 230 | 189 | 156 | 33 | 74 | 40 | 0.825 | 0.678 | **0.745** | 0.647 |
| `anatomy_focus` * | 158 | 210 | 92 | 118 | 66 | 61 | 0.438 | 0.582 | **0.500** | 0.454 |
| `anatomy_region` | 214 | 233 | 158 | 75 | 56 | 37 | 0.678 | 0.738 | **0.707** | 0.598 |
| `laterality` * | 91 | 170 | 75 | 95 | 16 | 106 | 0.441 | 0.824 | **0.575** | 0.620 |
| `contrast` * | 242 | 144 | 136 | 8 | 106 | 40 | 0.944 | 0.562 | **0.705** | 0.607 |
| `view` | 59 | 75 | 0 | 75 | 59 | 187 | 0.000 | 0.000 | **0.000** | 0.583 |
| `guidance_action` | 22 | 28 | 9 | 19 | 13 | 249 | 0.321 | 0.409 | **0.360** | 0.890 |
| `guidance_object` | 13 | 17 | 4 | 13 | 9 | 263 | 0.235 | 0.308 | **0.267** | 0.924 |
| `timing` | 127 | 3 | 0 | 3 | 127 | 157 | 0.000 | 0.000 | **0.000** | 0.547 |
| `reason` | 8 | 23 | 0 | 23 | 8 | 255 | 0.000 | 0.000 | **0.000** | 0.892 |

> `*` = core attribute | `G` = grounded (RID comparison) | `-` = text comparison

#### Grounded-level (RadLex RID comparison)

| Attribute | #Gold | #Pred | Grnd Fail | TP | FP | FN | TN | Prec | Rec | F1 | Acc |
|-----------|------:|------:|----------:|---:|---:|---:|---:|-----:|----:|---:|----:|
| `modality` * G | 234 | 189 | 0 | 159 | 30 | 75 | 36 | 0.841 | 0.679 | **0.752** | 0.650 |
| `anatomy_focus` * G | 158 | 180 | 30 | 91 | 89 | 67 | 76 | 0.506 | 0.576 | **0.538** | 0.517 |
| `anatomy_region` G | 214 | 212 | 21 | 158 | 54 | 56 | 44 | 0.745 | 0.738 | **0.742** | 0.647 |
| `laterality` * G | 91 | 170 | 0 | 75 | 95 | 16 | 106 | 0.441 | 0.824 | **0.575** | 0.620 |
| `contrast` *  | 242 | 144 | 0 | 136 | 8 | 106 | 40 | 0.944 | 0.562 | **0.705** | 0.607 |
| `view` | 59 | 75 | 0 | 0 | 75 | 59 | 187 | 0.000 | 0.000 | **0.000** | 0.583 |
| `guidance_action` G | 22 | 27 | 1 | 9 | 18 | 13 | 249 | 0.333 | 0.409 | **0.367** | 0.893 |
| `guidance_object` G | 13 | 12 | 5 | 4 | 8 | 9 | 267 | 0.333 | 0.308 | **0.320** | 0.941 |
| `timing` | 127 | 3 | 0 | 0 | 3 | 127 | 157 | 0.000 | 0.000 | **0.000** | 0.547 |
| `reason` | 8 | 23 | 0 | 0 | 23 | 8 | 255 | 0.000 | 0.000 | **0.000** | 0.892 |

> **Grounded macro-mean F1**: 0.3999
>
> **Grounded all-core-correct rate**: 20.3% (58/285)

> `*` = core attribute used in all-correct rate
>
> **Macro-mean F1**: 0.3858
>
> **All-core-correct rate**: 19.7% (56/285)
>
> **No-LOINC all-null rate**: 18.6% (8/43)

---

## 4. Per-Attribute Deep Dive

### 4.1 Modality  (F1=0.745, Prec=0.825, Rec=0.678)

Modality is the most important attribute. Precision is high (0.825) — when SPIRES
extracts a modality it is usually correct — but recall is lower (0.678),
meaning SPIRES often **fails to infer modality** when it is not explicitly stated.

**FN=74: Cases where modality was not extracted (gold had a value, SPIRES returned null)**

Most common pattern: **implicit modality** — the procedure name contains no standard abbreviation.

| Local name | Gold modality | SPIRES output |
|------------|--------------|---------------|
| `Foot & Ankle Rt Lat (DF)` | `XR` | _null_ |
| `Femur Both Lat` | `XR` | _null_ |
| `Myelo-(C+T,T+L)(Musculoskeletal)` | `CT` | _null_ |
| `Defecography` | `RF` | _null_ |
| `Shoulder Both AP` | `XR` | _null_ |
| `Femur Rt (B)Obl(2매)` | `XR` | _null_ |
| `Hip Cross table Lat Both` | `XR` | _null_ |
| `Toe Rt AP` | `XR` | _null_ |

**FP=33: Cases where SPIRES extracted a modality but gold had none**
| Local name | Gold | SPIRES |
|------------|------|--------|
| `SONO Elbow Rt(팔꿈치관절 편측)` | _null_ | `US` |
| `SONO-GUIDED PROCEDURE III (PED)` | _null_ | `US` |
| `(외부)CT-Spine` | _null_ | `CT` |
| `SONO Foot Rt(족부관절 편측)` | _null_ | `US` |
| `SONO-GUIDED PROCEDURE III (INT)` | _null_ | `US` |

**Wrong modality (both non-null but mismatched)**

| Local name | Gold | SPIRES |
|------------|------|--------|
| `CT Angio + 3D Pulmonary artery (thoracoabdominal PPVI)(contrast)-(소아)` | `CT` | `CTA` |
| `PM(PET/MRI)-Chest wall (contrast)MRI` | `MR` | `PET` |
| `PET/MR Research Brain-RBD-JKY` | `MR` | `PET` |
| `PM(PET/MRI)-Methionine 2nd MRI Glioma PM(PET/MRI) (contrast)` | `MR` | `PET` |
| `PM(PET/MRI)-Liver(Stomach cancer)+Pelvis (contrast )(Gadovis` | `MR` | `PET` |

### 4.2 Anatomy Focus  (F1=0.500, Prec=0.438, Rec=0.582)

Anatomy focus is the most specific anatomic target. The main failure modes are:
1. **Expression mismatch**: SPIRES uses a different but valid term (e.g., `thyroid` vs `thyroid gland`)
2. **Focus/Region confusion**: SPIRES puts the focus into `anatomy_region` and vice versa
3. **Over-specificity**: SPIRES picks a sub-structure not listed in the Playbook

**Examples of expression mismatch:**

| Local name | Gold focus | SPIRES focus |
|------------|-----------|--------------|
| `CT Angio + 3D Pulmonary artery (thoracoabdominal PPVI)(contrast)-(소아)` | `chest vessels` | `pulmonary artery` |
| `Femur Rt (B)Obl(2매)` | `knee` | `femur` |
| `Toe Rt AP` | `toes` | `toe` |
| `PM(PET/MRI)-Methionine 2nd MRI Glioma PM(PET/MRI) (contrast)` | `brain` | `glioma` |
| `Toe Rt (B)Obl` | `toes` | `toe` |
| `Ped MRI Extended LS-spine (noncontrast)` | `spine.lumbar` | `spine` |
| `Foot & Ankle Rt Lat (PF)` | `ankle` | `foot` |
| `Both Subclavian arteriography (INT)` | `upper extremity arteries` | `subclavian artery` |

**Missed anatomy focus (gold has value, SPIRES returned null):**

| Local name | Gold focus | LOINC LCN |
|------------|-----------|-----------|
| `Myelo-(C+T,T+L)(Musculoskeletal)` | `spine.cervical` | `CT Cervical and thoracic spine W contrast IT` |
| `Defecography` | `rectum` | `RF Rectum Single view post contrast PR during defecation` |
| `Ped MRI IAC (contrast)` | `skull.base` | `MR Skull base W contrast IV` |
| `MRI Research_parkinsonism` | `brain` | `MR Brain` |
| `Sup. Rt.Venacavography` | `vein` | `RFA Vein - right Views W contrast IV` |

### 4.3 Laterality  (F1=0.575, Prec=0.441, Rec=0.824)

Recall is high (0.824) — SPIRES rarely misses laterality when present —
but precision is low (0.441) due to **over-extraction**: SPIRES assigns
`unspecified` to non-lateralized organs, generating FP=95.

**FP examples (gold=null, SPIRES extracted a laterality):**

| Local name | Gold | SPIRES |
|------------|------|--------|
| `1 Level bilateral Transforaminal epidural injection -Cervical` | _null_ | `bilateral` |
| `CT Angio + 3D Pulmonary artery (thoracoabdominal PPVI)(contrast)-(소아)` | _null_ | `unspecified` |
| `Ped MRI Growth Plate (noncontrast)` | _null_ | `unspecified` |
| `PCN tube reposition Rt` | _null_ | `right` |
| `Chest Lt Lat` | _null_ | `left` |
| `PM(PET/MRI)-Chest wall (contrast)MRI` | _null_ | `unspecified` |
| `Ped CT Chest Hemoptysis (contrast)` | _null_ | `unspecified` |
| `SONO Gun Biopsy - Head/Face (2 site)` | _null_ | `unspecified` |

**Wrong laterality value:**

| Local name | Gold | SPIRES |
|------------|------|--------|
| `Reposition of Ureter stent Lt (INT)` | `unspecified` | `left` |
| `Toe Rt (B)Obl` | `bilateral` | `right` |
| `Reposition of Ureter stent Rt (INT)` | `unspecified` | `right` |
| `MRI RT Plan Upper Extremity (non contrast)` | `unspecified` | `right` |
| `Toe Lt (B)Obl` | `bilateral` | `left` |

### 4.4 Contrast  (F1=0.705, Prec=0.944, Rec=0.562)

Precision is very high (0.944) — when SPIRES predicts contrast status, it
is almost always right. However, recall is 0.562: FN=106 cases where
SPIRES returned null even though the gold says WO.

Root cause: when no contrast keyword appears (e.g., plain X-ray named `Femur Both Lat`),
SPIRES defaults to null instead of inferring WO from context.

**FN examples (gold=WO/W, SPIRES returned null):**

| Local name | Gold contrast | LOINC LCN |
|------------|--------------|-----------|
| `Reposition of Ureter stent Lt (INT)` | `W` | `Guidance for placement of stent in Ureter` |
| `Femur Both Lat` | `WO` | `XR Femur - bilateral Single view` |
| `SONO Research Gun Biopsy - Breast` | `WO` | `US Guidance for biopsy of Breast` |
| `Defecography` | `W` | `RF Rectum Single view post contrast PR during defecation` |
| `Mammography Lt -SONO Localization 용` | `WO` | `MG Guidance for localization of Breast - left` |
| `Shoulder Both AP` | `WO` | `XR Shoulder - bilateral AP` |
| `Femur Rt (B)Obl(2매)` | `WO` | `XR Knee - right 2 Oblique Views` |
| `PET/MR Research Brain-RBD-JKY` | `WO` | `MR Brain` |

### 4.5 View  (F1=0.000)

View extraction completely fails (F1=0.000). SPIRES extracts views (75 times)
but they never match the gold (59 non-null gold values).
The root cause is **vocabulary mismatch**: gold uses Playbook-standardized terms
(`2 views`, `Single view`, `Views`) while SPIRES outputs informal terms
(`Lateral`, `AP`, `3D`). Neither value set is wrong — they use different granularities.

| Local name | Gold view | SPIRES view |
|------------|-----------|-------------|
| `Foot & Ankle Rt Lat (DF)` | `Views` | `Lateral` |
| `Femur Both Lat` | `view` | `Lateral` |
| `Shoulder Both AP` | `view; ap` | `AP` |
| `Femur Rt (B)Obl(2매)` | `views 2; oblique` | `Oblique` |
| `Hip Cross table Lat Both` | `view; lateral crosstable` | `crosstable lateral` |
| `Toe Rt AP` | `Views` | `AP` |
| `Wrist Lt (B)Obl(2회)` | `views 2` | `Oblique` |
| `Elbow Rt AP` | `view; ap` | `AP` |

### 4.6 Timing  (F1=0.000)

Timing fails entirely (F1=0.000). Gold timing values (`wo`, `w`, etc.) appear to be
artefacts of the Playbook's `Rad.Timing` field encoding contrast timing, not temporal
context in the usual sense. SPIRES correctly returns null almost always (only 3
extractions), but gold has 127 non-null values — leading to FN=127.

### 4.7 Reason for Exam  (F1=0.000)

Reason fails (F1=0.000) due to **SPIRES hallucination**: FP=23 cases where SPIRES
invents a clinical reason that is not in the local procedure name or the gold.
Gold has only 8 non-null reason values in the Playbook, so this is a rare attribute.

**FP examples (SPIRES hallucinated a reason):**

| Local name | Gold | SPIRES reason |
|------------|------|---------------|
| `CT Rt Lower leg Trauma + 3D (contrast)` | _null_ | `trauma` |
| `CT Hip Trauma + 3D (noncontrast)` | _null_ | `trauma` |
| `CT (Metal) Lt Ankle Trauma + 3D (noncontrast)` | _null_ | `trauma` |
| `Ped CT Chest Hemoptysis (contrast)` | _null_ | `hemoptysis` |
| `Ped MRI Knee Patellar Dislocation (noncontrast)` | _null_ | `patellar dislocation` |
| `CT (Metal) Rt Thigh Trauma + 3D (noncontrast)` | _null_ | `trauma` |

---

## 5. No-LOINC Case Analysis (없음, N=43)

For 없음-labeled samples, SPIRES should ideally return all-null.
Only **18.6%** (8/43) were
correctly abstained. The remaining 35 had at least one spurious attribute.

**Correctly abstained examples (SPIRES returned all-null):**

- `Infantogram`
- `Gastrojejunostomy tube check`
- `1 Level single Medial branch block ; MBB`
- `SBS (3개월 미만 소아)`
- `T-M Joint`

**Hallucination examples (SPIRES extracted attributes for no-LOINC cases):**

| Local name | Spurious extractions |
|------------|----------------------|
| `1 Level bilateral Transforaminal epidural injection -Cervical` | `anatomy_focus`=`cervical`, `anatomy_region`=`neck`, `laterality`=`bilateral`, `guidance_action`=`injection` |
| `PCN tube reposition Rt` | `laterality`=`right`, `guidance_action`=`reposition`, `guidance_object`=`tube` |
| `Chest Lt Lat` | `anatomy_region`=`chest`, `laterality`=`left`, `view`=`Lateral` |
| `Angioplasty : other central veins` | `guidance_action`=`angioplasty`, `guidance_object`=`central veins` |
| `Teleradiogram Lt Lat (Lower Ext)` | `anatomy_focus`=`lower extremity`, `anatomy_region`=`lower extremity`, `laterality`=`left`, `view`=`Lateral` |
| `(HPC) Chest Both Lat` | `anatomy_region`=`chest`, `laterality`=`bilateral`, `view`=`Lateral` |
| `Vascular stents : aorta a. (MFM)` | `anatomy_focus`=`aorta`, `anatomy_region`=`abdomen`, `guidance_action`=`placement`, `guidance_object`=`stent` |
| `Chest Lt Decubitus` | `anatomy_region`=`chest`, `laterality`=`left`, `view`=`Decubitus` |
| `SONO-GUIDED PROCEDURE III (PED)` | `modality`=`US` |
| `Intercostal arteriography 5-10vessels(Lt)` | `anatomy_focus`=`intercostal artery`, `anatomy_region`=`chest`, `laterality`=`left`, `view`=`5-10 views` |

**Pattern**: SPIRES tends to extract `anatomy_focus`, `laterality`, and `guidance_action`
from procedure names that contain anatomic terms (e.g., `PCN Lt` -> laterality=left,
anatomy_focus=kidney) even when the procedure has no standard LOINC imaging code.

---

## 6. Fully Correct Predictions (All Attributes Match)

**3 / 242 has-LOINC samples** had all 10 attributes correct.
These share a common pattern: **explicit, unambiguous procedure names**.

- `CT-Guided Biopsy (Upper Ex.) (noncontrast)` -> modality=CT, laterality=unspecified, contrast=WO
- `MRI NP-Dementia Brain+DTI(DWI)+MRA(Intra+Caro) (noncontrast)` -> modality=MR, focus=brain, contrast=WO
- `CT Whole body Low Dose + 3D (noncontrast)` -> modality=CT, contrast=WO

---

## 7. Worst-Case Predictions

Samples with the most attribute mismatches:

| Local name | Gold LOINC | # Mismatches | Wrong attributes |
|------------|-----------|:------------:|-----------------|
| `(HPC) D-L-spine Lat(standing)` | `37003-1` | 7 | `modality`, `anatomy_focus`, `anatomy_region`, `laterality`, `contrast`, `view`, `timing` |
| `EBD tube check` | `43788-9` | 7 | `modality`, `anatomy_focus`, `anatomy_region`, `contrast`, `view`, `timing`, `reason` |
| `D-L-spine Rt Bending AP` | `42379-8` | 7 | `modality`, `anatomy_focus`, `anatomy_region`, `laterality`, `contrast`, `view`, `timing` |
| `CT Angio + 3D Pulmonary artery (thoracoabdominal PPVI)(contrast)-(소아)` | `36266-5` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `laterality`, `view`, `timing` |
| `T-spine Lat(neut)` | `30756-1` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `laterality`, `contrast`, `view` |
| `Sup. Rt.Venacavography` | `26066-1` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `contrast`, `view`, `timing` |
| `PCN tube reposition Rt (INT)` | `26330-1` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `contrast`, `guidance_action`, `guidance_object` |
| `Bone age` | `37362-1` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `contrast`, `view`, `reason` |
| `(외부)Myelo-(whole spine)` | `30808-0` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `contrast`, `view`, `timing` |
| `TFCA, Rt Common carotid artery` | `26081-0` | 6 | `modality`, `anatomy_focus`, `anatomy_region`, `contrast`, `view`, `timing` |

---

## 8. Error Pattern Summary

| Error Pattern | Count | Root Cause |
|---------------|------:|-----------|
| Modality FN (null when should extract) | 56 | Implicit modality — no standard abbreviation in name |
| Laterality FP (extracted when null gold) | 88 | Over-assignment of `unspecified` to non-paired structures |
| Anatomy focus mismatch | 52 | Vocabulary granularity difference (thyroid vs thyroid gland) |
| Contrast FN (defaulted to null) | 101 | Missing explicit contrast keyword in name (e.g., plain XR) |
| View mismatch | 36 | Schema uses informal terms; gold uses Playbook-standardized counts |
| Reason FP (hallucinated reason) | 22 | SPIRES invents clinical reasons not present in text |
| No-LOINC hallucination | 35 | Extracts attributes from non-imaging/interventional names |

---

## 9. Limitations

1. **Gold standard imperfection**: The Playbook's `Rad.Timing` field encodes contrast timing
   (`W`, `WO`) rather than temporal context, causing all timing evaluations to fail.
   Some LOINC codes have placeholder modality values (`{Imaging modality}`).

2. **Normalization mismatch**: Anatomy terms like `thyroid gland` vs `thyroid` are treated
   as mismatches despite being semantically equivalent. A fuzzy-match or ontology-based
   comparison (RadLex grounding) would reduce false negatives.

3. **No grounding**: This experiment evaluates text-level extraction only.
   SPIRES's grounding step (mapping to RadLex RIDs) was skipped, so ontology-level
   equivalence (e.g., `knee` = RID2093) is not leveraged.

4. **Implicit attributes**: Many attributes are not stated in the local order name and
   require domain knowledge to infer (e.g., `Defecography` -> modality=RF,
   `Infantogram` -> modality=XR). SPIRES cannot infer these without examples.

5. **Schema prompt sensitivity**: SPIRES prompts are derived directly from the LinkML
   attribute `description` field. Small changes in wording affect extraction behavior.

6. **Model**: All results use gpt-4o-mini. Larger models (GPT-4o, Claude Opus) may
   produce better results, especially for implicit attributes.

---

*Generated by `report_generator.py` — Experiment A, SPIRES parsing-only evaluation*