import pytest


@pytest.fixture
def _ensure_spacy():
    """Skip English-lemmatization assertions if the spaCy model is not available."""
    try:
        import spacy
        spacy.load("en_core_web_sm")
    except Exception:
        pytest.skip("spaCy en_core_web_sm model not available")


class TestLemmatizeForBm25Cjk:
    def test_chinese_text_space_separated_tokens(self):
        from mem0.utils.lemmatization import lemmatize_for_bm25

        result = lemmatize_for_bm25("这条记忆很重要")
        tokens = result.split()
        assert "记忆" in tokens
        assert "重要" in tokens
        assert len(tokens) > 1

    def test_chinese_query_word_is_tokenized(self):
        from mem0.utils.lemmatization import lemmatize_for_bm25

        result = lemmatize_for_bm25("搜索记忆")
        assert "记忆" in result.split()

    def test_mixed_chinese_english(self):
        from mem0.utils.lemmatization import lemmatize_for_bm25

        result = lemmatize_for_bm25("我使用Python写代码")
        tokens = result.split()
        assert "代码" in tokens
        assert "Python" in tokens

    @pytest.mark.usefixtures("_ensure_spacy")
    def test_pure_english_unchanged(self):
        from mem0.utils.lemmatization import lemmatize_for_bm25

        result = lemmatize_for_bm25("memories")
        assert "memory" in result.split()

    @pytest.mark.usefixtures("_ensure_spacy")
    def test_english_verb_forms_regression(self):
        from mem0.utils.lemmatization import lemmatize_for_bm25

        result = lemmatize_for_bm25("attend attending attended")
        assert "attend" in result.split()
