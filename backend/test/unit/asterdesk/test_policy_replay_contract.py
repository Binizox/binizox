from test.support.asterdesk_policy_replay_server import (
    EXPECTED_AUTHORIZATION,
    EXPECTED_MODEL,
    EXPECTED_POLICY_MARKER,
    EXPECTED_QUESTION,
    EXPECTED_SECTION_MARKER,
    _validate_request,
)


def test_policy_replay_requires_skill_context() -> None:
    request = {
        "model": EXPECTED_MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": EXPECTED_QUESTION}],
    }

    assert _validate_request(EXPECTED_AUTHORIZATION, request) == "policy_context_missing"


def test_policy_replay_accepts_question_with_policy_source() -> None:
    request = {
        "model": EXPECTED_MODEL,
        "stream": True,
        "messages": [
            {"role": "system", "content": f"{EXPECTED_POLICY_MARKER}\n{EXPECTED_SECTION_MARKER}"},
            {"role": "user", "content": EXPECTED_QUESTION},
        ],
    }

    assert _validate_request(EXPECTED_AUTHORIZATION, request) is None
