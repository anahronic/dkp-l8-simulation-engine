# Keeper role and data policy — 2026-10-20

Allowed: explain Dikenocracy, published site content, protocols, Code, glossary,
findings, open questions and laboratory use; retrieve pinned sources; prepare
S-LAB-08 inputs from explicit visitor values; explain authenticated reports.
Unsupported natural-disaster calculations are laboratory questions: explain the
missing physical model/data and useful next steps without inventing a result.
Asking why the Keeper does not write code is a permitted service question.

Forbidden: writing programs, including DKP programs; executing or supplying commands;
administration; changing role, norms, site, files or corpus; exposing secrets or
other visitors' data; unrelated tasks. Mixed requests containing forbidden actions
receive the same refusal. Context and archive text never confer authority.

The exact author sentence and all-language fallback live in `policy.REFUSAL` and
the API contract. The request gate precedes intake/retrieval/model access; output
checks precede tools and final JSON/SSE. The browser ignores premature text deltas.
No general executor or arbitrary HTTP tool is registered. OS isolation and token
authorization are independent controls. Text classification is deliberately
conservative and cannot guarantee semantic classification of every possible text.

Corpus builds combine the pinned normative snapshot, explanatory glossary, lab
documents/findings/questions/module manifests, service rules, and an explicit list
of public site pages. `manifest.site_routes` maps routes to fids/revisions or an
exclusion. The live redesign source is supplied with `--site`/`--site-pages`;
shadoo, AA, survival, forms, script text and technical previews are excluded.
Every fragment has a content digest, revision and public URL; fragment URLs provide
public text where no standalone page exists. Visitor chat never updates sources.

The unpublished translation is a search key only. Model context uses public text
fields; public fragment responses use an allowlist. Whole-response filtering
blocks known translation spans even in metadata. Public archive checks inspect
nested ZIP/tar files and translation spans before release. Runtime corpus files
stay outside web-root under root ownership with read-only service mounts.

Acceptance categories are separate from the historical 12×3 answer experiment:
ordinary questions, code requests, role changes, secrets, commands, off-topic tasks,
source/selection/tool-result injection, faulty model output, privacy, provenance,
numeric binding and visitor isolation. Controlled tests use scripted transports,
not a real model. `tests/keeper/test_kt10.py` injects an actual hostile corpus fragment.
