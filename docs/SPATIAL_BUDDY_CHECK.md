# SkyGuard AI — Spatial Consensus & AWS Buddy-Check Architecture (Tier 3.5)

## 1. Executive Summary

Automatic Weather Stations (AWS) operating in isolated point-mode are susceptible to confounding:
1. **Isolated Physical Sensor Faults:** Broken transducer, analog-to-digital converter (ADC) saturation, loose wire, or heater malfunction.
2. **Regional Meteorological Events:** Coherent passage of cold fronts, convective squalls, sea-breeze boundaries, or downbursts.

SkyGuard AI's **Tier 3.5 Spatial Consensus / AWS Buddy-Check Layer** (`backend/app/spatial/consensus.py`) provides an additive spatial disambiguation engine that cross-references target observations against neighboring stations within a geographic radius.

---

## 2. Mathematical Formulation

### 2.1 Haversine Great-Circle Distance
The distance $d$ between target station coordinates $(\phi_1, \lambda_1)$ and neighbor station $(\phi_2, \lambda_2)$ is computed via the Haversine formula:

$$\Delta\phi = \phi_2 - \phi_1, \quad \Delta\lambda = \lambda_2 - \lambda_1$$
$$a = \sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)$$
$$c = 2 \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1-a}\right)$$
$$d = R_{\text{earth}} \cdot c \quad (R_{\text{earth}} = 6371.0\text{ km})$$

Stations where $d \le R_{\text{search}}$ (default $R = 50.0\text{ km}$) are designated as active peer neighbors.

---

### 2.2 Robust Neighbor Statistics & Median Absolute Deviation (MAD)
To prevent contamination by a broken neighboring station, we use **Median Absolute Deviation (MAD)** instead of sample mean and standard deviation:

$$\text{Median}(X) = \text{med}(x_1, x_2, \dots, x_N)$$
$$\text{MAD}(X) = \text{med}(|x_i - \text{Median}(X)|)$$
$$\text{Robust } Z(x_{\text{target}}) = \frac{x_{\text{target}} - \text{Median}(X)}{1.4826 \cdot \text{MAD}(X) + \epsilon}$$

Where $1.4826$ is the asymptotic consistency factor for normal distributions.

---

### 2.3 Consensus Decision Logic

$$\text{Max Spatial } Z = \max\left(|Z_T|, |Z_P|, |Z_{\text{RH}}|\right)$$
$$\text{Consensus Score} = \max\left(0.0, \min\left(1.0, 1.0 - \frac{\text{Max Spatial } Z}{5.0}\right)\right)$$

- If $\text{Max Spatial } Z \le 3.0$: `SUPPORTED` ($\ge 80\%$ agreement with regional network).
- If $\text{Max Spatial } Z > 3.0$: `ISOLATED` (Station diverges significantly from regional cluster $\rightarrow$ Probable sensor fault).
- If Neighbor Count $N < 2$: `INSUFFICIENT_DATA` (Isolated station; spatial check gracefully skipped without penalization).

---

## 3. System Integration & UI Visualization

- **ML Pipeline:** Integrated additively into `InferenceResult.spatial_consensus`.
- **Alert Center Drawer (`AlertCenterView.tsx`):** Displays real-time neighbor count, search radius, agreement percentage, and spatial status badges (`SUPPORTED` in emerald, `ISOLATED` in amber/rose).
