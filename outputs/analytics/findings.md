# Findings: is complaint resolution systematically slower / less favourable?

Data: 17,510,651 complaints, 2011-12 to 2026-08. Groups are compared with a product-mix-adjusted expectation (indirect standardisation), exact Poisson tests, Benjamini-Hochberg FDR q<0.05.


## Outcome: slower (untimely response)  (overall 0.62%, 109,328 events)

### institution (company)
- 1390 groups tested; **432 worse**, 454 better than expected; association strength Cramer's V = 0.584 (p=0).
  - IPAC'S INC.: 99.81% vs expected 0.33% (SIR 304.11, n=533, q=0)
  - ENTRATA INC.: 58.86% vs expected 0.27% (SIR 218.48, n=350, q=0)
  - BETTERNOI, LLC: 36.36% vs expected 0.17% (SIR 214.58, n=132, q=1e-91)
  - PORANIA, LLC: 72.31% vs expected 0.76% (SIR 95.44, n=195, q=5.7e-219)
  - NOVO PLATFORM INC.: 68.24% vs expected 0.75% (SIR 90.65, n=148, q=7.4e-155)

### institution type (FDIC tier)
- 5 groups tested; **2 worse**, 2 better than expected; association strength Cramer's V = 0.012 (p=0).
  - Under $1B: 4.12% vs expected 2.01% (SIR 2.05, n=2,696, q=2.1e-11)
  - Not FDIC-matched: 0.60% vs expected 0.56% (SIR 1.07, n=16,263,922, q=9.6e-104)

### product category
- 20 groups tested; **13 worse**, 5 better than expected; association strength Cramer's V = 0.170 (p=0).
  - Debt or credit management: 8.66% vs expected 0.41% (SIR 21.12, n=10,177, q=0)
  - Payday loan, title loan, personal loan, or advance loan: 4.54% vs expected 0.41% (SIR 11.12, n=37,440, q=0)
  - Student loan: 10.55% vs expected 1.32% (SIR 7.98, n=132,980, q=0)
  - Prepaid card: 4.99% vs expected 0.81% (SIR 6.14, n=23,079, q=0)
  - Payday loan, title loan, or personal loan: 5.14% vs expected 1.23% (SIR 4.19, n=30,614, q=0)

### geography (state)
- 52 groups tested; **20 worse**, 9 better than expected; association strength Cramer's V = 0.026 (p=0).
  - ME: 2.41% vs expected 1.52% (SIR 1.58, n=13,940, q=7.7e-14)
  - WY: 2.17% vs expected 1.41% (SIR 1.54, n=5,940, q=1.5e-05)
  - MT: 2.26% vs expected 1.49% (SIR 1.52, n=9,846, q=3.5e-08)
  - ND: 1.44% vs expected 0.97% (SIR 1.49, n=10,584, q=1.6e-05)
  - SD: 1.95% vs expected 1.51% (SIR 1.29, n=7,346, q=0.0089)


## Outcome: less favourable (closed without relief)  (overall 63.74%, 10,984,884 events)

### institution (company)
- 1387 groups tested; **869 worse**, 101 better than expected; association strength Cramer's V = 0.448 (p=0).
  - ADVANCED RESOLUTION SERVICES INC.: 99.96% vs expected 53.92% (SIR 1.85, n=2,481, q=2.5e-169)
  - CASCADE CISS HOLDINGS, LLC: 100.00% vs expected 54.86% (SIR 1.82, n=1,684, q=1.3e-109)
  - LCI ACQUISITION INC.: 100.00% vs expected 56.03% (SIR 1.78, n=3,091, q=6.9e-188)
  - FACTORTRUST, INC.: 99.84% vs expected 56.58% (SIR 1.76, n=1,915, q=1.8e-112)
  - BETTERNOI, LLC: 100.00% vs expected 57.03% (SIR 1.75, n=132, q=1.7e-08)

### institution type (FDIC tier)
- 5 groups tested; **4 worse**, 1 better than expected; association strength Cramer's V = 0.077 (p=0).
  - $1B - $10B: 94.74% vs expected 84.28% (SIR 1.12, n=1,046, q=0.00039)
  - Under $1B: 84.72% vs expected 79.22% (SIR 1.07, n=2,696, q=0.0016)
  - $10B - $250B: 78.11% vs expected 73.83% (SIR 1.06, n=298,425, q=2.5e-159)
  - Over $250B: 76.61% vs expected 76.00% (SIR 1.01, n=940,913, q=3.2e-11)

### product category
- 20 groups tested; **13 worse**, 5 better than expected; association strength Cramer's V = 0.207 (p=0).
  - Payday loan, title loan, personal loan, or advance loan: 92.89% vs expected 59.78% (SIR 1.55, n=37,118, q=0)
  - Debt or credit management: 85.43% vs expected 59.41% (SIR 1.44, n=10,079, q=2.6e-221)
  - Money transfer, virtual currency, or money service: 90.19% vs expected 64.90% (SIR 1.39, n=190,162, q=0)
  - Vehicle loan or lease: 90.54% vs expected 67.36% (SIR 1.34, n=102,162, q=0)
  - Student loan: 93.02% vs expected 70.64% (SIR 1.32, n=132,166, q=0)

### geography (state)
- 52 groups tested; **17 worse**, 8 better than expected; association strength Cramer's V = 0.035 (p=0).
  - WY: 74.02% vs expected 71.32% (SIR 1.04, n=5,877, q=0.031)
  - IN: 64.21% vs expected 62.83% (SIR 1.02, n=194,724, q=3.8e-13)
  - HI: 67.85% vs expected 66.41% (SIR 1.02, n=29,968, q=0.0065)
  - MO: 65.95% vs expected 64.65% (SIR 1.02, n=193,367, q=1.6e-11)
  - UT: 70.42% vs expected 69.10% (SIR 1.02, n=53,954, q=0.00076)

- State SIR (closed w/o relief) vs state_poverty_rate_pct: Spearman rho=-0.20, p=0.151, 52 states
- State SIR (closed w/o relief) vs state_median_income: Spearman rho=0.09, p=0.512, 52 states