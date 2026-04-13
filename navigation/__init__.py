"""
Navigation & Route Intelligence Module
---------------------------------------
Owner: Sanskruti Rajesh Ninawe

Provides route processing, map integration, polyline decoding,
turn-by-turn instruction generation, and offline route caching.
"""

from .route_processor import RouteProcessor
from .map_manager import MapManager
from .turn_extractor import TurnExtractor
from .offline_cache import OfflineCache
from .contracts import (
	LocalizationEventType,
	TurnClass,
	LandmarkClass,
	NavMode,
	PositionMode,
	NetworkStatus,
	LocalizationModuleType,
	LocalizationControlAction,
	UIActionType,
	TurnPayload,
	LandmarkPayload,
	SignboardPayload,
	EventMessage,
	NavHintMessage,
	UIStateMessage,
	StartNavigationPayload,
	RerouteRequestPayload,
	EmptyPayload,
	UIActionMessage,
	ConnectivityStatusMessage,
	LocalizationControlMessage,
)
from .event_validator import NavigationContractValidator, ContractValidationError
from .event_pipeline import LocalizationEventPipeline, EventIngestResult
from .route_progress import RouteProgressEngine, ProgressUpdate
from .api_service import NavigationAPIService
from .confidence_tracker import NavigationConfidenceTracker, ConfidenceState
from .vision_bridge import NavigationVisionBridge, HTTPVisionNavHintSender

__all__ = [
	"RouteProcessor",
	"MapManager",
	"TurnExtractor",
	"OfflineCache",
	"LocalizationEventType",
	"TurnClass",
	"LandmarkClass",
	"NavMode",
	"PositionMode",
	"NetworkStatus",
	"LocalizationModuleType",
	"LocalizationControlAction",
	"UIActionType",
	"TurnPayload",
	"LandmarkPayload",
	"SignboardPayload",
	"EventMessage",
	"NavHintMessage",
	"UIStateMessage",
	"StartNavigationPayload",
	"RerouteRequestPayload",
	"EmptyPayload",
	"UIActionMessage",
	"ConnectivityStatusMessage",
	"LocalizationControlMessage",
	"NavigationContractValidator",
	"ContractValidationError",
	"LocalizationEventPipeline",
	"EventIngestResult",
	"RouteProgressEngine",
	"ProgressUpdate",
	"NavigationAPIService",
	"NavigationConfidenceTracker",
	"ConfidenceState",
	"NavigationVisionBridge",
	"HTTPVisionNavHintSender",
]
