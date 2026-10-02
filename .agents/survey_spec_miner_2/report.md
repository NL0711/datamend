# SkyGuard AI — Specification & Mathematical Mining Report

**Agent**: `survey_spec_miner_2`  
**Date**: 2026-08-24  
**Workspace**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard`  
**Target Specification Scope**: Diurnal simulation formulas, anomaly injection mathematics, 5-tier ML anomaly detection pipeline, fault classification taxonomy, sensor health index formulation, explainability engine, fusion logic, and edge cases.

---

## 1. Executive Summary & Core Objective

SkyGuard AI is a production-grade, real-time quality control (QC), anomaly detection, fault classification, and sensor health platform for Automatic Weather Stations (AWS). The system is strictly constrained to process three primary meteorological parameters:
- **Temperature ($T$)** in degrees Celsius ($^\circ\text{C}$)
- **Atmospheric Pressure ($P$)** in hectopascals ($\text{hPa}$)
- **Relative Humidity ($RH$)** in percentage ($\%$)

This specification mining report defines the exact mathematical formulations, thermodynamic laws, statistical algorithms, machine learning architectures, and decision-tree classification rules required to build a fully executable, non-faked system adhering to `AGENTS.md`, `ARCHITECTURE.md`, `GOAL.md`, and `TODO.md`.

---

## 2. Diurnal Cycle Simulation Engine Specification

The simulation engine (`backend/simulator/diurnal_generator.py`) generates physically realistic, continuous AWS telemetry exhibiting standard diurnal cycles, synoptic weather fluctuations, thermal atmospheric tides, and thermodynamic cross-correlations.

### 2.1 Time Parameterization
Let:
- $t \ge 0$: Discrete time step index (seconds or minutes elapsed).
- $\Delta t$: Sampling interval in minutes (standard AWS interval: $\Delta t = 5\text{ minutes}$).
- $h(t) \in [0, 24)$: Continuous hour of the day:
  $$h(t) = \left( \frac{t \cdot \Delta t}{60} + h_0 \right) \pmod{24}$$
- $d(t) \in \mathbb{N}$: Day index:
  $$d(t) = \left\lfloor \frac{t \cdot \Delta t}{1440} \right\rfloor$$

---

### 2.2 Diurnal Temperature Formulation ($T$)
The diurnal temperature cycle is driven by solar radiative heating with a characteristic phase lag:
- Minimum temperature occurs at solar sunrise ($h_{\text{min}} \approx 06:00$).
- Maximum temperature occurs post-solar noon ($h_{\text{max}} \approx 14:30 - 15:00$) due to surface thermal inertia.

#### Mathematical Model:
$$T(t) = T_{\text{mean}} + A_{\text{seasonal}} \sin\left(\frac{2\pi d(t)}{365} + \phi_{\text{season}}\right) + A_T \cdot f_T(h(t)) + \eta_T(t)$$

Where the diurnal waveform $f_T(h)$ is modeled as an asymmetric cosine wave:
$$f_T(h) = \sin\left( \frac{2\pi (h - 9.0)}{24} \right)$$
- At $h = 15:00$ (3:00 PM), $\sin\left(\frac{2\pi \cdot 6}{24}\right) = \sin\left(\frac{\pi}{2}\right) = +1.0$ (Peak maximum).
- At $h = 03:00$ (3:00 AM), $\sin\left(\frac{2\pi \cdot (-6)}{24}\right) = \sin\left(-\frac{\pi}{2}\right) = -1.0$ (Night minimum).

#### Correlated Thermal Noise $\eta_T(t)$:
Thermal noise follows a stationary first-order Autoregressive process $\text{AR}(1)$ to emulate atmospheric turbulence:
$$\eta_T(t) = \rho_T \cdot \eta_T(t-1) + \sqrt{1 - \rho_T^2} \cdot \epsilon_T(t), \quad \epsilon_T(t) \sim \mathcal{N}(0, \sigma_T^2)$$
- Default parameters: $T_{\text{mean}} = 22.0^\circ\text{C}$, $A_T = 6.5^\circ\text{C}$, $\rho_T = 0.85$, $\sigma_T = 0.35^\circ\text{C}$.

---

### 2.3 Atmospheric Pressure Formulation ($P$)
Atmospheric pressure comprises:
1. Synoptic base pressure $P_0$ modulated by multi-day planetary Rossby waves (period $\tau_{\text{synoptic}} \approx 3 - 7\text{ days}$).
2. Semi-diurnal atmospheric thermal tides with a 12-hour period (peaks at ~10:00 and ~22:00 local time, troughs at ~04:00 and ~16:00 local time).

#### Mathematical Model:
$$P(t) = P_0 + A_{\text{synoptic}} \sin\left(\frac{2\pi t \cdot \Delta t}{1440 \cdot \tau_{\text{synoptic}}} + \phi_{\text{syn}}\right) + A_{\text{tide}} \cos\left(\frac{4\pi (h(t) - 10.0)}{24}\right) + \eta_P(t)$$

#### Noise Model:
$$\eta_P(t) = \rho_P \cdot \eta_P(t-1) + \sqrt{1 - \rho_P^2} \cdot \epsilon_P(t), \quad \epsilon_P(t) \sim \mathcal{N}(0, \sigma_P^2)$$
- Default parameters: $P_0 = 1013.25\text{ hPa}$, $A_{\text{synoptic}} = 8.0\text{ hPa}$, $\tau_{\text{synoptic}} = 5\text{ days}$, $A_{\text{tide}} = 1.2\text{ hPa}$, $\rho_P = 0.90$, $\sigma_P = 0.15\text{ hPa}$.

---

### 2.4 Relative Humidity Formulation ($RH$) & Thermodynamic Coupling
Relative humidity is governed by the Clausius-Clapeyron relation. Under constant atmospheric moisture (steady dew point $T_d$), saturation vapor pressure $e_s(T)$ increases exponentially with temperature, causing $RH$ to drop during the afternoon peak and peak near sunrise.

#### Saturation Vapor Pressure $e_s(T)$ (Magnus-Tetens Formula):
$$e_s(T) = 6.112 \cdot \exp\left( \frac{17.67 \cdot T}{T + 243.5} \right) \quad [\text{hPa}]$$

#### Dew Point & Actual Vapor Pressure:
Let base dew point be $T_d \approx T_{\text{mean}} - 6.0^\circ\text{C}$. The baseline vapor pressure is:
$$e = e_s(T_d) = 6.112 \cdot \exp\left( \frac{17.67 \cdot T_d}{T_d + 243.5} \right) \quad [\text{hPa}]$$

#### Relative Humidity Equation:
$$RH_{\text{raw}}(t) = \left( \frac{e}{e_s(T(t))} \right) \times 100\% + \eta_{RH}(t)$$
$$RH(t) = \text{clip}\left( RH_{\text{raw}}(t), 5.0, 100.0 \right)$$
- Default parameters: $\rho_{RH} = 0.85$, $\sigma_{RH} = 1.2\%$.

---

## 3. Anomaly Injection Engine Specification

The anomaly injector (`backend/simulator/anomaly_injector.py`) injects controlled, ground-truth labeled perturbations into clean time series.

### 3.1 Formal Anomaly Taxonomy & Mathematical Formulas

| Anomaly Type | Mathematical Injection Formulation | Parameter Range | Description | Ground Truth Label |
|---|---|---|---|---|
| **Spike (Impulse)** | $x'(t) = x(t) + \Delta x \cdot \mathbf{1}_{\{t \in [t_{\text{start}}, t_{\text{start}}+k-1]\}}$ | $\Delta x_T \in [\pm 8, \pm 25]^\circ\text{C}$<br>$\Delta x_P \in [\pm 15, \pm 50]\text{ hPa}$<br>$\Delta x_{RH} \in [\pm 30, \pm 60]\%$<br>$k \in [1, 3]\text{ steps}$ | Sudden transient impulse returning quickly to baseline. | `SPIKE` |
| **Linear Drift** | $x'(t) = x(t) + \alpha \cdot (t - t_{\text{start}}) \cdot \mathbf{1}_{\{t \ge t_{\text{start}}\}}$ | $\alpha_T \in [\pm 0.05, \pm 0.2]^\circ\text{C}/\text{step}$<br>$\Delta x_{\text{max}} \in [3, 15]^\circ\text{C}$ | Progressive calibration degradation offset accumulating over time. | `DRIFT` |
| **Frozen Sensor** | $x'(t) = x(t_{\text{start}}) \quad \forall t \in [t_{\text{start}}, t_{\text{end}}]$ | Duration: $L \in [12, 144]\text{ steps}$ (1 hour to 12 hours) | Constant stuck value with zero empirical variance. | `FROZEN` |
| **Dropout / Missing** | $x'(t) \in \{\text{NaN}, 0.0, -999.0\} \quad \forall t \in [t_{\text{start}}, t_{\text{end}}]$ | Duration: $L \in [1, 24]\text{ steps}$ | Total sensor electrical failure, null payload, or missing packet. | `DROPOUT` |
| **Noise Burst** | $x'(t) = x(t) + \xi(t), \quad \xi(t) \sim \mathcal{N}(0, k^2 \sigma_x^2)$ | Noise multiplier: $k \in [5, 15]$<br>Duration: $L \in [10, 50]\text{ steps}$ | High-frequency jitter surge indicating grounding/EMI fault. | `DATA_CORRUPTION` |
| **Multivariate Inconsistency** | Perturb $T \uparrow$ by $+15^\circ\text{C}$ and $RH \uparrow$ by $+40\%$ simultaneously without storm pressure drop ($P$ unchanged). | $T' = T + 12^\circ\text{C}, RH' = 98\%, P' = P_0$ | Physical violation of Clausius-Clapeyron relations. | `MULTIVARIATE_INCONSISTENCY` |
| **Meteorological Extreme** | Rapid drop in $T$ ($\Delta T = -8^\circ\text{C}/15\text{ min}$), sharp $P$ dip ($\Delta P = -6\text{ hPa}/15\text{ min}$), and $RH \uparrow 95\%$ | Plausible thermodynamic correlation: $T_d \le T$, $e \le e_s(T)$ | Genuine severe convective storm / squall line (not a fault). | `METEOROLOGICAL_EXTREME` |
| **Data Corruption** | Corrupt string `"$ERR_NaN#"`, duplicate timestamp, or bit-flip: $x' = x \oplus \text{0x7F800000}$ | String / non-numeric / negative timestamp | Payload transmission / ADC register bit corruption. | `DATA_CORRUPTION` |

---

## 4. 5-Tier ML Anomaly Detection Pipeline Architecture

The anomaly detection pipeline (`backend/app/ml/`) executes a strictly layered architecture from deterministic physics bounds to multivariate ML and explainability.

```
                    Raw Observation (T, P, RH, timestamp)
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ TIER 1: Deterministic Quality Control & Physics │
             └────────────────────────┬─────────────────────────┘
                                      │ Passes basic physics
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ TIER 2: Point & Temporal ML                     │
             │  - Isolation Forest / One-Class SVM (Point)      │
             │  - PyTorch GRU/LSTM Autoencoder (Temporal MSE)   │
             └────────────────────────┬─────────────────────────┘
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ TIER 3: Multivariate Thermodynamic Consistency   │
             │  - Clausius-Clapeyron & Dew Point Violation     │
             │  - Mahalanobis Distance / Chi-Square CDF         │
             └────────────────────────┬─────────────────────────┘
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ ANOMALY FUSION LAYER                             │
             │  - Unified Anomaly Score (0-1)                   │
             │  - Decision Confidence (0-1)                     │
             │  - Severity Level (LOW/MED/HIGH/CRITICAL)        │
             └────────────────────────┬─────────────────────────┘
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ TIER 4: Fault Classification Engine              │
             │  - Rule-ML Hybrid Decision Classifier            │
             └────────────────────────┬─────────────────────────┘
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ TIER 5: Sensor Health Index & SHAP Explainability│
             │  - Dynamic SHI (0-100) Formulation               │
             │  - SHAP Attribution & Human-Readable Reasons     │
             └──────────────────────────────────────────────────┘
