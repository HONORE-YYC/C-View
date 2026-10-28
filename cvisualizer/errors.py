"""User-facing errors shared by preprocessing, parsing and execution."""


class CError(Exception):
    def __init__(self, message, line=0, column=0):
        self.message, self.line, self.column = message, line, column
        super().__init__(f'第 {line} 行：{message}' if line else message)


class TeachingExit(Exception):
    """Terminate the interpreted program without terminating the host."""
    def __init__(self, status):
        self.status = status
        super().__init__(status)
