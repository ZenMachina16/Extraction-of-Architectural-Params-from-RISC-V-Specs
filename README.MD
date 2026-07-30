# AI-Assisted Extraction of Architectural Parameters from RISC-V Specifications

This project explores whether Large Language Models (LLMs) can reliably extract **implementation-defined / implementation-specific architectural parameters** from sections of the RISC-V ISA Manual (Privileged Specification), and outputs them as structured, evidence-grounded YAML.

The core challenge isn't extraction itself — it's getting an LLM to extract **only what the specification actually states**, without filling gaps using its own general knowledge of computer architecture. Most of the engineering effort in this repo went into prompt design and hallucination mitigation, not the extraction pipeline itself.

---

## Table of Contents

- [Motivation](#motivation)
- [What Counts as a "Parameter"](#what-counts-as-a-parameter)
- [Repository Structure](#repository-structure)
- [LLMs Used](#llms-used)
- [Setup](#setup)
- [Usage](#usage)
- [Prompt Development](#prompt-development)
- [Hallucination Mitigation Strategy](#hallucination-mitigation-strategy)
- [Output Schema](#output-schema)
- [Results](#results)
- [Cross-Model Evaluation](#cross-model-evaluation)
- [Known Limitations](#known-limitations)
- [Future Work](#future-work)
- [License](#license)

---

## Motivation

RISC-V is an open ISA, and its specification deliberately leaves many architectural properties open to implementers — cache sizes, organization, certain CSR behaviors, and so on. These properties are marked in the spec text using specific modal/qualifying language:

- `may` / `might` / `should`
- `optional` / `optionally`
- `implementation-defined` / `implementation-specific`

Manually cataloguing every such parameter across the full Privileged and Unprivileged specs is tedious and error-prone. This project evaluates whether an LLM, guided by a carefully constrained prompt, can do this extraction reliably and reproducibly — while flagging where it still fails.

---

## What Counts as a "Parameter"

A candidate is only extracted as a parameter if:

1. It refers to a property (size, capacity, organization, behavior, encoding, etc.) whose value **may legitimately differ across compliant implementations**, and
2. The specification text uses one of the trigger phrases above **in direct reference to that property**.

Fixed rules, mandatory encodings, and normative conventions (e.g. `shall`, `must`, or fixed bit-field encodings) are explicitly **excluded**, even when they appear in the same section as real parameters. This distinction — configurable property vs. fixed architectural rule — is the main thing the prompt is designed to enforce, and the main thing weaker models get wrong.

---

## Repository Structure

```text
.
├── input/
│   ├── caches.txt              # Privileged Spec §19.3.1 (cache block parameters)
│   └── csr.txt                 # Privileged Spec §2.1 (CSR address mapping - negative example)
├── output/
│   ├── gemini/
│   │   ├── caches-gemini.yaml
│   │   └── csr-gemini.yaml
│   ├── gpt-oss/
│   │   ├── caches.yaml
│   │   └── csr.yaml
│   └── llama/
│       ├── caches.yaml
│       └── csr.yaml
├── prompts/
│   └── extraction_prompt.md
├── src/
│   ├── __init__.py
│   ├── extractor.py
│   ├── models.py
│   └── utils.py
├── .gitignore
├── README.MD
├── requirements.txt
└── run.py
```

---

## LLMs Used

Multiple LLMs were used across different stages of the project — prompt engineering, primary extraction, and cross-model robustness evaluation — to test whether the finalized prompt generalizes across model families rather than overfitting to one model's instruction-following quirks.

| Model | Provider | Access Method | Context Window | Role |
|---|---|---|---|---|
| **Claude Sonnet 5** | Anthropic | Claude Web Interface | ~200K tokens | Prompt engineering, iterative refinement, hallucination analysis, qualitative evaluation |
| **Gemini 3.5 Flash** | Google | Gemini API | 1M tokens | Primary automated extraction pipeline, YAML generation |
| **GPT-OSS-120B** | OpenAI (via Groq) | Groq API | 131,072 tokens (128K) | Cross-model evaluation, prompt validation |
| **Llama 3.3 70B Versatile** | Meta (via Groq) | Groq API | 131,072 tokens (128K) | Robustness evaluation across open-weight models |

### Gemini 3.5 Flash — Generation Configuration

Used as the primary automated pipeline model, with low-temperature, near-deterministic settings intentionally chosen to reduce hallucination during structured extraction:

```python
generation_config = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}
```

---

## Setup

```bash
git clone https://github.com/ZenMachina16/Extraction-of-Architectural-Params-from-RISC-V-Specs.git
cd Extraction-of-Architectural-Params-from-RISC-V-Specs
pip install -r requirements.txt
```

Set your API key(s) as environment variables:

```bash
export GEMINI_API_KEY="your-key-here"
export GROQ_API_KEY="your-key-here"   # only needed for GPT-OSS-120B / Llama 3.3 evaluation
```

---

## Usage

Run extraction on a single specification snippet:

```bash
python pipeline/extract.py --input specs/caches.txt --model gemini-3.5-flash --output outputs/gemini/caches.yaml
```

Run the finalized prompt against all configured models for cross-model comparison:

```bash
python pipeline/extract.py --input specs/caches.txt --all-models
```

Verify that every `evidence_quote` in a generated YAML file is an exact verbatim substring of the source spec (catches truncation/paraphrasing errors before they're trusted):

```bash
python pipeline/verify_quotes.py --yaml outputs/gemini/caches.yaml --source specs/caches.txt
```

---

## Prompt Development

The prompt was refined iteratively across three versions, each addressing specific failure modes observed in the previous version's output.

### Version 1 — Initial Extraction Prompt

```
Extract implementation-specific architectural parameters from the given
RISC-V specification and return them in YAML format with their name,
description, type, constraints, and evidence.
```

**Observed issues:**
- Model inferred information not explicitly stated in the spec.
- Descriptions were expanded using general computer-architecture knowledge (e.g. `description: The total amount of data that a cache can hold` — technically correct, but not text the specification actually contains).
- Parameter types were invented (`integer`, `size`, `power-of-two`) despite the spec never stating a type.
- Multiple distinct properties were sometimes merged into a single parameter.
- Fixed architectural definitions were occasionally extracted as if they were configurable parameters.

### Version 2 — Restricting Model Inference

Explicit constraints were added to force the model to stay grounded in the source text:

- Extract only parameters explicitly described in the specification.
- Do not use external computer-architecture knowledge.
- Every field must be directly supported by the specification.
- If information is unavailable, return `"unspecified"` instead of inferring it.
- Do not infer units, examples, implementation details, or data types.

```
You are an expert in the RISC-V ISA.

Task:
Extract implementation-specific architectural parameters from the given
specification.

A parameter is a property whose value or behavior may vary across
different compliant implementations.

Rules:
1. Extract ONLY parameters explicitly mentioned in the specification.
2. Do not use external computer architecture knowledge.
3. If information is not explicitly stated, return "unspecified" instead
   of inferring it.
4. Do not infer parameter types, units, examples, or implementation
   details.
5. Keep separate parameters separate; do not merge them.
6. Description should summarize only what is stated in the
   specification.
7. Constraints should include only explicit requirements stated in the
   text.
8. Include an evidence quote from the specification supporting each
   parameter.
9. If no implementation-specific parameters are present, return:
   parameters: []

Return valid YAML only.

Fields:
- name
- description
- classification
- type
- constraints
- evidence_quote

Specification:
{spec_text}
```

**Improvement observed:** `type: integer` → `type: unspecified`; inferred cache-organization examples like "direct-mapped" / "set-associative" disappeared.

**Remaining issues:** some models still merged parameters, paraphrased evidence instead of quoting it exactly, and occasionally extracted fixed ISA encodings (e.g. `csr[11:0]`, `csr[11:10]`) as if they were implementation-specific — even though these are mandatory, fixed bit-field conventions.

### Version 3 — Final Prompt

The final version explicitly defines what a parameter *is*, and tightens every rule that had previously leaked hallucinations through.

```
You are an expert in the RISC-V ISA.

Task:
Extract implementation-specific architectural parameters from the
specification.

Definition:
A parameter is an implementation-defined or implementation-specific property
whose value, behavior, or existence may differ between compliant
implementations.

Rules:
1. Extract ONLY parameters explicitly described in the specification.
2. Never use external computer architecture knowledge.
3. Every field must be directly supported by the text.
4. If information is not stated, return "unspecified" or [] rather than
   infer.
5. Do not combine separate parameters into one.
6. Do not infer units, examples, data types, or implementation details.
7. Description must summarize only what the specification states.
8. Constraints must be copied from explicit statements only.
9. Evidence must be an exact quotation from the specification.
10. If no parameters exist, return
    parameters: []

Return valid YAML only.

Fields:
- name
- description
- classification
- type
- constraints
- evidence_quote

Specification:
{spec_text}
```

This is the prompt used across all four models in the final evaluation.

---

## Hallucination Mitigation Strategy

| Technique | Purpose |
|---|---|
| **Explicit parameter definition** | Restricts extraction to implementation-defined/-specific properties only — filters out fixed rules that merely *sound* configurable. |
| **Evidence-grounded extraction** | Every field must be traceable to specific text in the spec. |
| **No external knowledge** | Prevents the model from padding descriptions/types using general RISC-V or CPU-design knowledge not present in the given excerpt. |
| **No inference** | Missing information is represented as `"unspecified"` rather than guessed — turns a plausible-sounding fabrication into a visible, auditable gap. |
| **Verbatim evidence** | Requires exact quotations, enabling automated and manual verification against the source text. |
| **Negative case handling** | Explicitly instructs the model that `parameters: []` is a valid, expected output — without this, models tend to manufacture a parameter rather than report "none found." |

### Evidence Verification

After generation, every `evidence_quote` field is checked against the original specification text to confirm it is an **exact verbatim substring**, not a paraphrase or reconstruction. This step is what actually validates the "verbatim evidence" rule above — without it, a model can silently violate rule 9 while still producing well-formed YAML. See [`pipeline/verify_quotes.py`](pipeline/verify_quotes.py).

---

## Output Schema

Every extracted parameter follows this schema:

```yaml
parameters:
  - name: string              # short snake_case identifier
    description: string       # paraphrase of the spec text, no invented detail
    classification: string    # e.g. implementation-specific / implementation-defined
    type: string               # "unspecified" unless a type is explicitly stated
    constraints:                # list of explicit requirements stated in the text
      - string
    evidence_quote: string     # exact verbatim quotation from the specification
```

If a specification excerpt contains no implementation-specific parameters, the correct and expected output is:

```yaml
parameters: []
```

---

## Results

### 3.1 Cache Management (Privileged Spec §19.3.1) — Positive Example

**Claude Sonnet 5 output:**

```yaml
parameters:
  - name: cache_capacity
    description: The capacity of a cache
    classification: implementation-specific
    type: unspecified
    constraints: []
    evidence_quote: "The capacity and organization of a cache and the size of a cache block are both implementation-specific"

  - name: cache_organization
    description: The organization of a cache
    classification: implementation-specific
    type: unspecified
    constraints: []
    evidence_quote: "The capacity and organization of a cache and the size of a cache block are both implementation-specific"

  - name: cache_block_size
    description: The size of a cache block
    classification: implementation-specific
    type: unspecified
    constraints:
      - "the size of a cache block shall be uniform throughout the system"
    evidence_quote: "The capacity and organization of a cache and the size of a cache block are both implementation-specific, and the execution environment provides software a means to discover information about the caches and cache blocks in a system. In the initial set of CMO extensions, the size of a cache block shall be uniform throughout the system."
```

**Gemini 3.5 Flash output:**

```yaml
metadata:
  provider: gemini
  model: gemini-3.5-flash
  source_file: caches.txt
  generated_at: '2026-07-29T21:29:40Z'
parameters:
  - name: Cache capacity
    description: The capacity of a cache.
    classification: implementation-specific
    type: unspecified
    constraints: []
    evidence_quote: "The capacity and organization of a cache and the size of a cache block are both implementation-specific"

  - name: Cache organization
    description: The organization of a cache.
    classification: implementation-specific
    type: unspecified
    constraints: []
    evidence_quote: "The capacity and organization of a cache and the size of a cache block are both implementation-specific"

  - name: Cache block size
    description: The size of a cache block.
    classification: implementation-specific
    type: unspecified
    constraints:
      - "each of which represents a contiguous, naturally aligned power-of-two (or NAPOT) range of memory locations."
      - "In the initial set of CMO extensions, the size of a cache block shall be uniform throughout the system."
    evidence_quote: "The capacity and organization of a cache and the size of a cache block are both implementation-specific, and the execution environment provides software a means to discover information about the caches and cache blocks in a system. In the initial set of CMO extensions, the size of a cache block shall be uniform throughout the system"
```

**Observations:** Both models correctly identified all three parameters and kept types as `unspecified` rather than inventing them. Outputs are largely consistent, but differ slightly in constraint extraction — Gemini also captured the NAPOT (power-of-two) alignment requirement as a constraint on `cache_block_size`, which Claude's output omitted. This is a minor but real discrepancy worth tracking rather than glossing over.

### 3.2 CSR Address Mapping (Privileged Spec §2.1) — Negative Example

This section describes a **fixed, normative encoding convention** (`csr[11:0]`, `csr[11:10]`), not a configurable implementation choice. The correct output is an empty parameter list.

**Claude Sonnet 5:**
```yaml
parameters: []
```

**Gemini 3.5 Flash:**
```yaml
metadata:
  provider: gemini
  model: gemini-3.5-flash
  source_file: csr.txt
  generated_at: '2026-07-29T21:29:50Z'
parameters: []
```

Both models correctly returned an empty list, demonstrating that the final prompt distinguishes fixed ISA definitions from genuinely configurable implementation parameters — this negative control is arguably more informative than the positive extraction case, since it's easy for a model to hallucinate *something* when a section merely mentions bit-field encodings.

---

## Cross-Model Evaluation

| Model | Cache Extraction | CSR Extraction (negative case) | Observation |
|---|:---:|:---:|---|
| Claude Sonnet 5 | ✅ | ✅ | Highest fidelity to prompt constraints |
| Gemini 3.5 Flash | ✅ | ✅ | Used as primary automated pipeline model |
| GPT-OSS-120B | ✅ | ✅ | Minor descriptive inference beyond the spec, otherwise compliant |
| Llama 3.3 70B Versatile | ⚠️ | ❌ | Misclassified fixed CSR bit-field encodings as implementation-specific parameters |

Llama 3.3 70B Versatile correctly extracted the cache-related parameters but showed a markedly higher tendency to treat fixed architectural definitions as configurable parameters, particularly in the CSR address-mapping case. This reinforces that **prompt constraints alone don't fully normalize behavior across model families** — instruction-following fidelity still varies meaningfully even under an identical, tightly-constrained prompt.

---

## Known Limitations

- **Small test set.** Evaluation currently covers two spec excerpts (one dense positive case, one clean negative case). Real spec sections often mix fixed and configurable content within the same paragraph, and enumerated tables (like the CSR privilege table itself) are a harder case not yet tested.
- **No quantitative scoring.** Evaluation is currently qualitative (✅ / ⚠️ / ❌). A precision/recall-style rubric per parameter per model would make cross-model comparisons more rigorous.
- **Uncontrolled sampling for Claude.** Gemini's generation parameters are fixed and documented; Claude was used via the web interface without an explicit, reproducible temperature setting, which is a minor confound in the cross-model comparison.
- **`classification` field is currently low-information**, since extraction is already scoped to implementation-specific/defined parameters by design. Consider expanding it to distinguish `implementation-defined` vs. `implementation-specific` vs. `optional` per the original trigger-word categories, rather than collapsing them into one label.
- **GPT-OSS-120B and Llama 3.3-70B failure outputs are not yet included verbatim** in this repo's results — only summarized. Including raw outputs would make the "minor descriptive inference" / "misclassified" claims independently auditable.

---

## Future Work

- Expand the spec corpus to additional Privileged and Unprivileged ISA sections (e.g. PMP configuration, interrupt/exception delegation, vector extension parameters).
- Add an automated scoring harness comparing extracted parameters against a manually curated ground-truth list (e.g. cross-referenced against the [RISC-V Unified Database](https://github.com/riscv-software-src/riscv-unified-db)).
- Add few-shot examples (one positive, one negative) directly into the prompt to further reduce false positives on weaker models like Llama 3.3.
- Package the pipeline as a reusable CLI so new spec sections can be processed with a single command.

---

## License

Add your chosen license here (e.g. MIT, Apache 2.0). RISC-V specification text referenced/quoted in this repository remains subject to its original license from RISC-V International.