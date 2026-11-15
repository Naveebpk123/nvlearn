from utils import create_code

def test_create_code_is_six_digit_string():
    code = create_code()
    assert isinstance(code,str)
    assert len(code)==6
    assert code.isdigit()
