"""Typed Custom-mode sentences -> words only, so the scoring, the native TTS
clip and what the learner sees all agree. Korean digits get the reading a native would say: native numbers
(한/두/세...) before native counters (잔, 명, 시, 살...), Sino numbers (일/이/삼...) for everything else."""
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.custom import MAX_CHARS, custom_text, native_number, sino_number

client = TestClient(app)


# ---------- number words ----------

@pytest.mark.parametrize("n,word", [
    (0, "영"), (1, "일"), (10, "십"), (11, "십일"), (20, "이십"), (100, "백"), (110, "백십"), (1000, "천"),
    (2026, "이천이십육"), (5000, "오천"), (10000, "만"), (15000, "만 오천"), (123456, "십이만 삼천사백오십육"),
    (100000000, "일억"),
])
def test_sino_number(n, word):
    assert sino_number(n) == word


@pytest.mark.parametrize("n,word", [
    (1, "한"), (2, "두"), (3, "세"), (4, "네"), (5, "다섯"), (10, "열"), (11, "열한"), (12, "열두"),
    (20, "스무"), (21, "스물한"), (30, "서른"), (99, "아흔아홉"),
])
def test_native_number_before_a_counter(n, word):
    assert native_number(n) == word


# ---------- Korean sentences ----------

@pytest.mark.parametrize("typed,said", [
    ("커피 2잔 주세요.", "커피 두 잔 주세요."),      # a real bug: g2pk said 이잔
    ("3시에 만나요.", "세 시에 만나요."),
    ("3시 30분에 봐요.", "세 시 삼십 분에 봐요."),
    ("3:30에 봐요.", "세 시 삼십 분에 봐요."),
    ("친구 5명이 와요.", "친구 다섯 명이 와요."),
    ("저는 20살이에요.", "저는 스무 살이에요."),
    ("21살이야.", "스물한 살이야."),
    ("2시간 걸려요.", "두 시간 걸려요."),             # 시간 (longer) wins over 시
    ("3개월 됐어요.", "삼 개월 됐어요."),             # 개월 (Sino) wins over 개 (native)
    ("5,000원이에요.", "오천 원이에요."),
    ("15000원", "만 오천 원"),
    ("2026년에 졸업해요.", "이천이십육 년에 졸업해요."),
    ("6월에 가요.", "유월에 가요."),                  # 6월 = 유월, 10월 = 시월 (not 육월 / 십월)
    ("10월이 좋아요.", "시월이 좋아요."),
    ("12월", "십이월"),
    ("1번째 사람", "첫 번째 사람"),
    ("2번째예요.", "두 번째예요."),
    ("3번 해 봐.", "세 번 해 봐."),                   # 번 = times (native) by default
    ("3번 출구로 나가세요.", "삼 번 출구로 나가세요."),  # ...but a NUMBERED thing (exit, bus, seat) is Sino
    ("2번 버스 타요.", "이 번 버스 타요."),
    ("2인분 주세요.", "이 인분 주세요."),
    ("1.5킬로", "일 점 오 킬로"),
    ("010-1234-5678", "공일공 일이삼사 오육칠팔"),    # phone numbers: digit by digit, 0 = 공
    ("맥주 2병이랑 소주 1병", "맥주 두 병이랑 소주 한 병"),
])
def test_korean_digits_become_spoken_words(typed, said):
    assert custom_text(typed, "ko") == said


def test_korean_without_digits_is_unchanged_except_spaces():
    assert custom_text("  안녕하세요,   반가워요! ", "ko") == "안녕하세요, 반가워요!"


# ---------- English sentences ----------

@pytest.mark.parametrize("typed,said", [
    ("I have 2 cats!", "I have two cats!"),
    ("Dr. Kim's café", "Doctor Kim's café"),          # g2p_en said "drive"
    ("Mr. and Mrs. Lee", "Mister and Missus Lee"),
    ("Meet me at 10:30.", "Meet me at ten thirty."),
    ("Come at 7:00.", "Come at seven o'clock."),
    ("Come at 7:05.", "Come at seven oh five."),
    ("50% off", "fifty percent off"),
    ("the 1st time", "the first time"),
    ("in 1999", "in nineteen ninety-nine"),
    ("salt & pepper", "salt and pepper"),
    ("It's 3 pm.", "It's three P M."),
    ("at 9 a.m.", "at nine A M."),
    ("I was No. 1", "I was number one"),
])
def test_english_numbers_and_abbreviations_become_words(typed, said):
    assert custom_text(typed, "en") == said


# ---------- refused input (clear messages) ----------

def test_korean_text_in_english_mode_is_refused():
    with pytest.raises(ValueError, match="Korean"):
        custom_text("안녕 hello", "en")


def test_too_long_is_refused():
    with pytest.raises(ValueError, match=str(MAX_CHARS)):
        custom_text("가" * (MAX_CHARS + 1), "ko")


@pytest.mark.parametrize("text", ["", "   ", "?!...", "123"])
def test_nothing_to_say_is_refused(text):
    if text == "123":
        assert custom_text(text, "ko") == "백이십삼"     # a bare number is still something to say
        return
    with pytest.raises(ValueError):
        custom_text(text, "ko")


def test_unknown_language_is_refused():
    with pytest.raises(ValueError):
        custom_text("hello", "fr")


# ---------- endpoint ----------

def test_custom_endpoint_returns_the_spoken_text():
    r = client.get("/custom", params={"text": "커피 2잔 주세요.", "lang": "ko"})
    assert r.status_code == 200
    assert r.json() == {"text": "커피 두 잔 주세요.", "typed": "커피 2잔 주세요.", "changed": True}


def test_custom_endpoint_unchanged_text():
    r = client.get("/custom", params={"text": "I like it.", "lang": "en"})
    assert r.status_code == 200 and r.json()["changed"] is False


def test_custom_endpoint_refusal_is_a_400_with_the_reason():
    r = client.get("/custom", params={"text": "안녕 hello", "lang": "en"})
    assert r.status_code == 400 and "Korean" in r.json()["detail"]
