"""Custom exception classes for the SVP microservices system.

Each exception maps to a single, specific failure point in the system.
The ``logger`` module is responsible for recording detail; these classes
exist only to signal *what* went wrong so callers can handle it precisely.

All exceptions inherit directly from the built-in ``Exception`` base
class and carry no extra state — the raising site should log a message
with full context before raising.
"""


class CustomerDeactivatedError(Exception):
    """Raised when an operation is attempted on a deactivated customer.

    Signals that the target customer account has been deactivated and
    therefore cannot be the subject of the requested operation.
    """

    pass


class PlanConfirmationError(Exception):
    """Raised when a visit plan cannot be confirmed.

    Signals a failure during the plan-confirmation step, such as a
    scheduling conflict or a missing required approval.
    """

    pass


class ExternalMappingUnavailableError(Exception):
    """Raised when the external mapping service is unreachable or returns an error.

    Signals that the system could not retrieve or apply a coordinate or
    route mapping from the external provider.
    """

    pass


class InvalidCoordinatesError(Exception):
    """Raised when a set of geographic coordinates fails validation.

    Signals that the supplied latitude/longitude values are outside
    acceptable ranges or are otherwise malformed.
    """

    pass


class VisitCompletionError(Exception):
    """Raised when a field visit cannot be marked as complete.

    Signals a failure in the visit-completion workflow, such as missing
    required data or a backend persistence error.
    """

    pass


class ExpenseApprovalError(Exception):
    """Raised when an expense claim fails the approval process.

    Signals that a submitted expense could not be approved, for example
    because it exceeds policy limits or lacks required documentation.
    """

    pass


class OutboxPublishError(Exception):
    """Raised when an outbox event cannot be published to the message broker.

    Signals a failure in the transactional-outbox publishing step,
    indicating that downstream consumers may not receive the event.
    """

    pass


class OfflineSyncConflictError(Exception):
    """Raised when an offline sync operation produces an unresolvable conflict.

    Signals that local changes made while offline cannot be automatically
    merged with the current server state and require manual resolution.
    """

    pass