```

---

### 4.1 Tier 1: Deterministic Quality Control & Physics Plausibility Engine

#### 1. Range Validation (Physical Bounds)
- Temperature: $T_{\text{valid}} \iff -40.0^\circ\text{C} \le T \le +60.0^\circ\text{C}$
- Atmospheric Pressure: $P_{\text{valid}} \iff 300.0\text{ hPa} \le P \le 1100.0\text{ hPa}$
- Relative Humidity: $RH_{\text{valid}} \iff 0.0\% \le RH \le 104.0\%$ (allowing $4\%$ sensor tolerance for supersaturation)

If $x \notin [x_{\min}, x_{\max}]$, flag immediately with $S_{\text{Tier1}} = 1.0$, Severity = `CRITICAL`, Classification = `SPIKE` or `DATA_CORRUPTION`.

#### 2. Rate of Change (Step Limits)
Given step interval $\Delta t = 5\text{ min}$:
- $|\Delta T| = |T_t - T_{t-1}| \le 5.0^\circ\text{C} \quad (1.0^\circ\text{C}/\text{min})$
- $|\Delta P| = |P_t - P_{t-1}| \le 3.0\text{ hPa} \quad (0.6\text{ hPa}/\text{min})$
- $|\Delta RH| = |RH_t - RH_{t-1}| \le 25.0\% \quad (5.0\%/\text{min})$

#### 3. Persistence & Frozen Sensor Check
Over a rolling window of $K = 6$ consecutive steps (30 minutes):
$$\text{Var}(x_{t-K+1:t}) = \frac{1}{K} \sum_{i=0}^{K-1} (x_{t-i} - \bar{x})^2 < 10^{-6} \implies \text{Flag as FROZEN}$$

#### 4. Completeness, Format & Monotonicity Check
- Check for `NaN`, `None`, empty string, non-numeric ASCII, and duplicate timestamps ($t_i \le t_{i-1}$).

---

### 4.2 Tier 2: Point & Temporal ML Anomaly Detection

#### 4.2.1 Point Anomaly Detection (Isolation Forest / One-Class SVM)
- **Input Feature Vector**:
  $$\mathbf{z}_t = \left[ \tilde{T}_t, \tilde{P}_t, \widetilde{RH}_t, \Delta \tilde{T}_t, \Delta \tilde{P}_t, \Delta \widetilde{RH}_t, \sigma_{T, W}, \sigma_{P, W}, \sigma_{RH, W} \right]^T \in \mathbb{R}^9$$
  where $\tilde{x} = \frac{x - \mu_x}{\sigma_x}$ is z-score normalized.
- **Isolation Forest Score Formulation**:
  $$s(\mathbf{z}, n) = 2^{ -\frac{\mathbb{E}(h(\mathbf{z}))}{c(n)} }$$
  where $h(\mathbf{z})$ is the path length across $n_{\text{trees}} = 100$ isolation trees, and average path length of unsuccessful search is:
  $$c(n) = 2 \left( \ln(n - 1) + 0.5772156649 \right) - \frac{2(n - 1)}{n}$$
- **Normalized Point Anomaly Score**:
  $$S_{\text{point}}(t) = \text{clip}\left( \frac{s(\mathbf{z}_t, n) - 0.5}{0.5}, 0.0, 1.0 \right)$$

#### 4.2.2 Temporal ML Anomaly Detection (PyTorch GRU/LSTM Autoencoder)
- **Sliding Window Input**:
  $$\mathbf{X}_t = \begin{bmatrix} \mathbf{x}_{t-W+1} \\ \mathbf{x}_{t-W+2} \\ \vdots \\ \mathbf{x}_t \end{bmatrix} \in \mathbb{R}^{W \times 3}, \quad W = 30 \text{ steps (2.5 hours)}$$
- **Architecture**:
  - **Encoder**: $\mathbf{h}_w = \text{GRU}_{\text{enc}}(\mathbf{x}_{t-W+w}, \mathbf{h}_{w-1})$, Hidden Dimension $H = 32$, Latent Bottleneck $\mathbf{z}_{\text{latent}} = \mathbf{h}_W \in \mathbb{R}^{16}$.
  - **Decoder**: $\mathbf{\hat{x}}_{t-W+w} = \text{Linear}(\text{GRU}_{\text{dec}}(\mathbf{z}_{\text{latent}}, \mathbf{h}'_{w-1}))$, Hidden Dimension $H = 32$.
- **Reconstruction Error at Step $t$**:
  $$e_t = \frac{1}{3} \sum_{j \in \{T, P, RH\}} \left( \frac{x_{t, j} - \hat{x}_{t, j}}{\sigma_j} \right)^2$$
- **Temporal Anomaly Score**:
  Using baseline validation error threshold $\theta_{\text{temporal}} = \mu_{\text{train\_error}} + 3 \cdot \sigma_{\text{train\_error}}$:
  $$S_{\text{temporal}}(t) = \min\left(1.0, \; \frac{e_t}{\theta_{\text{temporal}}}\right)$$

---

### 4.3 Tier 3: Multivariate Thermodynamic & Statistical Consistency

#### 4.3.1 Thermodynamic Clausius-Clapeyron Constraint
- Dew point temperature $T_d$ calculated from $T$ and $RH$:
  $$\gamma(T, RH) = \frac{17.67 \cdot T}{T + 243.5} + \ln\left(\frac{RH}{100.0}\right)$$
  $$T_d(t) = \frac{243.5 \cdot \gamma(T_t, RH_t)}{17.67 - \gamma(T_t, RH_t)}$$
- **Thermodynamic Violation Criterion**:
  Under atmospheric physical equilibrium:
  $$T_d(t) \le T(t) + 0.5^\circ\text{C}$$
  If $T_d(t) > T(t) + 0.5^\circ\text{C}$ (implying unphysical supersaturation $RH > 104\%$), calculate physical discrepancy:
  $$\Delta_{\text{thermo}}(t) = \max\left(0.0, \; T_d(t) - T(t)\right)$$
  $$S_{\text{thermo}}(t) = \min\left(1.0, \; \frac{\Delta_{\text{thermo}}(t)}{3.0}\right)$$

#### 4.3.2 Mahalanobis Distance & Chi-Square CDF
- Mean vector $\boldsymbol{\mu} = [\mu_T, \mu_P, \mu_{RH}]^T$, Covariance Matrix $\boldsymbol{\Sigma} \in \mathbb{R}^{3 \times 3}$.
- Mahalanobis Distance:
  $$D_M(\mathbf{x}_t) = \sqrt{ (\mathbf{x}_t - \boldsymbol{\mu})^T \boldsymbol{\Sigma}^{-1} (\mathbf{x}_t - \boldsymbol{\mu}) }$$
- For $k = 3$ degrees of freedom, $D_M^2 \sim \chi^2(3)$.
- The cumulative probability (p-value complement) gives the statistical multivariate score:
  $$S_{\text{mahalanobis}}(t) = F_{\chi^2(3)}(D_M^2(t)) = \frac{\gamma(1.5, D_M^2(t) / 2)}{\Gamma(1.5)}$$
- Combined Tier 3 Score:
  $$S_{\text{Tier3}}(t) = \max\left( S_{\text{thermo}}(t), \; S_{\text{mahalanobis}}(t) \right)$$

---

### 4.4 Anomaly Fusion Formulation

The anomaly fusion engine combines evidence across all tiers into three standardized outputs:
1. Unified Anomaly Score $S_{\text{fused}} \in [0.0, 1.0]$
2. Decision Confidence $C_{\text{fused}} \in [0.0, 1.0]$
3. Severity Level $\in \{\text{LOW}, \text{MEDIUM}, \text{HIGH}, \text{CRITICAL}\}$

#### 4.4.1 Fused Anomaly Score:
$$S_{\text{fused}}(t) = \begin{cases}
1.0 & \text{if } S_{\text{Tier1}}(t) = 1.0 \text{ (Deterministic Override)} \\
w_1 S_{\text{point}} + w_2 S_{\text{temporal}} + w_3 S_{\text{Tier3}} + w_{\text{int}} (S_{\text{temporal}} \cdot S_{\text{Tier3}}) & \text{otherwise}
\end{cases}$$
- Calibrated weights: $w_1 = 0.25, w_2 = 0.35, w_3 = 0.25, w_{\text{int}} = 0.15$ (sum = 1.00).

#### 4.4.2 Decision Confidence:
Confidence measures the concordance/agreement across models penalized by missing context:
$$C_{\text{fused}}(t) = 1.0 - \sqrt{ \frac{(S_{\text{point}} - \bar{S})^2 + (S_{\text{temporal}} - \bar{S})^2 + (S_{\text{Tier3}} - \bar{S})^2}{3} } \cdot \sqrt{2} - \text{Penalty}_{\text{buffer}}$$
- If feature history buffer $< 30$ steps, $\text{Penalty}_{\text{buffer}} = 0.20$, otherwise $0.0$.
- $C_{\text{fused}}$ is clipped to $[0.10, 1.00]$.

#### 4.4.3 Severity Mapping:
$$\text{Severity}(t) = \begin{cases}
\text{CRITICAL} & \text{if } S_{\text{Tier1}} = 1.0 \text{ or } S_{\text{fused}} \ge 0.90 \\
\text{HIGH} & \text{if } 0.75 \le S_{\text{fused}} < 0.90 \\
\text{MEDIUM} & \text{if } 0.50 \le S_{\text{fused}} < 0.75 \\
\text{LOW} & \text{if } 0.30 \le S_{\text{fused}} < 0.50 \\
\text{NONE} & \text{if } S_{\text{fused}} < 0.30
\end{cases}$$

---

### 4.5 Tier 4: Fault Classification Logic & Taxonomy

The fault classifier determines the root cause of the anomaly.

```
                    Is S_fused >= 0.30 (Anomaly Detected)?
                                      │
                     YES              ▼              NO
                      ┌───────────────┴───────────────┐
                      │                               │
                      ▼                               ▼
     Check Deterministic Tier 1 Flags              NORMAL
                      │
       ┌──────────────┼───────────────────────────┐
       │ NaN / Null   │ Var(x) == 0 for >= 6 steps │ Range Bound Viol.
       ▼              ▼                           ▼
    DROPOUT        FROZEN                      SPIKE / CORRUPT
       │
       ▼ (If Tier 1 Clean)
     Check Temporal Transition Duration
       │
       ├─ Duration 1-2 steps with high Delta-x ─────────► SPIKE
       │
       ├─ Duration >= 15 steps with continuous slope ───► DRIFT
       │
       ├─ Noise variance > 5x nominal ──────────────────► DATA_CORRUPTION
       │
       ├─ Thermodynamic violation (CC / Dew point) ─────► MULTIVARIATE_INCONSISTENCY
       │
       └─ High Delta-T & Delta-P but CC Holds (Storm) ──► METEOROLOGICAL_EXTREME
