# Experiment A: SPIRES 기반 영상검사 속성 추출 분석 보고서

**작성일**: 2026-03-25
**모델**: gpt-4o-mini
**데이터셋**: SNUH 오더명 (`snuh_250926.xlsx`, N=290)
**Gold Standard**: LOINC/RSNA Radiology Playbook
**평가**: 텍스트 수준 / RadLex RID Grounding 수준 이중 평가

---

## 1. 실험 목적

SNUH 원내 영상검사 오더명(local term)으로부터 구조화된 속성(modality, anatomy, laterality, contrast 등)을 추출하는 SPIRES의 성능을 측정한다.

- **입력**: SNUH 오더명 (한영 혼용, 원내 약어 포함)
- **출력**: 10개 속성 (modality, anatomy_focus, anatomy_region, laterality, contrast, view, guidance_action, guidance_object, timing, reason)
- **평가 기준**: LOINC/RSNA Radiology Playbook에서 도출한 Gold Standard 속성값

---

## 2. 방법론

### 2.1 SPIRES 파이프라인

SPIRES(Structured Prompt Interrogation and Recursive Extraction from Schemas)는 OntoGPT의 핵심 추출 엔진으로, **LinkML 스키마 정의**를 기반으로 LLM에게 구조화된 정보 추출을 요청한다. 파이프라인은 4단계로 구성된다:

```
입력 텍스트
    ↓
[1] GeneratePrompt
    스키마 속성 정의 → pseudo-YAML 형식의 프롬프트 생성
    ↓
[2] CompletePrompt
    LLM(gpt-4o-mini) 호출 → pseudo-YAML 형식 응답 반환
    ↓
[3] ParseCompletion
    응답 파싱 → 속성별 텍스트값 추출
    (중첩 클래스는 재귀 호출)
    ↓
[4] Ground
    추출된 텍스트값 → 온톨로지 식별자(RID) 매핑
    (본 실험: Playbook CSV 기반 커스텀 lookup 사용)
```

본 실험에서는 TranslateToOWL 이전 단계까지만 수행한다 (OWL 변환 제외).

---

### 2.2 LinkML 스키마 설계 (`radiology_procedure.yaml`)

LOINC/RSNA Radiology Playbook의 PartTypeName 체계에 대응하는 10개 속성으로 스키마를 구성했다:

| 속성 | Playbook PartTypeName | 예시 값 |
|------|-----------------------|---------|
| `modality` | Rad.Modality.Modality Type | CT, MR, US, XR, RF, NM, PET, MG |
| `anatomy_focus` | Rad.Anatomic Location.Imaging Focus | brain, knee, thyroid gland |
| `anatomy_region` | Rad.Anatomic Location.Region Imaged | chest, abdomen, lower extremity |
| `laterality` | Rad.Anatomic Location.Laterality | left, right, bilateral, unspecified |
| `contrast` | (LCN 텍스트에서 파생) | W, WO, W_WO |
| `view` | Rad.View.Aggregation + View Type | AP, Lateral, 2 views |
| `guidance_action` | Rad.Guidance for.Action | biopsy, injection, placement |
| `guidance_object` | Rad.Guidance for.Object | nerve, stent, mass |
| `timing` | Rad.Timing | pre-procedure, dynamic |
| `reason` | Rad.Reason for Exam | trauma, metastasis |

각 속성의 스키마 정의 예시:

```yaml
modality:
  description: >-
    Imaging modality using standard LOINC abbreviations.
    Examples: CT, MR, US, XR (plain radiograph/X-ray), NM (nuclear medicine),
    RF (fluoroscopy), PET, MG (mammography), CTA, MRA, SPECT.
    Map common synonyms: MRI->MR, Sono/Sonography->US, X-ray->XR,
    Ultrasound->US, PET/CT->PET, PET/MR->PET.
    Return null if not determinable.
  range: string
```

---

### 2.3 SPIRES 실제 프롬프트 구조 (GeneratePrompt 단계)

SPIRES는 스키마의 각 속성 `description`을 그대로 프롬프트 필드 힌트로 변환한다.
아래는 실제 LLM에 전달된 전체 프롬프트이다:

