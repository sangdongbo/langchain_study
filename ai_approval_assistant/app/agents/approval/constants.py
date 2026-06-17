from __future__ import annotations

MAX_REVIEW_COUNT = 2

FIELD_DEPENDENCIES = {
    "start_date": ["end_date"],
    "rest_start_time": ["rest_end_time", "rest_duration"],
    "rest_end_time": ["rest_duration"],
    "go_out_start_time": ["go_out_end_time", "go_out_duration"],
    "go_out_end_time": ["go_out_duration"],
}

LOCAL_MOCK_APPROVAL_TYPES = {
    "leave",
    "expense",
    "purchase",
    "seal",
    "inbound",
    "outbound",
    "overtime",
}
