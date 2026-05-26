from __future__ import annotations

from src.search import run_search


class TestRunSearchCLI:
    def test_no_model_id_prints_info(self, capsys):
        run_search(query="test", model_id=None)
        captured = capsys.readouterr()
        assert "No model_id specified" in captured.out

    def test_no_query_prints_info(self, capsys):
        run_search(query=None, model_id=1)
        captured = capsys.readouterr()
        assert "No query provided" in captured.out

    def test_empty_query_prints_info(self, capsys):
        run_search(query="", model_id=1)
        captured = capsys.readouterr()
        assert "No query provided" in captured.out

    def test_with_query_and_model_id_prints_instructions(self, capsys):
        run_search(query="kick", model_id=1, topk=5)
        captured = capsys.readouterr()
        assert "Semantic search requires a real embedding backend" in captured.out
        assert "model_id=1" in captured.out
        assert "topk=5" in captured.out