```
Split the following piece of text into fields in the following format:

modality: <Imaging modality using standard LOINC abbreviations. Examples: CT, MR, US, XR
(plain radiograph/X-ray), NM (nuclear medicine), RF (fluoroscopy), PET, MG (mammography),
CTA (CT angiography), MRA (MR angiography), SPECT. Map common synonyms: MRI->MR,
Sono/Sonography->US, X-ray->XR, Ultrasound->US, PET/CT->PET, PET/MR->PET.
Return null if not determinable.>

anatomy_focus: <The most specific anatomic target or organ being imaged. Use standard
English anatomic terms, lowercase singular form. Examples: brain, knee, liver, lung,
breast, spine, aorta, ankle, shoulder, hip, wrist, elbow, thyroid, prostate.
If multiple specific foci, list the primary one. Return null if only a broad region is known.>

anatomy_region: <The broader anatomic region containing the imaging focus. Use standard
terms, lowercase. Examples: head, chest, abdomen, pelvis, spine, upper extremity,
lower extremity, neck, whole body. Return null if not specified.>

laterality: <Anatomic side. Use exactly one of these values: "left", "right",
"bilateral", "unspecified". Common abbreviations to map: Rt/RT/right->right,
Lt/LT/left->left, Both/bil/bilateral->bilateral. Return null ONLY if laterality
is truly not applicable (e.g., organs without a side like aorta, brain midline structures).
Return "unspecified" if the procedure involves a paired organ but side is not mentioned.>

contrast: <Contrast administration status. Use exactly one of: "W" (with contrast),
"WO" (without contrast), "W_WO" (with and without contrast).
Inference rules: "(contrast)" or "W contrast" -> W,
"(noncontrast)" or "WO contrast" or "non-contrast" or "without contrast" -> WO,
"W and WO contrast" or "before and after contrast" -> W_WO.
When no contrast information is available, infer from clinical context:
most plain X-rays (XR, MG) -> WO; procedural guidance -> WO.
Return null only if truly indeterminate.>

...

Text:
[입력 오더명]

===
```

---

### 2.4 실제 입력/출력 예시 (CompletePrompt + ParseCompletion)

#### 예시 1: 명시적 정보가 충분한 케이스 — 성공

**입력**: `MRI Brain WO contrast`

**LLM 원문 응답 (pseudo-YAML)**:
```yaml
modality: MR
anatomy_focus: brain
anatomy_region: head
laterality: null
contrast: WO
view: null
guidance_action: null
guidance_object: null
timing: null
reason: null
```

**Gold (Playbook)**:
- LOINC: `30657-1` — MR Brain WO contrast
- modality=MR, anatomy_focus=brain, laterality=null, contrast=WO ✅

**평가**: 모든 속성 일치 (완벽한 추출)

---

#### 예시 2: 부분 성공 — 임상 맥락 필요

**입력**: `CT Rt Lower leg Trauma + 3D (contrast)`

**LLM 원문 응답**:
```yaml
modality: CT
anatomy_focus: lower leg
anatomy_region: lower extremity
laterality: right
contrast: W
view: 3D
guidance_action: null
guidance_object: null
timing: null
reason: trauma
```

**Gold (Playbook)**:
- LOINC: `36262-4` — CT Lower leg - right W contrast IV
- modality=CT ✅, anatomy_focus=lower leg ✅, laterality=right ✅, contrast=W ✅
- reason=null (Gold에 없음) → FP

**평가**: 핵심 4개 속성 모두 정확. 단, `reason: trauma`는 Playbook에 없는 hallucination.

---

#### 예시 3: Modality 암묵적 추론 실패

**입력**: `Foot & Ankle Rt Lat (DF)`

**LLM 원문 응답**:
```yaml
modality: null
anatomy_focus: ankle
anatomy_region: lower extremity
laterality: right
contrast: WO
view: Lateral
guidance_action: null
...
```

**Gold (Playbook)**:
- LOINC: `51394-5` — XR Ankle and Foot - right Views
- modality=**XR** (SPIRES: null) ❌

**문제**: "Foot & Ankle Rt Lat" 같은 오더명에는 XR이라는 modality 약어가 없음.
SPIRES는 단순히 약어가 없으면 null로 처리하고, plain X-ray임을 추론하지 못함.

---

#### 예시 4: 완전 실패 — 도메인 상식 필요

**입력**: `Defecography`

**LLM 원문 응답**:
```yaml
modality: null
anatomy_focus: null
anatomy_region: null
laterality: null
contrast: null
view: null
...
```

