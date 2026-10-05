"""Exceptions that carry a translatable message code"""


class McplainError(Exception):
    """Class that carries a message code and its parameters"""

    def __init__(self, code: str, **params: object) -> None:
        """Store the message code and its parameters as strings"""

        super().__init__(code)
        self.code = code
        self.params = {key: str(value) for key, value in params.items()}


class InputError(McplainError):
    """Class for a user input that MCPlain refuses"""


class FetchError(McplainError):
    """Class for a failure while downloading a source"""


class ArchiveError(McplainError):
    """Class for an archive that cannot be extracted safely"""


class DetectionError(McplainError):
    """Class for a source folder that cannot be inspected"""


class JobError(McplainError):
    """Class for a job folder that cannot be analyzed as it is"""
