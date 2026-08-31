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

        output_dir = tmp_path / "output_test"
        summary = categorize_results(
            csv_path=mock_csv,
            output_dir=output_dir,
            base_filename="mock_test",
        )

        assert summary.good_count == 2
        assert summary.bad_count == 2
        assert summary.risky_count == 2
        assert summary.good_file.exists()
        assert summary.bad_file.exists()
        assert summary.risky_file.exists()
        assert " - good - 2 good.csv" in summary.good_file.name
        assert " - bad.csv" in summary.bad_file.name
        assert " - risky.csv" in summary.risky_file.name

        assert "good1@example.com" in summary.good_file.read_text(encoding="utf-8")
        assert "bad1@example.com" in summary.bad_file.read_text(encoding="utf-8")
        assert "risky1@example.com" in summary.risky_file.read_text(encoding="utf-8")

        print("test_categorize_results passed.")


def test_prepare_csv_preserves_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        input_csv = tmp_path / "input_with_columns.csv"
        content = (
            "First Name,Last Name,Email Address,Company,Phone\n"
            "Alice,Smith,alice@example.com,Acme Corp,1234567890\n"
            "Bob,Jones,bob@example.com,Globex,0987654321\n"
            "Charlie,Brown,charlie@example.com,Initech,1122334455\n"
            "Duplicate,User,alice@example.com,Acme Duplicate,9999999999\n"
        )
        input_csv.write_text(content, encoding="utf-8")

        result = prepare_csv(input_file=input_csv, output_directory=tmp_path / "prepared")
        assert result.unique_emails == 3
        assert result.duplicate_emails == 1
        assert result.output_file.exists()

        prepared_content = result.output_file.read_text(encoding="utf-8")
        assert "First Name,Last Name,Email Address,Company,Phone" in prepared_content
        assert "Alice,Smith,alice@example.com,Acme Corp,1234567890" in prepared_content
        assert "Bob,Jones,bob@example.com,Globex,0987654321" in prepared_content
        assert "Charlie,Brown,charlie@example.com,Initech,1122334455" in prepared_content
        print("test_prepare_csv_preserves_columns passed.")


def test_categorize_results_preserves_all_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        mock_csv = tmp_path / "mock_results.csv"

        content = (
            "First Name,Last Name,Email,Company,quality,result,subresult\n"
            "John,Doe,good1@example.com,Acme,good,ok,ok\n"
            "Jane,Smith,bad1@example.com,Beta,bad,invalid,mailbox_not_found\n"
            "Jim,Beam,risky1@example.com,Gamma,risky,catch_all,catch_all\n"
        )
        mock_csv.write_text(content, encoding="utf-8")

        output_dir = tmp_path / "output_test"
        summary = categorize_results(
            csv_path=mock_csv,
            output_dir=output_dir,
            base_filename="mock_test",
        )

        good_text = summary.good_file.read_text(encoding="utf-8")
        assert "First Name,Last Name,Email,Company,quality,result,subresult" in good_text
        assert "John,Doe,good1@example.com,Acme,good,ok,ok" in good_text
        assert summary.good_file.parent.name == "good"

        bad_text = summary.bad_file.read_text(encoding="utf-8")
        assert "Jane,Smith,bad1@example.com,Beta,bad,invalid,mailbox_not_found" in bad_text
        assert summary.bad_file.parent.name == "bad"

        risky_text = summary.risky_file.read_text(encoding="utf-8")
        assert "Jim,Beam,risky1@example.com,Gamma,risky,catch_all,catch_all" in risky_text
        assert summary.risky_file.parent.name == "risky"

        print("test_categorize_results_preserves_all_columns passed.")


def test_restore_columns():
    from restore_columns import merge_and_categorize

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        orig_csv = tmp_path / "sample_input.csv"
        ver_csv = tmp_path / "verified_sample_input.csv"

        orig_csv.write_text(
            "First Name,Last Name,Email Address,Company,City\n"
            "John,Doe,john@example.com,Acme,New York\n"
            "Jane,Smith,jane@example.com,Beta,London\n"
            "Bob,Lee,bob@example.com,Gamma,Tokyo\n",
            encoding="utf-8",
        )

        ver_csv.write_text(
            "email,quality,result,free,role\n"
            "john@example.com,good,ok,no,no\n"
            "jane@example.com,bad,invalid,no,no\n"
            "bob@example.com,risky,catch_all,no,no\n",
            encoding="utf-8",
        )

        output_dir = tmp_path / "output"
        counts = merge_and_categorize(
            original_csv=orig_csv,
            verified_csv=ver_csv,
            output_dir=output_dir,
        )

        assert counts["good"] == 1
        assert counts["bad"] == 1
        assert counts["risky"] == 1

        good_file = output_dir / "good" / "sample_input - good - 1 good - 3 total.csv"
        assert good_file.exists()
        content = good_file.read_text(encoding="utf-8")
        assert "First Name,Last Name,Email Address,Company,City,quality,result,free,role" in content
        assert "John,Doe,john@example.com,Acme,New York,good,ok,no,no" in content

        bad_file = output_dir / "bad" / "sample_input - bad.csv"
        assert bad_file.exists()

        risky_file = output_dir / "risky" / "sample_input - risky.csv"
        assert risky_file.exists()

        print("test_restore_columns passed.")


if __name__ == "__main__":
    test_classification()
    test_categorize_results()
    test_prepare_csv_preserves_columns()
    test_categorize_results_preserves_all_columns()
    test_restore_columns()
    print("All unit tests passed successfully!")
