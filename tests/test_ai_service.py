from ai_service import (
    is_ai_error,    
    ai_error,
    is_rate_limit_error,
    parse_json_object,
    validate_router_response,
)

def test_is_ai_error_returns_true_for_error_dict():
    assert is_ai_error({"error": True, "type": "api_error", "msg": "x"}) is True

def test_is_ai_error_returns_false_for_non_error_dict():
    assert is_ai_error({"error": False}) is False
    assert is_ai_error({"result": "something"}) is False

def test_is_ai_error_returns_false_for_non_dict():
    assert is_ai_error("string") is False
    assert is_ai_error([1, 2, 3]) is False
    assert is_ai_error(None) is False

def test_ai_error_builds_structured_dict():
    result = ai_error("rate_limit", "Too fast")
    assert result == {"error": True, "type": "rate_limit", "msg": "Too fast"}

def test_is_rate_limit_error_detects_429_in_message():
    assert is_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert is_rate_limit_error(Exception("resource exhausted")) is True

def test_is_rate_limit_error_detects_status_code_attribute():
    class FakeErr(Exception):
        status_code = 429
    assert is_rate_limit_error(FakeErr("anything")) is True

def test_is_rate_limit_error_returns_false_for_other_errors():
    assert is_rate_limit_error(Exception("network timeout")) is False

def test_parse_json_object_accepts_valid_dict():
    assert parse_json_object('{"a": 1}', "fallback") == {"a": 1}

def test_parse_json_object_returns_error_for_invalid_json():
    result = parse_json_object("not json", "fallback msg")
    assert is_ai_error(result) is True
    assert result["msg"] == "fallback msg"

def test_parse_json_object_rejects_list_by_default():
    result = parse_json_object("[1, 2, 3]", "fallback")
    assert is_ai_error(result) is True

def test_parse_json_object_allows_list_when_requested():
    result = parse_json_object("[1, 2, 3]", "fallback", allow_list=True)
    assert result == [1, 2, 3]

def test_parse_json_object_passes_through_dict_unchanged():
    data = {"already": "parsed"}
    assert parse_json_object(data, "fallback") is data

def test_validate_router_response_returns_none_for_valid():
    response = {"action": ["chat"], "content": ["hello"]}
    assert validate_router_response(response) is None

def test_validate_router_response_rejects_mismatched_lengths():
    response = {"action": ["chat", "create_note"], "content": ["hello"]}
    result = validate_router_response(response)
    assert is_ai_error(result) is True

def test_validate_router_response_rejects_unknown_action():
    response = {"action": ["nonexistent_action"], "content": ["x"]}
    result = validate_router_response(response)
    assert is_ai_error(result) is True


def test_validate_router_response_accepts_rename_chat():
    response = {
        "action": ["chat", "rename_chat"],
        "content": ["<p>hi</p>", "Test Title"],
    }
    assert validate_router_response(response) is None


def test_build_ai_instructions_handles_rename_chat(monkeypatch):
    import ai_service
    monkeypatch.setattr(ai_service, "ask_intent_router", lambda *a, **kw: {
        "action": ["chat", "rename_chat"],
        "content": ["<p>hello</p>", "Hello Chat"],
    })
    instructions = ai_service.build_ai_instructions(
        contents=[{"role": "user", "contents": "hi"}],
        username="test",
        new_session=True,
    )
    actions = [i["action"] for i in instructions]
    assert "rename_chat" in actions
    rename_instruction = next(i for i in instructions if i["action"] == "rename_chat")
    assert rename_instruction["content"] == "Hello Chat"