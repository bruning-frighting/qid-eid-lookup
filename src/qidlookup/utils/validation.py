"""Input validation helpers shared by the importer and CLI.

Keeping validation here (rather than scattered across the importer and
CLI) means both layers reject bad input the same way and with the same
error messages.
"""

from __future__ import annotations

from pathlib import Path

REQUIRED_CSV_COLUMNS = {
    "eid",
    "event_category",
    "qid",
    "event_name",
    "description",
}


class RowValidationError(ValueError):
    """A single CSV row failed validation and should be counted invalid."""


class InputValidationError(ValueError):
    """A user-supplied CLI argument failed validation."""


def validate_header(fieldnames: list[str] | None) -> None:
    """Ensure the CSV header contains all required columns.

    Raises:
        ValueError: if fieldnames is None or missing required columns.
    """
    if fieldnames is None:
        raise ValueError("CSV file has no header row.")
    present = {name.strip() for name in fieldnames}
    missing = REQUIRED_CSV_COLUMNS - present
    if missing:
        raise ValueError(
            f"CSV header is missing required column(s): {', '.join(sorted(missing))}"
        )


def clean_str(value: str | None) -> str | None:
    """Trim whitespace; convert empty strings to None."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def parse_optional_int(value: str | None, field_name: str) -> int | None:
    """Parse an optional integer field.

    Empty/None is allowed and returns None. A non-empty, non-integer value
    raises RowValidationError.
    """
    cleaned = clean_str(value)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise RowValidationError(f"{field_name} must be an integer, got: {cleaned!r}") from exc


def parse_qid_arg(value: str) -> int:
    """Parse a QID CLI argument, raising a user-friendly error on failure."""
    try:
        return int(value.strip())
    except (ValueError, AttributeError) as exc:
        raise InputValidationError("QID must be an integer.") from exc


def split_csv_arg(value: str) -> list[str]:
    """Split a comma-separated CLI argument into trimmed, non-empty tokens."""
    return [token.strip() for token in value.split(",") if token.strip()]


def split_category_arg(value: str) -> tuple[str | None, str]:
    """Split a combined 'High Level.Low Level' category string.

    QRadar displays categories as "<High Level Category>.<Low Level
    Category>" (e.g. "System.Process Creation Success", "Audit.Command
    Execution Success"). The same Low Level Category name can exist under
    multiple High Level Categories (e.g. "Command Execution Success"
    appears under both "Audit" and "System"), so the combined form is
    needed to disambiguate.

    If ``value`` contains a '.', it is split on the first occurrence into
    (high_level, low_level). Otherwise the whole string is returned as the
    Low Level Category with no High Level Category component.
    """
    if "." in value:
        prefix, _, suffix = value.partition(".")
        prefix = prefix.strip()
        suffix = suffix.strip()
        if prefix and suffix:
            return prefix, suffix
    return None, value.strip()


def validate_readable_file(path: str | Path) -> Path:
    """Validate that ``path`` refers to an existing, readable regular file.

    Raises:
        InputValidationError: if the path does not exist or is not a file.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise InputValidationError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise InputValidationError(f"Not a file: {resolved}")
    return resolved


def validate_output_path(path: str | Path, force: bool) -> Path:
    """Validate an output file path, refusing to silently overwrite.

    Raises:
        InputValidationError: if the file already exists and ``force`` is False.
    """
    resolved = Path(path).expanduser().resolve()
    if resolved.exists() and not force:
        raise InputValidationError(
            f"Output file already exists: {resolved} (use --force to overwrite)"
        )
    return resolved
