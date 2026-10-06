

This page provides a comprehensive overview of Transformer-based architectures applied to time series tasks. Transformers have revolutionized time series analysis by addressing key challenges in long-sequence modeling, capturing complex dependencies, and improving forecasting accuracy across diverse applications from multivariate forecasting to anomaly detection.

![Repository Overview](https://github.com/lixus7/Time-Series-Works-Conferences/blob/main/docs/WeChat.jpeg?raw=true)

## Core Transformer Architectures for Time Series Forecasting

The transformer architecture has been extensively adapted for time series forecasting, with innovations focusing on computational efficiency, long-range dependency modeling, and decomposition of complex temporal patterns. The following models represent significant advances in applying transformers to multivariate time series forecasting tasks.

### Long-Sequence Forecasting Transformers

Long-sequence time series forecasting presents unique challenges due to quadratic complexity in standard attention mechanisms. Several models have introduced efficient attention patterns and architectural modifications to address these limitations.

**FEDformer** (Frequency Enhanced Decomposed Transformer) introduces a frequency-domain approach to decomposition that significantly improves long-term forecasting performance. Published in ICML 2022, FEDformer decomposes time series into trend and seasonal components in the frequency domain, then applies specialized transformers to each component. This approach is particularly effective on benchmarks like ETT, Electricity, Exchange, Traffic, and Weather datasets, achieving state-of-the-art results while maintaining computational efficiency through frequency-based operations [docs/Recent-Time-Series-Work-Group-by-Task.md#L18-L18].

**Pyraformer** (Low-Complexity Pyramidal Attention) addresses the computational bottleneck through a novel pyramidal attention mechanism. Published in ICLR 2022, this architecture creates multi-scale representations using a pyramid structure that captures both local and global temporal patterns efficiently. The model has been validated on diverse datasets including ETT, Electricity, Wind, and App Flow, demonstrating superior performance for long-range time series modeling while reducing computational complexity from O(n²) to near-linear scaling [docs/Recent-Time-Series-Work-Group-by-Task.md#L23-L23].

**Autoformer** (Decomposition Transformers with Auto-Correlation) introduces a fundamental reformulation of self-attention as auto-correlation, which replaces dot-product attention with auto-correlation mechanisms. Published in NeurIPS 2021, Autoformer achieves superior decomposition of time series into auto-correlation and trend-seasonality components. The model has demonstrated strong performance across multivariate forecasting benchmarks including ETT, Electricity, Exchange, Traffic, Weather, and ILI datasets, establishing it as a foundational architecture for transformer-based time series forecasting [docs/Recent-Time-Series-Work-Group-by-Task.md#L38-L38].

**Informer** represents a breakthrough in efficient transformer design for long sequence time-series forecasting. Published in AAAI 2021, Informer introduces ProbSparse self-attention mechanism that reduces complexity to O(L log L), along with self-attention distillation and generative style decoder for efficient long-sequence prediction. Validated on ETT, Weather, and ECL datasets, Informer established new standards for computational efficiency while maintaining competitive forecasting accuracy [docs/Recent-Time-Series-Work-Group-by-Task.md#L52-L52].

### Specialized Attention Mechanisms

Several models have developed specialized attention mechanisms tailored to specific characteristics of time series data.

**Triformer** (Triangular, Variable-Specific Attentions) introduces a unique attention pattern combining triangular and variable-specific attention mechanisms. Published in IJCAI 2022, this architecture captures both temporal dependencies and inter-variable relationships more effectively through its specialized attention design. The model demonstrates effectiveness on ETT, ECL, and Weather datasets, particularly excelling in scenarios where different time series variables exhibit complex cross-correlations [docs/Recent-Time-Series-Work-Group-by-Task.md#L30-L30].

**TopAttn** (Topological Attention) incorporates topological information into attention computation for improved forecasting performance. Published in NeurIPS 2021, this approach leverages topological properties of time series data to enhance attention mechanisms. The model has been validated on M4, Electricity, car-parts, and other benchmarks, demonstrating the value of incorporating topological structure into transformer architectures [docs/Recent-Time-Series-Work-Group-by-Task.md#L36-L36].

### Decomposition and Normalization Innovations

Transformer models have increasingly incorporated sophisticated decomposition and normalization techniques to handle distribution shifts and complex temporal patterns.

**RevIN** (Reversible Instance Normalization) addresses the critical challenge of distribution shift in time series forecasting. Published in ICLR 2022, RevIN introduces reversible instance normalization that allows the model to handle non-stationary distributions while preserving the original signal characteristics. This technique has proven effective across multiple datasets including ETT, ECL, M4, Air Quality, and Nasdaq, making it particularly valuable for real-world forecasting scenarios where data distributions shift over time [docs/Recent-Time-Series-Work-Group-by-Task.md#L24-L24].

**CoST** (Contrastive Learning of Disentangled Seasonal-Trend Representations) combines contrastive learning with transformer architectures to learn disentangled seasonal and trend representations. Published in ICLR 2022, CoST leverages contrastive learning objectives to improve representation quality, achieving strong performance on ETT, Electricity, and Weather datasets. The model demonstrates the value of combining self-supervised learning techniques with transformer architectures for time series [docs/Recent-Time-Series-Work-Group-by-Task.md#L21-L22].

**LogSparse** (Log-Sparse Transformer) addresses the memory bottleneck of transformers through log-sparse attention patterns. Published in NeurIPS 2019, this approach enhances locality properties while reducing memory requirements for long sequence modeling. The model has been validated on Electricity, Traffic, and M4 datasets, demonstrating early innovations in efficient attention mechanisms before they became mainstream in time series transformers [docs/Recent-Time-Series-Work-Group-by-Task.md#L114-L114].

### Sparse and Adversarial Approaches

**AST** (Adversarial Sparse Transformer) combines sparse attention mechanisms with adversarial training for robust time series forecasting. Published in NeurIPS 2020, AST introduces sparsity into attention computation while using adversarial objectives to improve generalization. The model has demonstrated effectiveness across multiple domains including Electricity, Traffic, Wind, Solar, and M4-Hourly datasets, showcasing the value of adversarial training in transformer architectures [docs/Recent-Time-Series-Work-Group-by-Task.md#L76-L77].

## Transformer Variants for Specialized Applications

Beyond general forecasting, transformer architectures have been adapted for specialized time series applications including anomaly detection, probabilistic forecasting, financial prediction, and representation learning.

### Anomaly Detection Transformers

Transformer architectures have proven particularly effective for time series anomaly detection by capturing complex temporal dependencies and detecting subtle deviations from normal patterns.

**Anomaly Transformer** introduces association discrepancy mechanisms specifically designed for anomaly detection. The model identifies anomalies by measuring discrepancies between associations in the input and reconstructed sequences. Validated on challenging benchmarks including SMD, PSM, MSL&SMAP, and SWaT NeurIPS-TS datasets, Anomaly Transformer demonstrates the effectiveness of transformer architectures for detecting subtle anomalies in multivariate time series [docs/Recent-Time-Series-Work-Group-by-Task.md#L238-L238].

**TranAD** (Deep Transformer Networks for Anomaly Detection) applies transformer architectures specifically designed for multivariate time series anomaly detection. The model has been validated across multiple datasets including NAB, UCR, MBA, SMAP, MSL, SWaT, WADI, SMD, and MSDS, demonstrating broad applicability across different anomaly detection scenarios. TranAD showcases how transformer architectures can be specialized for the specific requirements of anomaly detection tasks [docs/Recent-Time-Series-Work-Group-by-Task.md#L245-L245].

### Probabilistic Forecasting Transformers

Probabilistic forecasting requires models to capture uncertainty and generate distributions rather than point forecasts, presenting unique challenges for transformer architectures.

**ProTran** (Probabilistic Transformer For Time Series Analysis) extends transformer architectures to probabilistic forecasting by incorporating uncertainty estimation capabilities. Published in NeurIPS 2021, ProTran enables the model to generate probabilistic forecasts with confidence intervals across diverse applications including Exchange, Solar, Electricity, Traffic, Taxi, and Wikipedia data. This demonstrates the adaptability of transformer architectures to probabilistic modeling requirements [docs/Recent-Time-Series-Work-Group-by-Task.md#L163-L163].

### Financial and Stock Prediction Transformers

Financial time series present unique challenges including market microstructure effects, multiple data sources, and the need to interpret complex cross-asset relationships.

**NumHTML** (Numeric-Oriented Hierarchical Transformer Model) applies hierarchical transformer architectures specifically for financial forecasting tasks. Published in AAAI 2022, NumHTML demonstrates effectiveness on options data (Calls) for multi-task financial forecasting, showcasing how transformer architectures can be specialized for financial applications requiring hierarchical modeling of complex financial instruments [docs/Recent-Time-Series-Work-Group-by-Task.md#L422-L422].

**DTML** (Data-Axis Transformer with Multi-Level Contexts) introduces a data-axis transformer architecture specifically designed for multivariate stock movement prediction. Published in KDD 2021, DTML has been validated across multiple international markets including ACL18, KDD17, NDX100, CSI300, NI225, and FTSE100. The model demonstrates how transformers can effectively capture multi-level contextual information in financial markets across different geographic regions [docs/Recent-Time-Series-Work-Group-by-Task.md#L424-L424].

**HTML** (Hierarchical Transformer-based Multi-task Learning) applies hierarchical transformer architectures to volatility prediction tasks. Published in WWW 2020, HTML has been validated on options data (Calls) for volatility forecasting, demonstrating the effectiveness of hierarchical multi-task learning with transformers for financial applications requiring prediction of multiple related quantities [docs/Recent-Time-Series-Work-Group-by-Task.md#L437-L437].

**HMG-TF** (Hierarchical Multi-Scale Gaussian Transformer) combines hierarchical and multi-scale approaches with transformer architectures for stock movement prediction. Published in IJCAI 2020, HMG-TF has demonstrated effectiveness on TPX500 and TPX100 indices, showing the value of multi-scale hierarchical processing in transformer architectures for capturing temporal patterns at different scales in financial markets [docs/Recent-Time-Series-Work-Group-by-Task.md#L435-L435].

### Representation Learning Transformers

Transformer architectures have proven particularly powerful for learning universal representations of time series that can transfer across different tasks and domains.

**Transformer-based Framework** (Multivariate Time Series Representation Learning) provides a comprehensive framework for learning representations from multivariate time series using transformer architectures. Published in KDD 2021, this framework has been validated on diverse datasets including Benz, Air Quality, and FuelMoisture, demonstrating the potential of transformers to learn universal representations that transfer across different application domains [docs/Recent-Time-Series-Work-Group-by-Task.md#L43-L43].

**TS2Vec** extends universal representation learning approaches to time series domains using transformer-inspired architectures. Published in AAAI 2022, TS2Vec learns universal representations that transfer across different tasks, validated on GoogleSymptoms, Covid19, Power, and Tweet datasets. This demonstrates the potential of transformer architectures for creating pre-trained models that can be fine-tuned for specific time series tasks, similar to advances in computer vision and NLP [docs/Recent-Time-Series-Work-Group-by-Task.md#L29-L29].

### Hybrid and Graph-Integrated Transformers

Recent advances have combined transformers with other architectures to capture both temporal and spatial dependencies, particularly important for traffic forecasting and other spatio-temporal applications.

**AGCNT** (Adaptive Graph Convolutional Network for Transformer-based Long Sequence Time-Series Forecasting) integrates graph neural networks with transformer architectures to capture spatial dependencies alongside temporal patterns. Published in CIKM 2021, AGCNT has been validated on ETT and ELE datasets, demonstrating the effectiveness of combining graph-based spatial modeling with transformer temporal modeling for complex forecasting tasks [docs/Recent-Time-Series-Work-Group-by-Task.md#L66-L66].

**DSANet** (Dual Self-Attention Network) combines multiple self-attention mechanisms for multivariate time series forecasting. Published in CIKM 2019, DSANet introduces dual self-attention architectures that have proven effective on Gas Station and other datasets, showcasing early innovations in combining multiple attention mechanisms within transformer architectures [docs/Recent-Time-Series-Work-Group-by-Task.md#L136-L136].

## Evolution and Trends in Transformer Architectures

The development of transformer architectures for time series reveals clear evolution patterns and emerging trends that reflect the unique challenges of temporal data.

### Architectural Evolution

The timeline of transformer-based time series models shows progressive refinement from initial adaptations to specialized architectures:

1. **Early Adaptations (2018-2019)**: Initial applications of transformers to time series focused on adapting NLP architectures with minimal modifications. Models like LogSparse (NeurIPS 2019) and DSANet (CIKM 2019) began addressing computational efficiency and multi-attention challenges specific to time series data [docs/Recent-Time-Series-Work-Group-by-Task.md#L114-L114].

2. **Efficiency Breakthroughs (2020-2021)**: Focus shifted dramatically to addressing the O(n²) complexity limitation. Informer (AAAI 2021) and Autoformer (NeurIPS 2021) introduced ProbSparse attention and auto-correlation mechanisms respectively, achieving computational breakthroughs that made transformers practical for long-sequence forecasting [docs/Recent-Time-Series-Work-Group-by-Task.md#L52-L52].

3. **Decomposition Innovations (2021-2022)**: Recognition that time series require decomposition into trend and seasonal components led to models like FEDformer (ICML 2022) and CoST (ICLR 2022) that explicitly model different frequency components with specialized architectures [docs/Recent-Time-Series-Work-Group-by-Task.md#L18-L18].

4. **Specialized Attention (2022-Present)**: Recent work focuses on specialized attention mechanisms like Pyraformer's pyramidal attention (ICLR 2022) and TopAttn's topological attention (NeurIPS 2021), demonstrating increasing sophistication in attention mechanism design for temporal data [docs/Recent-Time-Series-Work-Group-by-Task.md#L23-L23].

### Key Architectural Innovations

Several innovations have emerged as particularly influential across multiple transformer-based time series models:

**Efficient Attention Mechanisms**: The development of sparse, low-rank, and frequency-domain attention mechanisms represents the most significant architectural innovation. Techniques like ProbSparse attention (Informer), auto-correlation (Autoformer), and pyramidal attention (Pyraformer) have collectively made transformers practical for long-sequence time series forecasting while maintaining or improving accuracy.

**Decomposition Strategies**: Recognizing that time series contain multiple components with different characteristics (trend, seasonality, noise) has led to decomposition-based approaches. FEDformer's frequency-domain decomposition and Autoformer's auto-correlation decomposition have proven particularly effective, with these concepts being adopted across subsequent models.

**Hierarchical Processing**: Multi-scale hierarchical processing has emerged as crucial for capturing patterns at different temporal scales. Models like Triformer (variable-specific attentions), HMG-TF (multi-scale Gaussian transformers), and NumHTML (harchical transformers) demonstrate the value of hierarchical architectures for temporal data [docs/Recent-Time-Series-Work-Group-by-Task.md#L30-L30].

**Distribution Shift Handling**: Techniques like RevIN (reversible instance normalization) address the fundamental challenge of non-stationarity in time series, a problem not encountered in most NLP or computer vision applications where transformers originated. This innovation has proven critical for real-world forecasting applications [docs/Recent-Time-Series-Work-Group-by-Task.md#L24-L24].

### Application Domain Expansion

Transformer architectures have expanded from initial focus on general multivariate forecasting to specialized domains:

**Financial Applications**: Specialized transformers like NumHTML, DTML, HTML, and HMG-TF address the unique challenges of financial time series including market microstructure effects, multiple asset classes, and the need to model complex cross-asset relationships [docs/Recent-Time-Series-Work-Group-by-Task.md#L422-L437].

**Anomaly Detection**: Transformers like AnomalyTransformer and TranAD have proven particularly effective for anomaly detection by capturing complex temporal dependencies and detecting subtle deviations from normal patterns, demonstrating advantages over traditional autoencoder-based approaches [docs/Recent-Time-Series-Work-Group-by-Task.md#L238-L245].

**Probabilistic Forecasting**: Models like ProTran extend transformers to probabilistic forecasting, requiring architectural modifications to handle uncertainty estimation and distribution generation rather than point forecasting [docs/Recent-Time-Series-Work-Group-by-Task.md#L163-L163].

**Representation Learning**: Frameworks like TS2Vec and the KDD 2021 transformer framework demonstrate the potential for learning universal time series representations that can transfer across tasks and domains, similar to advances in computer vision and NLP [docs/Recent-Time-Series-Work-Group-by-Task.md#L29-L29].

## Implementation Considerations and Best Practices

Based on the surveyed models, several implementation patterns and best practices have emerged for transformer-based time series models.

### Computational Efficiency

**Attention Mechanism Selection**: The choice of attention mechanism significantly impacts computational efficiency:
- Standard O(n²) attention: Suitable for shorter sequences (<512 time steps)
- ProbSparse attention (Informer): Reduces complexity to O(L log L), suitable for long sequences
- Auto-correlation (Autoformer): Efficient for frequency-domain analysis
- Pyramidal attention (Pyraformer): Near-linear scaling for very long sequences

**Decomposition Integration**: Incorporating decomposition into the architecture typically improves both accuracy and efficiency:
- Frequency-domain decomposition (FEDformer): Enables parallel processing of different frequency components
- Trend-seasonality decomposition (Autoformer): Specialized processing for different components
- Contrastive learning decomposition (CoST): Improved representation through disentangled components

**Normalization Strategies**: Proper normalization is critical for training stability and performance:
- RevIN: Essential for handling distribution shifts in non-stationary data
- Layer normalization: Standard practice for transformer training
- Instance normalization: Important for multivariate normalization across variables

### Architecture Design Patterns

**Encoder-Decoder Structure**: Most successful time series transformers follow encoder-decoder architectures with:
- Encoder: Processes input sequence with efficient attention mechanisms
- Decoder: Generates output sequence, often with cross-attention to encoder
- Bridge: May include bottleneck layers or specialized processing

**Multi-Scale Processing**: Capturing patterns at multiple temporal scales consistently improves performance:
- Hierarchical architectures: Process at multiple scales simultaneously
- Temporal pyramid: Explicit multi-resolution temporal modeling
- Variable-specific attention: Different attention patterns for different variables or scales

**Specialized Components**: Incorporating domain-specific components improves performance:
- Graph neural networks: For spatial dependencies in traffic forecasting
- Temporal convolutions: For local pattern extraction
- Adaptive mechanisms: For handling different time series characteristics

### Training and Evaluation

**Training Strategies**: Best practices for training transformer-based time series models include:
- Curriculum learning: Start with shorter sequences, gradually increase
- Regularization: Dropout and weight decay are crucial for preventing overfitting
- Gradient clipping: Important for stable training with long sequences

**Evaluation Metrics**: Standard evaluation metrics for transformer-based time series forecasting include:
- Point forecasting: MSE, MAE, RMSE for accuracy assessment
- Probabilistic forecasting: CRPS, likelihood metrics for uncertainty calibration
- Anomaly detection: Precision, recall, F1-score for anomaly detection quality

**Benchmark Datasets**: Consistent use of standard datasets enables comparison:
- General forecasting: ETT, Electricity, Weather, Traffic, Exchange, ILI
- Probabilistic: M4, Traffic, Electricity, Wiki, Solar
- Anomaly detection: SMD, PSM, MSL&SMAP, SWaT

## Model Comparison and Selection Guide

The following table compares key transformer-based models across important dimensions to assist in model selection:

| Model | Publication | Key Innovation | Strengths | Best Applications |
|-------|-------------|----------------|----------|-----------------|
| FEDformer | ICML 2022 | Frequency-domain decomposition | Long-term forecasting accuracy | Long-sequence forecasting, multi-frequency data |
| Autoformer | NeurIPS 2021 | Auto-correlation mechanism | Decomposition quality, computational efficiency | General multivariate forecasting, trend-seasonality decomposition |
| Informer | AAAI 2021 | ProbSparse attention | Computational efficiency for long sequences | Long-sequence forecasting when computational budget limited |
| Pyraformer | ICLR 2022 | Pyramidal attention | Very long sequence modeling | Extremely long time series (>1000 time steps) |
| Triformer | IJCAI 2022 | Variable-specific attentions | Multi-variable relationship modeling | Multivariate forecasting with complex cross-correlations |
| RevIN | ICLR 2022 | Reversible instance normalization | Distribution shift handling | Non-stationary data, real-world forecasting |
| CoST | ICLR 2022 | Contrastive learning decomposition | Representation quality, transferability | Pre-training, representation learning |
| Anomaly Transformer | - | Association discrepancy | Anomaly detection accuracy | Multivariate anomaly detection |
| ProTran | NeurIPS 2021 | Probabilistic forecasting | Uncertainty estimation | Probabilistic forecasting applications |
| NumHTML | AAAI 2022 | Hierarchical multi-task | Multi-task financial forecasting | Financial options and derivatives pricing |
| DTML | KDD 2021 | Data-axis multi-level context | Cross-market modeling | International stock market prediction |

**Selection Criteria**:
- **For long-sequence forecasting (>512 time steps)**: FEDformer, Pyraformer, Informer
- **For high accuracy on standard benchmarks**: Autoformer, FEDformer
- **For anomaly detection**: Anomaly Transformer, TranAD
- **For probabilistic forecasting**: ProTran
- **For financial applications**: NumHTML, DTML, HMG-TF
- **For representation learning**: CoST, TS2Vec, KDD 2021 framework
- **For distribution shift scenarios**: RevIN-enhanced models

> [!TIP]
> When implementing transformer-based time series models, always start with the simplest architecture that meets your requirements (typically Autoformer or Informer) and only progress to more complex models (FEDformer, Pyraformer) if needed. The complexity-performance tradeoff is steeper for time series transformers than for computer vision models.

## Future Research Directions

Based on the evolution of transformer architectures for time series, several promising research directions emerge:

**Pre-trained Foundation Models**: Following the success of pre-trained models in NLP and computer vision, developing foundation models pre-trained on large-scale time series corpora represents a significant opportunity. Models like TS2Vec demonstrate early progress in this direction, but much work remains in developing truly universal time series foundation models that transfer across diverse domains and tasks [docs/Recent-Time-Series-Work-Group-by-Task.md#L29-L29].

**Multimodal Integration**: Real-world time series applications often involve multiple modalities (numerical time series, text descriptions, images, etc.). Transformer architectures with strong multimodal fusion capabilities could provide significant advantages. Current work in financial prediction with news sentiment hints at this potential, but systematic approaches to multimodal time series transformers remain underexplored.

**Causal Reasoning**: Incorporating causal reasoning into transformer architectures could improve forecasting by distinguishing correlation from causation, particularly important for applications like healthcare and economics where understanding causal relationships is as important as accurate prediction.

**Physics-Informed Transformers**: Integrating physical constraints and domain knowledge into transformer architectures could improve accuracy and interpretability, particularly important for scientific applications like weather forecasting, energy systems, and climate modeling.

**Efficient Deployment**: While computational efficiency has improved significantly, deploying transformer-based models on edge devices and resource-constrained environments remains challenging. Further research into model compression, quantization, and efficient inference for time series transformers is needed.

**Explainability**: Transformer architectures are often criticized as black boxes. Developing techniques for interpreting transformer decisions and explaining forecasts to domain experts, particularly in critical applications like healthcare and finance, represents an important research direction.

## Recommended Reading Path

To develop expertise in transformer-based time series models, we recommend the following reading progression:

**Foundational Understanding**: Begin with Informer (AAAI 2021) to understand efficient transformer architectures for time series, then progress to Autoformer (NeurIPS 2021) to learn about decomposition approaches [docs/Recent-Time-Series-Work-Group-by-Task.md#L52-L52].

**Advanced Architectures**: Study FEDformer (ICML 2022) and Pyraformer (ICLR 2022) to understand state-of-the-art approaches to long-sequence forecasting and efficient attention mechanisms [docs/Recent-Time-Series-Work-Group-by-Task.md#L18-L18].

**Specialized Applications**: Explore Anomaly Transformer for anomaly detection, ProTran for probabilistic forecasting, and NumHTML/DTML for financial applications to understand domain-specific adaptations [docs/Recent-Time-Series-Work-Group-by-Task.md#L238-L238].

**Representation Learning**: Investigate CoST, TS2Vec, and the KDD 2021 framework to understand approaches to universal representation learning in time series [docs/Recent-Time-Series-Work-Group-by-Task.md#L29-L29].

For broader context, explore [Graph Neural Networks for Time Series](16-graph-neural-networks-for-time-series) to understand how transformer architectures are being integrated with graph-based approaches, and [LLM-Empowered Time Series Models](17-llm-empowered-time-series-models) to understand the emerging intersection of large language models and time series analysis.