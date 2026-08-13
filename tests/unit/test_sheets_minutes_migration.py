import pytest

from meeting_intelligence.domain.errors import GoogleSheetsSchemaError
from meeting_intelligence.sheets.google import GoogleSheetsConfig, GoogleSheetsMeetingSink
from meeting_intelligence.sheets.projection import HEADERS


class Request:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class Values:
    def __init__(self, api): self.api = api
    def get(self, **kwargs): return Request({"values": [list(row) for row in self.api.rows]})


class Spreadsheets:
    def __init__(self, rows): self.rows = rows; self.bodies = []; self.values_api = Values(self)
    def get(self, **kwargs): return Request({"sheets": [{"properties": {"title": "Meetings", "sheetId": 7}}]})
    def values(self): return self.values_api
    def batchUpdate(self, **kwargs):
        self.bodies.append(kwargs["body"])
        for request in kwargs["body"]["requests"]:
            update = request["updateCells"]
            row = update["range"]["startRowIndex"]
            column = update["range"]["startColumnIndex"]
            self.rows[row][column] = update["rows"][0]["values"][0]["userEnteredValue"]["stringValue"]
        return Request({})


class Service:
    def __init__(self, rows): self.api = Spreadsheets(rows)
    def spreadsheets(self): return self.api


def legacy_rows():
    header = list(HEADERS["Meetings"])
    header[7] = "MTG全体の議事録"
    return [header, ["other", *[""] * 6, "other full minutes", *[""] * 6], ["m1", *[""] * 6, "old full minutes", *[""] * 6]]


def test_migration_renames_header_and_updates_only_exact_existing_row():
    rows = legacy_rows()
    untouched = list(rows[1])
    service = Service(rows)
    GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service).migrate_minutes_reference("m1", "C:/output/m1/meeting-minutes.md")
    assert rows[0][7] == "議事録"
    assert rows[2][7] == "C:/output/m1/meeting-minutes.md"
    assert rows[1] == untouched
    assert len(service.api.bodies) == 1
    assert len(service.api.bodies[0]["requests"]) == 2
    assert all("appendCells" not in request for request in service.api.bodies[0]["requests"])


@pytest.mark.parametrize("meeting_ids", [[], ["m1", "m1"]])
def test_migration_requires_exactly_one_row_and_performs_no_write(meeting_ids):
    rows = legacy_rows()[:1] + [[meeting_id, *[""] * 13] for meeting_id in meeting_ids]
    service = Service(rows)
    with pytest.raises(GoogleSheetsSchemaError):
        GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service).migrate_minutes_reference("m1", "minutes.md")
    assert service.api.bodies == []