**Gold (Playbook)**:
- LOINC: `24893-0` — RF Rectum Single view post contrast PR during defecation
- modality=RF, anatomy_focus=rectum, anatomy_region=pelvis, contrast=W, view=Single view

**문제**: "Defecography"는 fluoroscopy(RF) 기반 직장 조영 검사이지만,
이를 알려면 영상의학 도메인 지식이 필요하다. SPIRES의 zero-shot 접근은 이런 암묵적 지식에 취약하다.

---

#### 예시 5: 없음(no LOINC) 케이스 — Hallucination

**입력**: `PCN tube reposition Rt`

**LLM 원문 응답**:
```yaml
modality: null
anatomy_focus: kidney
anatomy_region: abdomen
laterality: right
contrast: WO
guidance_action: reposition
guidance_object: PCN tube
...
```

**Gold**: 없음(no LOINC) — 모든 속성 null이어야 함

**문제**: 중재 시술명에서 anatomy(kidney), laterality(right), guidance_action(reposition) 등을 추출함.
LOINC에 매핑되지 않는 시술이지만 SPIRES는 이를 판별하지 못하고 속성을 생성함.

---

### 2.5 Gold Standard 구축

#### 방법

1. `snuh_250926.xlsx`의 `label` 컬럼에서 LOINC 코드 파싱
   - 형식: `"30657-1 - MR Brain WO contrast"` → LOINC_NUM = `30657-1`
2. `LoincRsnaRadiologyPlaybook.csv`에서 해당 LOINC 코드의 모든 PartTypeName 행 조회
3. 각 PartTypeName에서 속성값(PartName) 및 RadLex RID 추출
4. Contrast는 LOINC Long Common Name의 텍스트 패턴에서 파생:
   - `"W AND WO"` → `W_WO`
   - `"WO contrast"` 또는 `" WO "` → `WO`
   - `"W contrast"` 또는 IV/IT/IA 등 route 존재 → `W`
   - 나머지 → `WO` (default)
5. `없음` 라벨 = 모든 속성 null (SPIRES가 아무것도 추출하지 않아야 정답)

#### 데이터셋 구성

| 구분 | 수량 |
|------|-----:|
| 전체 | 290 |
| LOINC 있음 | 247 |
| 없음 (no LOINC) | 43 |
| SPIRES 결과 미수집 | 5 |
| **평가 대상** | **285** |

#### Gold 속성 분포

| 속성 | Gold 非null 수 | 비율 |
|------|---------------|------|
| contrast | 242 | 84.9% |
| modality | 230 | 80.7% |
| anatomy_region | 214 | 75.1% |
| anatomy_focus | 158 | 55.4% |
| timing | 127 | 44.6% |
| laterality | 91 | 31.9% |
| view | 59 | 20.7% |
| guidance_action | 22 | 7.7% |
| guidance_object | 13 | 4.6% |
| reason | 8 | 2.8% |

> **주의**: `timing` gold값 127개 중 대부분은 Playbook `Rad.Timing` 필드의 `"WO"`, `"W"` 값으로,
> 이는 시간적 맥락이 아닌 **contrast 관련 timing 코드**다. 따라서 timing 평가 결과는 해석에 주의 필요.

---

### 2.6 Grounding (RadLex RID 매핑)

텍스트 수준 비교의 한계를 보완하기 위해 **Playbook 기반 커스텀 Grounder**를 구현했다.

#### 동작 방식

1. Playbook CSV에서 각 PartTypeName별로 `{PartName.lower() → RID}` lookup 테이블 구축
2. SPIRES가 추출한 텍스트값을 lookup 테이블에서 조회
3. 조회 성공 → RID 비교 (온톨로지 수준 동등성 판단)
4. 조회 실패 → "Grounding Fail" (해당 예측값은 FN으로 처리)

#### Suffix Stripping 규칙

LLM이 Playbook PartName과 약간 다른 표현을 쓰는 경우를 처리:

| LLM 출력 | 처리 | 매핑 결과 |
|----------|------|-----------|
| `thyroid` | "thyroid gland"에서 ` gland` 제거 | RID7578 |
| `knee joint` | ` joint` 제거 → `knee` | RID2743 |
| `spinal cord` | ` cord` 제거 → `spinal` ... fallback | — |
| `MRI` | 별칭 등록 | RID10312 (= MR) |
| `CTA` | 별칭 → CT modality | RID10321 |
| `Sono` | 별칭 → US | RID10326 |

