# Standard Operating Procedure (SOP)

**Document Number:** SOP-BPR-402  
**Effective Date:** 2026-10-01  
**Version:** 2.0  
**Title:** Steady-State Operation and Critical Process Parameter (CPP) Control of Perfusion Bioreactors Using Alternating Tangential Flow (ATF) Filtration in cGMP Pilot Facilities  
**Department:** Translational Bioprocess Development & Pilot Biomanufacturing (Stanford ChEM-H / MITI Platform)  
**Applicability:** Single-Use Perfusion Bioreactors (10 L – 50 L scale)  

---

## 1. Purpose & Objective

1.1 This Standard Operating Procedure defines the protocol for initiating, operating, monitoring, and terminating continuous perfusion cell culture for recombinant therapeutic proteins in cGMP-compliant single-use bioreactor systems.  
1.2 The objective is to maintain steady-state viable cell density (VCD), high culture viability ($\ge 90\%$), and stable Critical Quality Attributes (CQAs) through automated feedback control of fresh medium feed, cell bleed, and filtration flux.

---

## 2. Scope & Responsibilities

| Role | Operational Responsibilities |
|:---|:---|
| **Bioprocess Scientist (Lead)** | Author protocol, establish Design Space & CPP ranges, oversee batch-to-perfusion transition, evaluate online PAT data, review batch records. |
| **Manufacturing Associate** | Perform sterile tubing welding, sensor calibrations (pH, DO, capacitance), daily sampling, offline analytical measurements, and equipment sanitation. |
| **Quality Assurance (QA)** | Review and approve SOP, audit deviations and environmental monitoring logs, verify raw material release, release final drug substance batch. |

---

## 3. Regulatory References & Safety Guidelines

* **ICH Q8(R2):** Pharmaceutical Development — Design Space & Control Strategy.
* **ICH Q11:** Development and Manufacture of Drug Substances.
* **FDA Guidance for Industry:** Quality Considerations for Continuous Manufacturing (March 2023).
* **Biosafety:** Biosafety Level 1 (BSL-1) / BSL-2 practices per Institutional Biosafety Committee guidelines.
* **PPE:** Full cleanroom gowning (Tyvek coverall, sterile nitrile gloves, safety goggles, shoe covers, hairnet).

---

## 4. Equipment, Instruments & Materials

### 4.1 Equipment
* 50 L Single-Use Bioreactor (SUB) with dual-impeller microsparge vessel.
* Repligen XCell ATF-4 Filtration Module with C24 automated diaphragm controller.
* Hollow Fiber Cartridge: $0.2\,\mu\text{m}$ polyethersulfone (PES), surface area $0.5\text{ m}^2$, sterile gamma-irradiated.
* Automated cell bleed peristaltic pump (Watson-Marlow 120U or integrated SUB bleed control).
* Aber Biomass Capacitance System (inline $12\text{ mm}$ reusable sensor).
* Kaiser Raman Rxn2 Analyzer with bIO optic immersion probe.

### 4.2 Raw Materials & Media
* Basal Perfusion Media: Chemically defined, protein-free, animal-origin-free (AOF) medium supplemented with $4\text{ mM}$ L-glutamine and $0.1\%$ Poloxamer 188.
* Base Neutralization Solution: $0.5\text{ M}$ Sodium Hydroxide ($\text{NaOH}$), sterile filtered.
* Antifoam C Emulsion ($1:10$ dilution in sterile WFI).
* Single-use sterile transfer sets with C-Flex tubing and CPC AseptiQuik sterile connectors.

---

## 5. Critical Process Parameters (CPPs) & Control Limits

| Parameter | Normal Operating Range (NOR) | Action Limit (Alert) | Critical Limit (OOS) | Frequency / Sensor |
|:---|:---|:---|:---|:---|
| **Viable Cell Density (VCD)** | $60.0 - 70.0 \times 10^6\text{ c/mL}$ | $< 55.0\text{ or } > 75.0$ | $< 50.0\text{ or } > 80.0$ | Continuous (Aber probe) / 1x daily Vi-CELL |
| **Cell Viability** | $\ge 92.0\%$ | $< 90.0\%$ | $< 85.0\%$ | Daily offline trypan blue / flow cytometry |
| **Perfusion Rate ($D$)** | $1.20 - 1.50\text{ vvd}$ | $\pm 0.15\text{ vvd}$ | $\pm 0.25\text{ vvd}$ | Continuous balance gravimetric load cells |
| **CSPR** | $22.0 - 28.0\text{ pL/cell/day}$ | $< 20.0\text{ or } > 30.0$ | $< 18.0\text{ or } > 35.0$ | Calculated daily from VCD & Perfusion Rate |
| **pH** | $7.05 \pm 0.05$ | $\pm 0.08$ | $\pm 0.15$ | Continuous dual optical sensor (offline crosscheck) |
| **Dissolved Oxygen (DO)**| $40.0\% \pm 5.0\%$ | $\pm 8.0\%$ | $< 25.0\%\text{ or } > 60.0\%$ | Continuous inline polarographic probe |
| **Culture Temperature** | $33.0^\circ\text{C} \pm 0.3^\circ\text{C}$ (Day 3+) | $\pm 0.5^\circ\text{C}$ | $\pm 1.0^\circ\text{C}$ | Inline Pt100 RTD sensor |
| **ATF Flow Rate** | $1.5 - 2.0\text{ L/min}$ | $\pm 0.2\text{ L/min}$ | $\pm 0.4\text{ L/min}$ | ATF C24 controller screen |

---

## 6. Detailed Step-by-Step Procedure

