from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from .sec_edgar import (
    ParsedCompanyFacts,
    normalize_cik,
    parse_companyfacts,
    parse_submission_acceptance_times,
)


class SecBulkArchives:
    """Read SEC nightly companyfacts/submissions ZIPs without extracting them.

    The raw SEC archives can be large, so this adapter keeps them local and reads
    only selected issuer JSON members. A ticker index is built lazily from the
    submissions archive when symbol-to-CIK resolution is needed.
    """

    def __init__(self, companyfacts_zip: str | Path, submissions_zip: str | Path) -> None:
        self.companyfacts_zip = Path(companyfacts_zip)
        self.submissions_zip = Path(submissions_zip)
        for path in (self.companyfacts_zip, self.submissions_zip):
            if not path.is_file():
                raise FileNotFoundError(path)
        self._ticker_to_cik: dict[str, str] | None = None
        self._company_members: dict[str, str] | None = None
        self._submission_members: dict[str, str] | None = None

    @staticmethod
    def _cik_from_member(member: str) -> str | None:
        name = Path(member).name
        if not name.startswith("CIK") or not name.endswith(".json"):
            return None
        raw = name[3:-5]
        if not raw.isdigit():
            return None
        return normalize_cik(raw)

    @classmethod
    def _member_index(cls, archive_path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                cik = cls._cik_from_member(info.filename)
                if cik:
                    result[cik] = info.filename
        return result

    @staticmethod
    def _read_json(archive_path: Path, member: str) -> dict[str, Any]:
        with zipfile.ZipFile(archive_path) as archive:
            with archive.open(member) as handle:
                payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"SEC bulk member is not a JSON object: {member}")
        return payload

    def _company_index(self) -> dict[str, str]:
        if self._company_members is None:
            self._company_members = self._member_index(self.companyfacts_zip)
        return self._company_members

    def _submissions_index(self) -> dict[str, str]:
        if self._submission_members is None:
            self._submission_members = self._member_index(self.submissions_zip)
        return self._submission_members

    def companyfacts(self, cik: str | int) -> dict[str, Any]:
        normalized = normalize_cik(cik)
        member = self._company_index().get(normalized)
        if member is None:
            raise KeyError(f"CIK {normalized} not found in companyfacts ZIP")
        return self._read_json(self.companyfacts_zip, member)

    def submissions(self, cik: str | int) -> dict[str, Any]:
        normalized = normalize_cik(cik)
        member = self._submissions_index().get(normalized)
        if member is None:
            raise KeyError(f"CIK {normalized} not found in submissions ZIP")
        return self._read_json(self.submissions_zip, member)

    def ticker_index(self) -> dict[str, str]:
        if self._ticker_to_cik is not None:
            return self._ticker_to_cik
        result: dict[str, str] = {}
        with zipfile.ZipFile(self.submissions_zip) as archive:
            for info in archive.infolist():
                if info.is_dir() or self._cik_from_member(info.filename) is None:
                    continue
                try:
                    with archive.open(info) as handle:
                        payload = json.load(handle)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                try:
                    cik = normalize_cik(payload.get("cik") or self._cik_from_member(info.filename) or "")
                except ValueError:
                    continue
                tickers = payload.get("tickers", [])
                if not isinstance(tickers, list):
                    continue
                for ticker in tickers:
                    symbol = str(ticker).strip().upper()
                    if symbol:
                        # Duplicate current tickers are unusual. First occurrence wins so
                        # a later malformed filing cannot silently overwrite the mapping.
                        result.setdefault(symbol, cik)
        self._ticker_to_cik = result
        return result

    def cik_for_ticker(self, ticker: str) -> str | None:
        return self.ticker_index().get(ticker.strip().upper())

    def parsed_companyfacts(self, cik: str | int) -> ParsedCompanyFacts:
        submissions = self.submissions(cik)
        acceptance_times = parse_submission_acceptance_times(submissions)
        return parse_companyfacts(self.companyfacts(cik), acceptance_times=acceptance_times)