```

#### Grounded Meteorological Extreme Discrimination Rule:
An event is classified as `METEOROLOGICAL_EXTREME` if and only if:
1. $S_{\text{fused}} \ge 0.50$
2. Physical bounds are NOT violated: $-40 \le T \le 60, 300 \le P \le 1100, 0 \le RH \le 100$.
3. Clausius-Clapeyron consistency holds: $T_d \le T + 0.5^\circ\text{C}$.
4. Multivariate correlation aligns with convective front dynamics:
   $$(\Delta T < -3.0^\circ\text{C}/15\text{min}) \land (\Delta P < -2.0\text{ hPa}/15\text{min} \lor \Delta P > +2.0\text{ hPa}/15\text{min}) \land (\Delta RH > +15\%)$$
If condition (4) fails while $S_{\text{Tier3}}$ is high, it is classified as `MULTIVARIATE_INCONSISTENCY`.

---

### 4.6 Tier 5: Sensor Health Index (SHI) & SHAP Explainability

#### 4.6.1 Sensor Health Index (SHI) Formulation
Sensor Health is computed dynamically over a rolling evaluation window $W_{\text{health}} = 288\text{ steps}$ (past 24 hours):

$$\text{SHI}_{\text{raw}}(t) = 100.0 \cdot \left[ 1.0 - \left( w_A R_{\text{anomaly}} + w_F R_{\text{frozen}} + w_D S_{\text{drift}} + w_Q R_{\text{missing}} + w_S \bar{S}_{\text{sev}} \right) \right]$$

Where:
- $R_{\text{anomaly}} = \frac{\text{Count of anomalous steps in } W_{\text{health}}}{W_{\text{health}}}$
- $R_{\text{frozen}} = \frac{\text{Count of frozen steps in } W_{\text{health}}}{W_{\text{health}}}$
- $S_{\text{drift}} = \text{clip}\left( \frac{|\mu_{T, W_{\text{health}}} - \mu_{T, \text{baseline}}|}{5.0}, 0.0, 1.0 \right)$
- $R_{\text{missing}} = \frac{\text{Count of null/missing steps in } W_{\text{health}}}{W_{\text{health}}}$
- $\bar{S}_{\text{sev}} = \frac{1}{W_{\text{health}}} \sum_{\tau = t - W_{\text{health}} + 1}^t S_{\text{fused}}(\tau)$
- Calibrated Weights: $w_A = 0.30, w_F = 0.25, w_D = 0.20, w_Q = 0.15, w_S = 0.10$ (sum = 1.00).

#### EMA Smoothing:
To prevent jitter from isolated transient spikes:
$$\text{SHI}(t) = \alpha_{\text{health}} \cdot \text{SHI}_{\text{raw}}(t) + (1 - \alpha_{\text{health}}) \cdot \text{SHI}(t-1), \quad \alpha_{\text{health}} = 0.10$$

#### Health Status & Operational Action Mapping:
| Health Score ($\text{SHI}$) | Status Tier | Badge Color | Recommended Operator Action |
|---|---|---|---|
| **$90.0 - 100.0$** | `EXCELLENT` | Green | Normal operation. No action needed. |
| **$75.0 - 89.9$** | `GOOD` | Blue | Routine monitoring. |
| **$50.0 - 74.9$** | `DEGRADED` | Yellow | Schedule sensor inspection within 7 days. |
| **$25.0 - 49.9$** | `POOR` | Orange | Immediate sensor calibration required. |
| **$0.0 - 24.9$** | `CRITICAL` | Red | Sensor offline / replace hardware immediately. |

---

#### 4.6.2 SHAP Explainability & Reason Generation Engine
For every alert with $\text{Severity} \ge \text{LOW}$, TreeSHAP / KernelSHAP computes exact Shapley feature attributions:
$$\phi_i(f, \mathbf{z}) = \sum_{S \subseteq F \setminus \{i\}} \frac{|S|!(|F| - |S| - 1)!}{|F|!} [f(S \cup \{i\}) - f(S)]$$

- Percentage Contribution per Feature $i \in \{T, P, RH, \Delta T, \Delta P, \Delta RH\}$:
  $$C_i = \frac{|\phi_i|}{\sum_{j \in F} |\phi_j|} \times 100\%$$
- **Human-Readable Rule Translation**:
  1. If $C_T > 40\%$ and $\Delta T > 0$: `"Temperature jumped +{ΔT:.1f}°C rapidly within 5 minutes."`
  2. If $C_P > 40\%$ and $S_{\text{temporal}} > 0.7$: `"Pressure deviated {P:.1f} hPa from expected temporal baseline."`
  3. If $S_{\text{thermo}} > 0.6$: `"Multivariate relationship inconsistent: RH={RH:.1f}% unphysical at T={T:.1f}°C."`
  4. If $R_{\text{frozen}} > 0.5$: `"Sensor reading stuck at {x:.2f} for {duration} consecutive timestamps."`

---

## 5. Features Discovered Table

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|---|---|---|---|---|---|---|
| 1 | Simulator | Diurnal Generator | Generates synthetic daily solar cycles with diurnal temperature, thermal tides, and inverse RH | $\Delta t, h_0, T_{\text{mean}}, A_T, P_0, A_P, \rho, \sigma$ | DataFrame $(t, T, P, RH)$ | Raises ValueError on negative amplitude or invalid sampling interval | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 2 | Simulator | Anomaly Injector | Programmatically injects 8 ground-truth anomaly types into clean series | Baseline series, anomaly type, start index, duration, magnitude | Perturbed series + ground truth label array | Raises KeyError on unknown anomaly type; truncates if index out of bounds | `ORIGINAL_REQUEST.md`, `GOAL.md` |
| 3 | Simulator | Test Scenarios | Pre-packaged evaluation scenarios (Clean, Spikes, Frozen, Drift, Multi-Fault) | Scenario name, duration in days | Benchmarking dataset with label metadata | Raises FileNotFoundError if output directory unwritable | `ORIGINAL_REQUEST.md`, `TODO.md` |
| 4 | Tier 1 ML | Physics Bounds Check | Validates strict WMO physical limits for T, P, RH | Raw observation $(T, P, RH)$ | Tier 1 boolean flag, error code | Hard flag $S_{\text{Tier1}} = 1.0$ if bounds violated | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 5 | Tier 1 ML | Step / Rate of Change Check | Checks maximum 5-minute derivative limits | Current and previous observations $(\mathbf{x}_t, \mathbf{x}_{t-1})$ | $\Delta \mathbf{x}$, rate flag | Flags high gradient if $|\Delta x| > \text{threshold}$ | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 6 | Tier 1 ML | Persistence / Frozen Check | Computes empirical variance over sliding window $K=6$ | Rolling buffer of past $K$ observations | Variance value, is_frozen boolean | Returns False if buffer length $< K$ | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 7 | Tier 1 ML | Data Integrity Check | Detects NaNs, strings, out-of-order timestamps, duplicates | Raw record payload | is_valid boolean, error message | Rejects malformed payload with 422 Unprocessable Entity | `ARCHITECTURE.md`, `AGENTS.md` |
| 8 | Tier 2 ML | Isolation Forest Point Detector | Detects multivariate statistical point outliers on normalized features | Standard scaled vector $\mathbf{z}_t \in \mathbb{R}^9$ | $S_{\text{point}} \in [0, 1]$ | Graceful fallback to Tier 1 if model uninitialized | `ARCHITECTURE.md`, `TODO.md` |
| 9 | Tier 2 ML | GRU/LSTM Autoencoder | Reconstructs sliding sequence ($W=30$) and measures MSE | Sequence tensor $\mathbf{X}_t \in \mathbb{R}^{30 \times 3}$ | Reconstruction tensor $\mathbf{\hat{X}}_t$, $S_{\text{temporal}} \in [0, 1]$ | Returns zero score with buffer warning if window $< 30$ | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 10 | Tier 3 ML | Clausius-Clapeyron Consistency | Evaluates physical dew point vs dry bulb temperature | $(T, RH)$ | $T_d$, $\Delta_{\text{thermo}}$, $S_{\text{thermo}} \in [0, 1]$ | Handles $RH \le 0$ by clamping to $0.1\%$ to avoid $\ln(0)$ | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 11 | Tier 3 ML | Mahalanobis Distance | Measures statistical deviation using full covariance matrix | $\mathbf{x}_t, \boldsymbol{\mu}, \boldsymbol{\Sigma}^{-1}$ | $D_M$, $S_{\text{mahalanobis}} \in [0, 1]$ | Uses pseudo-inverse if covariance matrix singular | `ARCHITECTURE.md`, `TODO.md` |
| 12 | Anomaly Fusion | Unified Fusion Engine | Fuses Tier 1-3 scores into unified score, confidence, severity | $S_{\text{Tier1}}, S_{\text{point}}, S_{\text{temporal}}, S_{\text{Tier3}}$ | $(S_{\text{fused}}, C_{\text{fused}}, \text{Severity})$ | Overrides to $1.0 / \text{CRITICAL}$ if Tier 1 violated | `ARCHITECTURE.md`, `GOAL.md` |
| 13 | Tier 4 ML | Fault Classifier | Classifies anomaly into 8 specific fault categories | Rule flags, feature gradients, duration, CC status | Fault category enum | Defaults to `UNCERTAIN_EVENT` if ambiguous | `ARCHITECTURE.md`, `GOAL.md` |
| 14 | Tier 5 ML | Sensor Health Engine | Dynamic 0-100 SHI score tracking anomaly rate and drift | History buffer of past 288 inferences | $\text{SHI} \in [0, 100]$, Health Status, Action | Returns 100.0 if history buffer empty | `ARCHITECTURE.md`, `GOAL.md` |
| 15 | Tier 5 ML | SHAP Explainability Engine | Generates Shapley feature importance and human explanation | Trained model, feature vector $\mathbf{z}_t$ | $\boldsymbol{\phi} \in \mathbb{R}^9$, text explanation bullets | Returns rule-based explanation if SHAP calculation times out | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 16 | Real-Time | Streaming Inference Service | Ingests live telemetry, updates buffer, runs full pipeline | Observation JSON payload | Full inference result schema | Returns error JSON if database or model fails | `ARCHITECTURE.md`, `TODO.md` |
| 17 | Storage | SQLite Repository | Stores stations, observations, anomaly events, and health | Processed observation & anomaly models | Database record IDs | Handles SQLite busy/lock retries | `ARCHITECTURE.md` |

---

## 6. Edge Cases & Boundary Conditions

| # | Feature | Input / Condition | Expected / Observed Behavior | Handling / Safeguard |
|---|---|---|---|---|
| 1 | Clausius-Clapeyron Formula | $RH \le 0.0\%$ | $\ln(RH/100)$ produces $\ln(0) = -\infty$ | Clamp $RH$ internally to $\epsilon = 0.01\%$ before evaluating logarithm |
| 2 | Magnus-Tetens Equation | $T = -243.5^\circ\text{C}$ | Division by zero in denominator $T + 243.5$ | Tier 1 range check rejects $T < -40.0^\circ\text{C}$ before thermodynamic calculation |
| 3 | Autoencoder Windowing | Cold start with fewer than $W=30$ observations in buffer | Unable to form $(30, 3)$ tensor for GRU/LSTM | Zero-pad left side or fallback to Tier 1 + Point ML with buffer penalty $C_{\text{fused}} -= 0.20$ |
| 4 | Mahalanobis Covariance | Constant/frozen sensor inputs causing singular covariance $\det(\boldsymbol{\Sigma}) = 0$ | Matrix inversion fails with Singular Matrix error | Add ridge regularization $\boldsymbol{\Sigma} + \lambda \mathbf{I}$ ($\lambda = 10^{-5}$) or use `np.linalg.pinv` |
| 5 | Frozen Sensor Detection | Missing or variable time steps $(\Delta t \ne 5\text{ min})$ | False positive frozen detection across large gaps | Reset variance counter if gap $\Delta t > 15\text{ min}$ |
| 6 | Extreme Meteorological Squall | $\Delta T = -12^\circ\text{C}/5\text{min}, \Delta P = -8\text{hPa}/5\text{min}, \Delta RH = +45\%$ | Point ML flags high anomaly score | Tier 4 classifier checks thermodynamic consistency and labels `METEOROLOGICAL_EXTREME` instead of `SPIKE` |
| 7 | Duplicate Timestamps | Two consecutive records with timestamp $t_i = t_{i-1}$ | Division by $\Delta t = 0$ in rate of change | Tier 1 rejects duplicate timestamp with status `DUPLICATE_DISCARDED` |
| 8 | Large Missing Gap | Station offline for 12 hours then resumes | Autoencoder sequence spans across the gap, misinterpreting as anomaly | Ingestion engine inserts `NaN` records and resets temporal buffer upon resumption |
| 9 | Out-of-Order Packets | Timestamp $t_i < t_{i-1}$ received via REST/MQTT | Negative gradient calculation and corrupted sliding buffer | Buffer sorts incoming observations by timestamp or rejects if older than retention window |
| 10 | High Temperature Supersaturation | $T = 45^\circ\text{C}, RH = 100\%$ | High vapor pressure exceeding standard atmospheric limits ($e > 95\text{ hPa}$) | Flagged by Tier 3 Multivariate Inconsistency as physically improbable for non-marine AWS |
| 11 | Sensor Health Initial State | Newly registered station with zero historical observations | Division by zero in $\frac{\text{Anomalies}}{\text{Total}}$ | Default $\text{SHI} = 100.0$, Status = `EXCELLENT` until $N \ge 12$ steps |
| 12 | SHAP Computation Latency | Real-time streaming under high load ($> 100\text{ obs/sec}$) | KernelSHAP overhead ($> 500\text{ms}$) violates latency target | Use TreeSHAP or fast gradient approximations; cache background reference datasets |

---

## 7. Mathematical & Algorithmic Verification Criteria

1. **Simulator Realism**:
   - Diurnal cycle must pass spectral analysis showing peak Fourier power at $\frac{1}{24\text{ hours}}$ for Temperature and $\frac{1}{12\text{ hours}}$ for Pressure.
   - Temperature and Relative Humidity cross-correlation must satisfy:
     $$\text{Corr}(T, RH) \le -0.75 \quad \text{under clean baseline simulation}$$
2. **Deterministic Tier 1 Bounds**:
   - $100\%$ of synthetic inputs outside $[-40, +60]^\circ\text{C}$, $[300, 1100]\text{ hPa}$, or $[0, 104]\%$ must trigger $S_{\text{Tier1}} = 1.0$.
3. **Temporal Model Convergence**:
   - PyTorch GRU/LSTM Autoencoder trained on clean baseline data must achieve validation $\text{MSE} < 0.05$ on normalized features.
4. **Fault Classification Accuracy**:
   - Benchmark script `scripts/test_anomaly_detection.py` must achieve macro F1-score $\ge 0.80$ across injected `SPIKE`, `DRIFT`, `FROZEN`, and `MULTIVARIATE_INCONSISTENCY` test sets.
5. **Sensor Health Monotonicity**:
   - Injected persistent drift or frozen faults must cause $\text{SHI}$ to decay monotonically from $>90.0$ to $<30.0$.
6. **No-Fake Functionality Enforcement**:
   - Zero hardcoded anomaly scores, confidence constants, or mock SHAP values anywhere in the codebase.