#### Lookup 테이블 규모

- 총 12개 속성 축 구축
- 총 1,028개 (PartName → RID) 매핑 항목
- 고유 RID: 899개

#### 텍스트 vs Grounded 평가 차이

Gold에서 Playbook RID를 직접 읽어오므로 **Gold Grounding은 100% 정확**.
SPIRES 출력 Grounding만 조회 실패가 발생할 수 있다.

---

## 3. 결과

### 3.1 샘플 수준 이진 분류 (맞췄냐 / 못맞췄냐)

한 샘플이 "정답"으로 분류되는 조건:

- **LOINC 있음**: 10개 평가 속성 **전부** gold와 일치
- **없음**: SPIRES가 모든 속성에 null 반환 (올바르게 추출 포기)

| 지표 | 값 |
|------|-----|
| 전체 샘플 정확도 | **3.9%** (11/285) |
| LOINC 있음: 전속성 정답률 | **1.2%** (3/242) |
| 없음: 올바른 추출 포기율 | **18.6%** (8/43) |

**Detection 수준** (SPIRES가 뭔가 추출 vs 아무것도 안함)

| 지표 | 값 |
|------|-----|
| Accuracy | 0.8737 |
| Precision | 0.8736 |
| Recall | **1.000** |
| F1 | **0.9326** |
| TP (LOINC 있음, SPIRES 추출 시도) | 242 |
| FP (없음인데 SPIRES 추출) | 35 |
| FN (LOINC 있는데 SPIRES 추출 안함) | 0 |
| TN (없음이고 SPIRES도 null) | 8 |

> **해석**: SPIRES는 recall=1.0으로 LOINC 있는 케이스는 모두 추출을 시도한다.
> 단, 없음 케이스의 81.4%(35/43)에서도 속성을 만들어냄 (hallucination).

---

### 3.2 속성 수준 메트릭 — 텍스트 비교

*(정규화 후 문자열 비교. 예: `mri`→`mr`, `rt`→`right`)*

| 속성 | #Gold | #Pred | TP | FP | FN | TN | Prec | Rec | **F1** | Acc |
|------|------:|------:|---:|---:|---:|---:|-----:|----:|-------:|----:|
| `modality` ★ | 230 | 189 | 156 | 33 | 74 | 22 | 0.825 | 0.678 | **0.745** | 0.647 |
| `anatomy_focus` ★ | 158 | 210 | 92 | 118 | 66 | 9 | 0.438 | 0.582 | **0.500** | 0.454 |
| `anatomy_region` | 214 | 233 | 158 | 75 | 56 | — | 0.678 | 0.738 | **0.707** | 0.598 |
| `laterality` ★ | 91 | 170 | 75 | 95 | 16 | 99 | 0.441 | 0.824 | **0.575** | 0.620 |
| `contrast` ★ | 242 | 144 | 136 | 8 | 106 | 35 | 0.944 | 0.562 | **0.705** | 0.607 |
| `view` | 59 | 75 | 0 | 75 | 59 | 151 | 0.000 | 0.000 | **0.000** | 0.583 |
| `guidance_action` | 22 | 28 | 9 | 19 | 13 | 224 | 0.321 | 0.409 | **0.360** | 0.890 |
| `guidance_object` | 13 | 17 | 4 | 13 | 9 | 259 | 0.235 | 0.308 | **0.267** | 0.924 |
| `timing` | 127 | 3 | 0 | 3 | 127 | 155 | 0.000 | 0.000 | **0.000** | 0.547 |
| `reason` | 8 | 23 | 0 | 23 | 8 | 254 | 0.000 | 0.000 | **0.000** | 0.892 |

> ★ = 핵심 속성 (all-core-correct 판정 기준)
> **Macro-mean F1 (텍스트)**: 0.3858
> **All-core-correct rate**: 19.7% (56/285)
> **No-LOINC 추출 포기율**: 18.6% (8/43)

---

### 3.3 속성 수준 메트릭 — RadLex RID Grounded 비교

*(Playbook PartName→RID lookup으로 SPIRES 출력을 grounding 후 RID 비교)*

