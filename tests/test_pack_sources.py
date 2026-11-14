"""Candidate pools for the sentence packs (content/sources.py). No network: XML and rows are inline."""
import io
import urllib.error

import pytest

from content import sources as S

# ---------- style of a spoken line ----------

@pytest.mark.parametrize("text,style", [
    ("손님, 주문을 받겠습니다.", "formal"),
    ("고맙습니다.", "formal"),
    ("아내를 사랑하십니까?", "formal"),
    ("맛있게 드십시오.", "formal"),
    ("여기 메뉴 좀 주세요.", "polite"),        # mecab calls 주세요 a noun; the 요 rule must win
    ("깔끔한게 좋죠.", "polite"),
    ("지수 씨, 사장님의 주문을 들으셨어요?", "polite"),
    ("나 너무 무서워.", "casual"),
    ("오늘 한잔 할까?", "casual"),
    ("첫 번째를 눌러.", "casual"),
    ("한 번 해 보자!", "casual"),               # -자 = "let's", spoken
    ("어디 가니?", "casual"),
    ("서울에는 사람이 정말 많다.", "written"),   # 한다 style: books, not talk
    ("그는 학생이다.", "written"),
    ("갈비찜을 주문하다.", "written"),
    ("아이스 커피", "fragment"),                # no verb ending
    ("감당 못하는 사랑", "fragment"),
    ("12시 땡!", "fragment"),
    ("좀 오래 머물 계획이오.", "hao"),          # 하오체: old-fashioned, not how friends talk
    ("어서 들어오시오.", "formal"),             # -시오 is still the formal command
])
def test_spoken_style(text, style):
    assert S.spoken_style(text) == style


def test_style_uses_last_sentence_and_rejects_any_written_piece():
    assert S.spoken_style("네. 꽃 그림이 들어간 그릇으로 만들어 주세요.") == "polite"
    assert S.spoken_style("맛있다. 또 와요.") == "written"


def test_syllables_counts_hangul_only():
    assert S.syllables("여기 메뉴 좀 주세요.") == 8   # 여·기 메·뉴 좀 주·세·요
    assert S.syllables("OK 좋아!") == 2


@pytest.mark.parametrize("text,ok", [
    ("여기 메뉴 좀 주세요.", True),
    ("네.", False),                           # under 4 syllables
    ("우리 제과점은 고객의 주문에 따라 개별적으로 빵이나 케이크를 만들어요.", False),  # over 15
    ("두명 예약해주세요 18:28에요.", False),     # digits (fake times, TTS reads them oddly)
    ("'쓰리플러스'가 좋네요.", False),          # quoted made-up names
    ("OK 그럼 가요.", False),                  # Latin letters
    ("서울 중구 38345입니다.", False),
])
def test_clean_line(text, ok):
    assert S.clean_reason(text) is None if ok else S.clean_reason(text) is not None


def test_split_sentences():
    assert S.split_sentences("네. 꽃 그림이 들어간 그릇으로 만들어 주세요.") == ["네.", "꽃 그림이 들어간 그릇으로 만들어 주세요."]
    assert S.split_sentences("정말? 진짜 좋아!") == ["정말?", "진짜 좋아!"]


# ---------- the dictionary (krdict) ----------

SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?><channel><total>2</total><start>1</start><num>100</num>
<item><target_code>11111</target_code><word>메뉴</word><sup_no>0</sup_no></item>
<item><target_code>22222</target_code><word>주문</word><sup_no>0</sup_no></item></channel>"""

VIEW_XML = """<?xml version="1.0" encoding="UTF-8"?><channel><item><target_code>11111</target_code>
<word_info><word>메뉴</word><word_grade>초급</word_grade>
<category_info><type>의미 범주</type><written_form>식생활 &gt; 식사 및 조리 행위</written_form></category_info>
<category_info><type>주제 및 상황 범주</type><written_form>음식 주문하기</written_form></category_info>
<sense_info><definition>...</definition>
<example_info><type>구</type><example>메뉴를 고르다.</example></example_info>
<example_info><type>문장</type><example>그 식당은 메뉴가 많다.</example></example_info>
<example_info><type>대화</type><example>아줌마, 여기 메뉴 좀 주세요.</example></example_info>
<example_info><type>대화</type><example>여기 있습니다.</example></example_info>
</sense_info></word_info></item></channel>"""


def test_parse_search():
    assert S.parse_search(SEARCH_XML) == (2, [("11111", "메뉴"), ("22222", "주문")])


def test_parse_view_keeps_only_dialogue_lines():
    v = S.parse_view(VIEW_XML)
    assert v["word"] == "메뉴" and v["target_code"] == "11111" and v["grade"] == "초급"
    assert v["topics"] == ["음식 주문하기"]
    assert v["dialogue"] == ["아줌마, 여기 메뉴 좀 주세요.", "여기 있습니다."]


def test_api_error_is_raised_without_the_key(tmp_path):
    secret = "0123456789abcdef0123456789abcdef"
    err = '<?xml version="1.0"?><error><error_code>020</error_code><message>Unregistered key</message></error>'
    c = S.Krdict(key=secret, cache_dir=tmp_path, fetch=lambda url: err, pause=0)
    with pytest.raises(S.KrdictError) as e:
        c.get("search", q="메뉴")
    assert "020" in str(e.value) and secret not in str(e.value)


def test_network_error_message_has_no_key(tmp_path):
    secret = "0123456789abcdef0123456789abcdef"

    def boom(url):
        raise urllib.error.URLError(f"failed for {url}")  # a careless library could echo the URL (with the key)
    c = S.Krdict(key=secret, cache_dir=tmp_path, fetch=boom, pause=0, retry_wait=0)
    with pytest.raises(S.KrdictError) as e:
        c.get("search", q="메뉴")
    assert secret not in str(e.value)


def test_transient_network_errors_are_retried(tmp_path):
    attempts = []

    def flaky(url):
        attempts.append(url)
        if len(attempts) < 3:
            raise urllib.error.URLError("timed out")
        return SEARCH_XML
    c = S.Krdict(key="k" * 32, cache_dir=tmp_path, fetch=flaky, pause=0, retry_wait=0)
    assert S.parse_search(c.get("search", q="메뉴"))[0] == 2 and len(attempts) == 3


def test_api_errors_are_not_retried(tmp_path):
    attempts = []
    err = '<?xml version="1.0"?><error><error_code>020</error_code><message>Unregistered key</message></error>'

    def fetch(url):
        attempts.append(url)
        return err
    c = S.Krdict(key="k" * 32, cache_dir=tmp_path, fetch=fetch, pause=0, retry_wait=0)
    with pytest.raises(S.KrdictError):
        c.get("search", q="메뉴")
    assert len(attempts) == 1


def test_cache_is_used_and_never_holds_the_key(tmp_path):
    secret = "0123456789abcdef0123456789abcdef"
    calls = []

    def fetch(url):
        calls.append(url)
        return SEARCH_XML + f"<!-- {secret} -->"  # pretend the server echoed the key back
    c = S.Krdict(key=secret, cache_dir=tmp_path, fetch=fetch, pause=0)
    a = c.get("search", q="메뉴")
    b = c.get("search", q="메뉴")
    assert a == b and len(calls) == 1
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert secret not in f.read_text(encoding="utf-8")


def test_missing_key_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("KRDICT_API_KEY", raising=False)
    monkeypatch.setattr(S, "load_env", lambda: None)
    with pytest.raises(S.KrdictError, match="KRDICT_API_KEY"):
        S.Krdict(cache_dir=tmp_path)


def test_krdict_candidates_carry_source_and_license():
    view = S.parse_view(VIEW_XML)
    rows = S.krdict_rows(view)
    assert [r["text"] for r in rows] == ["아줌마, 여기 메뉴 좀 주세요.", "여기 있습니다."]
    r = rows[0]
    assert r["source"] == "krdict" and r["license"] == "CC BY-SA 2.0 KR"
    assert r["source_id"] == "11111#0" and "11111" in r["source_url"]
    assert "국립국어원" in r["credit"] and r["context"] == "메뉴"


def test_collect_krdict_sends_food_topic_and_bar_seeds_to_bar_restaurant(tmp_path):
    fetch = lambda url: SEARCH_XML if "/search?" in url else VIEW_XML   # noqa: E731
    c = S.Krdict(key="k" * 32, cache_dir=tmp_path, fetch=fetch, pause=0)
    out = S.collect_krdict(c, ["메"])
    assert set(out) == set(S.PACKS)
    assert {r["text"] for r in out["bar_restaurant"]} == {"아줌마, 여기 메뉴 좀 주세요.", "여기 있습니다."}
    assert all(not rows for pack, rows in out.items() if pack != "bar_restaurant")


# ---------- Chatbot_data and KLUE WoS ----------

CHATBOT_CSV = "Q,A,label\n오늘 한잔 할까,좋아요.,0\n이별했어,힘내세요.,1\n수건 썩었어,식초 넣고 빨래해보세요.,0\n"


def test_chatbot_rows_daily_life_questions_and_answers():
    rows = S.chatbot_rows(io.StringIO(CHATBOT_CSV))
    assert [r["text"] for r in rows] == ["오늘 한잔 할까", "좋아요.", "수건 썩었어", "식초 넣고 빨래해보세요."]
    assert [r["context"] for r in rows] == ["Q", "A", "Q", "A"]
    assert rows[0]["license"] == "MIT" and rows[0]["source_id"] == "row1.Q" and rows[3]["source_id"] == "row3.A"


def test_wos_rows_restaurant_only_dialogues_split_into_sentences():
    dialogues = [
        {"guid": "wos-v1_dev_1", "domains": ["식당"], "dialogue": [
            {"role": "user", "text": "가격은 상관없어요. 야외석이 있으면 좋겠네요.", "state": []},
            {"role": "sys", "text": "원하시는 가격대가 있으실까요?", "state": []}]},
        {"guid": "wos-v1_dev_2", "domains": ["숙소"], "dialogue": [
            {"role": "user", "text": "방 있어요?", "state": []}]},
    ]
    rows = S.wos_rows(dialogues)
    assert [r["text"] for r in rows] == ["가격은 상관없어요.", "야외석이 있으면 좋겠네요.", "원하시는 가격대가 있으실까요?"]
    assert rows[0]["source_id"] == "wos-v1_dev_1#0.0" and rows[0]["license"] == "CC BY-SA 4.0"
    assert rows[2]["context"] == "sys"


# ---------- Tatoeba ----------

TATOEBA_TSV = ("5350\tkor\t뭔가 해 보자!\tnative_a\t\\N\t2014\n"
               "5351\tkor\t톰은 집에 갔어.\tnative_a\t\\N\t2014\n"       # translated Tom line: skipped
               "5352\tkor\t어디 가요?\tlearner_b\t\\N\t2014\n"          # author not native: skipped
               "5353\tkor\t배고파 죽겠어.\tnative_c\t\\N\t2014\n")
USERS_TSV = "kor\t5\tnative_a\t\nkor\t2\tlearner_b\t\nkor\t5\tnative_c\t\neng\t5\tlearner_b\t\n"


def test_tatoeba_rows_native_authors_only_no_tom():
    rows = S.tatoeba_rows(io.StringIO(TATOEBA_TSV), io.StringIO(USERS_TSV))
    assert [r["text"] for r in rows] == ["뭔가 해 보자!", "배고파 죽겠어."]
    r = rows[0]
    assert r["source"] == "tatoeba" and r["source_id"] == "5350" and r["license"] == "CC BY 2.0 FR"
    assert r["source_url"] == "https://tatoeba.org/en/sentences/show/5350" and "native_a" in r["credit"]


# ---------- topic words -> packs ----------

@pytest.mark.parametrize("text,packs", [
    ("내일 시험 있어.", {"school"}),
    ("대학생이라 바빠요.", {"school"}),
    ("회사 가기 싫어.", {"office"}),
    ("팀장님께 보고서 드렸어요.", {"office"}),
    ("오늘 한잔 할까?", {"bar_restaurant"}),
    ("여기 메뉴 좀 주세요.", {"bar_restaurant"}),
    ("기술 배우고 싶어.", set()),                 # 기술 is not 술 (drink)
    ("안녕하세요, 반가워요.", {"basics"}),
    ("도와줘서 고마워.", {"basics"}),
    ("오늘 너무 피곤해.", set()),
    ("회식 때 술 마셨어.", {"office", "bar_restaurant"}),
])
def test_topic_packs(text, packs):
    assert S.topic_packs(text) == packs


# ---------- pool per pack ----------

def _row(text, source="chatbot", sid="1"):
    return {"text": text, "source": source, "source_id": sid, "source_url": "u", "license": "L",
            "credit": "c", "context": "x"}


def test_pool_keeps_both_speech_levels_cleans_and_dedupes():
    # The 존댓말/반말 switch filters every pack, so every pack keeps BOTH levels.
    rows = [_row("오늘 한잔 할까?"), _row("오늘 한잔 할까?", sid="2"), _row("여기 메뉴 좀 주세요."),
            _row("서울에는 사람이 정말 많다."), _row("네."), _row("나 너무 무서워.")]
    for pack in S.PACKS:
        kept = S.pool(rows, pack)
        assert [r["text"] for r in kept] == ["오늘 한잔 할까?", "여기 메뉴 좀 주세요.", "나 너무 무서워."], pack
        assert all(r["syllables"] >= 4 for r in kept)                        # 네. is too short; 많다. is written


def test_pool_labels_banmal_and_jondaetmal():
    rows = [_row("오늘 한잔 할까?"), _row("여기 메뉴 좀 주세요."), _row("맛있게 드십시오.")]
    assert [r["speech"] for r in S.pool(rows, "bar_restaurant")] == ["반말", "존댓말", "존댓말"]


def test_dedupe_ignores_spacing_and_punctuation():
    rows = [_row("오늘 한잔 할까?"), _row("오늘 한잔할까", sid="2")]
    assert len(S.pool(rows, "casual")) == 1


def test_route_sends_rows_to_packs():
    chat = [_row("내일 시험 있어."), _row("오늘 너무 피곤해."), _row("회사 가기 싫어.")]
    wos = [_row("가격은 상관없어요.", source="klue_wos")]
    tat = [_row("안녕하세요, 반가워요.", source="tatoeba")]
    kr = {p: [] for p in S.PACKS}
    kr["office"] = [_row("손님, 회의실은 이쪽입니다.", source="krdict")]
    raw = S.route(chat, wos, tat, kr)
    assert set(raw) == set(S.PACKS)
    texts = {p: [r["text"] for r in rows] for p, rows in raw.items()}
    assert texts["school"] == ["내일 시험 있어."]
    assert texts["office"] == ["손님, 회의실은 이쪽입니다.", "회사 가기 싫어."]   # krdict first
    assert texts["basics"] == ["안녕하세요, 반가워요."]
    assert texts["bar_restaurant"] == ["가격은 상관없어요."]          # every WoS line is restaurant talk
    assert "오늘 너무 피곤해." in texts["casual"] and "가격은 상관없어요." not in texts["casual"]


def test_every_pack_is_defined():
    assert set(S.PACKS) == {"basics", "school", "office", "casual", "bar_restaurant"}
    for name, p in S.PACKS.items():
        assert p["styles"] and p["styles"] <= {"formal", "polite", "casual"}
    assert all(p["styles"] == {"formal", "polite", "casual"} for p in S.PACKS.values())   # both levels


def test_every_dictionary_topic_has_a_code_and_a_pack():
    used = [t for p in S.PACKS.values() for t in p["topics"]]
    assert sorted(used) == sorted(S.TOPIC_CODES) and len(used) == len(set(used))
    assert S.PACKS["bar_restaurant"]["seeds"] and "음식 주문하기" in S.PACKS["bar_restaurant"]["topics"]
