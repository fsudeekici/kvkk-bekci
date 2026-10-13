import pytest

from kvkk_bekci import validators as v


@pytest.mark.parametrize("tc", ["10000000146", "12345678950", " 10000000146 "])
def test_tc_valid(tc):
    assert v.tc_valid(tc)


@pytest.mark.parametrize(
    "tc",
    [
        "10000000147",  # last check digit wrong
        "10000000156",  # tenth digit wrong
        "00000000000",  # starts with 0
        "1000000014",  # 10 digits
        "100000001466",  # 12 digits
        "1000000014a",
        "",
    ],
)
def test_tc_invalid(tc):
    assert not v.tc_valid(tc)


def test_tc_check_digits():
    assert v.tc_check_digits("100000001") == "46"
    assert v.tc_check_digits("123456789") == "50"


@pytest.mark.parametrize(
    "iban",
    [
        "TR330006100519786457841326",
        "TR33 0006 1005 1978 6457 8413 26",
        "tr330006100519786457841326",
    ],
)
def test_iban_valid(iban):
    assert v.iban_valid(iban)


@pytest.mark.parametrize(
    "iban",
    [
        "TR340006100519786457841326",  # check digits wrong
        "TR330006100519786457841327",  # one digit changed
        "TR33000610051978645784132",  # too short
        "GB82WEST12345698765432",  # valid IBAN, but not Turkish
        "not an iban",
    ],
)
def test_iban_invalid(iban):
    assert not v.iban_valid(iban)


def test_iban_check_digits_roundtrip():
    bban = "0006100519786457841326"
    assert v.iban_check_digits("TR", bban) == "33"


@pytest.mark.parametrize(
    "phone",
    ["+90 532 123 45 67", "0532 123 45 67", "05321234567", "5321234567", "+90 (532) 123-45-67", "905321234567"],
)
def test_phone_valid(phone):
    assert v.phone_valid(phone)
    assert v.phone_national(phone) == "5321234567"


@pytest.mark.parametrize("phone", ["532 123", "+90 212 123 45 67", "0532 123 45 6x", "+1 532 123 45 67", ""])
def test_phone_invalid(phone):
    assert not v.phone_valid(phone)


def test_bare_tc_is_not_phone_shaped():
    assert not v.phone_shape("10000000146")
    assert v.phone_shape("05321234567")


@pytest.mark.parametrize("value", ["2024-05-30", "2024-05-30-1200", "2024.05.30", "12345"])
def test_dates_and_short_numbers_are_not_phone_shaped(value):
    assert not v.phone_shape(value)


@pytest.mark.parametrize("email", ["ayse@example.com", "a.b+c@mail.co.tr"])
def test_email_valid(email):
    assert v.email_valid(email)


@pytest.mark.parametrize("email", ["ayse.example.com", "ayse@", "@example.com", "ayse@example", "a b@example.com"])
def test_email_invalid(email):
    assert not v.email_valid(email)


@pytest.mark.parametrize("name", ["Ayşe Yılmaz", "Çağrı Öztürk Şahin", "Dr. Ali Veli"])
def test_name_valid(name):
    assert v.name_valid(name)


@pytest.mark.parametrize("name", ["Ayşe", "Ali 123", "shipped", ""])
def test_name_invalid(name):
    assert not v.name_valid(name)


@pytest.mark.parametrize("value", [None, "", "   ", "\t"])
def test_is_empty(value):
    assert v.is_empty(value)


def test_is_not_empty():
    assert not v.is_empty("x")
    assert not v.is_empty(0)
