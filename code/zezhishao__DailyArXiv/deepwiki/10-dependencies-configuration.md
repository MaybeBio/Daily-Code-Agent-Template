# Dependencies & Configuration

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [.gitignore](.gitignore)
- [requirements.txt](requirements.txt)

</details>



This document covers the system dependencies, Python package requirements, and configuration management for the DailyArXiv system. It details the minimal external dependencies required for the automated paper aggregation pipeline and explains how configuration is managed through hardcoded constants and environment setup.

For information about the automated deployment workflow, see [GitHub Actions Workflow](#5.1). For details about the core processing implementation, see [Core Implementation](#4).

## Python Dependencies

The DailyArXiv system maintains a minimal dependency footprint with only three external Python packages required for operation.

### Core Dependencies Overview

```mermaid
graph TB
    subgraph "Python Runtime Environment"
        PYTHON["python 3.9+"]
    end
    
    subgraph "Required Packages"
        EASYDICT["easydict"]
        FEEDPARSER["feedparser"] 
        PYTZ["pytz"]
    end
    
    subgraph "Core Modules"
        MAIN["main.py"]
        UTILS["utils.py"]
    end
    
    subgraph "External APIs"
        ARXIV_API["arXiv API"]
        GITHUB_API["GitHub API"]
    end
    
    PYTHON --> EASYDICT
    PYTHON --> FEEDPARSER
    PYTHON --> PYTZ
    
    EASYDICT --> UTILS
    FEEDPARSER --> UTILS
    PYTZ --> UTILS
    
    UTILS --> MAIN
    MAIN --> ARXIV_API
    MAIN --> GITHUB_API
```

**Sources:** [requirements.txt:1-3]()

### Dependency Details

| Package | Version | Purpose | Usage Location |
|---------|---------|---------|----------------|
| `easydict` | Latest | Configuration object management | [utils.py]() for paper data structures |
| `feedparser` | Latest | XML/RSS parsing | [utils.py]() for arXiv API response processing |
| `pytz` | Latest | Timezone handling | [main.py]() for Beijing timezone operations |

The system intentionally avoids version pinning to ensure compatibility with the latest package releases and security updates in the GitHub Actions environment.

**Sources:** [requirements.txt:1-3]()

## Configuration Management

The DailyArXiv system uses embedded configuration constants rather than external configuration files. This approach simplifies deployment and reduces the number of files that need to be managed.

### Configuration Architecture

```mermaid
graph LR
    subgraph "Configuration Sources"
        HARDCODED["Hardcoded Constants"]
        ENV_VARS["Environment Variables"]
        GITHUB_SECRETS["GitHub Secrets"]
    end
    
    subgraph "Configuration Categories"
        API_CONFIG["API Configuration"]
        PAPER_LIMITS["Paper Limits"]
        KEYWORDS["Research Keywords"]
        TIMEZONE["Timezone Settings"]
    end
    
    subgraph "Application Components"
        MAIN_PY["main.py"]
        UTILS_PY["utils.py"]
        WORKFLOW["github_actions.yml"]
    end
    
    HARDCODED --> API_CONFIG
    HARDCODED --> PAPER_LIMITS
    HARDCODED --> KEYWORDS
    ENV_VARS --> TIMEZONE
    GITHUB_SECRETS --> WORKFLOW
    
    API_CONFIG --> UTILS_PY
    PAPER_LIMITS --> MAIN_PY
    KEYWORDS --> MAIN_PY
    TIMEZONE --> MAIN_PY
    
    WORKFLOW --> MAIN_PY
```

**Sources:** [main.py](), [utils.py](), [.github/workflows/]()

### Key Configuration Constants

The system configuration is distributed across the main processing files:

- **Paper Retrieval Limits**: Maximum number of papers per keyword (`max_result`, `issues_result`)
- **Research Keywords**: Predefined list of research areas (Time Series, Trajectory, Graph Neural Networks)
- **API Endpoints**: arXiv API base URL and query parameters
- **Timezone Settings**: Beijing timezone for scheduling alignment
- **File Paths**: Output file locations for README.md and ISSUE_TEMPLATE.md

**Sources:** [main.py](), [utils.py]()

## Runtime Environment

The system is designed to run in a containerized GitHub Actions environment with minimal setup requirements.

### Environment Requirements

```mermaid
graph TB
    subgraph "GitHub Actions Runner"
        UBUNTU["ubuntu-latest"]
        PYTHON_SETUP["actions/setup-python@v4"]
        PIP_INSTALL["pip install -r requirements.txt"]
    end
    
    subgraph "Runtime Components"
        PYTHON39["Python 3.9"]
        PIP["pip package manager"]
        GIT["git client"]
    end
    
    subgraph "Execution Context"
        REPO_ACCESS["Repository write access"]
        ISSUE_CREATE["Issue creation permissions"]
        NETWORK["Internet connectivity"]
    end
    
    UBUNTU --> PYTHON_SETUP
    PYTHON_SETUP --> PYTHON39
    PYTHON39 --> PIP
    PIP --> PIP_INSTALL
    
    PIP_INSTALL --> REPO_ACCESS
    REPO_ACCESS --> ISSUE_CREATE
    ISSUE_CREATE --> NETWORK
```

**Sources:** [.github/workflows/](), [requirements.txt:1-3]()

### Execution Environment Setup

The system requires:
- **Python Version**: 3.9 or higher
- **Package Manager**: pip for dependency installation
- **Git Access**: Repository write permissions for file updates
- **Network Access**: Outbound HTTPS connections to arXiv API
- **GitHub Permissions**: Issue creation and repository modification rights

**Sources:** [.github/workflows/]()

## Development Setup

For local development and testing, the system can be set up with minimal configuration.

### Local Development Configuration

```mermaid
flowchart TD
    subgraph "Development Environment"
        CLONE["git clone repository"]
        PYTHON_ENV["Python 3.9+ environment"]
        INSTALL_DEPS["pip install -r requirements.txt"]
    end
    
    subgraph "Configuration Steps"
        SET_TIMEZONE["Configure timezone (optional)"]
        TEST_API["Test arXiv API access"]
        CHECK_PERMS["Verify file write permissions"]
    end
    
    subgraph "Execution"
        RUN_MAIN["python main.py"]
        CHECK_OUTPUT["Verify README.md updates"]
        CHECK_ISSUES["Verify ISSUE_TEMPLATE.md"]
    end
    
    CLONE --> PYTHON_ENV
    PYTHON_ENV --> INSTALL_DEPS
    INSTALL_DEPS --> SET_TIMEZONE
    SET_TIMEZONE --> TEST_API
    TEST_API --> CHECK_PERMS
    CHECK_PERMS --> RUN_MAIN
    RUN_MAIN --> CHECK_OUTPUT
    CHECK_OUTPUT --> CHECK_ISSUES
```

**Sources:** [requirements.txt:1-3](), [main.py](), [utils.py]()

### Development Dependencies

Local development requires only the three packages specified in `requirements.txt`. No additional development-specific dependencies are needed as the system uses only Python standard library features beyond the core requirements.

**Sources:** [requirements.txt:1-3]()

## Version Control Configuration

The repository includes a comprehensive `.gitignore` file to prevent tracking of unnecessary files and maintain a clean repository structure.

### Ignored File Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| Python artifacts | Compiled bytecode and cache | `__pycache__/`, `*.pyc`, `*.py[cod]` |
| Data files | Research data and exports | `*.npz`, `*.npy`, `*.csv`, `*.pkl` |
| Environment files | Virtual environments and configs | `.venv/`, `.env`, `venv/` |
| IDE artifacts | Editor-specific files | `.vscode/`, `.spyderproject` |
| Distribution files | Build and packaging outputs | `build/`, `dist/`, `*.egg-info/` |

**Sources:** [.gitignore:1-174]()

### Repository File Management

The `.gitignore` configuration ensures that only source code, documentation, and configuration files are tracked in version control. This prevents the repository from becoming cluttered with temporary files, compiled artifacts, or environment-specific configurations.

Notable exclusions include:
- All data file formats commonly used in research (`*.npz`, `*.npy`, `*.csv`, `*.pkl`, `*.h5`, `*.pt`)
- Python compilation artifacts and virtual environments
- IDE and editor configuration directories
- Build and distribution artifacts

**Sources:** [.gitignore:6-16](), [.gitignore:137-144]()