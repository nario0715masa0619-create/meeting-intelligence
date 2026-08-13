"""Google Sheets adapter using service-account credentials and atomic writes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.errors import DuplicateMeetingError, GoogleSheetsAuthenticationError, GoogleSheetsPermissionError, GoogleSheetsSchemaError, GoogleSheetsWriteError
from meeting_intelligence.sheets.projection import HEADERS, SheetsMeetingContext, project_analysis


@dataclass(frozen=True)
class GoogleSheetsConfig:
    spreadsheet_id: str
    service_account_file: Path | None = None
    meetings_sheet: str = "Meetings"
    decisions_sheet: str = "Decisions"
    action_items_sheet: str = "Action Items"
    open_items_sheet: str = "Open Items"

    @property
    def names(self):
        return {"Meetings": self.meetings_sheet, "Decisions": self.decisions_sheet, "Action Items": self.action_items_sheet, "Open Items": self.open_items_sheet}


def build_google_sheets_service(service_account_file: Path) -> Any:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        credentials = Credentials.from_service_account_file(str(service_account_file), scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        raise GoogleSheetsAuthenticationError("Google Sheets credentials could not be loaded") from exc


class GoogleSheetsMeetingSink:
    def __init__(self, config: GoogleSheetsConfig, service: Any = None):
        if not config.spreadsheet_id:
            raise GoogleSheetsSchemaError("Google Sheets spreadsheet ID is not configured")
        if service is None and (config.service_account_file is None or not config.service_account_file.is_file()):
            raise GoogleSheetsAuthenticationError("Google service-account file is not configured")
        self.config = config
        self.service = service or build_google_sheets_service(config.service_account_file)

    @staticmethod
    def _cell(value: str) -> dict:
        return {"userEnteredValue": {"stringValue": value}}

    def _execute(self, request):
        try:
            return request.execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 401:
                raise GoogleSheetsAuthenticationError("Google Sheets authentication failed") from exc
            if status == 403:
                raise GoogleSheetsPermissionError("Google Sheets permission denied") from exc
            raise GoogleSheetsWriteError("Google Sheets request failed") from exc

    def _metadata(self):
        return self._execute(self.service.spreadsheets().get(spreadsheetId=self.config.spreadsheet_id, includeGridData=False))

    def _duplicate(self, meeting_id: str, titles: set[str]) -> bool:
        if self.config.meetings_sheet not in titles:
            return False
        result = self._execute(self.service.spreadsheets().values().get(spreadsheetId=self.config.spreadsheet_id, range=f"'{self.config.meetings_sheet}'!A:A"))
        return any(row and row[0] == meeting_id for row in result.get("values", [])[1:])

    def contains(self, meeting_id: str) -> bool:
        """Read-only existence check used by unattended state classification."""
        metadata = self._metadata()
        titles = {sheet["properties"]["title"] for sheet in metadata.get("sheets", [])}
        return self._duplicate(meeting_id, titles)

    def initialize_schema(self) -> tuple[dict[str, int], dict[str, list[str]]]:
        metadata = self._metadata()
        sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in metadata.get("sheets", [])}
        missing = [name for name in self.config.names.values() if name not in sheets]
        inspected: dict[str, list[list[str]]] = {}
        for canonical, actual in self.config.names.items():
            if actual not in sheets:
                inspected[actual] = []
                continue
            current = self._execute(self.service.spreadsheets().values().get(spreadsheetId=self.config.spreadsheet_id, range=f"'{actual}'!A:ZZ")).get("values", [])
            existing = list(current[0]) if current else []
            if len(existing) != len(set(existing)):
                raise GoogleSheetsSchemaError(f"Google Sheet '{actual}' has duplicate headers")
            if any(any(str(value) for value in row) for row in current[1:]) and existing != HEADERS[canonical]:
                raise GoogleSheetsSchemaError(f"Google Sheet '{actual}' has data and cannot be migrated destructively")
            inspected[actual] = current
        if missing:
            requests = [{"addSheet": {"properties": {"title": name}}} for name in missing]
            self._execute(self.service.spreadsheets().batchUpdate(spreadsheetId=self.config.spreadsheet_id, body={"requests": requests}))
            metadata = self._metadata()
            sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in metadata.get("sheets", [])}
        header_requests = []
        columns = {}
        for canonical, actual in self.config.names.items():
            current = inspected[actual]
            required = HEADERS[canonical]
            existing = list(current[0]) if current else []
            columns[actual] = required
            if existing != required:
                width = max(len(existing), len(required))
                values = [self._cell(value) for value in required] + [{} for _ in range(width - len(required))]
                header_requests.append({"updateCells": {"range": {"sheetId": sheets[actual], "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": width}, "rows": [{"values": values}], "fields": "userEnteredValue"}})
        if header_requests:
            self._execute(self.service.spreadsheets().batchUpdate(spreadsheetId=self.config.spreadsheet_id, body={"requests": header_requests}))
        for canonical, actual in self.config.names.items():
            read_back = self._execute(self.service.spreadsheets().values().get(spreadsheetId=self.config.spreadsheet_id, range=f"'{actual}'!1:1")).get("values", [])
            if not read_back or list(read_back[0]) != HEADERS[canonical]:
                raise GoogleSheetsSchemaError(f"Google Sheet '{actual}' header read-back verification failed")
        return sheets, columns

    def write(self, analysis: MeetingAnalysis, context: SheetsMeetingContext | None = None) -> None:
        metadata = self._metadata()
        titles = {s["properties"]["title"] for s in metadata.get("sheets", [])}
        if self._duplicate(analysis.meeting_id, titles):
            raise DuplicateMeetingError("Meeting has already been projected")
        sheet_ids, columns = self.initialize_schema()
        if self._duplicate(analysis.meeting_id, set(sheet_ids)):
            raise DuplicateMeetingError("Meeting has already been projected")
        projection = project_analysis(analysis, self.config.names, context)
        order = [self.config.decisions_sheet, self.config.action_items_sheet, self.config.open_items_sheet, self.config.meetings_sheet]
        requests = []
        for name in order:
            rows = projection.rows[name]
            if rows:
                canonical = next(key for key, value in self.config.names.items() if value == name)
                required = HEADERS[canonical]
                mapped_rows = [[dict(zip(required, row, strict=True)).get(header, "") for header in columns[name]] for row in rows]
                requests.append({"appendCells": {"sheetId": sheet_ids[name], "rows": [{"values": [self._cell(v) for v in row]} for row in mapped_rows], "fields": "userEnteredValue"}})
        if requests:
            self._execute(self.service.spreadsheets().batchUpdate(spreadsheetId=self.config.spreadsheet_id, body={"requests": requests}))

    def migrate_minutes_reference(self, meeting_id: str, minutes_reference: str) -> None:
        """Rename the one legacy header and update exactly one existing meeting row."""
        if not meeting_id or not minutes_reference:
            raise GoogleSheetsSchemaError("meeting_id and minutes_reference are required for migration")
        metadata = self._metadata()
        sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in metadata.get("sheets", [])}
        title = self.config.meetings_sheet
        if title not in sheets:
            raise GoogleSheetsSchemaError("Meetings sheet does not exist")
        values = self._execute(
            self.service.spreadsheets().values().get(
                spreadsheetId=self.config.spreadsheet_id,
                range=f"'{title}'!A:ZZ",
            )
        ).get("values", [])
        if not values:
            raise GoogleSheetsSchemaError("Meetings sheet is empty")
        header = list(values[0])
        if len(header) != len(set(header)):
            raise GoogleSheetsSchemaError("Meetings sheet has duplicate headers")
        try:
            meeting_column = header.index("ミーティングID")
        except ValueError as exc:
            raise GoogleSheetsSchemaError("Meetings sheet has no meeting ID column") from exc
        legacy = "MTG全体の議事録"
        current = "議事録"
        if legacy in header and current in header:
            raise GoogleSheetsSchemaError("Meetings sheet has ambiguous minutes headers")
        try:
            minutes_column = header.index(current if current in header else legacy)
        except ValueError as exc:
            raise GoogleSheetsSchemaError("Meetings sheet has no supported minutes column") from exc
        matching_rows = [index for index, row in enumerate(values[1:], start=1) if len(row) > meeting_column and row[meeting_column] == meeting_id]
        if len(matching_rows) != 1:
            raise GoogleSheetsSchemaError("migration requires exactly one matching meeting row")
        row_index = matching_rows[0]
        requests = []
        if header[minutes_column] == legacy:
            requests.append(self._single_cell_request(sheets[title], 0, minutes_column, current))
        requests.append(self._single_cell_request(sheets[title], row_index, minutes_column, minutes_reference))
        self._execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.config.spreadsheet_id,
                body={"requests": requests},
            )
        )
        read_back = self._execute(
            self.service.spreadsheets().values().get(
                spreadsheetId=self.config.spreadsheet_id,
                range=f"'{title}'!A:ZZ",
            )
        ).get("values", [])
        if len(read_back) <= row_index:
            raise GoogleSheetsSchemaError("minutes migration read-back verification failed")
        verified_header = list(read_back[0])
        verified_row = list(read_back[row_index])
        if (
            len(verified_header) <= minutes_column
            or verified_header[minutes_column] != current
            or len(verified_row) <= minutes_column
            or verified_row[minutes_column] != minutes_reference
        ):
            raise GoogleSheetsSchemaError("minutes migration read-back verification failed")

    @classmethod
    def _single_cell_request(cls, sheet_id: int, row_index: int, column_index: int, value: str) -> dict:
        return {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_index,
                    "endRowIndex": row_index + 1,
                    "startColumnIndex": column_index,
                    "endColumnIndex": column_index + 1,
                },
                "rows": [{"values": [cls._cell(value)]}],
                "fields": "userEnteredValue",
            }
        }
