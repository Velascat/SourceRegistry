from enum import StrEnum


class InstallKind(StrEnum):
    PYTHON_TOOL = "python_tool"
    EXTERNAL = "external"
    NONE = "none"
