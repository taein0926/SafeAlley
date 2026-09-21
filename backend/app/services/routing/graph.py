from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphNode:
    id: int
    x: float
    y: float


@dataclass(frozen=True)
class GraphEdge:
    segment_id: int
    source_id: str
    name: str | None
    from_node_id: int
    to_node_id: int
    distance_m: float
    streetlight_score: float
    cctv_score: float
    population_score: float
    safety_score: float
    coordinates: tuple[tuple[float, float], ...]
    highway: str | None = None
    step_count: str | None = None
    incline: str | None = None
    ramp: str | None = None
    wheelchair: str | None = None
    handrail: str | None = None
    streetlight_data_available: bool = True
    walkability_factor: float = 1.0
    crossing_node_ids: tuple[int, ...] = ()
    is_steps: bool = False
    sidewalk_confirmed: bool = False
    incline_percent: float | None = None
    walkability_class: str | None = None
    field_status: str = "unverified"


@dataclass
class RoadGraph:
    nodes: dict[int, GraphNode] = field(default_factory=dict)
    adjacency: dict[int, list[GraphEdge]] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes.setdefault(node.id, node)
        self.adjacency.setdefault(node.id, [])

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.from_node_id not in self.nodes or edge.to_node_id not in self.nodes:
            raise ValueError("Both edge nodes must be added before the edge")
        if edge.distance_m <= 0:
            raise ValueError("Edge distance must be greater than zero")
        self.adjacency[edge.from_node_id].append(edge)

    def neighbors(self, node_id: int) -> tuple[GraphEdge, ...]:
        return tuple(self.adjacency.get(node_id, ()))
