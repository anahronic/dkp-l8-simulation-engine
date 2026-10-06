"""Inter-module contract (lab specification §6.3): messages, declared order, no reading of the future."""

import random

import pytest

from lab.core.bus import ContractError, EventLog, Message, epistemic_problems


def obs(i, t, source="ground", order=0, measured=None, prov=()):
    return Message(event_id=f"o{i}", kind="observation", source=source, arrived_at=t, value=str(i),
                   unit="u", measured_at=t if measured is None else measured, order=order, provenance=prov)


def test_message_fields_are_checked():
    with pytest.raises(ContractError):
        Message(event_id="", kind="observation", source="s", arrived_at=0)
    with pytest.raises(ContractError):
        Message(event_id="a", kind="rumour", source="s", arrived_at=0)
    with pytest.raises(ContractError):
        Message(event_id="a", kind="observation", source="s", arrived_at=5, measured_at=6)    # arrives before measured
    with pytest.raises(ContractError):
        Message(event_id="a", kind="decision", source="s", arrived_at=5)                     # decision without decided_at
    with pytest.raises(ContractError):
        Message(event_id="a", kind="observation", source="s", arrived_at=True)                # bool is not a time
    with pytest.raises(ContractError):
        Message(event_id="a", kind="observation", source="s", arrived_at=1.5)


def test_ids_are_unique_and_provenance_cannot_point_forward():
    log = EventLog("minute")
    log.append(obs(1, 10))
    with pytest.raises(ContractError):
        log.append(obs(1, 11))                                          # duplicate id
    with pytest.raises(ContractError):
        log.append(Message(event_id="e", kind="evaluation", source="m", arrived_at=12, provenance=("missing",)))
    log.append(obs(2, 20))
    with pytest.raises(ContractError):                                  # derived at 15 from a message arriving at 20
        log.append(Message(event_id="e", kind="evaluation", source="m", arrived_at=15, provenance=("o2",)))
    log.append(Message(event_id="e", kind="evaluation", source="m", arrived_at=20, provenance=("o1", "o2")))


def test_append_order_does_not_change_the_log():
    msgs = [obs(i, t, source=s, order=o) for i, (t, s, o) in
            enumerate([(0, "ground", 0), (0, "orbital", 1), (5, "ground", 0), (5, "orbital", 0), (7, "ground", 2)])]
    digests = set()
    for seed in range(5):
        log = EventLog("minute")
        shuffled = msgs[:]
        random.Random(seed).shuffle(shuffled)
        for m in shuffled:
            log.append(m)
        digests.add(log.digest())
    assert len(digests) == 1


def test_simultaneous_events_follow_the_declared_order():
    log = EventLog("minute", tie_rule="order field")
    log.append(obs("b", 5, order=2))
    log.append(obs("a", 5, order=1))
    assert [m.event_id for m in log.messages()] == ["oa", "ob"]


def test_a_view_never_shows_the_future():
    log = EventLog("minute")
    for i, t in enumerate([0, 10, 20, 30]):
        log.append(obs(i, t))
    v = log.view(15)
    assert [m.event_id for m in v.messages()] == ["o0", "o1"]
    assert v.latest("observation", "ground").event_id == "o1"
    with pytest.raises(ContractError):
        v.get("o3")
    assert log.view(-1).latest("observation", "ground") is None


def test_latest_is_by_measurement_time_including_zero():
    log = EventLog("minute")
    log.append(obs("late", 9, measured=0))      # measured at 0, delivered late
    log.append(obs("fresh", 5, measured=4))
    assert log.view(9).latest("observation", "ground").event_id == "ofresh"
    assert log.view(5).latest("observation", "ground").event_id == "ofresh"


def test_epistemic_metadata_completeness():
    full = {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": "s", "revalidation_required": False, "dispute_allowed": True}
    assert epistemic_problems(full) == []
    assert epistemic_problems(None) == ["no epistemic metadata"]
    assert "missing scope_ref" in epistemic_problems({**full, "scope_ref": None})
    assert any("undefined" in p for p in epistemic_problems({**full, "validity_state": "MAYBE"}))