```
[Day 0: Inoculation (0.5 x 10⁶ c/mL)]
                 │
                 ▼
[Days 1-2: Batch Growth Phase (Reach VCD ≥ 4.0 x 10⁶ c/mL)]
                 │
                 ▼
[Day 3: Perfusion Initiation (0.5 vvd) & Temperature Shift (36.5°C ──► 33.0°C)]
                 │
                 ▼
[Days 4-7: Perfusion Ramp-up (0.5 ──► 1.5 vvd) until VCD = 65 x 10⁶ c/mL]
                 │
                 ▼
[Days 8-30: Steady-State Automated Control (Bleed activated, CSPR 25 pL/c/d)]
```

### 6.1 Pre-Operational Verification & Setup
1. Verify cleanroom environmental monitoring status (ISO Class 7 / Grade C background).
2. Connect single-use bag to SUB hardware; ensure temperature jacket and load cell tare are calibrated.
3. Weld ATF hollow-fiber cartridge to the bioreactor recirculation loop using an automated tube welder (Terumo TSCD-II). Inspect weld integrity.
4. Perform filter wetting and 3-point pressure hold integrity test on ATF hollow fiber ($25\text{ psi}$ for $10\text{ min}$, allowable pressure drop $\le 0.5\text{ psi}$).

### 6.2 Inoculation & Batch Phase
1. Inoculate bioreactor at an initial seeding density of $0.50 \pm 0.05 \times 10^6\text{ cells/mL}$ with working volume of $35.0\text{ L}$.
2. Operate in batch mode for $48 - 72\text{ hours}$ under standard parameters ($36.5^\circ\text{C}$, $\text{pH } 7.10$, $\text{DO } 40\%$).
3. Monitor daily offline cell counts using Vi-CELL XR automated analyzer.

### 6.3 Perfusion Initiation & Ramp-Up
1. When culture VCD reaches $4.0 - 5.0 \times 10^6\text{ cells/mL}$ (typically Day 3), initiate ATF pumping at $1.2\text{ L/min}$.
2. Start fresh media feed pump at $0.50\text{ vvd}$ ($17.5\text{ L/day}$) and match harvest rate via gravimetric feedback control.
3. Execute hypothermic temperature shift from $36.5^\circ\text{C}$ to $33.0^\circ\text{C}$ to suppress cell proliferation, prolong viability, and boost specific productivity.
4. Ramp perfusion rate daily as VCD increases:
   * VCD $10 - 20 \times 10^6$: Perfusion rate $0.80\text{ vvd}$.
   * VCD $20 - 40 \times 10^6$: Perfusion rate $1.20\text{ vvd}$.
   * VCD $40 - 65 \times 10^6$: Perfusion rate $1.50\text{ vvd}$.

### 6.4 Steady-State Operation & Automated Cell Bleed
1. When target VCD reaches $65.0 \times 10^6\text{ cells/mL}$, activate automated bleed control loop.
2. The Aber capacitance probe transmits real-time viable biovolume to the PLC. When estimated VCD exceeds $65.0 \times 10^6\text{ cells/mL}$, the bleed pump engages automatically to discharge excess cells to the bio-waste receptacle.
3. Calculate CSPR daily:
   $$\text{CSPR} = \frac{D}{\text{VCD}} = \frac{1.50\text{ day}^{-1}}{65.0 \times 10^6\text{ cells/mL}} = 23.1\text{ pL/cell/day}$$
4. If CSPR drifts below $20\text{ pL/cell/day}$, increase media feed rate by $0.1\text{ vvd}$ to avoid nutrient starvation.

### 6.5 Daily Sampling & Analytical Monitoring Schedule
* **Every 24 Hours:**
  * Sample $15\text{ mL}$ culture via needleless swabable valve.
  * Analyze offline: VCD/viability (trypan blue), glucose/lactate/glutamine (BioProfile FLEX2), pH crosscheck (blood gas analyzer).
* **Every 48 Hours:**
  * Collect clarified harvest sample from ATF permeate line.
  * Test bioburden ($10\text{ mL}$ onto $0.45\,\mu\text{m}$ membrane filter placed on TSA, 5-day incubation).
  * Measure product titer by Protein A HPLC ($2.1\text{ mm} \times 30\text{ mm}$ column).
* **Weekly (Days 7, 14, 21, 28):**
  * Harvest sample for CQA tracking: SEC-HPLC (HMWS/aggregates), icIEF (charge variants), LC-MS glycoprofiling.

---

## 7. Deviation Handling & Out-of-Specification (OOS) Protocols

1. **Membrane Fouling / Transmembrane Pressure (TMP) Spike ($> 3.0\text{ psi}$):**
   * Immediately reduce ATF flow rate by $20\%$.
   * Perform reverse flush with $200\text{ mL}$ warm permeate buffer under sterile conditions.
   * If TMP does not normalize within 4 hours, initiate secondary pre-sterilized ATF filter swap protocol.
2. **Loss of Capacitance Signal:**
   * Switch bleed pump from automated Aber feedback to fixed manual daily bleed volume calculated from offline Vi-CELL counts.
   * Log non-conformance event; QA review required within 24 hours.
3. **Bioburden Positive ($\ge 1\text{ CFU/10 mL}$):**
   * Quarantine harvest pool immediately.
   * Take confirmatory sample from bioreactor core and media feed lines.
   * If core is confirmed positive, terminate run immediately per SOP-DEV-012.

---

## 8. Document History & Approval

| Version | Date | Author | Description of Change |
|:---|:---|:---|:---|
| 1.0 | 2026-04-15 | Bioprocess Engineer | Initial Release for 10 L pilot trials. |
| 2.0 | 2026-09-29 | Senior Bioprocess Scientist | Upgraded for 50 L cGMP continuous manufacturing with Aber capacitance automated bleed and Raman PAT feedback. |
