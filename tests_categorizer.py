from pathlib import Path
import shutil
import tempfile

from app.services.categorizer import categorize_results, classify_row
from app.services.input_processor import prepare_csv


def test_classification():
    assert classify_row({"quality": "good", "result": "ok"}) == "good"
    assert classify_row({"quality": "bad", "result": "invalid"}) == "bad"
    assert classify_row({"quality": "risky", "result": "catch_all"}) == "risky"
    assert classify_row({"result": "disposable"}) == "bad"
    assert classify_row({"result": "unknown"}) == "risky"
    print("test_classification passed.")


def test_categorize_results():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        mock_csv = tmp_path / "mock_results.csv"

        content = (
            "email,quality,result,subresult\n"
            "good1@example.com,good,ok,ok\n"
            "good2@example.com,good,ok,ok\n"
            "bad1@example.com,bad,invalid,mailbox_not_found\n"
            "bad2@example.com,bad,disposable,disposable\n"
            "risky1@example.com,risky,catch_all,catch_all\n"
            "risky2@example.com,risky,unknown,greylist\n"
        )
        mock_csv.write_text(content, encoding="utf-8")

        output_subfolder = tmp_path / "output_test"
        summary = categorize_results(
            csv_path=mock_csv,
            output_subfolder=output_subfolder,
            base_filename="mock_test",
        )

        assert summary.good_count == 2
        assert summary.bad_count == 2
        assert summary.risky_count == 2
        assert summary.good_file.exists()
        assert summary.bad_file.exists()
        assert summary.risky_file.exists()

        assert "good1@example.com" in summary.good_file.read_text(encoding="utf-8")
        assert "bad1@example.com" in summary.bad_file.read_text(encoding="utf-8")
        assert "risky1@example.com" in summary.risky_file.read_text(encoding="utf-8")

        print("test_categorize_results passed.")


if __name__ == "__main__":
    test_classification()
    test_categorize_results()
    print("All unit tests passed successfully!")
