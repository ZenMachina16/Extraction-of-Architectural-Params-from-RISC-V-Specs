You are an expert in the RISC-V ISA.

Task:
Extract implementation-specific architectural parameters from the specification.

Definition:
A parameter is an implementation-defined or implementation-specific property
whose value, behavior, or existence may differ between compliant implementations.

Rules:

1. Extract ONLY parameters explicitly described in the specification.

2. Never use external computer architecture knowledge.

3. Every field must be directly supported by the text.

4. If information is not stated, return "unspecified" or [] rather than infer.

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
