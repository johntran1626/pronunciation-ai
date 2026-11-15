"""The learning-English packs: original sentences plus Korean translations, LLM-written (Claude) and human-reviewed.

Each sentence is short, spoken, everyday English, written to contain the sounds Korean speakers find hard
(R, L, F, V, TH, ship/sheep). The tags are NOT typed by hand: build() runs our own G2P on each sentence and
tags whichever target sounds really appear, so a tag can never claim a sound the sentence doesn't have.

Every line has two Korean translations: `translation` = 존댓말 (해요, or 합니다 where that's
what people say) and `translation_informal` = 반말. A few lines are normally said to staff ("A table for two,
please."), so their 반말 form is what you'd say only to a friend.

Run `python -m content.en_packs` after editing a sentence; it rewrites content/packs/en_<pack>.json.
"""
import json
from pathlib import Path

from content.build_dev_pack import english_tags, flat_phonemes

OUT = Path(__file__).resolve().parent / "packs"

SOURCE = ("Written for this project with an LLM (Claude, Anthropic); English reviewed by the author. "
          "Korean translations (존댓말 + 반말) also LLM-written.")
LICENSE = "This project's own content"

NAMES = {"basics": "Basics", "casual": "Casual"}

# pack -> [(English sentence, Korean 존댓말 (polite), Korean 반말 (casual))]. Every line gets both.
SENTENCES = {
    "basics": [
        ("Thank you very much.", "정말 감사합니다.", "정말 고마워."),
        ("Nice to meet you.", "만나서 반가워요.", "만나서 반가워."),
        ("Where is the restroom?", "화장실이 어디예요?", "화장실 어디야?"),
        ("I'm sorry, I'm late.", "늦어서 죄송해요.", "늦어서 미안해."),
        ("Please speak more slowly.", "좀 더 천천히 말씀해 주세요.", "좀 더 천천히 말해 줘."),
        ("I live in a big city.", "저는 큰 도시에 살아요.", "나는 큰 도시에 살아."),
        ("Have a good weekend.", "주말 잘 보내세요.", "주말 잘 보내."),
        ("I feel fine, thanks.", "괜찮아요, 고마워요.", "괜찮아, 고마워."),
        ("This is my friend.", "이쪽은 제 친구예요.", "얘는 내 친구야."),
        ("Can you help me, please?", "좀 도와주시겠어요?", "좀 도와줄래?"),
    ],
    "casual": [
        ("What are you doing this weekend?", "이번 주말에 뭐 해요?", "이번 주말에 뭐 해?"),
        ("That movie was really funny.", "그 영화 정말 웃겼어요.", "그 영화 진짜 웃겼어."),
        ("Let's grab some coffee.", "커피 한잔해요.", "커피 한잔하자."),
        ("I'm so tired right now.", "저 지금 너무 피곤해요.", "나 지금 너무 피곤해."),
        ("Did you sleep well last night?", "어젯밤에 잘 주무셨어요?", "어젯밤에 잘 잤어?"),
        ("Call me when you're free.", "시간 될 때 전화 주세요.", "시간 될 때 전화해."),
        ("I really love this song.", "저 이 노래 정말 좋아요.", "나 이 노래 진짜 좋아."),
        ("Let's take the bus there.", "거기 버스 타고 가요.", "거기 버스 타고 가자."),
        ("Your new phone looks great.", "새 폰 멋지네요.", "새 폰 멋지네."),
        ("Think about it and tell me.", "생각해 보고 말해 주세요.", "생각해 보고 말해 줘."),
    ],
}


def build():
    """pack name -> pack dict, in the same shape as the dev packs. Writes nothing."""
    packs = {}
    for name, rows in SENTENCES.items():
        items = [{"id": f"en_{name}_{i:02d}", "text": text, "translation": polite,
                  "translation_informal": casual, "tags": english_tags(flat_phonemes(text, "en"))}
                 for i, (text, polite, casual) in enumerate(rows, 1)]
        packs[name] = {"id": "en-" + name.replace("_", "-"), "lang": "en", "name": NAMES[name],
                       "dev_only": False, "reviewed": True, "source": SOURCE, "license": LICENSE,
                       "items": items}
    return packs


def main():
    for name, pack in build().items():
        path = OUT / f"en_{name}.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tags = sorted({t for it in pack["items"] for t in it["tags"]})
        print(f"{path.name}: {len(pack['items'])} sentences, targets {', '.join(tags)}")


if __name__ == "__main__":
    main()
