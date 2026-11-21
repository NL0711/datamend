"""The bulk-ingest and reviewer-driven feedback loop (wayfinder map docs/wayfinder/ingest-and-feedback-loop).

Raw observations are stored immutably and compactly (never overwritten); checking reuses the validation platform's runs, results and
reviews; AI or rule proposals, corrections, labels and audit samples are stored apart from the data; a training snapshot leaves the
platform for OFFLINE training and a model version comes back through a registry and a promotion gate. NOT IMPLEMENTED here: training
itself, scoring with a trained model on the server, and the LLM proposer (the narrator team's service).
"""
