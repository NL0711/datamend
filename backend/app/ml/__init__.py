"""SkyGuard AI Machine Learning Package.

Organized into three modular layers:
- `backend.app.ml.screening`: Tier 0 Edge and Gateway Ingestion Screener
- `backend.app.ml.stages`: Production 6-Stage Deep ML Pipeline (STL, Ensemble, Physics, Classifier, Explainability, Imputer)
- `backend.app.ml.legacy_tiers`: Retained prototype Tier 1-5 engines and legacy SkyGuardPipeline
"""

import sys
from importlib import import_module

# Backward compatibility alias map: legacy/flat paths -> organized subpackages
_MODULE_ALIASES = {
    # Tier 0 Screening
    "backend.app.ml.tier0_screener": "backend.app.ml.screening.tier0_screener",
    # Production Stages 1-6
    "backend.app.ml.stage1_stl": "backend.app.ml.stages.stage1_stl",
    "backend.app.ml.stage2_ensemble": "backend.app.ml.stages.stage2_ensemble",
    "backend.app.ml.stage3_physics": "backend.app.ml.stages.stage3_physics",
    "backend.app.ml.stage4_classifier": "backend.app.ml.stages.stage4_classifier",
    "backend.app.ml.stage5_explain": "backend.app.ml.stages.stage5_explain",
    "backend.app.ml.stage6_imputer": "backend.app.ml.stages.stage6_imputer",
    # Legacy Prototype Tiers 1-5
    "backend.app.ml.tier1_qc": "backend.app.ml.legacy_tiers.tier1_qc",
    "backend.app.ml.tier2_point_ml": "backend.app.ml.legacy_tiers.tier2_point_ml",
    "backend.app.ml.tier2_temporal_ml": "backend.app.ml.legacy_tiers.tier2_temporal_ml",
    "backend.app.ml.tier3_multivariate": "backend.app.ml.legacy_tiers.tier3_multivariate",
    "backend.app.ml.tier4_classifier": "backend.app.ml.legacy_tiers.tier4_classifier",
    "backend.app.ml.tier5_explain": "backend.app.ml.legacy_tiers.tier5_explain",
    "backend.app.ml.tier5_health": "backend.app.ml.legacy_tiers.tier5_health",
    "backend.app.ml.fusion": "backend.app.ml.legacy_tiers.fusion",
    "backend.app.ml.pipeline": "backend.app.ml.legacy_tiers.pipeline",
    "backend.app.ml.preprocessor": "backend.app.ml.legacy_tiers.preprocessor",
}


class _MlPackageMetaFinder:
    """Dynamic finder for backward-compatible module resolution across reorganized ML packages."""

    def find_spec(self, fullname: str, path, target=None):
        if fullname in _MODULE_ALIASES:
            target_name = _MODULE_ALIASES[fullname]
            mod = import_module(target_name)
            sys.modules[fullname] = mod
            return mod.__spec__
        return None


if not any(isinstance(f, _MlPackageMetaFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _MlPackageMetaFinder())
