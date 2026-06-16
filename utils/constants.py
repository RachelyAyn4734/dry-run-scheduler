"""
Shared constants — single source of truth for cross-layer values.
Pure Python — no Streamlit, no DB imports.
"""

# Manager-assignment service types.
# These strings must match the CHECK constraint in migration_managers_v3.sql:
#   service_type IN ('dry_run', 'grandma')
SERVICE_DRY_RUN = "dry_run"
SERVICE_GRANDMA = "grandma"

# All valid service types — handy for validation and UI iteration.
SERVICE_TYPES = (SERVICE_DRY_RUN, SERVICE_GRANDMA)
