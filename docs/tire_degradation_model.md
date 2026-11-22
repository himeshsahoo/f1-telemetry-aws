# 📐 Tire Degradation Modeling & Mathematical Foundations

## Ordinary Least Squares (OLS) Linear Formulation
Tire degradation is calculated using linear regression modeling lap time $T_i$ against stint lap age $L_i$:

$$T_i = m \cdot L_i + c + \epsilon_i$$

Where:
- $m$: **Degradation Slope** (seconds lost per lap due to tire compound thermal & mechanical degradation).
- $c$: **Base Pace** (extrapolated initial tire pace on zero-wear rubber).
- $\epsilon_i$: Random noise (traffic, minor driver errors).

## Safety Car & In-Lap Filtering
To prevent extreme outlier bias, the following filters are applied before computing $m$:
1. $T_i \le 1.10 \times T_{\text{fastest}}$ (excludes Yellow Flag / Safety Car / VSC laps).
2. Out-laps (lap 1 of stint) and In-laps (pit entry lap) are excluded from regression.
3. Minimum stint length requirement: $\ge 3$ green-flag laps.
