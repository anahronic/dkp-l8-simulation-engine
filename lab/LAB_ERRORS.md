# Errors of the lab

Errors in the lab's own code, data or reports, kept apart from findings about the protocols.  Two earlier lab errors
became findings classified IMPLEMENTATION_BUG (F-001, F-013); the entries below are errors found by reviews of the
checkpoints or by the lab itself after checkpoint 4.  Each entry names what was wrong, what results it touched, the fix
and the regression that keeps it fixed.

| Id | Where | What was wrong | Results touched | Fix | Regression |
|---|---|---|---|---|---|
| КТ4-GPT-01 | `failure_chain` | The arbitration window closed at the first grid step after 14 days (21 000 min at 1000-min steps) | ORACLE-11-03 on coarse grids | `fb7138e`: last step within the deadline; minutes compared without rounding | `test_arbitration_deadline_is_not_rounded_up` |
| КТ4-GPT-02 | `lab/core/export.py` | `replay` accepted a package whose `result.json` was edited with its ids kept and SHA256SUMS refreshed | package verification | `fb7138e`: ids recomputed from the stored content; full document, reports and records compared with a fresh run | `test_edited_result_with_kept_ids_and_fresh_manifest_is_refused`, `test_edited_report_or_records_are_refused` |
| КТ4-GPT-03 | `code_economy` | IDENTITY-6-02 failed on the vote-pricing unit, which is a model choice, not an identity rule | IDENTITY-6-02 | `fb7138e`: coalition status checked separately; pricing unit declared (H-CE-4) | `test_pricing_unit_is_a_model_choice_not_an_identity_rule` |
| КТ4-GPT-04 | site page | Long URLs overflowed at 390 px | interface only | `424fcfd` (site): wrapping; every drill-down measured | UI test `mobile_drilldown_no_overflow` |
| CP5-TRACE | `lab/tools/trace.py` | "Resolvable" excluded provisions whose draft open point is `implementation_only` (text clear, only lab code missing) | matrix: resolvable uncovered shown as 0 instead of 145; stages C–F shown DONE | `894f087` | matrix rebuilt; numbers stated in the checkpoint 5 report |
| КТ5-GPT-01 | `defense_envelope` | VPI revalidation was measured from the first grant and the first termination with the revalidations of all authorizations, joining separate episodes | false FAIL of the VPI revalidation check (DEFENSE trajectory authorization -02) with two authorizations | each authorization is its own episode (grant to termination); termination checked per episode | `test_kt5_01_each_vpi_authorization_is_its_own_episode` |
| КТ5-GPT-02 | `defense_envelope` | Model and check both exempted evacuation in D1 from PTL supremacy, so an action on an unconfirmed observation passed DEFENSE-4.1-01 | DEFENSE-4.1-01 | exception removed; usable evidence per EB §9 (H-DE-4); each action cites its evidence; the check recomputes it | `test_kt5_02_no_evacuation_exception`, `test_kt5_02_evidence_validity_under_stability_and_lost_integrity` |
| КТ5-GPT-03 | checkpoint 5 report §7 | The five categories summed to 375, not 380: five provisions with draft origin `implementation_only` but `checkable = no` were left out | report only | report corrected; the five provisions read and reconciled | — |
| КТ5-GPT-04 | checkpoint 5 report §1.3 | The table said 10 votes for costs that belong to 100 votes | report and `COUNTEREXAMPLES_KT4.json` labels | report corrected; counterexample records now carry the normalized `vote_buying` and `pricing_unit` | — |
