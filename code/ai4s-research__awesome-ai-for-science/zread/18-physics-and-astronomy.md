

AI is reshaping the fundamental sciences — from decoding quantum error correction on real processors to jointly embedding galaxy images and spectra into shared latent spaces. This page catalogs the tools, models, datasets, and agents that sit at the intersection of artificial intelligence and the physical universe, spanning quantum many-body systems, plasma fusion, continuum dynamics, and extragalactic surveys. Whether you are a physicist seeking ML accelerants for your next simulation or a machine learning researcher looking for physically grounded benchmarks, this is your launch point.

Sources: [README.md](/README.md#L707-L728)

## Landscape at a Glance

The AI-for-Physics ecosystem divides into three concentric layers: **domain-specific agents** that orchestrate multi-step physics workflows, **foundation models** that learn cross-modal physical representations, and **numerical frameworks** that embed differentiable physics into training loops. The diagram below maps these layers and their interdependencies.

```mermaid
graph TD
    subgraph Agents
        A1[Get Physics Done<br/>PSI]
        A2[Foam-Agent<br/>CFD Automation]
        A3[SR-Scientist<br/>Equation Discovery]
    end

    subgraph Foundation Models
        F1[AlphaQubit<br/>Quantum Decoding]
        F2[FermiNet<br/>Quantum Chemistry]
        F3[AION / AstroCLIP<br/>Astronomy]
        F4[Walrus<br/>Continuum Dynamics]
        F5[TORAX<br/>Fusion Transport]
    end

    subgraph SciML Frameworks
        S1[DeepXDE / PINNs<br/>PDE Solvers]
        S2[NeuralOperator<br/>Fourier Ops]
        S3[PySR / PSRN<br/>Symbolic Regression]
        S4[JAX-MD / JAX-CFD<br/>Differentiable Sim]
        S5[NetKet<br/>Quantum Many-Body]
    end

    Agents -->|orchestrate| Foundation Models
    Agents -->|invoke| SciML Frameworks
    Foundation Models -->|trained on| SciML Frameworks
```

Sources: [README.md](/README.md#L707-L728), [README.md](/README.md#L314-L316), [README.md](/README.md#L355-L377)

## Machine Learning for Physics

### Quantum Computing & Quantum Chemistry

The quantum layer addresses two grand challenges: **quantum error correction** for building fault-tolerant processors, and **ab-initio electronic structure** for predicting molecular and material properties from first principles.

| Tool | Focus | Key Capability | Scale / Result |
|------|-------|----------------|----------------|
| **AlphaQubit** | Quantum Error Correction | Transformer-based neural decoder trained on real Sycamore data | Outperforms tensor-network decoders at code distances up to 29 |
| **FermiNet** | Quantum Chemistry | Variational Monte Carlo with antisymmetric wavefunctions | Directly solves many-electron Schrödinger equation; extended to excited states (Science 2024) |
| **NetKet** | Quantum Many-Body | Neural quantum states, VMC, tensor networks | Implements ground-state and dynamical problems for condensed matter (3.5K+ stars) |

> [!TIP]
> AlphaQubit is the first decoder demonstrated on **real** quantum hardware — not just simulations — making it a critical reference for anyone bridging ML and quantum error correction.

FermiNet represents a paradigm shift: rather than approximating the wavefunction with a fixed basis set, it parameterizes the full antisymmetric wavefunction with a neural network and optimizes via variational Monte Carlo. The FermiNet architecture enforces permutation antisymmetry through multiple determinant streams, ensuring physical correctness while maintaining expressivity. NetKet complements this by providing a broader toolkit — neural quantum states, variational Monte Carlo, and tensor network algorithms — targeting condensed matter and quantum chemistry problems at scale.

Sources: [README.md](/README.md#L710-L712)

### Plasma Fusion & Differentiable Simulation

Fusion energy research demands coupling PDE solvers with neural-network surrogates in a differentiable pipeline. **TORAX** is Google DeepMind's differentiable tokamak core transport simulator that couples PDE solvers with JAX auto-differentiation and neural-network surrogates for fast forward modelling, pulse-design, and trajectory optimization. On the simulation side, **JAX-MD** provides GPU-accelerated molecular dynamics in JAX, enabling end-to-end differentiable physics pipelines where force fields, integrators, and observables are all autodiff-compatible. **JAX-CFD** extends this paradigm to computational fluid dynamics, offering differentiable Navier-Stokes simulations with automatic differentiation for ML-accelerated CFD research.

Sources: [README.md](/README.md#L713-L718), [README.md](/README.md#L886-L886)

### Continuum Dynamics & Cross-Domain Foundation Models

**Walrus** is PolymathicAI's cross-domain foundation model for continuum dynamics, trained on 19 physical scenarios spanning 63 variables. It features adaptive compute via stride modulation and patch jittering for long-run stability. This approach represents a key trend: rather than training a model for a single PDE, Walrus learns transferable representations across fluid dynamics, magnetohydrodynamics, and other continuum systems. The model's stride-modulation mechanism allows it to dynamically allocate computation across spatial and temporal scales — critical for multi-physics simulations where features exist at vastly different resolutions.

Sources: [README.md](/README.md#L720-L720)

### Equivariant Architectures for 3D Atomic Systems

Physics is fundamentally about symmetries. Equivariant neural networks — architectures that respect rotational and translational symmetry by construction — have become the backbone of modern atomistic ML. **Equiformer** and its successor **EquiformerV2** introduce equivariant graph attention Transformers for 3D atomic graphs, achieving top performance on the Open Catalyst Project and Materials Project benchmarks. These models guarantee that rotating or translating the input coordinates produces a correspondingly rotated/translated output, eliminating the need for data augmentation to learn symmetry. The **e3nn** library provides the foundational Euclidean neural network primitives for building such architectures, enabling E(3)-equivariant deep learning across molecular dynamics, materials science, and physics.

Sources: [README.md](/README.md#L716-L717), [README.md](/README.md#L875-L875)

### Robotics & Differentiable Physics

**DiffPhysDrone** (Nature Machine Intelligence 2025) is the first real quadrotor robot trained end-to-end with differentiable physics for vision-based agile flight. It bridges the simulation-to-reality gap by embedding physics-informed neural networks directly into the control pipeline, enabling the system to learn agile flight maneuvers that transfer from simulation to physical hardware without manual tuning.

Sources: [README.md](/README.md#L719-L719)

## Astronomy & Astrophysics

### Foundation Models for Astronomical Surveys

The astronomical data deluge — petabytes of imaging and spectroscopic surveys — demands foundation models that can jointly reason across modalities. Two projects from Polymathic AI lead this frontier:

| Model | Modalities | Key Capability | Use Cases |
|-------|-----------|----------------|-----------|
| **AstroCLIP** | Galaxy imaging + optical spectra | Cross-modal self-supervised embedding into shared latent space | Zero/few-shot redshift estimation, galaxy property prediction, morphological classification |
| **AION** | 39 distinct modalities (imaging, spectra, photometry, catalogs) | Large omnimodal foundation model for astronomical surveys | Similarity search, property prediction, generative tasks across survey data |

AION represents a dramatic scaling of ambition: rather than aligning two modalities, it integrates 39 distinct data types — from pixel-level imaging to catalog entries — into a single model. This enables scientists to query across modalities naturally: find galaxies with similar spectra to a given image, predict photometric properties from spectroscopic features, or generate synthetic observations across instruments.

Sources: [README.md](/README.md#L723-L724)

### Classical Astronomy Tools & Spherical CNNs

The bedrock of astronomical computing remains **AstroPy**, the community Python library providing core astronomy utilities for coordinates, time systems, units, and data I/O. The **Gaia Archive** provides stellar astrometric and photometric data for over a billion stars, serving as a primary ML dataset for stellar classification and galactic structure studies. **DeepSphere** introduces spherical CNNs specifically designed for astronomical data on the celestial sphere — where traditional planar convolutions introduce distortion at the poles. By operating directly on the sphere using graph-based representations, DeepSphere preserves the geometric integrity of all-sky surveys.

Sources: [README.md](/README.md#L725-L727)

## Physics-Focused Agents

### Get Physics Done (PSI)

**Get Physics Done** is the first open-source agentic AI physicist that turns research questions into structured workflows with rigorous verification and multi-step analytical work for long-horizon physics projects. It integrates with Claude Code, Codex, and Gemini, providing a natural-language interface for posing physics questions and receiving step-by-step analytical solutions with built-in verification gates. This is particularly valuable for complex physics problems that require chaining multiple analytical steps — from setting up equations, through dimensional analysis, to numerical verification.

Sources: [README.md](/README.md#L315-L315)

### Foam-Agent (NeurIPS 2025)

**Foam-Agent** is an end-to-end composable multi-agent framework for automating OpenFOAM-based CFD simulations from natural language prompts. It manages the full CFD pipeline — meshing, case setup, execution, error correction, and post-processing — achieving a 100% success rate on standard benchmarks. For physicists and engineers who routinely run CFD simulations, Foam-Agent eliminates the steep OpenFOAM learning curve by translating natural-language descriptions of flow problems into complete, runnable simulation cases.

Sources: [README.md](/README.md#L316-L316)

### SR-Scientist (ICLR 2026)

**SR-Scientist** elevates LLMs from equation proposers to autonomous scientists that write code, analyze data, implement equations, and optimize based on experimental feedback. It outperforms baselines on scientific equation discovery tasks, representing a key bridge between the symbolic regression tools (PySR, PSRN) and autonomous physics discovery.

Sources: [README.md](/README.md#L282-L282)

## Scientific ML Methods for Physics

The tools below are cataloged in dedicated SciML pages but are indispensable for physics applications. They are summarized here with their physics-specific relevance.

### Physics-Informed Neural Networks (PINNs)

PINNs embed governing PDEs directly into the loss function, ensuring that the network satisfies physical laws by construction. **DeepXDE** is the most widely used library, supporting 11 PDE types with deep learning backends. **PINA** provides a PyTorch-native alternative with advanced modeling capabilities. **NeuralPDE.jl** brings PINNs to the Julia ecosystem with high-performance solvers. **Lang-PINN** (ICLR 2026) pushes the frontier by using LLM-driven multi-agent systems to build trainable PINNs from natural language task descriptions, achieving 3–5 orders of magnitude MSE reduction.

Sources: [README.md](/README.md#L356-L363)

### Neural Operators & Symbolic Regression

| Method | What It Discovers | Physics Relevance |
|--------|-------------------|-------------------|
| **Fourier Neural Operator** | PDE solution operators in Fourier space | Learns infinite-dimensional maps between function spaces |
| **PySR** | Interpretable symbolic equations from data | Widely used in physics and astronomy for law discovery |
| **PSRN** | Parallel symbolic regression on GPU | Evaluates millions of expressions; Nature Computational Science cover |
| **PySR → PySR** | LLM-guided symbolic regression | Combines code generation with evolutionary search (ICLR 2025 Oral) |

**PySR** deserves special emphasis: it is the go-to tool for physicists who want to discover interpretable equations from experimental or simulation data. Its multi-population evolutionary search with a Python/Julia backend has been used to rediscover known physical laws and discover new ones across fluid dynamics, astrophysics, and condensed matter.

Sources: [README.md](/README.md#L366-L376)

### Simulation-Based Inference

**sbi** is a Python package for simulation-based inference enabling likelihood-free Bayesian parameter estimation from scientific simulators. In physics, this is critical when the likelihood function is intractable — for example, in cosmological inference from CMB data or gravitational wave parameter estimation. The package provides flexible interfaces for neural posterior estimation, sequential methods, and MCMC/variational backends.

Sources: [README.md](/README.md#L379-L379)

## Physics Datasets & Benchmarks

| Dataset | Domain | Size | Key Use |
|---------|--------|------|---------|
| **The Well** | Multi-physics simulations | 15TB, 16 datasets | Training foundation models on physical dynamics |
| **RealPDEBench** | Complex PDE systems | 700+ trajectories, 5 scenarios | Paired real-world measurements + simulations (ICLR 2026 Oral) |
| **LIGO Open Science Center** | Gravitational waves | Public GW data | Signal detection, parameter estimation |
| **Particle Data Group** | Particle physics | Standardized particle data | ML-based event classification |
| **OpenQuantumMaterials** | Quantum materials | Materials database | Property prediction, discovery |
| **NewtonBench** | Physics law rediscovery | 324 tasks, 12 physics domains | Evaluating LLMs on interactive experimentation (ICLR 2026) |
| **BuildArena** | Engineering construction | Physics simulator tasks | LLM agents in engineering construction |
| **SciCode** | Scientific coding | 338 subproblems, 16 subdomains | Realistic scientific programming tasks (NeurIPS 2024) |

> [!TIP]
> **The Well** is the largest multi-physics simulation dataset publicly available — if you are training a foundation model for physical dynamics, start here. Its 15TB spans fluid dynamics, MHD, astrophysics, and biological systems with unified PyTorch dataloaders.

**RealPDEBench** is particularly notable as the first benchmark that pairs real-world physical measurements with matched numerical simulations, addressing the critical gap between simulation-only benchmarks and real experimental validation. **NewtonBench** introduces memorization-resistant metaphysical shifts of canonical laws, ensuring that models are actually discovering physics rather than memorizing textbook equations.

Sources: [README.md](/README.md#L840-L845), [README.md](/README.md#L295-L299)

## Computing Frameworks for Physics

Physics-specific ML workflows benefit from frameworks that natively support differentiable simulation, equivariant architectures, and quantum computing:

| Framework | Core Capability | Physics Domain |
|-----------|----------------|----------------|
| **PennyLane** | Differentiable quantum computing | Quantum chemistry, NISQ algorithms (3K+ stars) |
| **Qiskit** | Quantum circuit SDK | Quantum algorithm development (7.4K+ stars) |
| **Newton** | GPU-accelerated differentiable physics | Rigid/soft body, gradient-based optimization |
| **PhiFlow** | Differentiable PDE solving | Fluid simulation with PyTorch/JAX/TensorFlow backends |
| **exponax** | Differentiable n-dimensional PDE solvers | 46+ built-in equations, Fourier spectral methods |
| **TorchSim** | PyTorch-native atomistic simulation | MLIP-based molecular dynamics and relaxation |
| **PaddleScience** | AI-driven scientific computing | PDE solving, inverse problems |

Sources: [README.md](/README.md#L862-L891)

## Where to Go Next

The Physics & Astronomy domain intersects deeply with several other areas in this catalog. For the mathematical foundations underlying the tools discussed here, explore [Physics-Informed Neural Networks](13-physics-informed-neural-networks), [Neural Operators & Model Discovery](14-neural-operators-and-model-discovery), and [Neural Differential Equations](15-neural-differential-equations). For the broader infrastructure that powers these workflows, see [Computing Frameworks](22-computing-frameworks) and [Datasets & Benchmarks](23-datasets-and-benchmarks). For autonomous agents that can orchestrate physics research end-to-end, visit [Autonomous Research Systems](10-autonomous-research-systems) and [Domain-Specific Research Agents](11-domain-specific-research-agents). For the frontier models that learn cross-domain physical representations, see [Foundation Models for Science](21-foundation-models-for-science).
