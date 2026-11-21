# Federated-update protocol: aggregation, update validation, privacy options and phone-sensor evidence (primary sources)

Compiled 2026-11-19 for the phone-fl-prototype map (ticket t04). Question: FedAvg and its one-client case; update validation (norm clipping, anomaly screening); secure aggregation and differential privacy (only to know what to label PLANNED); update formats and sizes in mobile settings; evidence on federated learning from phone sensor data.

This note makes no novelty claim (`AGENTS.md` section 5). Every technique below is published prior work.

## BANNER: what was opened and what was not

OPENED (full text downloaded from arXiv as PDF and read as extracted text; sections read, not every page):
- McMahan et al. 2017, FedAvg, arXiv:1602.05629 (AISTATS 2017).
- Bonawitz et al. 2019, "Towards Federated Learning at Scale: System Design", arXiv:1902.01046.
- Bonawitz et al. 2016/2017, "Practical Secure Aggregation for Federated Learning on User-Held Data", arXiv:1611.04482 (v1; abstract and cost table only).
- McMahan et al. 2018, "Learning Differentially Private Recurrent Language Models", arXiv:1710.06963 (ICLR 2018).
- Sun et al. 2019, "Can You Really Backdoor Federated Learning?", arXiv:1911.07963.
- Bagdasaryan et al. 2018/2020, "How To Backdoor Federated Learning", arXiv:1807.00459.
- Yin et al. 2018, "Byzantine-Robust Distributed Learning", arXiv:1803.01498 (abstract and introduction only).
- Hard et al. 2018, "Federated Learning for Mobile Keyboard Prediction", arXiv:1811.03604.
- Konecny et al. 2016, "Federated Learning: Strategies for Improving Communication Efficiency", arXiv:1610.05492 (abstract and method headings).
- Kairouz et al. 2019, "Advances and Open Problems in Federated Learning", arXiv:1912.04977 (survey; used only for sections on poisoning, DP, cross-device; a survey is not a primary source for the underlying results, so each result is attributed to its original paper where one is named).
- Flower framework reference pages (flower.ai/docs/framework), read through a summarising fetch tool, not verbatim.
- NeurIPS 2017 abstract page for Krum (Blanchard et al.), abstract only.
- arXiv abstract page for Presotto et al. (arXiv:2104.08094) and Ek et al. (arXiv:2210.16918); ar5iv HTML full text of Ek et al. PerCom 2021 version (arXiv:2110.10223).

NOT OPENED / COULD NOT OPEN:
- Krum full paper, Bonawitz secure aggregation CCS 2017 final version (the arXiv v1 was read), Sozinov et al. 2018 "Human Activity Recognition using Federated Learning" (searches returned only citations of it; its abstract was NOT seen).
- The Flower page for the client-side mods (`fixedclipping_mod`, `adaptiveclipping_mod`) described nothing; the Flower differential-privacy how-to page timed out. Flower's stated behaviour of those mods is UNVERIFIED.
- Flower source code was not read. Flower was not run.
- No code in this repo was executed for this note; `ml-service/qc/federated.py` was only read.

## 1. FedAvg and what it reduces to with one client

1.1 Algorithm. In each round the server picks m = max(C x K, 1) of K clients, each client k runs E local epochs of SGD with minibatch size B on its own data starting from the current global weights, and the server sets the new global weights to the average of the returned client weights, weighted by n_k / m_t where n_k is client k's example count and m_t is the sum of n_k over the selected clients. Source: McMahan et al. 2017, Algorithm 1 (arXiv:1602.05629), including the note in the arXiv version history that v4 fixes a typo in the pseudocode.

1.2 FedSGD is the special case B = infinity (one full-batch step) and E = 1. Source: McMahan et al. 2017, Section 2 (arXiv:1602.05629).

1.3 One client per round is a case the paper itself runs: its Table 1 uses C = 0.0 to mean one client per round. Source: McMahan et al. 2017, Table 1 caption (arXiv:1602.05629).

1.4 DERIVED (from 1.1, not stated in the paper): with exactly one participating client the weights n_k / m_t equal 1, so the new global model is the client's locally trained model. Averaging does nothing, and the procedure is ordinary local fine-tuning of the previous global weights on that client's data. This matches the map's label "degenerate federation (fine-tuning with one client)". The server's job reduces to storing, versioning and validating that one update and handing the weights back.

