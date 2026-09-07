"""Domain models for BCOS problem reconstruction."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ProblemType(str, Enum):
    """High-level problem classes."""

    FACT_LOOKUP = "fact_lookup"
    CALCULATION = "calculation"
    MATHEMATICS = "mathematics"
    CAUSAL = "causal"
    OPTIMIZATION = "optimization"
    DEBUG = "debug"
    DESIGN = "design"
    DECISION = "decision"
    UNKNOWN = "unknown"


@dataclass
class ProblemInput:
    """Original user input."""

    raw_text: str
    normalized_text: str = ""
    source_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.normalized_text:
            self.normalized_text = " ".join(
                self.raw_text.strip().split()
            )


@dataclass
class Variable:
    """Variable or quantity."""

    name: str
    value: Optional[Any] = None
    unit: Optional[str] = None
    description: str = ""
    source: Optional[str] = None


@dataclass
class Relation:
    """Relationship between entities or variables."""

    name: str
    expression: Optional[str] = None
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    description: str = ""
    source: Optional[str] = None


@dataclass
class Constraint:
    """Constraint that a solution must satisfy."""

    description: str
    expression: Optional[str] = None
    kind: str = "general"
    hard: bool = True
    source: Optional[str] = None


@dataclass
class Unknown:
    """Unknown quantity or fact."""

    name: str
    description: str = ""
    unit: Optional[str] = None
    source: Optional[str] = None


@dataclass
class Assumption:
    """Explicit assumption."""

    description: str
    confidence: float = 0.5
    source: Optional[str] = None


@dataclass
class EvidenceRequirement:
    """Evidence required to establish a conclusion."""

    description: str
    source_type: Optional[str] = None
    required: bool = True
    reason: str = ""


@dataclass
class SuccessCriterion:
    """Criterion used to determine whether the problem is solved."""

    description: str
    measurable: bool = False
    metric: Optional[str] = None
    target: Optional[Any] = None


@dataclass
class ProblemModel:
    """Canonical representation of a user problem."""

    input: ProblemInput

    goal: str = ""

    entities: List[str] = field(default_factory=list)

    variables: List[Variable] = field(
        default_factory=list
    )

    relations: List[Relation] = field(
        default_factory=list
    )

    constraints: List[Constraint] = field(
        default_factory=list
    )

    unknowns: List[Unknown] = field(
        default_factory=list
    )

    assumptions: List[Assumption] = field(
        default_factory=list
    )

    evidence_requirements: List[
        EvidenceRequirement
    ] = field(default_factory=list)

    success_criteria: List[
        SuccessCriterion
    ] = field(default_factory=list)

    problem_types: List[ProblemType] = field(
        default_factory=list
    )

    primary_problem_type: ProblemType = (
        ProblemType.UNKNOWN
    )

    observations: List[str] = field(
        default_factory=list
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    # ---------------------------------------------------------
    # ADD METHODS
    # ---------------------------------------------------------

    def add_entity(self, entity: str):
        entity = entity.strip()

        if entity and entity not in self.entities:
            self.entities.append(entity)

    def add_variable(self, variable: Variable):
        if not any(
            item.name == variable.name
            for item in self.variables
        ):
            self.variables.append(variable)

    def add_relation(self, relation: Relation):
        self.relations.append(relation)

    def add_constraint(self, constraint: Constraint):
        self.constraints.append(constraint)

    def add_unknown(self, unknown: Unknown):
        if not any(
            item.name == unknown.name
            for item in self.unknowns
        ):
            self.unknowns.append(unknown)

    def add_assumption(self, assumption: Assumption):
        self.assumptions.append(assumption)

    def add_evidence_requirement(
        self,
        requirement: EvidenceRequirement
    ):
        self.evidence_requirements.append(
            requirement
        )

    def add_success_criterion(
        self,
        criterion: SuccessCriterion
    ):
        self.success_criteria.append(
            criterion
        )

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    def has_unknowns(self) -> bool:
        return bool(self.unknowns)

    def has_numeric_structure(self) -> bool:
        return bool(
            self.variables
            or any(
                relation.expression
                for relation in self.relations
            )
        )

    # ---------------------------------------------------------
    # SERIALIZATION
    # ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:

        return {
            "input": {
                "raw_text": self.input.raw_text,
                "normalized_text": (
                    self.input.normalized_text
                ),
                "source_type": (
                    self.input.source_type
                ),
                "metadata": (
                    self.input.metadata
                ),
            },

            "goal": self.goal,

            "entities": list(
                self.entities
            ),

            "variables": [
                {
                    "name": item.name,
                    "value": item.value,
                    "unit": item.unit,
                    "description": item.description,
                    "source": item.source,
                }
                for item in self.variables
            ],

            "relations": [
                {
                    "name": item.name,
                    "expression": item.expression,
                    "subject": item.subject,
                    "predicate": item.predicate,
                    "object": item.object,
                    "description": item.description,
                    "source": item.source,
                }
                for item in self.relations
            ],

            "constraints": [
                {
                    "description": item.description,
                    "expression": item.expression,
                    "kind": item.kind,
                    "hard": item.hard,
                    "source": item.source,
                }
                for item in self.constraints
            ],

            "unknowns": [
                {
                    "name": item.name,
                    "description": item.description,
                    "unit": item.unit,
                    "source": item.source,
                }
                for item in self.unknowns
            ],

            "assumptions": [
                {
                    "description": item.description,
                    "confidence": item.confidence,
                    "source": item.source,
                }
                for item in self.assumptions
            ],

            "evidence_requirements": [
                {
                    "description": item.description,
                    "source_type": item.source_type,
                    "required": item.required,
                    "reason": item.reason,
                }
                for item in self.evidence_requirements
            ],

            "success_criteria": [
                {
                    "description": item.description,
                    "measurable": item.measurable,
                    "metric": item.metric,
                    "target": item.target,
                }
                for item in self.success_criteria
            ],

            "problem_types": [
                item.value
                for item in self.problem_types
            ],

            "primary_problem_type": (
                self.primary_problem_type.value
            ),

            "observations": list(
                self.observations
            ),

            "metadata": dict(
                self.metadata
            ),
        }

    def summary(self) -> str:

        return (
            "Problem("
            f"type={self.primary_problem_type.value}, "
            f"goal={self.goal!r}, "
            f"entities={self.entities}, "
            f"variables="
            f"{[v.name for v in self.variables]}, "
            f"unknowns="
            f"{[u.name for u in self.unknowns]}, "
            f"constraints="
            f"{len(self.constraints)}, "
            f"relations="
            f"{len(self.relations)}"
            ")"
        )