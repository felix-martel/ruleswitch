import yamlrocks
from ruleswitch_editor import edit

LEXICON = """# Words, by theme.
reminds: SENSITIVE_FIGURE

entries:
  # --- Politicians
  - word: "macron"
    meaning: "Emmanuel Macron"  # living
  - word: "mao"
    meaning: "Mao Zedong"
tags: [a, b]
"""


def test_edit_keeps_comments_and_untouched_lines():
    entries = [{"word": "macron", "meaning": "Emmanuel Macron, politician"}, {"word": "zola", "meaning": "Émile"}]
    text = edit(LEXICON, ["entries"], entries)
    assert yamlrocks.loads(text)["entries"] == entries
    kept = ["# Words, by theme.", "reminds: SENSITIVE_FIGURE", "", "  # --- Politicians", '  - word: "macron"']
    assert all(line in text.splitlines() for line in kept)
    assert "# living" in text

    appended = edit(LEXICON, ["entries"], [*yamlrocks.loads(LEXICON)["entries"], {"word": "x", "meaning": "y"}])
    assert appended.startswith(LEXICON.split("tags:")[0])
    assert edit(LEXICON, ["tags"], ["a", "b", "c"]).endswith('tags: ["a", "b", "c"]\n')
    assert '"mao"' not in edit(LEXICON, ["entries", 1], None)
