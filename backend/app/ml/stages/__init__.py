"""Production 6-Stage Deep Meteorological Anomaly Detection Pipeline.

Stage 1: STL Baseline Engine (Diurnal decomposition & cold-start donor clustering)
Stage 2: Multivariate Ensemble (PyOD I-Forest + PyTorch sequence autoencoder)
Stage 3: Thermodynamic Physics Validator (Clausius-Clapeyron, hypsometric SLP)
Stage 4: Evidence Fusion Classifier (8-class fault taxonomy with confidence)
Stage 5: TreeSHAP Explainability (Attributions & natural language narratives)
Stage 6: Meteorological Safe Imputer (STL baseline & spatial IDW reconstruction)
"""

from backend.app.ml.stages.stage1_stl import (
    STLBaselineEngine,
    StationBaseline,
    CHANNELS,
    infer_diurnal_period,
    decompose_series_stl,
    cluster_and_initialize_baselines,
)
from backend.app.ml.stages.stage2_ensemble import (
    MultivariateEnsembleDetector,
    EnsembleResult,
    ResidualIsolationForest,
    SequenceAutoencoderScorer,
)
from backend.app.ml.stages.stage3_physics import (
    ThermodynamicPhysicsValidator,
    PhysicsValidationResult,
    calculate_magnus_dew_point,
    compute_hypsometric_slp,
    MULTIVARIATE_FLAG,
)
from backend.app.ml.stages.stage4_classifier import (
    EvidenceFusionClassifier,
    DiagnosticEvidence,
    ClassificationResult,
    FAULT_CLASSES,
)
from backend.app.ml.stages.stage5_explain import (
    Stage5ExplainEngine,
    ExplanationReport,
    FeatureContribution,
    stage5_explain_engine,
)
from backend.app.ml.stages.stage6_imputer import (
    MeteorologicalSafeImputer,
    ImputationResult,
    meteorological_safe_imputer,
)

__all__ = [
    "STLBaselineEngine",
    "StationBaseline",
    "CHANNELS",
    "infer_diurnal_period",
    "decompose_series_stl",
    "cluster_and_initialize_baselines",
    "MultivariateEnsembleDetector",
    "EnsembleResult",
    "ResidualIsolationForest",
    "SequenceAutoencoderScorer",
    "ThermodynamicPhysicsValidator",
    "PhysicsValidationResult",
    "calculate_magnus_dew_point",
    "compute_hypsometric_slp",
    "MULTIVARIATE_FLAG",
    "EvidenceFusionClassifier",
    "DiagnosticEvidence",
    "ClassificationResult",
    "FAULT_CLASSES",
    "Stage5ExplainEngine",
    "ExplanationReport",
    "FeatureContribution",
    "stage5_explain_engine",
    "MeteorologicalSafeImputer",
    "ImputationResult",
    "meteorological_safe_imputer",
]
