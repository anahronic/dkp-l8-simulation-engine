"""DKP-8 infrastructure: the software side of DKP-8-SIMULATION-001 beyond the research bench and the lab.

canonical (RFC 8785 subset), ed25519 (RFC 8032), trust (keys, nodes, revocations), bundle (Calibration Bundle §9-§10),
invariants (§6), gate (§5-§8, §12), reproduction (§8, §11), enforcement (§4, §13, §14), composite (§9 indices),
scenarios (synthetic catalogue), traceability (48 provisions).  CLI: ``python -m dkp8 --help``.

Nothing here is an operational L8: the canonical trust store designates no signing authority and no independent
node, and no calibration value or PTL dataset exists.  Every outcome that needs them is NOT_ESTABLISHED.
"""
__version__ = "1.0.0"