| 속성 | #Gold RID | #Pred RID | Grnd Fail | TP | FP | FN | **F1** | Acc |
|------|----------:|----------:|----------:|---:|---:|---:|-------:|----:|
| `modality` ★ G | 234 | 189 | 0 | 159 | 30 | 75 | **0.752** | 0.650 |
| `anatomy_focus` ★ G | 158 | 180 | 30 | 91 | 89 | 67 | **0.538** | 0.517 |
| `anatomy_region` G | 214 | 212 | 21 | 158 | 54 | 56 | **0.742** | 0.647 |
| `laterality` ★ G | 91 | 170 | 0 | 75 | 95 | 16 | **0.575** | 0.620 |
| `contrast` ★ (text) | 242 | 144 | — | 136 | 8 | 106 | **0.705** | 0.607 |
| `view` (text) | 59 | 75 | — | 0 | 75 | 59 | **0.000** | 0.583 |
| `guidance_action` G | 22 | 27 | 1 | 9 | 18 | 13 | **0.367** | 0.893 |
| `guidance_object` G | 13 | 12 | 5 | 4 | 8 | 9 | **0.320** | 0.941 |
| `timing` (text) | 127 | 3 | — | 0 | 3 | 127 | **0.000** | 0.547 |
| `reason` (text) | 8 | 23 | — | 0 | 23 | 8 | **0.000** | 0.892 |

> ★ = 핵심 속성 | G = RID grounding 적용 (나머지는 텍스트 비교)
> **Macro-mean F1 (grounded)**: 0.3999
> **All-core-correct rate (grounded)**: 20.3% (58/285)

#### 텍스트 vs Grounded F1 비교

| 속성 | 텍스트 F1 | Grounded F1 | 개선 | 해석 |
|------|:---------:|:-----------:|:----:|------|
| `modality` | 0.745 | **0.752** | +0.007 | MRI→MR, CTA→CT RID 등 별칭 처리 |
| `anatomy_focus` | 0.500 | **0.538** | **+0.038** | `thyroid`→RID7578 수렴 등 표현 차이 흡수 |
| `anatomy_region` | 0.707 | **0.742** | **+0.035** | 동일 효과 |
| `laterality` | 0.575 | 0.575 | 0 | Playbook PartName이 이미 "Left"/"Right" 형태 |
| `guidance_action` | 0.360 | **0.367** | +0.007 | 소폭 개선 |

> Grounding은 표현 다양성(vocabulary mismatch)을 상당 부분 흡수하지만,
> **의미적으로 다른 오류**(예: `femur` vs `knee`)는 여전히 잡아내지 못한다.

---

## 4. 속성별 심층 분석

### 4.1 Modality (F1: text=0.745, grounded=0.752)

**Precision 0.825** — 추출할 때는 거의 맞음
**Recall 0.678** — FN=74: 추출 못하는 케이스가 많음

#### 주요 실패 패턴: 암묵적 Modality (FN=74)

오더명에 modality 약어가 없는 경우 SPIRES는 null을 반환한다.

| 오더명 | Gold Modality | SPIRES | 실패 이유 |
|--------|--------------|--------|-----------|
| `Foot & Ankle Rt Lat (DF)` | XR | null | "Lat"만으로 plain X-ray 추론 불가 |
| `Femur Both Lat` | XR | null | 동일 |
| `Myelo-(C+T,T+L)(Musculoskeletal)` | CT | null | "Myelo-"가 myelography → CT임을 모름 |
| `Defecography` | RF | null | 도메인 지식 필요 |
| `Shoulder Both AP` | XR | null | "AP"만으로 XR 추론 불가 |
| `Hip Cross table Lat Both` | XR | null | "Cross table Lat"이 XR임을 모름 |
| `Toe Rt AP` | XR | null | 동일 |

> **해석**: Plain X-ray(XR)는 "XR", "X-ray" 약어 없이 부위+방향만으로 오더가 작성되는 경우가 많다.
> SPIRES가 이를 처리하려면 영상의학 도메인 few-shot 예시가 필요하다.

#### 잘못된 Modality (mismatch)

| 오더명 | Gold | SPIRES | 원인 |
|--------|------|--------|------|
| `CT Angio + 3D Pulmonary artery...` | CT | CTA | CTA가 CT의 하위 개념 (Grounding 후에는 RID 동일) |

---

