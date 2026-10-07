You classify why provisions of one Dikenocracy protocol document cannot yet be decided by a program.

Standard input contains two parts:
  === DOCUMENT {DOC_ID} ===   the full pinned text of the document
  === REQUIREMENTS ===        a JSON list of provisions of that document whose decision is open;
                              each has id, quote (verbatim), interpretation (a machine draft — NOT a
                              confirmed reading), criterion, gap and hypotheses_needed (the open points
                              a previous drafting pass named).

For EVERY provision in the list, decide the origin of the open point.  Use exactly one primary
category and at most one secondary category:

1. normative_ambiguity — the wording of the corpus admits more than one reading that changes a
   result, and the corpus itself does not settle it.  Only the author can choose.
2. architecture_definition — the corpus needs a structural definition it does not give and that
   cannot be derived from the corpus: a data model, an interface, a state machine, the responsible
   component, a mapping between protocols, a referenced symbol or document section that is not defined.
3. l8_parameter — a numeric threshold, weight, duration, model or calibration that the texts assign
   (explicitly, or through DKP-8-SIMULATION-001 §2/§9) to L8 calibration.  Missing numbers are NOT
   ambiguity.
4. empirical_model_data — needs real-world data or an empirical, causal or behavioural model
   (measurement methods, effectiveness, attribution from data).
5. external_dependency — depends on a document, system or actor outside this corpus.
6. implementation_only — the text is clear enough; only lab code, a record or a data structure is
   missing.

Rules:
- Judge from the document text, not from the drafted interpretation.  If the drafted
  interpretation invented an ambiguity the text does not contain, say so and choose
  implementation_only.
- Missing calibration, missing data and unwritten code are never normative_ambiguity.
- author_question_candidate is true only for normative_ambiguity or architecture_definition, and
  only when the document text cannot resolve the point.
- rationale: one sentence that names the exact words of the quote or document that cause the open
  point.

Return the structured output for document {DOC_ID} with one item per provision id, in input order.
