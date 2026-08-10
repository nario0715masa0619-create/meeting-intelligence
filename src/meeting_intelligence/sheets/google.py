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

    def _ensure_schema(self, metadata: dict) -> tuple[dict[str, int], dict[str, list[str]]]:
        sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in metadata.get("sheets", [])}
        missing = [name for name in self.config.names.values() if name not in sheets]
        if missing:
            requests = [{"addSheet": {"properties": {"title": name}}} for name in missing]
            self._execute(self.service.spreadsheets().batchUpdate(spreadsheetId=self.config.spreadsheet_id, body={"requests": requests}))
            metadata = self._metadata()
            sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in metadata.get("sheets", [])}
        header_requests = []
        columns = {}
        for canonical, actual in self.config.names.items():
            current = self._execute(self.service.spreadsheets().values().get(spreadsheetId=self.config.spreadsheet_id, range=f"'{actual}'!1:1")).get("values", [])
            required = HEADERS[canonical]
            existing = list(current[0]) if current else []
            if len(existing) != len(set(existing)):
                raise GoogleSheetsSchemaError(f"Google Sheet '{actual}' has duplicate headers")
            missing_headers = [header for header in required if header not in existing]
            final = existing + missing_headers
            columns[actual] = final
            if missing_headers:
                start = len(existing)
                header_requests.append({"updateCells": {"range": {"sheetId": sheets[actual], "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": start}, "rows": [{"values": [self._cell(x) for x in missing_headers]}], "fields": "userEnteredValue"}})
        if header_requests:
            self._execute(self.service.spreadsheets().batchUpdate(spreadsheetId=self.config.spreadsheet_id, body={"requests": header_requests}))
        return sheets, columns

    def write(self, analysis: MeetingAnalysis, context: SheetsMeetingContext | None = None) -> None:
        metadata = self._metadata()
        titles = {s["properties"]["title"] for s in metadata.get("sheets", [])}
        if self._duplicate(analysis.meeting_id, titles):
            raise DuplicateMeetingError("Meeting has already been projected")
        sheet_ids, columns = self._ensure_schema(metadata)
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
