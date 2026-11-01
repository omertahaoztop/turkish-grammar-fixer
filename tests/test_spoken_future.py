import pytest

from tdk.engines import RuleEngine

rules = RuleEngine()


@pytest.mark.parametrize("wrong, right", [
    ("gelicem", "geleceğim"),
    ("gelecem", "geleceğim"),
    ("gidicem", "gideceğim"),
    ("yapıcam", "yapacağım"),
    ("yapicam", "yapacağım"),
    ("yiyecem", "yiyeceğim"),
    ("gelemiyecem", "gelemeyeceğim"),
    ("gelemeyicem", "gelemeyeceğim"),
    ("gelmiyecem", "gelmeyeceğim"),
    ("yapamıyacam", "yapamayacağım"),
    ("Gelicem", "Geleceğim"),
])
def test_fixes_spoken_future(wrong, right):
    assert [(e.original, e.replacement) for e in rules._spoken_future(f"Yarın {wrong}.")] == [(wrong, right)]


@pytest.mark.parametrize("word", ["gecem", "hecem", "bacam", "hocam", "Ecem", "düşüncem", "geleceğim"])
def test_leaves_real_words(word):
    assert rules._spoken_future(f"Bu {word} işte.") == []
