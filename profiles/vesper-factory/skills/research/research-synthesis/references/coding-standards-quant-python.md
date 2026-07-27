# Python Coding Standards & Quant Project Structure Research

> Reference file for `research-synthesis` skill.
> Compiled 2026-07-05 from multi-source research on Python style guides,
> Clean Architecture, and quant project structures applied to a
> factor-modeling system (Vesper).

## Source Summary Table

| Source | URL | Key Contribution | Best For |
|--------|-----|------------------|----------|
| Google Python Style Guide | google.github.io/styleguide/pyguide.html | Language rules (imports, exceptions, type annotations), style rules (naming, docstrings, line length) | The single best reference for what good Python looks like at scale |
| PEP 8 | peps.python.org/pep-0008/ | Official Python conventions (indentation, naming, blank lines, imports) | Baseline — all other guides build on this |
| PEP 257 | peps.python.org/pep-0257/ | Docstring conventions (one-line vs multi-line, what to document) | Standardizing docstring format (Google-style or NumPyDoc) |
| Hitchhiker's Guide | docs.python-guide.org/writing/structure/ | Repository structure (module at root, tests separate, Makefile), module design | Quick reference for repo layout |
| Clean Architecture w/ Python | medium.com/@shaliamekh | Ports & Adapters pattern, domain entities vs use cases, dependency inversion | Structuring a factor framework with pluggable data sources |
| Clean Code in Python | medium.com/@denis-learns-tech | KISS, DRY, Boy Scout, polymorphism over if/else, small functions | Day-to-day factor coding discipline |
| SOLID in Python | codesignal.com | SRP, OCP, LSP, ISP, DIP with Python examples | Designing factor class hierarchies |
| Quant Trading Project Structure | parrondo.github.io | Cookiecutter-based quant structure with data/raw/processed notebooks/ src/ | Getting a quant research project off the ground |
| Zipline | github.com/quantopian/zipline | Pipeline DAG architecture, CustomFactor base class, DataPortal abstraction | Reference implementation for factor computation engine |
| PyPortfolioOpt | github.com/PyPortfolio/PyPortfolioOpt | Modular optimizer design, NumPyDoc docstrings, ruff linting, backward-compat shims | Reference for library-quality quant code |

## Key Cross-Cutting Themes

1. **Small, focused modules** — Every guide says the same thing: one module, one responsibility. Factor models should each be their own file with a shared base class.

2. **Type annotations everywhere** — Google mandates them. PEP 8 encourages them. The quant libraries are adopting them. This is table stakes now.

3. **Config over code** — Factor parameters, universe definitions, and portfolio constraints belong in YAML/TOML, not hardcoded in factor computation functions.

4. **Data immutability** — Raw data is never modified. Every transformation produces new files. This is especially critical for quant backtesting where you need to reproduce results.

5. **Abstract base classes for pluggability** — Zipline's `CustomFactor`, PyPortfolioOpt's `BaseOptimizer`, Clean Architecture's repository interfaces. The pattern is universal: define an interface, implement concretions, inject at runtime.

6. **Docstrings are code** — They're not optional. They need a consistent format (Google-style or NumPyDoc). They should explain *why* not just *what*.

## Common Vesper Violations (from actual codebase scan)

- `app/services/` is flat with 15+ modules — should be sub-packaged into `factors/`, `data/`, `models/`
- Filenames up to ~95 characters — should be concise snake_case
- `deploy/src/na/` is 3 levels deep — should flatten to `vesper/trading/`
- No `__init__.py` in some packages — breaks `-m` invocation
- Mixed docstring formats — standardize on Google-style
- No type annotations on most functions — adding these catches real bugs
- No `pyproject.toml` — prevents modern tooling (ruff, mypy, Black auto-config)
- No `pre-commit` hooks — linting is opt-in rather than automatic

## Recommended Tool Stack

| Tool | Install | Config |
|------|---------|--------|
| ruff | `pip install ruff` | `target-version = "py311"`, `select = ["E", "F", "I", "N", "W", "UP"]` |
| mypy | `pip install mypy` | `--strict` on new code, `--ignore-missing-imports` on legacy |
| Black | `pip install black` | `line-length = 88` |
| pre-commit | `pip install pre-commit` | hooks: ruff, black, trailing-whitespace, end-of-file-fixer |
| pytest | `pip install pytest pytest-cov` | `testpaths = tests`, `addopts = -ra` |
| Sphinx | `pip install sphinx sphinx-autodoc` | Google-style or NumPyDoc docstrings, autodoc for API docs |

## References

- Google Python Style Guide: https://google.github.io/styleguide/pyguide.html
- PEP 8: https://peps.python.org/pep-0008/
- PEP 257: https://peps.python.org/pep-0257/
- Hitchhiker's Guide (Structure): https://docs.python-guide.org/writing/structure/
- Clean Architecture with Python: https://medium.com/@shaliamekh/clean-architecture-with-python-d62712fd8d4f
- Clean Code in Python: https://medium.com/@denis-learns-tech/how-to-apply-uncle-bobs-clean-code-principles-in-python-6a34e4465d10
- SOLID in Python: https://codesignal.com/learn/courses/applying-clean-code-principles-in-python/lessons/applying-solid-principles-in-python
- Quant Trading Project Structure: https://parrondo.github.io/quant-trading-project-structure/
- Cookiecutter Data Science: https://cookiecutter-data-science.drivendata.org/
- Zipline: https://github.com/quantopian/zipline
- PyPortfolioOpt: https://github.com/PyPortfolio/PyPortfolioOpt
- QuantConnect LEAN: https://www.quantconnect.com/