### 4.2 Anatomy Focus (F1: text=0.500, grounded=0.538)

FP=118(text)/89(grounded) 로 가장 많은 FP 발생. 주요 원인 세 가지:

#### ① 표현 차이 (Vocabulary Mismatch) — Grounding으로 해결 가능

| 오더명 | Gold | SPIRES | Grounded 결과 |
|--------|------|--------|--------------|
| `MRI Thyroid (contrast)` | thyroid gland | thyroid | RID7578 → **MATCH** ✅ |
| `Toe Rt AP` | toes | toe | 단복수 차이 → 동일 RID |

#### ② 의미적 오류 — Grounding으로도 해결 불가

| 오더명 | Gold (LOINC 기준) | SPIRES 출력 | 원인 |
|--------|------------------|-------------|------|
| `Femur Rt (B)Obl(2매)` | knee | femur | LOINC는 XR Knee인데 오더명은 Femur라고 쓰여 있음 |
| `Foot & Ankle Rt Lat (PF)` | ankle | foot | 복합 부위에서 LOINC 기준 focus와 다름 |
| `CT Angio + 3D Pulmonary artery...` | chest vessels | pulmonary artery | 더 구체적인 해부학 구조 선택 |

#### ③ 진단 목적 정보 사용 — Hallucination

| 오더명 | Gold | SPIRES | 원인 |
|--------|------|--------|------|
| `PM(PET/MRI)-Methionine 2nd MRI Glioma...` | brain | glioma | 진단명을 anatomy로 오인 |

---

### 4.3 Laterality (F1: text=grounded=0.575)

**Recall 0.824** — 존재하는 laterality는 잘 잡음
**Precision 0.441** — FP=95: 불필요한 laterality 과잉 생성

#### 주요 FP 패턴: 비쌍측 장기 또는 없음 케이스에 laterality 부여

| 오더명 | Gold | SPIRES | 실패 이유 |
|--------|------|--------|-----------|
| `CT Angio + 3D Pulmonary artery...` | null | unspecified | 흉부 혈관은 laterality 없음 |
| `Ped CT Chest Hemoptysis (contrast)` | null | unspecified | 흉부 검사 laterality 없음 |
| `SONO Gun Biopsy - Head/Face (2 site)` | null | unspecified | 두경부 검사 laterality 없음 |
| `Chest Lt Lat` (**없음** 케이스) | null | left | Gold 자체가 없음인데 오더명의 "Lt"를 잡아냄 |

> **해석**: 스키마에 *"Return null ONLY if laterality is truly not applicable"*,
> *"Return 'unspecified' if the procedure involves a paired organ"* 이라는 지시를 넣었는데,
> SPIRES가 "paired organ인지 여부"를 보수적으로 판단하여 `unspecified`를 과다 배정함.

#### 틀린 laterality 값

| 오더명 | Gold | SPIRES |
|--------|------|--------|
| `Reposition of Ureter stent Lt (INT)` | unspecified | left |

> 오더명의 "Lt"를 그대로 laterality=left로 매핑했으나, Playbook에서 해당 LOINC 코드(88938-6)는 laterality를 unspecified로 처리함.

---

### 4.4 Contrast (F1: 0.705)

**Precision 0.944** — 추출하면 거의 정확
**Recall 0.562** — FN=106: 명시적 키워드 없으면 null 반환

#### FN 주요 패턴: 명시적 contrast 키워드 없는 케이스

| 오더명 | Gold Contrast | 오더명 특징 |
|--------|--------------|-------------|
| `Femur Both Lat` | WO | plain X-ray이지만 키워드 없음 |
| `Shoulder Both AP` | WO | 동일 |
| `SONO Research Gun Biopsy - Breast` | WO | guidance 시술, 별도 contrast 언급 없음 |
| `PET/MR Research Brain-RBD-JKY` | WO | 연구 프로토콜명, 정보 없음 |

> **해석**: 스키마에 *"most plain X-rays (XR, MG) -> WO"* 규칙을 명시했지만,
> modality 자체를 null로 추출한 경우(위 XR 케이스들) contrast도 같이 null이 됨.
> Modality를 먼저 올바르게 추출해야 contrast 추론이 가능한 종속 관계가 존재함.

---

### 4.5 View (F1: 0.000) — 완전 실패

SPIRES는 view를 75회 추출했지만 gold(59개)와 단 1건도 일치하지 않음.

