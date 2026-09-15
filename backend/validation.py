import csv
import io
from typing import List, Tuple
from backend.models import StadiumZoneRecord, ValidationErrorItem, ValidationResult

REQUIRED_COLUMNS = [
    "timestamp",
    "zone",
    "capacity",
    "current_crowd",
    "inflow_per_min",
    "outflow_per_min",
    "queue_size",
    "transport_capacity",
    "next_transport_minutes",
    "available_shuttles",
    "gate_d_available",
]


def parse_boolean(val: str) -> Tuple[bool, bool]:
    """Returns (parsed_value, is_valid_bool)"""
    cleaned = val.strip().lower()
    if cleaned in ("true", "1", "yes", "t", "y"):
        return True, True
    if cleaned in ("false", "0", "no", "f", "n"):
        return False, True
    return False, False


def validate_csv_content(csv_text: str) -> ValidationResult:
    errors: List[ValidationErrorItem] = []
    records: List[StadiumZoneRecord] = []
    detected_zones: List[str] = []

    if not csv_text or not csv_text.strip():
        errors.append(ValidationErrorItem(
            row=None,
            field=None,
            message="CSV file is empty. Please upload an operational dataset with required columns."
        ))
        return ValidationResult(is_valid=False, total_records=0, detected_zones=[], records=[], errors=errors)

    try:
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
    except Exception as e:
        errors.append(ValidationErrorItem(
            row=None,
            field=None,
            message=f"Malformed CSV format: {str(e)}"
        ))
        return ValidationResult(is_valid=False, total_records=0, detected_zones=[], records=[], errors=errors)

    if not reader.fieldnames:
        errors.append(ValidationErrorItem(
            row=1,
            field=None,
            message="CSV file contains no headers."
        ))
        return ValidationResult(is_valid=False, total_records=0, detected_zones=[], records=[], errors=errors)

    # Normalize headers
    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in normalized_headers]

    if missing_columns:
        errors.append(ValidationErrorItem(
            row=1,
            field="headers",
            message=f"Missing required columns: {', '.join(missing_columns)}. Found: {', '.join(reader.fieldnames)}"
        ))
        return ValidationResult(is_valid=False, total_records=0, detected_zones=[], records=[], errors=errors)

    row_index = 1  # 1 is header
    has_rows = False

    for row_dict in reader:
        row_index += 1
        has_rows = True

        # Check for empty or missing values in row
        row_has_error = False
        parsed_fields = {}

        # 1. Timestamp
        raw_ts = row_dict.get(normalized_headers["timestamp"], "").strip()
        if not raw_ts:
            errors.append(ValidationErrorItem(row=row_index, field="timestamp", message="Timestamp cannot be empty."))
            row_has_error = True
        else:
            parsed_fields["timestamp"] = raw_ts

        # 2. Zone
        raw_zone = row_dict.get(normalized_headers["zone"], "").strip()
        if not raw_zone:
            errors.append(ValidationErrorItem(row=row_index, field="zone", message="Zone identifier cannot be empty."))
            row_has_error = True
        else:
            parsed_fields["zone"] = raw_zone
            if raw_zone not in detected_zones:
                detected_zones.append(raw_zone)

        # 3. Capacity
        raw_cap = row_dict.get(normalized_headers["capacity"], "").strip()
        try:
            cap = int(raw_cap)
            if cap <= 0:
                errors.append(ValidationErrorItem(row=row_index, field="capacity", message=f"Capacity must be greater than 0, got {cap}."))
                row_has_error = True
            else:
                parsed_fields["capacity"] = cap
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="capacity", message=f"Invalid numeric value for capacity: '{raw_cap}'."))
            row_has_error = True

        # 4. Current crowd
        raw_crowd = row_dict.get(normalized_headers["current_crowd"], "").strip()
        try:
            crowd = int(raw_crowd)
            if crowd < 0:
                errors.append(ValidationErrorItem(row=row_index, field="current_crowd", message=f"Current crowd cannot be negative, got {crowd}."))
                row_has_error = True
            elif "capacity" in parsed_fields and crowd > parsed_fields["capacity"]:
                errors.append(ValidationErrorItem(
                    row=row_index,
                    field="current_crowd",
                    message=f"Current crowd ({crowd}) cannot exceed maximum safe capacity ({parsed_fields['capacity']})."
                ))
                row_has_error = True
            else:
                parsed_fields["current_crowd"] = crowd
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="current_crowd", message=f"Invalid numeric value for current_crowd: '{raw_crowd}'."))
            row_has_error = True

        # 5. Inflow
        raw_inflow = row_dict.get(normalized_headers["inflow_per_min"], "").strip()
        try:
            inflow = int(raw_inflow)
            if inflow < 0:
                errors.append(ValidationErrorItem(row=row_index, field="inflow_per_min", message=f"Inflow rate cannot be negative, got {inflow}."))
                row_has_error = True
            else:
                parsed_fields["inflow_per_min"] = inflow
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="inflow_per_min", message=f"Invalid numeric value for inflow_per_min: '{raw_inflow}'."))
            row_has_error = True

        # 6. Outflow
        raw_outflow = row_dict.get(normalized_headers["outflow_per_min"], "").strip()
        try:
            outflow = int(raw_outflow)
            if outflow < 0:
                errors.append(ValidationErrorItem(row=row_index, field="outflow_per_min", message=f"Outflow rate cannot be negative, got {outflow}."))
                row_has_error = True
            else:
                parsed_fields["outflow_per_min"] = outflow
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="outflow_per_min", message=f"Invalid numeric value for outflow_per_min: '{raw_outflow}'."))
            row_has_error = True

        # 7. Queue size
        raw_queue = row_dict.get(normalized_headers["queue_size"], "").strip()
        try:
            queue = int(raw_queue)
            if queue < 0:
                errors.append(ValidationErrorItem(row=row_index, field="queue_size", message=f"Queue size cannot be negative, got {queue}."))
                row_has_error = True
            else:
                parsed_fields["queue_size"] = queue
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="queue_size", message=f"Invalid numeric value for queue_size: '{raw_queue}'."))
            row_has_error = True

        # 8. Transport capacity
        raw_tcap = row_dict.get(normalized_headers["transport_capacity"], "").strip()
        try:
            tcap = int(raw_tcap)
            if tcap < 0:
                errors.append(ValidationErrorItem(row=row_index, field="transport_capacity", message=f"Transport capacity cannot be negative, got {tcap}."))
                row_has_error = True
            else:
                parsed_fields["transport_capacity"] = tcap
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="transport_capacity", message=f"Invalid numeric value for transport_capacity: '{raw_tcap}'."))
            row_has_error = True

        # 9. Next transport minutes
        raw_tmin = row_dict.get(normalized_headers["next_transport_minutes"], "").strip()
        try:
            tmin = float(raw_tmin)
            if tmin < 0:
                errors.append(ValidationErrorItem(row=row_index, field="next_transport_minutes", message=f"Next transport minutes cannot be negative, got {tmin}."))
                row_has_error = True
            else:
                parsed_fields["next_transport_minutes"] = tmin
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="next_transport_minutes", message=f"Invalid numeric value for next_transport_minutes: '{raw_tmin}'."))
            row_has_error = True

        # 10. Available shuttles
        raw_shuttles = row_dict.get(normalized_headers["available_shuttles"], "").strip()
        try:
            shuttles = int(raw_shuttles)
            if shuttles < 0:
                errors.append(ValidationErrorItem(row=row_index, field="available_shuttles", message=f"Available shuttles cannot be negative, got {shuttles}."))
                row_has_error = True
            else:
                parsed_fields["available_shuttles"] = shuttles
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_index, field="available_shuttles", message=f"Invalid numeric value for available_shuttles: '{raw_shuttles}'."))
            row_has_error = True

        # 11. Gate D available
        raw_gated = row_dict.get(normalized_headers["gate_d_available"], "").strip()
        gated_val, is_valid_bool = parse_boolean(raw_gated)
        if not is_valid_bool:
            errors.append(ValidationErrorItem(row=row_index, field="gate_d_available", message=f"Invalid boolean value for gate_d_available: '{raw_gated}'. Expected true/false."))
            row_has_error = True
        else:
            parsed_fields["gate_d_available"] = gated_val

        if not row_has_error:
            records.append(StadiumZoneRecord(**parsed_fields))

    if not has_rows:
        errors.append(ValidationErrorItem(row=None, field=None, message="CSV file contains headers but no data rows."))

    is_valid = len(errors) == 0 and len(records) > 0
    return ValidationResult(
        is_valid=is_valid,
        total_records=len(records),
        detected_zones=detected_zones,
        records=records,
        errors=errors,
    )
