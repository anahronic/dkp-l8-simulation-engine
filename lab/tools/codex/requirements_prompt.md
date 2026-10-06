You are formalizing ONE normative document of the Dikenocracy corpus into a registry of checkable provisions for a research lab. The full document text is given below in the <stdin> block. Do not use any other source. Do not run commands; just answer.

Document id: {DOC_ID}
Requirement id prefix: {PREFIX}

Produce JSON matching the given schema. One entry per distinct provision that states an obligation, prohibition, condition, threshold, formula, state, transition, timing, required field, or invariant. Cover the WHOLE document, section by section, including Failure Modes, Invariants and Finality-type sections when they state rules. Typical count: 10–40 entries. Do not create entries for pure headings, narrative purpose text, or lists of other protocols' names unless they impose a rule.

Field rules (strict):
- id: "{PREFIX}-<section>-<nn>", e.g. "{PREFIX}-3.6-01"; nn counts from 01 within the section; ids unique.
- section: the section number exactly as printed in the document heading that contains the provision (e.g. "3.6", "9.1", "A.2", "5.x"); use "0" for text before the first numbered heading; use the heading title text if the heading has no number.
- quote: an EXACT contiguous excerpt copied character-for-character from the document (keep Unicode symbols such as ₖ, ≤, ⇔, →; you may drop Markdown bold markers ** and backslash escapes, nothing else). 1–3 lines. It must contain the operative words of the provision. Never paraphrase inside "quote".
- title: 3–8 words in English.
- interpretation: 1–3 sentences: how a program could test this provision and the limits of that reading. If the text is ambiguous, say so and name the alternative readings. Never invent numbers, weights, thresholds or formulas that are not in the text.
- kind: formula (computes a value), constraint (must/must-not on states or values), contract (required inputs/outputs/fields/metadata/interfaces), state_transition (states, allowed/forbidden transitions, timeouts), dynamic_model (needs a model of behaviour over time), definition (defines a term used by checks; include only definitions that carry a testable condition).
- checkable: yes = decidable from explicitly given structured inputs with the text alone; partial = decidable only with an extra declared model, data source or parameter; no = cannot be decided by a program (e.g. requires judgement, real-world measurement not specified, or undefined terms).
- inputs: the data a check needs, as short snake_case names.
- criterion: the test condition in plain words or simple math using only quantities from the text.
- numeric_source: text (all numbers/thresholds are given in this text), calibration (text says a value comes from calibration/simulation), hypothesis (a value is needed but not defined anywhere in the text), missing (a referenced formula/document is absent), none (no number involved).
- normative_dependencies: other DKP document ids that this provision explicitly relies on (exact spelling as in the text).
- data_dependencies: kinds of data the check needs from other modules (e.g. "oracle readings with TTL", "attribution confidence").
- gap: null if checkable == "yes"; otherwise one sentence: what is missing (model, data, definition, decision).
- hypotheses_needed: assumptions a simulation would have to declare to test it (empty if none).
- notes: anything the registry maintainer should know (ambiguities, internal contradictions, references to documents that may not exist). Do not judge the merit of the norms.

Output only the JSON object.