1.5 Shared initialization matters for averaging. The paper shows that averaging two models trained from different random initializations gives a worse loss than either parent, while starting both from the same initialization averages well. Source: McMahan et al. 2017, Figure 1 and text (arXiv:1602.05629). DERIVED consequence for this prototype: every round must start from the server's current global weights (or one fixed published initial model), not from a fresh random phone-side init. With one client the averaging concern vanishes but the rule is cheap to keep.

1.6 The paper's scale and cost reasoning is explicitly about many clients: it motivates the method by upload bandwidth of about 1 MB/s or less, and clients volunteering only when charged, plugged in and on unmetered wi-fi, participating in a small number of rounds per day. Source: McMahan et al. 2017, Section 1 (arXiv:1602.05629). The 10x to 100x round reduction versus synchronized SGD in the abstract was measured on five model architectures and four datasets with many simulated clients; it says nothing about the single-client case.

1.7 Framework default (Flower). Flower's `FedAvg` strategy (in `flwr.serverapp.strategy`) weights by the key `num-examples` (parameter `weighted_by_key`) and its documented defaults for `min_train_nodes`, `min_evaluate_nodes` and `min_available_nodes` are all 2. Source: Flower reference page for FedAvg, read through a summarising tool. DERIVED, UNVERIFIED by running: a single-client run in Flower would need those minimums set to 1. The page did not say how arrays (model weights) are weighted beyond naming the key.

## 2. How the existing simulation in this repo relates

`ml-service/qc/federated.py` (read, not run) simulates federated training sequentially on one machine and states in its header that it "makes NO privacy claim: all data sits on one machine". Its clients are gauge-grid clients, its `average_states` computes a normalised weighted mean of state dicts (the same average as 1.1), and it has variants `fedpers` (average the body, keep a per-client head), `fedavg`, `fedft` (fedavg then per-client fine-tune) and `local`; `prox_mu > 0` adds a FedProx term. It does no update validation, clipping, secure aggregation or noise. Its model is the gridded rainfall QC network, which the map says cannot take phone data. So for the phone prototype the existing code is a reference for the averaging step only; the server-side validation described in sections 3 and 6 is NOT IMPLEMENTED anywhere in the repo.

## 3. Update validation: norm clipping and anomaly screening

3.1 Norm clipping of client updates. The server scales a client update so its L2 norm is at most a bound M: the update is divided by max(1, norm / M). Source: Sun et al. 2019, norm-clipping formula (arXiv:1911.07963). The same operation is the first step of user-level differential privacy in federated averaging, with a flat clip or a per-layer clip. Source: McMahan et al. 2018, FlatClip and PerLayerClip (arXiv:1710.06963).

3.2 Evidence it helps. On EMNIST with simulated adversaries, Sun et al. report that norm clipping and "weak" differential privacy (clipping plus small Gaussian noise) mitigate backdoor attacks without hurting overall performance. Source: Sun et al. 2019, abstract (arXiv:1911.07963). This is a simulated study on one dataset. The survey notes that edge-case backdoors reported by Wang et al. can bypass such defenses and that choosing the clip bound for a given model is still open. Source: Kairouz et al. 2019, section on defending against model update poisoning (arXiv:1912.04977; Wang et al. itself NOT OPENED, so the edge-case claim is UNVERIFIED at first hand).

3.3 Anomaly screening by the aggregator. Bagdasaryan et al. state that anomaly detection on participants' submitted updates is not possible when secure aggregation hides individual updates, and they show a "constrain-and-scale" attack in which the attacker adds an anomaly-evasion term to its loss, so that detectors looking at, for example, p-norm distance between weight matrices can be evaded. They also state that a train-and-scale attack evades detectors that only consider update magnitude. Source: Bagdasaryan et al. (arXiv:1807.00459), abstract and attack sections. Implication, DERIVED: magnitude screening is a sanity check against bugs and crude abuse, not a security guarantee; and screening individual updates is only possible if secure aggregation is NOT used. With one client and no secure aggregation, individual update inspection is available (and is how a prototype would do it).

3.4 Robust aggregators replace the mean with a robust estimate. Coordinate-wise median and trimmed mean (Yin et al. 2018, arXiv:1803.01498, abstract) and Krum (Blanchard et al., NeurIPS 2017, abstract page: linear-combination aggregators cannot tolerate even one Byzantine worker; Krum is proposed as a rule that can). The survey cautions that Fang et al. showed several such defenses did little against model poisoning in federated learning, so their guarantees may rest on assumptions not met in practice. Source: Kairouz et al. 2019 (arXiv:1912.04977; Fang et al. NOT OPENED, UNVERIFIED at first hand). DERIVED: these need several simultaneous client updates per round (a median of one value is that value), so they are inapplicable to the single-device prototype and belong under PLANNED if a multi-client mode is ever built. Flower lists Krum, MultiKrum, Bulyan, FedMedian and FedTrimmedAvg as built-in strategies and documents Krum's `num_malicious_nodes` parameter (default 0); only Krum's page was read. Source: Flower reference pages, summarising tool.

