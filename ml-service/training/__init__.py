"""Training pipeline for learned rainfall anomaly detection (IMD RF25).

Seams (each is a deep module with a small interface):

- ``data.RainfallArchive``      yearly NetCDF files -> clean numpy cubes
- ``transform.RainfallTransform`` mm <-> model space (log1p), fit on train only
- ``splits.split_years``        chronological year split
- ``partition.partition_cells`` cell sets per (future) federated client
- ``injection.inject``          labelled synthetic anomalies on rainfall windows
- ``sampler.WindowSampler``     random windows (+ neighbour context) for a cell set
- ``trainer.LocalTrainer``      fit / evaluate / get_weights / set_weights
- ``artifact.save/load``        versioned model artifact
- ``evaluate.evaluate``         threshold-free, point-wise metrics + random baseline
"""
