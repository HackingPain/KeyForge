"""JSON-driven walkthrough engine for credential providers without a mint API.

Each provider has a JSON file in this directory describing the steps a user
must follow in the upstream dashboard to obtain a credential, plus a
validation regex that the pasted credential is checked against before it is
stored. The walkthrough engine is consumed by the
``backend.routes.walkthroughs`` router and rendered by the
``CredentialWalkthrough`` React component.
"""

from backend.walkthroughs.loader import (
    WalkthroughNotFoundError,
    list_walkthroughs,
    load_walkthrough,
    validate_credential_format,
)
from backend.walkthroughs.schema import (
    Walkthrough,
    WalkthroughStep,
    WalkthroughStepAction,
    WalkthroughSummary,
    WalkthroughValidation,
    WalkthroughValidationResponse,
)

__all__ = [
    "Walkthrough",
    "WalkthroughNotFoundError",
    "WalkthroughStep",
    "WalkthroughStepAction",
    "WalkthroughSummary",
    "WalkthroughValidation",
    "WalkthroughValidationResponse",
    "list_walkthroughs",
    "load_walkthrough",
    "validate_credential_format",
]