3.5 Non-malicious corruption is also a concern. The survey notes that noisy features or labels on a client can harm federated convergence, that these corruptions can be viewed as mild poisoning, and that cleaning the data on the server is unlikely in cross-device settings because of privacy restrictions. Source: Kairouz et al. 2019, section on non-malicious failure modes (arXiv:1912.04977). This is relevant here because tap labels are user-supplied.

3.6 Authenticity of the sender. Google's production system uses Android remote attestation to check that updates come from genuine devices and apps, which it says gives "some protection" against data poisoning from compromised devices; it explicitly leaves content-farm style manipulation by uncompromised phones out of scope. Source: Bonawitz et al. 2019, Attestation paragraph (arXiv:1902.01046). Whether a free-tier prototype can use Play Integrity or an equivalent is UNVERIFIED (not researched here); label device authentication PLANNED or NOT IMPLEMENTED unless built.

3.7 Not claimed in any source above: that any specific clip bound is right for a tiny pressure-tendency model. The bound would have to be chosen from the model's own observed update norms (measured, not assumed) before it is described as a defense.

## 4. Secure aggregation and differential privacy (to know what to label PLANNED)

4.1 Secure aggregation is a multi-party protocol that lets a server learn only the sum of many clients' vectors, not any single one. The 2017 protocol tolerates up to 1/3 of users failing to complete it and reports 1.73x communication expansion for 2^10 users with 2^20-dimensional vectors of 16-bit values, and 1.98x for 2^14 users with 2^24-dimensional vectors. Source: Bonawitz et al. (arXiv:1611.04482), abstract. The protocol runs as four interactive rounds. Source: Bonawitz et al. 2019, Section 6 (arXiv:1902.01046). Per-user cost is quadratic in the number of users in the first round for the server (O(n^2 + kn)) as listed in the paper's cost table. Source: arXiv:1611.04482 table (extraction was messy; treat the exact big-O entries as UNVERIFIED and check against the paper).