| 오더명 | Gold (Playbook) | SPIRES 출력 |
|--------|-----------------|-------------|
| `Foot & Ankle Rt Lat (DF)` | views | Lateral |
| `Femur Both Lat` | view | Lateral |
| `Shoulder Both AP` | views | AP |
| `CT Rt Lower leg Trauma + 3D (contrast)` | null | 3D |

> **원인**: Playbook의 view 표현은 **집계 단위** (`"2 views"`, `"Single view"`, `"Views"`)이고,
> SPIRES는 **방향/기법** (`"AP"`, `"Lateral"`, `"3D"`)을 추출한다.
> 두 체계가 다른 granularity를 사용하므로 어떤 쪽도 틀리지 않지만 비교가 불가능함.

---

### 4.6 Reason (F1: 0.000) — Hallucination 우세

Gold에 reason이 있는 케이스는 8개뿐이지만, SPIRES는 23회 reason을 추출 → FP=23.

| 오더명 | Gold | SPIRES 출력 |
|--------|------|-------------|
| `CT Rt Lower leg Trauma + 3D (contrast)` | null | trauma |
| `CT Hip Trauma + 3D (noncontrast)` | null | trauma |
| `Ped CT Chest Hemoptysis (contrast)` | null | hemoptysis |
| `Ped MRI Knee Patellar Dislocation (noncontrast)` | null | patellar dislocation |

> **해석**: 오더명에 임상 정보("Trauma", "Hemoptysis")가 포함된 경우 SPIRES가 이를 reason으로 추출한다.
> 이는 의미적으로 타당하지만 Playbook이 reason을 거의 코드화하지 않아 gold=null이 됨.
> 이는 **gold standard의 한계**이지 SPIRES의 실질적 오류가 아닐 수 있다.

---

## 5. 없음(no LOINC) 케이스 분석 (N=43)

없음으로 라벨된 43개 오더명에 대해 SPIRES가 올바르게 추출을 포기한 비율: **18.6% (8/43)**

### 올바르게 추출 포기한 케이스 (8개)

| 오더명 | 특징 |
|--------|------|
| `1 Level bilateral Transforaminal epidural injection -Cervical` | 긴 중재시술 명칭, 모호 |
| `Angioplasty : other central veins` | 혈관 중재 시술 |
| `Infusion for thrombolysis: Extracranial` | 약물 주입술 |
| `Diagnostic spinal tapping` | 척수 천자 (imaging 아님) |
| `Sclerotherapy: Check (INT)` | 경화 요법 확인 |

### Hallucination 발생 케이스 예시 (35개)

| 오더명 | SPIRES 잘못 추출한 속성 |
|--------|------------------------|
| `PCN tube reposition Rt` | anatomy_focus=kidney, laterality=right, guidance_action=reposition |
| `Chest Lt Lat` | anatomy_focus=chest, anatomy_region=chest, laterality=left, contrast=WO, view=Lateral |
| `PCN tube check Lt` | anatomy_focus=kidney, laterality=left |
| `Embolization : Rt uterine` | anatomy_focus=uterus, laterality=right, guidance_action=embolization |
| `Research DEXA - Lt Knee` | modality=DXA, anatomy_focus=knee, laterality=left |

> **패턴**: PCN(경피적 신루설치술), 혈관 중재술, 기타 시술명에서 anatomy와 laterality를 잘 추출하는 경향.
> 해부학 정보 자체는 맞지만 이 시술들에 LOINC imaging code가 없다는 사실을 판별하지 못함.

---

## 6. 오류 유형 요약

| 오류 유형 | 건수 | 주요 원인 |
|-----------|-----:|-----------|
| Modality FN (추출 실패) | 74 | 암묵적 modality — 약어 없는 XR/RF 오더명 |
| Laterality FP (과잉 추출) | 95 | 비쌍측 구조에도 `unspecified` 배정 |
| Anatomy focus 표현 불일치 | ~30 | `thyroid` vs `thyroid gland` (grounding으로 부분 해결) |
| Anatomy focus 의미 오류 | ~40 | LOINC 기준 focus와 오더명 기준 focus 불일치 |
| Contrast FN (추출 실패) | 106 | 명시적 키워드 없는 경우 null 반환 (XR의 WO 등) |
| View 어휘 불일치 | 75 | Playbook은 집계 단위, SPIRES는 방향/기법 단위 |
| Reason FP (hallucination) | 23 | 오더명의 임상 정보를 reason으로 추출 (gold에 없음) |
| No-LOINC hallucination | 35/43 | imaging 아닌 시술에서 anatomy/laterality 생성 |

