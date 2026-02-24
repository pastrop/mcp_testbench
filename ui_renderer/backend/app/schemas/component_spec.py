"""Component specification schemas for UI generation."""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ComponentType(str, Enum):
    """Available UI component types."""

    # Layout components
    CONTAINER = "Container"
    GRID = "Grid"
    CARD = "Card"
    SECTION = "Section"
    TABS = "Tabs"
    ACCORDION = "Accordion"

    # Data display components
    TABLE = "Table"
    KEY_VALUE_LIST = "KeyValueList"
    BADGE_LIST = "BadgeList"
    METRIC_CARD = "MetricCard"
    FEE_CARD = "FeeCard"
    TIERED_PRICING = "TieredPricing"

    # Text components
    HEADING = "Heading"
    TEXT = "Text"
    LABEL = "Label"

    # Data visualization
    CHART = "Chart"
    PROGRESS_BAR = "ProgressBar"


class DataBinding(BaseModel):
    """Defines how data from JSON maps to component props."""

    path: str = Field(
        ...,
        description="JSON path to data (e.g., 'fees_and_rates', 'document_info.company')",
    )
    transform: Optional[str] = Field(
        default=None,
        description="Optional transformation function name (e.g., 'formatCurrency', 'formatDate')",
    )
    default_value: Optional[Any] = Field(
        default=None, description="Default value if path doesn't exist"
    )


class StyleConfig(BaseModel):
    """Styling configuration for components."""

    variant: Optional[str] = Field(
        default=None, description="Component variant (e.g., 'primary', 'outlined')"
    )
    size: Optional[str] = Field(
        default="medium", description="Component size (small, medium, large)"
    )
    color: Optional[str] = Field(
        default=None, description="Color theme (e.g., 'success', 'warning', 'error')"
    )
    className: Optional[str] = Field(
        default=None, description="Additional CSS classes"
    )


class ComponentSpec(BaseModel):
    """Specification for a single UI component."""

    id: Optional[str] = Field(
        default=None, description="Unique identifier for this component instance"
    )
    type: ComponentType = Field(..., description="Type of component to render")
    props: Dict[str, Any] = Field(
        default_factory=dict, description="Static props for the component"
    )
    data_bindings: Dict[str, DataBinding] = Field(
        default_factory=dict,
        description="Dynamic data bindings mapping prop names to JSON paths",
    )
    style: Optional[StyleConfig] = Field(
        default=None, description="Styling configuration"
    )
    children: Optional[List["ComponentSpec"]] = Field(
        default=None, description="Child components (for layout components)"
    )
    condition: Optional[str] = Field(
        default=None,
        description="JSON path for conditional rendering (component shown if truthy)",
    )

    def __init__(self, **data):
        """Initialize and auto-generate ID if not provided."""
        if "id" not in data or data["id"] is None:
            component_type = data.get("type", "component")
            data["id"] = f"{component_type}-{uuid.uuid4().hex[:8]}"
        super().__init__(**data)


class UIComponentSpec(BaseModel):
    """Complete UI specification for rendering a contract."""

    contract_id: str = Field(..., description="Identifier for the contract")
    title: str = Field(..., description="Display title for the UI")
    description: Optional[str] = Field(
        default=None, description="Description of the contract"
    )
    components: List[ComponentSpec] = Field(
        ..., description="Root-level components to render"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the contract"
    )


# Update forward references
ComponentSpec.model_rebuild()