4.2 DERIVED: secure aggregation hides an individual update within a sum of at least k updates (Google's deployment aggregates in groups of at least k, a task parameter; source: arXiv:1902.01046, Section 6). With one client the "sum" is that client's update, so secure aggregation provides nothing. It is NOT IMPLEMENTED and not applicable to this prototype; the app must not describe uploads as "securely aggregated".

4.3 Central differential privacy in federated averaging: per-user updates are clipped to bounded L2 norm, aggregated, and Gaussian noise is added to the aggregate; privacy loss is tracked with a moments accountant. Source: McMahan et al. 2018 (arXiv:1710.06963), algorithm and Section 3; Kairouz et al. 2019, Section 4.3.2 (arXiv:1912.04977). The authors find that, given a dataset with a sufficiently large number of users, private training costs extra computation rather than accuracy (abstract). That caveat matters: the claim depends on a large user population. DERIVED: with one user the noise-to-signal ratio needed for a meaningful guarantee would swamp the update, and the guarantee is per user, so central DP is NOT IMPLEMENTED and is not a meaningful claim for the prototype. Flower provides wrappers (`DifferentialPrivacyServerSideFixedClipping` and adaptive/client-side variants) whose documented parameters are `noise_multiplier`, `clipping_norm` and `num_sampled_clients`, with an optional accountant; the Flower page states central DP requires trusting the server. Source: Flower reference and explanation pages, summarising tool.

4.4 Labelling guidance, DERIVED from the above: what the prototype may truthfully say is that raw readings stay on the phone and only weights leave. It must not say "private", "secure aggregation", "differentially private" or "anonymous". Model updates can still leak information about training data (the privacy motivation of secure aggregation and DP in the sources above); no source opened here quantifies the leakage for a tiny barometer model, so any statement about it is UNVERIFIED.

## 5. Update formats and sizes in mobile settings

5.1 What is sent. In FedAvg the client returns its full local weights (Algorithm 1: `return w to server`). Source: arXiv:1602.05629. In the DP variant of McMahan et al. 2018 the client returns a clipped difference from the starting weights (`ClipFn(theta - theta0)`, "update already clipped"). Source: arXiv:1710.06963, UserUpdateFedAvg. Weights and deltas are the same size; the delta form is what clipping and compression operate on.

5.2 Sizes. Google's production system reports that updates collected per round range from kilobytes to tens of megabytes. Source: Bonawitz et al. 2019, Section 4 (arXiv:1902.01046). The Gboard next-word model has 1.4 million parameters and is 1.4 MB after weight quantization on the device. Source: Hard et al. 2018 (arXiv:1811.03604). A model for rain onset from a handful of pressure-tendency features would be far smaller, but its size is not stated in any source and is ASSUMED until the architecture is chosen; compute it from the parameter count when it exists (parameters x bytes per parameter, DERIVED).

5.3 Compression exists but is unnecessary at this size, DERIVED. Konecny et al. propose structured updates (low-rank, random mask) and sketched updates (quantization, random rotations, subsampling), reporting communication cost reductions of up to two orders of magnitude in their experiments. Source: arXiv:1610.05492, abstract. A kilobyte-scale update does not need it; compression adds code and a reason to doubt what was sent. Do not add it until a measured size shows a need.

5.4 Wire format and framework details of Google's system are not a specification for this prototype: that paper describes plans, TensorFlow graphs and actors for a production system. A simple documented format (weights as a flat float32 array with a model identifier, version, parameter count, number of local examples and the round or base-version it started from) is a design choice, not something a source prescribes. The fields are suggested by what FedAvg's weighting needs (n_k, from 1.1) and by 1.5 (the base model). UNVERIFIED that any particular serialization is "standard".

5.5 Client eligibility in practice. Both Google systems train only while the device is idle, charging and on an unmetered network, via Android's JobScheduler, aborting if the conditions stop holding. Sources: Bonawitz et al. 2019, Section 3 (arXiv:1902.01046); Hard et al. 2018 (arXiv:1811.03604, devices participate only if charging, on an unmetered network and idle). This is the same set of conditions the map chose.

5.6 Rounds are slow even at scale. Hard et al. report that training the federated keyboard model typically takes 4 to 5 days (arXiv:1811.03604). One device may take part in a small number of rounds per day (arXiv:1602.05629, Section 1). DERIVED: a single phone will produce a handful of updates per week at most under the charging/idle/Wi-Fi rule, so a prototype's update log will be sparse and any evaluation should be planned around that.

## 6. Evidence on federated learning from phone sensor data

6.1 Large deployments are on keyboard text, not sensors. The two Google phone studies opened (Hard et al. next-word prediction; Bonawitz et al. system design) are on text typed on phones. The survey lists cross-device uses in Gboard, Android Messages, Apple iOS 13 (QuickType, "Hey Siri" classifier) and others. Source: Kairouz et al. 2019, Section 1.1 (arXiv:1912.04977). None of these is a sensor-tendency or weather model. I found no deployment report on barometer data in the sources opened; this is a gap, not a negative finding (search was limited).

6.2 Human activity recognition (HAR) from phone and watch IMU data is the closest sensor evidence opened. Ek et al. (PerCom 2021, arXiv:2110.10223; journal version Pervasive and Mobile Computing 87, 2022, arXiv:2210.16918) use the REALWORLD dataset (about 125 hours, 15 subjects, accelerometer and gyroscope at 50 Hz, Samsung Galaxy S4 and LG G Watch R, 8 activities) with each participant as a client. In simulation on a GPU, with F-scores reported: centralized 92.48%, FedAvg 83.44% on the server-side global test, local-only 51.94% on the global test set versus FedAvg 72.99%. The authors say they tried a Google Pixel 2 for feasibility but report no results. Source: ar5iv full text of arXiv:2110.10223. Reading, DERIVED: on real phone sensor data with person-specific distributions, federated averaging beat local-only for generalization but stayed below centralized training, and the study did not train on phones.

6.3 Presotto et al. (FedAR, Personal and Ubiquitous Computing 26(5), 2022, arXiv:2104.08094) address scarce labels for sensor HAR by combining active learning, label propagation and federated learning with per-user fine-tuning, evaluated on two public datasets; whether clients were real phones or partitions was NOT stated on the abstract page (UNVERIFIED; full text not opened). Relevance: it concerns few, user-supplied labels, which is the situation of tap labels.

6.4 Sozinov et al. 2018 (HAR with federated learning) is cited by later papers as having examined the trade-off between communication cost and model complexity and proposing a method for rejecting erroneous clients, but that is a second-hand description from one citing paper; the paper itself was NOT opened. UNVERIFIED.

6.5 What the evidence does not cover, so the prototype must not claim it: federated or on-device training of a pressure-tendency rain-onset model; learning from tap labels with unknown noise; results for one device. All simulated studies above used many clients.

## 7. Implications for the prototype (DERIVED from sections 1 to 6; design suggestions, not sourced facts)

- Name it correctly: single-client "federation" is on-device fine-tuning with a server that stores the result (1.4). Do not describe the server step as aggregation of many devices.
- Server-side update checks that are meaningful with one update and are cheap: reject files with wrong model id, version or parameter count; reject NaN or infinite values; compare the update's L2 norm (and per-layer norm) with a bound chosen from observed norms (measured), clip or reject beyond it; require a plausible example count; keep the raw update and any corrected or clipped version separately (matches `AGENTS.md` section 6, raw data is never overwritten). Label these as sanity checks, not security (3.3).
- Keep a per-run record of base-model version, update norm, example count and whether the update was accepted, clipped or rejected, with the reason (evidence behind every decision).
- PLANNED / NOT IMPLEMENTED labels: secure aggregation (4.2), central or local DP (4.3), robust multi-client aggregators (3.4), device attestation (3.6), update compression (5.3), multi-device federation, any statement of privacy guarantees (4.4).
- Do not claim the phone model improves anything until it is evaluated with the repo's evaluation rules (`AGENTS.md` section 9).

## 8. Open uncertainties

- Update size of the planned model: not known until the architecture is chosen (5.2).
- Whether Play Integrity or similar attestation is usable on a free-tier prototype (3.6): not researched.
- Whether per-layer or flat clipping suits a small model, and what bound: unmeasured (3.7).
- The exact big-O cost entries of the secure aggregation protocol (4.1): extraction was garbled.
- Flower's single-client behaviour and client-side clipping mods (1.7, banner): not run, partly unread.
- Edge-case backdoor results (Wang et al.) and the finding that robust aggregators fail (Fang et al.): second-hand via the survey.
- Sozinov et al. and Presotto et al. details (6.3, 6.4): unread.
- No phone-barometer federated-learning source was found (6.1).

## Source list

- McMahan, Moore, Ramage, Hampson, Agueera y Arcas. Communication-Efficient Learning of Deep Networks from Decentralized Data. AISTATS 2017. https://arxiv.org/abs/1602.05629
- Bonawitz et al. Towards Federated Learning at Scale: System Design. 2019. https://arxiv.org/abs/1902.01046
- Bonawitz et al. Practical Secure Aggregation for Federated Learning on User-Held Data. https://arxiv.org/abs/1611.04482
- McMahan, Ramage, Talwar, Zhang. Learning Differentially Private Recurrent Language Models. ICLR 2018. https://arxiv.org/abs/1710.06963
- Sun, Kairouz, Suresh, McMahan. Can You Really Backdoor Federated Learning? 2019. https://arxiv.org/abs/1911.07963
- Bagdasaryan, Veit, Hua, Estrin, Shmatikov. How To Backdoor Federated Learning. https://arxiv.org/abs/1807.00459
- Yin, Chen, Ramchandran, Bartlett. Byzantine-Robust Distributed Learning: Towards Optimal Statistical Rates. https://arxiv.org/abs/1803.01498
- Blanchard, El Mhamdi, Guerraoui, Stainer. Machine Learning with Adversaries: Byzantine Tolerant Gradient Descent. NIPS 2017. https://papers.nips.cc/paper/2017/hash/f4b9ec30ad9f68f89b29639786cb62ef-Abstract.html
- Hard et al. Federated Learning for Mobile Keyboard Prediction. 2018. https://arxiv.org/abs/1811.03604
- Konecny, McMahan, Yu, Richtarik, Suresh, Bacon. Federated Learning: Strategies for Improving Communication Efficiency. https://arxiv.org/abs/1610.05492
- Kairouz et al. Advances and Open Problems in Federated Learning. https://arxiv.org/abs/1912.04977
- Ek, Portet, Lalanda, Vega. A Federated Learning Aggregation Algorithm for Pervasive Computing: Evaluation and Comparison (PerCom 2021). https://arxiv.org/abs/2110.10223 ; journal version https://arxiv.org/abs/2210.16918
- Presotto, Civitarese, Bettini. Personalized Semi-Supervised Federated Learning for Human Activity Recognition. https://arxiv.org/abs/2104.08094
- Flower framework reference (FedAvg, Krum, DifferentialPrivacyServerSideFixedClipping, differential privacy explanation). https://flower.ai/docs/framework/ref-api/flwr.server.strategy.FedAvg.html and sibling pages under https://flower.ai/docs/framework/
