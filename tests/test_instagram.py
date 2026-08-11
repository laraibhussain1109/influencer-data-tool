from openpyxl import Workbook, load_workbook
import pytest

from influencer_service.deliverables import collect_workbook, write_results
from influencer_service.instagram import analyze_comments, collect_deliverable, shortcode_from_url


class FakeClient:
    def fetch(self, shortcode):
        assert shortcode == "ABC_123-x"
        return {
            "likes": 120,
            "views": 900,
            "comments_count": 4,
            "comments": ["Amazing work!", "This is awful", "information"],
        }


def make_input(path, url="https://www.instagram.com/reel/ABC_123-x/"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Influencer Name", "Deliverable URL"])
    sheet.append(["Ada", url])
    workbook.save(path)


def test_shortcode_validation():
    assert shortcode_from_url("https://www.instagram.com/reel/ABC_123-x/?utm=x") == "ABC_123-x"
    with pytest.raises(ValueError):
        shortcode_from_url("https://example.com/reel/ABC/")
    with pytest.raises(ValueError):
        shortcode_from_url("https://www.instagram.com/profile/")


def test_sentiment_summary_ignores_blank_comments():
    summary = analyze_comments(["I love it", "terrible", "plain words", " "])
    assert summary.total_analyzed == 3
    assert summary.positive == 1
    assert summary.negative == 1
    assert summary.neutral == 1


def test_collect_one_deliverable():
    result = collect_deliverable("https://instagram.com/p/ABC_123-x/", FakeClient())
    assert result["likes"] == 120
    assert result["views"] == 900
    assert result["comments"] == 4
    assert result["comments_collected"] == 3


def test_workbook_batch_and_output(tmp_path):
    source = tmp_path / "input.xlsx"
    output = tmp_path / "output.xlsx"
    make_input(source)

    results = collect_workbook(source, FakeClient())
    write_results(output, results)

    assert results[0]["status"] == "ok"
    sheet = load_workbook(output).active
    assert sheet["A2"].value == "Ada"
    assert sheet["D2"].value == 120
    assert sheet["H2"].value == 1


def test_batch_records_bad_url_instead_of_aborting(tmp_path):
    source = tmp_path / "input.xlsx"
    make_input(source, "not-a-url")
    results = collect_workbook(source, FakeClient())
    assert results[0]["status"] == "error"
    assert "Instagram" in results[0]["error"]
