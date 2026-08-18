def validate_choice(data, field, valid_values):
    """The 'if this field was given, it must be one of these values' check
    repeated across nearly every create/update route in this app. Returns an
    error message string if data[field] is present and not in valid_values,
    else None — callers just do `if err: return jsonify({"error": err}), 400`.
    """
    if field in data and data[field] is not None and data[field] not in valid_values:
        return f"{field} must be one of {valid_values}"
    return None
