from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class SnowResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None
    details: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    table: Optional[str] = None
    operation: Optional[str] = None

    def to_dict(self) -> dict:
        result: dict = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.details is not None:
            result["details"] = self.details
        if self.warnings:
            result["warnings"] = self.warnings
        if self.table is not None:
            result["table"] = self.table
        if self.operation is not None:
            result["operation"] = self.operation
        return result
