import re

BARE_NUMBER = re.compile(r"(Rs\.?\s?[\d,]+(?:\.\d+)?|INR\s?[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?%)(?!\s*<cite:)")


def enforce_citations(response: str) -> str:
    return BARE_NUMBER.sub("[uncited value removed]", response)


def extract_row_ids(response: str) -> list[str]:
    row_ids: list[str] = []
    for match in re.finditer(r"<cite:([^>]+)>", response):
        row_ids.extend(part.strip() for part in match.group(1).split(",") if part.strip())
    return list(dict.fromkeys(row_ids))
