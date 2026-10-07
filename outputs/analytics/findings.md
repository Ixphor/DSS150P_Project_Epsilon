# Findings: is complaint resolution systematically slower / less favourable?

Data: 17,499,205 complaints, 2011-12 to 2026-08. Groups are compared with a product-mix-adjusted expectation (indirect standardisation), exact Poisson tests, Benjamini-Hochberg FDR q<0.05.


## Outcome: slower (untimely response)  (overall 0.63%, 109,651 events)

### institution (company)
- 1390 groups tested; **431 worse**, 454 better than expected; association strength Cramer's V = 0.584 (p=0).
  - IPAC'S INC.: 99.81% vs expected 0.33% (SIR 303.12, n=533, q=0)
  - ENTRATA INC.: 58.86% vs expected 0.27% (SIR 218.18, n=350, q=0)
  - BETTERNOI, LLC: 36.36% vs expected 0.17% (SIR 214.38, n=132, q=1e-91)
  - PORANIA, LLC: 72.31% vs expected 0.76% (SIR 95.41, n=195, q=5.8e-219)
  - NOVO PLATFORM INC.: 68.24% vs expected 0.76% (SIR 90.20, n=148, q=1.2e-154)

### institution type (FDIC tier)
- 5 groups tested; **2 worse**, 2 better than expected; association strength Cramer's V = 0.012 (p=0).
  - Under $1B: 4.12% vs expected 2.01% (SIR 2.05, n=2,696, q=2.2e-11)
  - Not FDIC-matched: 0.61% vs expected 0.57% (SIR 1.07, n=16,252,427, q=3.9e-104)

### product category
- 20 groups tested; **13 worse**, 5 better than expected; association strength Cramer's V = 0.171 (p=0).
  - Debt or credit management: 8.68% vs expected 0.41% (SIR 21.05, n=10,189, q=0)
  - Payday loan, title loan, personal loan, or advance loan: 4.55% vs expected 0.41% (SIR 11.06, n=37,466, q=0)
  - Student loan: 10.67% vs expected 1.32% (SIR 8.06, n=132,985, q=0)
  - Prepaid card: 4.99% vs expected 0.81% (SIR 6.13, n=23,087, q=0)
  - Payday loan, title loan, or personal loan: 5.14% vs expected 1.23% (SIR 4.19, n=30,614, q=0)

### geography (state)
- 52 groups tested; **19 worse**, 9 better than expected; association strength Cramer's V = 0.026 (p=0).
  - ME: 2.41% vs expected 1.53% (SIR 1.58, n=13,928, q=1.2e-13)
  - WY: 2.17% vs expected 1.41% (SIR 1.54, n=5,934, q=1.8e-05)
  - MT: 2.29% vs expected 1.50% (SIR 1.52, n=9,845, q=2e-08)
  - ND: 1.44% vs expected 0.97% (SIR 1.48, n=10,578, q=1.8e-05)
  - ID: 1.80% vs expected 1.40% (SIR 1.29, n=20,061, q=1.4e-05)


## Outcome: less favourable (closed without relief)  (overall 63.67%, 11,032,029 events)

### institution (company)
- 1389 groups tested; **870 worse**, 100 better than expected; association strength Cramer's V = 0.447 (p=0).
  - ADVANCED RESOLUTION SERVICES INC.: 99.96% vs expected 53.92% (SIR 1.85, n=2,481, q=2.5e-169)
  - CASCADE CISS HOLDINGS, LLC: 100.00% vs expected 54.83% (SIR 1.82, n=1,684, q=7.9e-110)
  - LCI ACQUISITION INC.: 100.00% vs expected 56.04% (SIR 1.78, n=3,119, q=1.8e-189)
  - FACTORTRUST, INC.: 99.84% vs expected 56.58% (SIR 1.76, n=1,915, q=1.8e-112)
  - BETTERNOI, LLC: 100.00% vs expected 56.96% (SIR 1.76, n=132, q=1.6e-08)

### institution type (FDIC tier)
- 5 groups tested; **4 worse**, 1 better than expected; association strength Cramer's V = 0.077 (p=0).
  - $1B - $10B: 94.79% vs expected 84.19% (SIR 1.13, n=1,055, q=0.00031)
  - Under $1B: 84.72% vs expected 79.22% (SIR 1.07, n=2,696, q=0.0015)
  - $10B - $250B: 78.12% vs expected 73.82% (SIR 1.06, n=298,836, q=2.7e-161)
  - Over $250B: 76.60% vs expected 75.99% (SIR 1.01, n=941,862, q=2.2e-11)

### product category
- 20 groups tested; **13 worse**, 5 better than expected; association strength Cramer's V = 0.207 (p=0).
  - Payday loan, title loan, personal loan, or advance loan: 92.90% vs expected 59.69% (SIR 1.56, n=37,236, q=0)
  - Debt or credit management: 85.41% vs expected 59.34% (SIR 1.44, n=10,118, q=3e-223)
  - Money transfer, virtual currency, or money service: 90.18% vs expected 64.85% (SIR 1.39, n=190,353, q=0)
  - Vehicle loan or lease: 90.54% vs expected 67.31% (SIR 1.35, n=102,289, q=0)
  - Student loan: 93.03% vs expected 70.60% (SIR 1.32, n=132,365, q=0)

### geography (state)
- 52 groups tested; **17 worse**, 8 better than expected; association strength Cramer's V = 0.035 (p=0).
  - WY: 73.92% vs expected 71.26% (SIR 1.04, n=5,897, q=0.034)
  - IN: 64.16% vs expected 62.78% (SIR 1.02, n=195,565, q=2.3e-13)
  - HI: 67.71% vs expected 66.33% (SIR 1.02, n=30,170, q=0.0093)
  - MO: 65.90% vs expected 64.58% (SIR 1.02, n=194,187, q=6.8e-12)
  - DC: 66.04% vs expected 64.80% (SIR 1.02, n=59,606, q=0.00069)

- State SIR (closed w/o relief) vs state_poverty_rate_pct: Spearman rho=-0.21, p=0.127, 52 states
- State SIR (closed w/o relief) vs state_median_income: Spearman rho=0.10, p=0.464, 52 states