---

## 7. 한계점

### 7.1 Gold Standard 한계

1. **`Rad.Timing` 필드 문제**: Playbook의 timing 값(`WO`, `W`)은 시간적 맥락이 아닌 contrast 단계 코드. timing 평가 전체가 무의미한 결과를 낳음.

2. **`{Imaging modality}` 플레이스홀더**: 일부 LOINC 코드(중재 guidance 등)의 modality 필드가 `{Imaging modality}`로 채워져 있음 → 해당 케이스는 gold modality=null 처리.

3. **Reason 코드화 희소성**: Playbook이 reason을 8개 케이스에만 코드화. 임상적으로 의미 있는 reason을 gold로 삼기 어려움.

4. **Focus vs 오더명 불일치**: LOINC 코드가 실제 오더명의 anatomy focus와 다른 경우 존재
   (예: `Femur Rt` → gold=knee, `Foot & Ankle` → gold=ankle만)

### 7.2 SPIRES 구조적 한계

1. **Zero-shot 추론 한계**: 암묵적 modality(`Defecography`=RF, `Femur Lat`=XR)는 도메인 상식 없이 추론 불가. Few-shot 예시 추가로 일부 해결 가능.

2. **속성 간 종속 관계 처리 불가**: modality를 못 잡으면 contrast도 못 잡는 연쇄 실패. SPIRES의 flat 추출 구조상 이 종속 관계를 활용하지 못함.

3. **Laterality 과잉 배정**: `"unspecified"` vs `null` 경계 판단이 지나치게 보수적. 스키마 지시를 더 명확히 해도 한계 존재.

4. **없음 케이스 감지 불가**: SPIRES는 "이 오더명은 imaging 코드가 없다"는 판단을 내리지 못함. 별도의 pre-filtering 단계 필요.

5. **View 어휘 체계 불일치**: Playbook의 view 집계 체계와 SPIRES의 자연어 추출이 근본적으로 다름. Schema에 Playbook 어휘를 enum으로 제한하면 개선 가능.

### 7.3 Grounding 한계

1. **Anatomy 동의어 불완전**: 1,028개 항목 커버하지만 LLM이 Playbook에 없는 표현 사용 시 실패.

2. **Anatomy focus Grounding Fail: 30건**: SPIRES 출력을 RID로 매핑 못한 경우 FN으로 처리되어 grounded 지표가 보수적.

3. **Contrast RID 없음**: Playbook에서 contrast(W/WO/W_WO)는 별도 RID로 코드화되지 않아 텍스트 비교만 가능.

---

## 8. 결론 및 시사점

| 핵심 발견 | 내용 |
|-----------|------|
| **잘 되는 부분** | modality(명시), anatomy 전반, contrast(명시), laterality recall |
| **가장 취약한 부분** | 암묵적 modality, view 어휘 체계, reason/timing |
| **Grounding 효과** | anatomy F1 +0.038, region F1 +0.035 개선. 표현 다양성 흡수 유효 |
| **없음 케이스** | 81.4%에서 hallucination — 별도 필터링 레이어 필요 |
| **실용적 성능** | 핵심 4속성 동시 정답: 19.7% (grounded: 20.3%) |

### 향후 개선 방향

1. **Few-shot 예시 추가**: 암묵적 modality 케이스(XR 부위+뷰 오더명 등) few-shot으로 프롬프트 보강
2. **View enum 제한**: 스키마의 view 속성을 Playbook 어휘 enum으로 제한
3. **없음 필터**: SPIRES 전 단계에서 non-imaging 시술 분류기 적용
4. **Laterality 기준 명확화**: 비쌍측 장기 목록을 스키마 지시에 포함
5. **더 큰 모델 시험**: GPT-4o / Claude Opus로 암묵적 추론 성능 비교

---

*작성: Experiment A 평가 파이프라인 (`run_experiment_a.py`, `evaluator.py`, `grounder.py`)*
*데이터: SNUH 290개 오더명, LOINC/RSNA Playbook (2024)*
