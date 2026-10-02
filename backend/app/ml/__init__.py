"""SkyGuard AI Machine Learning Package."""

from backend.app.ml.fusion import AnomalyFusionEngine, FusionResult, Severity, TierScores as FusionTierScores
from backend.app.ml.pipeline import InferenceResult, SkyGuardPipeline, TierScores
from backend.app.ml.preprocessor import DataPreprocessor, Preprocessor, PreprocessorResult
from backend.app.ml.tier1_qc import Tier1QC, Tier1QCConfig, Tier1QCEngine, Tier1QCResult
from backend.app.ml.tier2_point_ml import IsolationForestPointDetector, PointAnomalyDetector
from backend.app.ml.tier2_temporal_ml import TemporalAnomalyDetector, TemporalAutoencoderDetector
from backend.app.ml.tier3_multivariate import (
    Tier3Multivariate,
    Tier3MultivariateDetector,
    Tier3Result,
    calculate_dew_point,
    evaluate_thermodynamic_consistency,
)
from backend.app.ml.tier4_classifier import ClassificationResult, FaultClass, FaultClassifier, Tier4FaultClassifier
from backend.app.ml.tier5_explain import ExplainabilityEngine, ExplanationResult, FeatureAttribution
from backend.app.ml.tier5_health import DegradationRisk, HealthRecord, HealthStatus, SensorHealthEngine, StationHealthState

__all__ = [
    "Tier1QC",
    "Tier1QCConfig",
    "Tier1QCResult",
    "Tier1QCEngine",
    "DataPreprocessor",
    "Preprocessor",
    "PreprocessorResult",
    "IsolationForestPointDetector",
    "PointAnomalyDetector",
    "TemporalAutoencoderDetector",
    "TemporalAnomalyDetector",
    "Tier3MultivariateDetector",
    "Tier3Multivariate",
    "Tier3Result",
    "calculate_dew_point",
    "evaluate_thermodynamic_consistency",
    "AnomalyFusionEngine",
    "FusionResult",
    "Severity",
    "FusionTierScores",
    "FaultClassifier",
    "Tier4FaultClassifier",
    "FaultClass",
    "ClassificationResult",
    "SensorHealthEngine",
    "HealthStatus",
    "DegradationRisk",
    "StationHealthState",
    "HealthRecord",
    "ExplainabilityEngine",
    "ExplanationResult",
    "FeatureAttribution",
    "SkyGuardPipeline",
    "InferenceResult",
    "TierScores",
]
