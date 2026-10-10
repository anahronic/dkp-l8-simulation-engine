"""
EDITION AND FINALITY module: how a document may change, how its editions are dated and listed.

Thirty documents end with a finality clause.  Each says the document is changed only through the
controlled procedure of DKP-4-UPGRADE-001 (proposal, simulation, audit, acceptance conditions,
activation window, rollback) and adds its own list: a new protocol identifier, an incompatibility
declaration, a full-system or a targeted simulation, a compatibility declaration with named
documents, public disclosure, a version increment, a migration path.  Presentation-only corrections
are not Upgrades and are recorded only by the document's "Last updated" date.  Twenty-five documents
say the SHA-256 digest of each published edition is listed in SHA256SUMS.txt of the canonical
repository; UPGRADE §12 adds that the edition date identifies the edition only and that rebuilding
the publication does not change the dates of unchanged documents.

The module reads the clause of every document (table FINALITY, checked against the pinned text by
tests), runs declared changes through a gate that applies the document's own list, publishes editions
in releases and writes the digest listing of each release.  Its checks recompute everything from the
input and the event log.  The pinned SHA256SUMS.txt of World@aad3e86 is checked against the pinned
documents as well.

What it does not decide:
  * whether a change is "presentation-only": the kind is declared;
  * simulation, audit and acceptance results: declared (the procedure itself is upgrade_lifecycle);
  * the target of an "explicit compatibility declaration." without named documents (ERROR, UPGRADE,
    CRISIS): FAIL if no declaration, UNKNOWN otherwise, with the declared targets recorded (F-041);
  * which protocols are "dependent" on SCOPE: two readings (H-EF-2, F-042); the verdict is fixed only
    where both agree.
Time unit: day; dates are the Gregorian "Last updated" dates the documents show.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.registry import catalog
from lab.core.schema import LabInputError, resolve

SCOPE = "DKP-7-SCOPE-001"
NEW, INC, PUB = "new_identifier", "incompatibility_declaration", "public_disclosure"
SIM, FULL, DEP = "sim:targeted", "sim:full_system", "sim:dependents"
UNSPEC, DEPENDENTS = "compat:?", "compat:dependents"
MAY_IFACE = "may:interfaces_resimulation"


def compat(*docs: str) -> str:
    return "compat:" + "+".join(docs)


# document -> (procedure provision, items checked under it, [(provision, items)], presentation provisions, integrity provision)
# Items of an "In addition" list that the registry does not hold as a provision of their own are checked
# under the procedure provision (H-EF-5).
FINALITY = {
    "DKP-1-IDENTITY-001": ("IDENTITY-14-01", (), [("IDENTITY-14-02", (NEW, INC, FULL))], ["IDENTITY-14-03"], "IDENTITY-14-04"),
    "DKP-1-IMPACT-001": ("IMPACT-12-01", (), [("IMPACT-12-02", (NEW, INC, FULL))], ["IMPACT-12-03"], "IMPACT-12-04"),
    "DKP-1-JUSTICE-001": ("JUSTICE-15-01", (), [("JUSTICE-15-02", (NEW, INC, FULL))], ["JUSTICE-15-03"], "JUSTICE-15-04"),
    "DKP-1-PREVENTION-001": ("PREV-15-01", (), [("PREV-15-02", ("version_increment", "compatibility_audit", "migration_path"))],
                             ["PREV-15-03"], None),
    "DKP-2-ASSETS-001": ("ASSETS-14-01", (), [("ASSETS-14-02", (NEW, INC, FULL))], ["ASSETS-14-03"], "ASSETS-14-04"),
    "DKP-2-FINANCE-001": ("FINANCE-14-01", (), [("FINANCE-14-02", (NEW, INC, FULL))], ["FINANCE-14-03"], "FINANCE-14-04"),
    "DKP-2-LABOR-001": ("LABOR-13-01", (), [("LABOR-13-02", (NEW, INC, FULL))], ["LABOR-13-03"], "LABOR-13-04"),
    "DKP-3-ANTITERROR-001": ("ANTITERROR-12-01", (), [("ANTITERROR-12-02", (NEW, SIM, INC))], ["ANTITERROR-12-03"], "ANTITERROR-12-04"),
    "DKP-3-DEFENSE-001": ("DEFENSE-12-01", (PUB,), [("DEFENSE-12-02", (NEW, INC, FULL))], ["DEFENSE-12-03"], "DEFENSE-12-04"),
    "DKP-3-INTERNAL-SEC-001": ("INTSEC-12-01", (), [("INTSEC-12-02", (NEW,)), ("INTSEC-12-03", (INC,)), ("INTSEC-12-04", (FULL,))],
                               ["INTSEC-12-05"], "INTSEC-12-06"),
    "DKP-3-POLICE-001": ("POLICE-11-01", (), [("POLICE-11-02", (NEW,)), ("POLICE-11-03", (SIM,)),
                                              ("POLICE-11-04", (compat("DKP-1-AXIOMS-001", SCOPE),))], ["POLICE-11-05"], None),
    "DKP-4-CRISIS-001": ("CRISIS-11-01", (NEW, FULL, UNSPEC), [], ["CRISIS-11-02"], "CRISIS-11-03"),
    "DKP-4-EPISTEMIC-TRANSITIONS-001": ("ETRANS-7-01", (), [("ETRANS-7-02", (NEW,)), ("ETRANS-7-03", (INC,)), ("ETRANS-7-04", (FULL,)),
                                                            ("ETRANS-7-05", (compat("DKP-1-EPISTEMIC-BOUNDARIES-001"),))],
                                        ["ETRANS-7-06"], "ETRANS-7-07"),
    "DKP-4-ERROR-001": ("ERROR-12-01", (SIM,), [("ERROR-12-02", (NEW,)), ("ERROR-12-03", (UNSPEC,))], ["ERROR-12-04"], "ERROR-12-05"),
    "DKP-4-UPGRADE-001": ("UPGRADE-12-01", (), [("UPGRADE-12-02", (NEW, SIM, "stage:audit", UNSPEC))], ["UPGRADE-12-03"], "UPGRADE-12-07"),
    "DKP-5-CULTURE-001": ("CULTURE-12-01", (), [("CULTURE-12-02", (NEW,)), ("CULTURE-12-03", (compat(SCOPE),)), ("CULTURE-12-04", (MAY_IFACE,))],
                          ["CULTURE-12-05"], "CULTURE-12-06"),
    "DKP-5-EDU-001": ("EDU-13-01", (), [("EDU-13-02", (NEW,)), ("EDU-13-03", (SIM,)), ("EDU-13-04", (compat("DKP-5-INFO-001", SCOPE),))],
                      ["EDU-13-05"], "EDU-13-06"),
    "DKP-5-HABITAT-001": ("HABITAT-13-01", (SIM,), [("HABITAT-13-02", (NEW,)), ("HABITAT-13-03", (compat("DKP-5-TRANSPORT-001", SCOPE),))],
                          ["HABITAT-13-04"], "HABITAT-13-05"),
    "DKP-5-INFO-001": ("INFO-14-01", (SIM, compat(SCOPE)), [("INFO-14-02", (NEW,))], ["INFO-14-03"], "INFO-14-04"),
    "DKP-5-TRANSPORT-001-APPENDIX-A": ("TRANSPORTA-A.5-01", (), [("TRANSPORTA-A.5-02", (NEW,)), ("TRANSPORTA-A.5-03", (INC,)),
                                                                 ("TRANSPORTA-A.5-04", (FULL,))],
                                       ["TRANSPORTA-A.5-05", "TRANSPORTA-A.5-06"], None),
    "DKP-6-EXIT-001": ("EXIT-16-01", (), [("EXIT-16-02", (NEW,)), ("EXIT-16-03", (SIM, compat(SCOPE)))], ["EXIT-16-04"], "EXIT-16-05"),
    "DKP-6-INTEGRATION-001": ("INTEGRATION-12-01", (), [("INTEGRATION-12-02", (NEW,)), ("INTEGRATION-12-03", (SIM, compat(SCOPE)))],
                              ["INTEGRATION-12-04"], "INTEGRATION-12-05"),
    "DKP-7-PRIVACY-001": ("PRIVACY-14-01", (SIM,), [("PRIVACY-14-02", (NEW,)), ("PRIVACY-14-03", (compat(SCOPE, "DKP-7-TRANSPARENCY-001"),))],
                          ["PRIVACY-14-04"], "PRIVACY-14-05"),
    "DKP-7-SCOPE-001": ("SCOPE-12-01", (SIM,), [("SCOPE-12-02", (NEW,)), ("SCOPE-12-03", (DEPENDENTS,))], ["SCOPE-12-04"], "SCOPE-12-05"),
    "DKP-7-TRANSPARENCY-001": ("TRANSPARENCY-14-01", (), [("TRANSPARENCY-14-02", (NEW,)),
                                                          ("TRANSPARENCY-14-03", (compat(SCOPE, "DKP-8-AUDIT-001"),))],
                               ["TRANSPARENCY-14-04"], "TRANSPARENCY-14-05"),
    "DKP-8-AUDIT-001": ("AUDIT-12-01", (), [("AUDIT-12-02", (NEW,)), ("AUDIT-12-03", (SIM,)), ("AUDIT-12-04", (compat(SCOPE),))],
                        ["AUDIT-12-05"], "AUDIT-12-06"),
    "DKP-8-INTEROP-001": ("INTEROP-13-01", (), [("INTEROP-13-02", (NEW,)), ("INTEROP-13-03", (SIM,)), ("INTEROP-13-04", (compat(SCOPE),))],
                          ["INTEROP-13-05"], "INTEROP-13-06"),
    "DKP-8-SIMULATION-001": ("SIMULATION-14-01", (), [("SIMULATION-14-02", (NEW,)), ("SIMULATION-14-03", (INC,)), ("SIMULATION-14-04", (DEP,))],
                             ["SIMULATION-14-05"], "SIMULATION-14-06"),
}
STAGES = ("proposal", "simulation", "audit", "acceptance_conditions", "activation_window", "rollback")   # the procedure sentence
SIM_LEVELS = ("none", "targeted", "dependents", "full_system")                                          # H-EF-1
SIM_RANK = {s: i for i, s in enumerate(SIM_LEVELS)}
DECLARATIONS = (NEW, INC, "compatibility_declaration", PUB, "version_increment", "compatibility_audit", "migration_path")
RELEASE_KINDS = ("edition", "rebuild", "navigation")
_CAT = catalog()
DOC_IDS = sorted(d["id"] for d in _CAT["documents"])

FAULTS = {
    "skip_finality": "the gate accepts a modification whatever its finality clause still requires",
    "date_as_certificate": "an edition date is taken as evidence that simulation and audit took place",
    "date_as_activation": "a deferred change is activated on its edition date",
    "rebuild_redates": "a rebuild or navigation change re-dates every document",
    "digest_not_listed": "a new edition is published without its digest in SHA256SUMS.txt",
    "presentation_as_upgrade": "a presentation-only correction is run through the upgrade gate and given a new identifier",
    "presentation_undated": "a presentation-only correction leaves the old 'Last updated' date",
    "accept_override": "another protocol's override of a document whose header says 'Override: Not permitted' is accepted",
}

CHANGE = {"type": "object", "fields": {
    "id": {"type": "str"},
    "doc": {"type": "enum", "values": list(FINALITY)},
    "kind": {"type": "enum", "values": ["normative", "presentation_only"], "default": "normative"},
    "channel": {"type": "enum", "values": ["upgrade", "direct"], "default": "upgrade"},
    "stages": {"type": "list", "min_items": 0, "max_items": len(STAGES), "items": {"type": "enum", "values": list(STAGES)},
               "default": list(STAGES)},
    "simulation": {"type": "enum", "values": list(SIM_LEVELS), "default": "full_system"},
    "declarations": {"type": "list", "min_items": 0, "max_items": len(DECLARATIONS), "items": {"type": "enum", "values": list(DECLARATIONS)},
                     "default": list(DECLARATIONS)},
    "compatibility_with": {"type": "list", "min_items": 0, "max_items": len(DOC_IDS) + 1,
                           "items": {"type": "enum", "values": ["as_required"] + DOC_IDS}, "default": ["as_required"]},
    "interfaces_resimulated": {"type": "bool", "default": False},
    "release": {"type": "str", "default": "r1"},
    "activation_after_days": {"type": "int", "min": 0, "max": 3650, "default": 30}}}
RELEASE = {"type": "object", "fields": {
    "id": {"type": "str"},
    "day": {"type": "int", "min": 0, "max": 3650},
    "kind": {"type": "enum", "values": list(RELEASE_KINDS), "default": "edition"}}}


# header line "Override: Not permitted" -> the provision that registers it (EB-0-01 is module epistemic_gate)
OVERRIDE_HEADERS = {"DKP-4-EPISTEMIC-TRANSITIONS-001": "ETRANS-EpistemicStateTransitionProtocol-01",
                    "DKP-1-PREVENTION-001": "PREV-0-01", "DKP-6-RESILIENCE-001": "RESILIENCE-0-01"}
OVERRIDE = {"type": "object", "fields": {"doc": {"type": "enum", "values": list(OVERRIDE_HEADERS)},
                                         "by": {"type": "enum", "values": DOC_IDS}}}
OVERRIDES = [{"doc": "DKP-4-EPISTEMIC-TRANSITIONS-001", "by": "DKP-2-FINANCE-001"},
             {"doc": "DKP-1-PREVENTION-001", "by": "DKP-4-CRISIS-001"},
             {"doc": "DKP-6-RESILIENCE-001", "by": "DKP-4-CRISIS-001"}]


def header(doc: str) -> Dict[str, Any]:
    """The header block of a pinned document (before section 1): override line and the 'Depends on' list."""
    from lab.tools.check_registry import doc_text, normalize
    text = doc_text(next(d for d in _CAT["documents"] if d["id"] == doc))
    head = normalize(re.split(r"\n#+\s*(?:0|1)\.", text, maxsplit=1)[0])
    m = re.search(r"Override:?\s*([A-Za-z ]+?)(?:\s*[·\"-]|$)", head)
    dep = re.search(r"Depends on:?(.*?)(?:Override|$)", head)
    return {"override": m.group(1).strip() if m else None,
            "depends_on": sorted(set(re.findall(r"DKP-[0-9A-Z-]+-\d{3}", dep.group(1)))) if dep else []}


def short(doc: str) -> str:
    return re.sub(r"^dkp_\d_|_001", "", doc.lower().replace("-", "_"))


def items_of(doc: str) -> List[str]:
    proc, extra, items, _, _ = FINALITY[doc]
    return list(extra) + [t for _, ts in items for t in ts]


def dependents(reading: str) -> List[str]:
    """Protocols dependent on SCOPE (H-EF-2): those whose text references it, or those listing it under 'Depends on'."""
    docs = [d for d in _CAT["documents"] if d["kind"] == "protocol" and d["id"] != SCOPE]
    if reading == "depends_on":
        return sorted(d["id"] for d in docs if SCOPE in d["declared_dependencies"])
    return sorted(d["id"] for d in docs if any(x["target"] == SCOPE for x in d["references"]))


def targets(ch: Dict[str, Any], reading: str) -> List[str]:
    out = set(x for x in ch["compatibility_with"] if x != "as_required")
    if "as_required" in ch["compatibility_with"]:
        for t in items_of(ch["doc"]):
            if t == DEPENDENTS:
                out |= set(dependents(reading))
            elif t.startswith("compat:") and t != UNSPEC:
                out |= set(t[7:].split("+"))
    return sorted(out)


def verdict(tok: str, ch: Dict[str, Any], tg: List[str]) -> str:
    """PASS / FAIL / UNKNOWN of one requirement for one change (declared facts only)."""
    decl = set(ch["declarations"])
    if tok.startswith("sim:"):
        return PASS if SIM_RANK[ch["simulation"]] >= SIM_RANK[tok[4:]] else FAIL
    if tok.startswith("stage:"):
        return PASS if tok[6:] in ch["stages"] else FAIL
    if tok == MAY_IFACE:
        return PASS if ch["interfaces_resimulated"] else UNKNOWN
    if tok.startswith("compat:"):
        if "compatibility_declaration" not in decl:
            return FAIL
        if tok == UNSPEC:
            return UNKNOWN
        if tok == DEPENDENTS:
            if not set(dependents("depends_on")) <= set(tg):
                return FAIL
            return PASS if set(dependents("references")) <= set(tg) else UNKNOWN
        return PASS if set(tok[7:].split("+")) <= set(tg) else FAIL
    return PASS if tok in decl else FAIL


def procedure_verdict(ch: Dict[str, Any], tg: List[str]) -> str:
    if ch["channel"] != "upgrade" or any(s not in ch["stages"] for s in STAGES) or SIM_RANK[ch["simulation"]] < 1:
        return FAIL
    return combine([verdict(t, ch, tg) for t in FINALITY[ch["doc"]][1]])


def combine(vs: List[str]) -> str:
    return FAIL if FAIL in vs else UNKNOWN if UNKNOWN in vs else PASS


def gate_missing(ch: Dict[str, Any], reading: str) -> List[str]:
    """What the gate finds missing under the reading it applies (H-EF-2 for SCOPE)."""
    tg = targets(ch, reading)
    miss = []
    if ch["channel"] != "upgrade":
        miss.append("channel:upgrade")
    miss += [f"stage:{s}" for s in STAGES if s not in ch["stages"]]
    if SIM_RANK[ch["simulation"]] < 1:
        miss.append(SIM)
    for t in items_of(ch["doc"]):
        if t == DEPENDENTS:
            ok = "compatibility_declaration" in ch["declarations"] and set(dependents(reading)) <= set(tg)
        else:
            ok = verdict(t, ch, tg) != FAIL
        if not ok:
            miss.append(t)
    return miss


def next_identifier(doc: str, taken: set) -> str:
    m = re.search(r"-(\d{3})(?=(-[A-Z][A-Z-]*)?$)", doc)
    n = int(m.group(1))
    while True:
        n += 1
        cand = doc[:m.start(1)] + f"{n:03d}" + doc[m.end(1):]
        if cand not in taken:
            return cand


def run(r: Dict[str, Any]) -> EventLog:
    faults = set(r["faults"])
    log = EventLog("day", tie_rule="decision < action < notice; then event_id")
    order = {"decision": 0, "action": 1, "notice": 2}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:04d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    docs = {d["id"]: d for d in _CAT["documents"]}
    base = date.fromisoformat(max(d["last_updated"] for d in docs.values() if d["last_updated"]))
    # published editions: identifier -> line (original document), digest, date
    pub = {i: {"line": i, "digest": d["sha256"], "date": d["last_updated"]} for i, d in docs.items()}
    listed = {i: d["sha256"] for i, d in docs.items()}
    for o in r["override_attempts"]:
        h = header(o["doc"])
        refused = h["override"] == "Not permitted" and "accept_override" not in faults
        put("decision", "OVERRIDE", 0, {"override_attempt": o["doc"], "by": o["by"], "accepted": not refused,
                                       "reason": "header: 'Override: Not permitted'; the document changes only through "
                                                 "DKP-4-UPGRADE-001" if refused else "accepted"})
    for rel in sorted(r["releases"], key=lambda x: (x["day"], x["id"])):
        k = rel["day"]
        when = (base + timedelta(days=k)).isoformat()
        changed = []
        for ch in [c for c in r["changes"] if c["release"] == rel["id"]]:
            seed = f"{ch['id']}|{ch['doc']}|{when}"
            if ch["kind"] == "presentation_only" and "presentation_as_upgrade" not in faults:
                ident = ch["doc"]
                pub[ident] = dict(pub[ident], digest=hashlib.sha256(seed.encode()).hexdigest(),
                                  date=pub[ident]["date"] if "presentation_undated" in faults else when)
                put("decision", "EDITION", k, {"change": ch["id"], "doc": ch["doc"], "kind": "presentation_only", "upgrade": False,
                                               "identifier": ident, "recorded_by": "Last updated"})
                changed.append(ident)
                continue
            miss = gate_missing(ch, r["dependents_reading"])
            evidence = ["declared " + s for s in ch["stages"]] + ([f"simulation {ch['simulation']}"] if ch["simulation"] != "none" else [])
            ok = not miss or "skip_finality" in faults
            if miss and "date_as_certificate" in faults and set(miss) <= {SIM, FULL, DEP, "stage:simulation", "stage:audit"}:
                ok, evidence = True, evidence + ["edition_date"]
            if ch["kind"] == "presentation_only":                       # fault presentation_as_upgrade
                ok, miss = True, []
            ident = None
            if ok:
                taken = set(pub)
                ident = next_identifier(ch["doc"], taken) if (NEW in ch["declarations"] or ch["kind"] == "presentation_only") else ch["doc"]
                pub[ident] = {"line": ch["doc"], "digest": hashlib.sha256(seed.encode()).hexdigest(), "date": when}
                changed.append(ident)
            put("decision", "EDITION", k, {"change": ch["id"], "doc": ch["doc"], "kind": ch["kind"], "upgrade": True, "accepted": ok,
                                           "missing": miss, "evidence": evidence, "identifier": ident,
                                           "compatibility_with": targets(ch, r["dependents_reading"])})
            if ok and ch["kind"] == "normative":
                act = k if "date_as_activation" in faults else k + ch["activation_after_days"]
                put("action", "EDITION", k, {"activation": ch["id"], "identifier": ident, "activation_day": act, "edition_date": when})
        if "rebuild_redates" in faults and rel["kind"] != "edition":
            for i in pub:
                pub[i] = dict(pub[i], date=when)
        for i in changed:
            strict = r["presentation_record_reading"] == "all_records" and \
                any(m.value.get("identifier") == i and m.value.get("kind") == "presentation_only" and not m.value["upgrade"]
                    for m in log.messages() if m.arrived_at == k)
            if "digest_not_listed" in faults or strict:
                continue                                                # the old digest (or none) stays listed
            listed[i] = pub[i]["digest"]
        put("notice", "RELEASE", k, {"release": rel["id"], "kind": rel["kind"], "date": when,
                                     "editions": {i: dict(e) for i, e in sorted(pub.items())}, "listed": dict(sorted(listed.items()))})
    return log


def override_checks(r: Dict[str, Any], msgs) -> List[CheckResult]:
    out = []
    att = [m.value for m in msgs if m.source == "OVERRIDE"]
    for doc, rid in OVERRIDE_HEADERS.items():
        h = header(doc)
        mine = [a for a in att if a["override_attempt"] == doc]
        bad = [] if h["override"] == "Not permitted" else [f"header reads {h['override']!r}"]
        bad += [f"override by {a['by']} accepted" for a in mine if a["accepted"]]
        if doc == "DKP-6-RESILIENCE-001":
            declared = sorted(next(d for d in _CAT["documents"] if d["id"] == doc)["declared_dependencies"])
            if h["depends_on"] != declared:
                bad.append(f"meta 'Depends on' {h['depends_on']} differs from the catalog {declared}")
        ok = (f"the pinned header says 'Override: Not permitted'; {len(mine)} override attempt(s) by other protocols refused"
              + ("; the meta 'Depends on' list matches the catalog" if doc == "DKP-6-RESILIENCE-001" else ""))
        out.append(CheckResult(rid, "override_not_permitted", FAIL if bad else PASS,
                               f"{len(bad)} breaches of the header" if bad else ok,
                               evidence={"violations": bad[:10]} if bad else {"header": h}))
    return out


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = override_checks(r, msgs)
    cs = {c["id"]: c for c in r["changes"]}
    dec = [m.value for m in msgs if m.kind == "decision" and m.source == "EDITION"]
    rels = [m for m in msgs if m.source == "RELEASE"]
    docs = {d["id"]: d for d in _CAT["documents"]}
    pinned = _CAT["corpus"]["release_manifest"]["entries"]

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    def res(rid, chk, rows, ok, extra=None):
        """rows: [(change, verdict)]"""
        st = combine([v for _, v in rows])
        bad = [c for c, v in rows if v == st and st != PASS]
        text = ok if st == PASS else (f"{len(bad)} accepted changes miss it" if st == FAIL else
                                      f"{len(bad)} accepted changes: the text does not fix the required content")
        ev = {"changes": [c for c, _ in rows][:10]}
        if bad:
            ev["violations" if st == FAIL else "undetermined"] = bad[:10]
        if extra:
            ev.update(extra)
        return CheckResult(rid, chk, st, text, evidence=ev)

    # per-document finality clauses
    for doc, (proc, extra, items, pres, integ) in FINALITY.items():
        acc = [d for d in dec if d["doc"] == doc and d.get("accepted") and cs[d["change"]]["kind"] == "normative"]
        ref = [d for d in dec if d["doc"] == doc and d.get("upgrade") and not d.get("accepted")]
        tg = {d["change"]: targets(cs[d["change"]], r["dependents_reading"]) for d in acc}
        why = f"{len(ref)} refused" if ref else "none"
        if acc:
            out.append(res(proc, "upgrade_procedure", [(d["change"], procedure_verdict(cs[d["change"]], tg[d["change"]])) for d in acc],
                           f"accepted changes went through every stage of the UPGRADE procedure{' and ' + ', '.join(extra) if extra else ''}",
                           {"refused": [d["change"] for d in ref][:10]}))
        elif ref:
            out.append(CheckResult(proc, "upgrade_procedure", PASS, f"no change accepted outside the procedure; {why}",
                                   evidence={"refused": [d["change"] for d in ref][:10], "missing": ref[0]["missing"]}))
        else:
            out.append(na(proc, "upgrade_procedure", "modifications", "none"))
        for rid, toks in items:
            chk = check_name(toks)
            if acc:
                rows = [(d["change"], combine([verdict(t, cs[d["change"]], tg[d["change"]]) for t in toks])) for d in acc]
                facts = {"declared_targets": {d["change"]: tg[d["change"]] for d in acc}} if any(t.startswith("compat:") for t in toks) else None
                out.append(res(rid, chk, rows, "accepted changes carry " + ", ".join(toks), facts))
            elif ref:
                out.append(CheckResult(rid, chk, PASS, f"no change accepted without it; {why}",
                                       evidence={"refused": [d["change"] for d in ref][:10]}))
            else:
                out.append(na(rid, chk, "modifications", "none"))
        pr = [d for d in dec if d["doc"] == doc and cs[d["change"]]["kind"] == "presentation_only"]
        for rid in pres:
            if not pr:
                out.append(na(rid, "presentation_not_upgrade", "presentation-only corrections", "none"))
                continue
            bad = []
            for d in pr:
                rel = next(m for m in rels if m.arrived_at == _release_day(r, cs[d["change"]]["release"]))
                e = rel.value["editions"].get(d["identifier"])
                if d["upgrade"] or d["identifier"] != doc or e is None or e["date"] != rel.value["date"]:
                    bad.append(d["change"])
            out.append(CheckResult(rid, "presentation_not_upgrade", FAIL if bad else PASS,
                                   f"{len(bad)} corrections handled as Upgrades or not dated" if bad else
                                   f"{len(pr)} presentation-only corrections kept the identifier, bypassed the gate and changed only the date",
                                   evidence={"violations": bad} if bad else {"corrections": [d["change"] for d in pr]}))
        if integ:
            out.append(integrity(integ, [doc], docs, pinned, rels))
    # UPGRADE §12: all documents
    out.append(integrity("UPGRADE-12-07", sorted(docs), docs, pinned, rels, replace=True))
    prev = {i: (d["sha256"], d["last_updated"]) for i, d in docs.items()}
    undated, redated = [], []
    glossary = {d["id"] for d in docs.values() if d["kind"] == "glossary"}     # whether it is a 'DKP document' is not said
    for m in rels:
        ed = m.value["editions"]
        for i, e in ed.items():
            if e["line"] in glossary:
                continue
            p = prev.get(i)
            if not e["date"] or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"]):
                undated.append(i)
            elif p is None or p[0] != e["digest"]:
                if e["date"] != m.value["date"]:
                    undated.append(f"{i} ({m.value['release']})")
            elif e["date"] != p[1]:
                redated.append(f"{i} ({m.value['release']})")
        prev = {i: (e["digest"], e["date"]) for i, e in ed.items()}
    no_date = [d for d in docs.values() if d["kind"] != "glossary" and not d.get("last_updated")]
    out.append(CheckResult("UPGRADE-12-04", "edition_dated", FAIL if undated or no_date else PASS,
                           f"{len(undated) + len(no_date)} editions do not show the date of their last edition" if undated or no_date else
                           f"every pinned document and every edition of {len(rels)} releases shows the date of its last edition",
                           evidence={"violations": (undated + [d["id"] for d in no_date])[:10]} if undated or no_date else {}))
    out.append(CheckResult("UPGRADE-12-06", "unchanged_keep_dates", FAIL if redated else PASS,
                           f"{len(redated)} unchanged documents re-dated" if redated else
                           f"no release re-dated an unchanged document ({sum(1 for m in rels if m.value['kind'] != 'edition')} rebuild or navigation releases)",
                           evidence={"violations": redated[:10]} if redated else {}) if rels else na("UPGRADE-12-06", "unchanged_keep_dates", "releases", "none"))
    acts = [m.value for m in msgs if m.source == "EDITION" and m.kind == "action"]
    cert = [d["change"] for d in dec if "edition_date" in d.get("evidence", [])]
    early = [a["activation"] for a in acts if a["activation_day"] != _release_day(r, cs[a["activation"]]["release"]) + cs[a["activation"]]["activation_after_days"]]
    if dec:
        out.append(CheckResult("UPGRADE-12-05", "date_identifies_edition_only", FAIL if cert or early else PASS,
                               (f"{len(cert)} decisions used the edition date as evidence; {len(early)} activations moved to the edition date")
                               if cert or early else "no decision cites an edition date as evidence; every activation is on its declared day, "
                               "not the edition date", evidence={"violations": (cert + early)[:10]} if cert or early else {}))
    else:
        out.append(na("UPGRADE-12-05", "date_identifies_edition_only", "changes", "none"))
    return out


def _release_day(r: Dict[str, Any], rid: str) -> int:
    return next(x["day"] for x in r["releases"] if x["id"] == rid)


def check_name(toks) -> str:
    if len(toks) > 1:
        return "modification_requirements"
    t = toks[0]
    return {NEW: "new_identifier", INC: "incompatibility_declared", SIM: "simulated", FULL: "full_system_simulation",
            DEP: "dependents_resimulated", MAY_IFACE: "interfaces_resimulation"}.get(t, "compatibility_declared" if t.startswith("compat:") else t)


def integrity(rid, lines, docs, pinned, rels, replace=False) -> CheckResult:
    """Pinned commit: each document's digest is listed; simulated releases: each published edition's digest is listed."""
    bad = [d for d in lines if pinned.get(docs[d]["path"]) != docs[d]["sha256"]]
    n = 0
    for m in rels:
        for i, e in m.value["editions"].items():
            if e["line"] in lines:
                n += 1
                if m.value["listed"].get(i) != e["digest"]:
                    bad.append(f"{i} ({m.value['release']})")
    scope = f"all {len(lines)} pinned documents" if replace else lines[0]
    return CheckResult(rid, "edition_integrity", FAIL if bad else PASS,
                       f"{len(bad)} editions without their digest in SHA256SUMS.txt" if bad else
                       f"{scope}: digest listed in the pinned SHA256SUMS.txt of World@aad3e86; {n} edition listings in simulated releases match",
                       evidence={"violations": sorted(set(bad))[:10]} if bad else {})


def _implements() -> Dict[str, Any]:
    note = {NEW: None, INC: None, FULL: "Simulation results are declared.", SIM: "Simulation results are declared.",
            DEP: "Simulation results are declared.", PUB: "Disclosure is declared.", "stage:audit": "Audit is declared.",
            UNSPEC: "No target named (F-041): FAIL without a declaration, UNKNOWN otherwise.",
            DEPENDENTS: "'Dependent protocols' has two readings (H-EF-2, F-042): verdict fixed only where both agree.",
            MAY_IFACE: "Who may require it is not said: UNKNOWN unless performed.",
            "version_increment": "No version ordering is defined; presence is declared.",
            "compatibility_audit": "No standard for the audit; presence is declared.",
            "migration_path": "No standard for the migration path; presence is declared."}
    out = {}
    for doc, (proc, extra, items, pres, integ) in FINALITY.items():
        out[proc] = ("upgrade_procedure", "PARTIAL", "Declared stages of the change; the procedure itself is upgrade_lifecycle.")
        for rid, toks in items:
            ns = [note[t] for t in toks if note.get(t)]
            out[rid] = (check_name(toks), "PARTIAL" if ns else "IMPLEMENTED", " ".join(dict.fromkeys(ns)) or None)
        for rid in pres:
            out[rid] = ("presentation_not_upgrade", "IMPLEMENTED", None)
        if integ:
            out[integ] = ("edition_integrity", "PARTIAL", "Checked on the pinned commit and on simulated releases, not on the published site.")
    out["UPGRADE-12-04"] = ("edition_dated", "PARTIAL", "Pinned corpus and simulated releases, not the published site.")
    for rid in OVERRIDE_HEADERS.values():
        out[rid] = ("override_not_permitted", "PARTIAL", "An override is a declared attempt by another protocol; changes through "
                                                         "UPGRADE are checked under the finality clause.")
    out["UPGRADE-12-05"] = ("date_identifies_edition_only", "PARTIAL", "Checked on the module's own gate and activation records.")
    out["UPGRADE-12-06"] = ("unchanged_keep_dates", "PARTIAL", "Simulated releases, not the site build.")
    return out


IMPLEMENTS = _implements()

RELEASES = [{"id": "r1", "day": 10, "kind": "edition"}, {"id": "r2", "day": 20, "kind": "rebuild"},
            {"id": "r3", "day": 25, "kind": "navigation"}, {"id": "r4", "day": 40, "kind": "edition"}]
CHANGES = [
    {"id": "info_v2", "doc": "DKP-5-INFO-001"},
    {"id": "justice_typo", "doc": "DKP-1-JUSTICE-001", "kind": "presentation_only"},
    {"id": "audit_direct", "doc": "DKP-8-AUDIT-001", "channel": "direct"},
    {"id": "error_v2", "doc": "DKP-4-ERROR-001"},
    {"id": "privacy_half", "doc": "DKP-7-PRIVACY-001", "compatibility_with": [SCOPE]},
    {"id": "crisis_light", "doc": "DKP-4-CRISIS-001", "simulation": "targeted"},
    {"id": "scope_v2", "doc": SCOPE, "release": "r4"},
    {"id": "info_typo", "doc": "DKP-5-INFO-001", "kind": "presentation_only", "release": "r4"},
]


class EditionFinalityModule(LabModule):
    id = "edition_finality"
    version = "1.1.0"
    title = {"en": "Editions and finality clauses (all documents)", "ru": "Редакции и заключительные положения (все документы)"}
    summary = {"en": "Changes to thirty documents go through a gate that applies each document's own finality clause; editions are "
                     "published in releases, dated and listed in SHA256SUMS.txt.  Is a quiet edit refused, a typo fix kept out of "
                     "the upgrade procedure, and does a rebuild leave dates alone?",
               "ru": "Изменения тридцати документов проходят шлюз, который применяет заключительное положение каждого документа; "
                     "редакции публикуются выпусками, датируются и вносятся в SHA256SUMS.txt.  Отклоняется ли тихая правка, обходит "
                     "ли исправление опечатки процедуру изменения, не меняет ли пересборка даты?"}
    protocols = ["DKP-4-UPGRADE-001"] + [d for d in FINALITY if d != "DKP-4-UPGRADE-001"]
    example_order = ["four_releases", "every_document", "unnamed_targets", "narrow_dependents_reading", "strict_record_reading",
                     "faulty_editions"]
    alternative_examples = ["narrow_dependents_reading", "strict_record_reading"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_edition_finality_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-EF-1", "source": "hypothesis", "text": {
            "en": "Simulation wording: 'full-system simulation', 'full-system revalidation under DKP-8-SIMULATION' and 'mandatory system "
                  "simulation' require a simulation of the whole system; 'mandatory simulation under DKP-8-SIMULATION-001' requires at "
                  "least a targeted one; 'full re-simulation of all dependent protocols' requires the dependents (a full-system "
                  "simulation covers them).  Results are declared.",
            "ru": "Формулировки симуляции: 'full-system simulation', 'full-system revalidation under DKP-8-SIMULATION' и 'mandatory "
                  "system simulation' требуют симуляции всей системы; 'mandatory simulation under DKP-8-SIMULATION-001' — хотя бы "
                  "целевой; 'full re-simulation of all dependent protocols' — зависимых протоколов (полная симуляция их покрывает). "
                  "Результаты объявляются."}},
        {"id": "H-EF-2", "source": "hypothesis", "text": {
            "en": "SCOPE §12 'across all dependent protocols': read as the protocols whose text references SCOPE (17) or as those that "
                  "list it under 'Depends on' (2: EPISTEMIC-BOUNDARIES in the body, RESILIENCE in the front matter; F-042).  The gate "
                  "applies the chosen reading; the check is PASS only if both are covered, FAIL if the narrow one is not, UNKNOWN in "
                  "between.",
            "ru": "SCOPE §12 'across all dependent protocols': протоколы, текст которых ссылается на SCOPE (17), или те, что указывают "
                  "его в списке 'Depends on' (2: EPISTEMIC-BOUNDARIES в тексте, RESILIENCE в метаданных; F-042).  Шлюз применяет "
                  "выбранное прочтение; проверка PASS, только если покрыты оба, FAIL — если не покрыто узкое, иначе UNKNOWN."}},
        {"id": "H-EF-3", "source": "hypothesis", "text": {
            "en": "'Recorded only by the \"Last updated\" date of this document' concerns the document's own record (no new identifier, "
                  "no version entry); the repository digest list (edition integrity) is not such a record.  Under the alternative "
                  "reading (no other record at all) a corrected edition cannot be listed, and the edition-integrity line fails.",
            "ru": "'Recorded only by the \"Last updated\" date of this document' относится к записи в самом документе (без нового "
                  "идентификатора и записи версии); список дайджестов репозитория такой записью не считается.  При другом прочтении "
                  "(никакой другой записи) исправленную редакцию нельзя внести в список, и строка о целостности редакций нарушается."}},
        {"id": "H-EF-4", "source": "hypothesis", "text": {
            "en": "An accepted modification is published on its release date as a new edition under the new identifier; the old "
                  "document stays published; activation is deferred to the declared day (UPGRADE §8).  A presentation-only correction "
                  "replaces the edition of the same identifier.",
            "ru": "Принятое изменение публикуется в день выпуска как новая редакция под новым идентификатором; старый документ "
                  "остаётся опубликованным; активация откладывается на объявленный день (UPGRADE §8).  Исправление оформления "
                  "заменяет редакцию с тем же идентификатором."}},
        {"id": "H-EF-5", "source": "lab", "text": {
            "en": "Items of an 'In addition' list that the registry does not hold as provisions of their own (e.g. CRISIS §11, INFO "
                  "§14, ERROR §12 simulation, DEFENSE public disclosure) are checked under the clause's procedure provision.",
            "ru": "Пункты списка 'In addition', которых нет в реестре отдельными положениями (например CRISIS §11, INFO §14, симуляция "
                  "ERROR §12, публичное раскрытие DEFENSE), проверяются в положении о процедуре."}},
    ]
    inputs = {
        "releases": {"type": "list", "min_items": 1, "max_items": 12, "items": RELEASE, "default": RELEASES, "source": "user",
                     "label": {"en": "Releases (day after the pinned edition date)", "ru": "Выпуски (день после даты закреплённой редакции)"}},
        "changes": {"type": "list", "min_items": 0, "max_items": 64, "items": CHANGE, "default": CHANGES, "source": "user",
                    "label": {"en": "Changes (declared)", "ru": "Изменения (объявленные)"}},
        "override_attempts": {"type": "list", "min_items": 0, "max_items": 12, "items": OVERRIDE, "default": OVERRIDES,
                              "source": "user", "label": {"en": "Attempts by other protocols to override a document",
                                                          "ru": "Попытки других протоколов переопределить документ"}},
        "dependents_reading": {"type": "enum", "values": ["references", "depends_on"], "default": "references",
                               "source": "hypothesis", "label": {"en": "SCOPE 'dependent protocols' read by the gate (H-EF-2)",
                                                                  "ru": "Прочтение 'зависимых протоколов' SCOPE в шлюзе (H-EF-2)"}},
        "presentation_record_reading": {"type": "enum", "values": ["document_metadata", "all_records"], "default": "document_metadata",
                                        "source": "hypothesis", "label": {"en": "'Recorded only by the date' (H-EF-3)",
                                                                           "ru": "'Recorded only by the date' (H-EF-3)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        for what, rows in (("changes", r["changes"]), ("releases", r["releases"])):
            ids = [x["id"] for x in rows]
            if len(set(ids)) != len(ids):
                p.append(f"input.{what}: repeated id")
            for x in ids:
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                    p.append(f"input.{what}: id {x!r} must be lowercase letters, digits or _ (at most 24)")
        days = [x["day"] for x in r["releases"]]
        if len(set(days)) != len(days):
            p.append("input.releases: two releases on one day")
        rel = {x["id"]: x for x in r["releases"]}
        for c in r["changes"]:
            if c["release"] not in rel:
                p.append(f"input.changes: {c['id']} names unknown release {c['release']!r}")
            elif rel[c["release"]]["kind"] != "edition":
                p.append(f"input.changes: {c['id']} is in a {rel[c['release']]['kind']} release, which changes no document")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        dec = [m.value for m in msgs if m.kind == "decision" and m.source == "EDITION"]
        rels = [m.value for m in msgs if m.source == "RELEASE"]
        base = {d["id"]: d["sha256"] for d in _CAT["documents"]}
        summary = []
        prev = dict(base)
        for x in rels:
            ch = sorted(i for i, e in x["editions"].items() if prev.get(i) != e["digest"])
            summary.append({"release": x["release"], "kind": x["kind"], "date": x["date"], "new_or_changed_editions": ch,
                            "listed": len(x["listed"]), "unlisted": sorted(i for i, e in x["editions"].items() if x["listed"].get(i) != e["digest"])})
            prev = {i: e["digest"] for i, e in x["editions"].items()}
        outputs = {"decisions": dec, "activations": [m.value for m in msgs if m.kind == "action"], "releases": summary,
                   "pinned_manifest": {"header": _CAT["corpus"]["release_manifest"]["header"],
                                       "entries": len(_CAT["corpus"]["release_manifest"]["entries"])},
                   "undetermined": [{"requirement": c.requirement_id, **c.evidence} for c in res if c.status == UNKNOWN],
                   "operational_use": False,
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = []
        for d in dec:
            if not d["upgrade"]:
                what = {"en": "presentation-only: date only", "ru": "только оформление: меняется лишь дата"}
            elif d["accepted"]:
                what = {"en": f"accepted as {d['identifier']}", "ru": f"принято как {d['identifier']}"}
            else:
                what = {"en": "refused, missing " + ", ".join(d["missing"]), "ru": "отклонено, не хватает: " + ", ".join(d["missing"])}
            e.append({"en": f"{d['change']} ({d['doc']}): {what['en']}.", "ru": f"{d['change']} ({d['doc']}): {what['ru']}."})
        return ModuleResult(outputs=outputs, checks=res, explain=e[:40])

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        d = outputs["decisions"]
        return {"accepted": sum(1 for x in d if x.get("accepted")), "refused": sum(1 for x in d if x["upgrade"] and not x.get("accepted")),
                "presentation_only": sum(1 for x in d if not x["upgrade"]), "violations": len(outputs["violations"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        every = []
        for doc in FINALITY:
            every.append({"id": f"n_{short(doc)}"[:24], "doc": doc, "interfaces_resimulated": doc == "DKP-5-CULTURE-001"})
            every.append({"id": f"p_{short(doc)}"[:24], "doc": doc, "kind": "presentation_only"})
        return {
            "four_releases": {},
            "every_document": {"releases": [{"id": "r1", "day": 10}], "changes": every},
            "unnamed_targets": {"releases": [{"id": "r1", "day": 10}], "changes": [
                {"id": "error_named", "doc": "DKP-4-ERROR-001", "compatibility_with": ["DKP-1-EPISTEMIC-BOUNDARIES-001"]},
                {"id": "upgrade_unnamed", "doc": "DKP-4-UPGRADE-001", "compatibility_with": []},
                {"id": "crisis_none", "doc": "DKP-4-CRISIS-001", "declarations": [NEW, INC]}]},
            "narrow_dependents_reading": {"dependents_reading": "depends_on", "releases": [{"id": "r1", "day": 10}],
                                          "changes": [{"id": "scope_narrow", "doc": SCOPE}]},
            "strict_record_reading": {"presentation_record_reading": "all_records", "releases": [{"id": "r1", "day": 10}],
                                      "changes": [{"id": "info_typo", "doc": "DKP-5-INFO-001", "kind": "presentation_only"}]},
            "faulty_editions": {"faults": ["skip_finality", "date_as_activation", "rebuild_redates", "digest_not_listed",
                                           "presentation_undated"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_change": {"changes": [{"id": "a", "doc": SCOPE}, {"id": "a", "doc": SCOPE}]},
                "unknown_release": {"changes": [{"id": "a", "doc": SCOPE, "release": "zz"}]},
                "change_in_rebuild": {"changes": [{"id": "a", "doc": SCOPE, "release": "r2"}]},
                "document_without_clause": {"changes": [{"id": "a", "doc": "DKP-0-TIME-001"}]},
                "two_releases_one_day": {"releases": [{"id": "r1", "day": 5}, {"id": "r2", "day": 5}]}}


for _spec in EditionFinalityModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
