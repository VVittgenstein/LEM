"""lem_pipeline: data and parameter generation pipeline for the L1 ocean-surrounded continent samples.

The pipeline has five stages, all driven by the decisions recorded in ``final-strategy/architecture-dataflow.md``
section 4.1.5 and ``current.md`` T-010:

1. ``reference`` / ``distributions``: reference-population statistics (34 low-latitude landmasses) and sampling helpers.
2. generator modules (land region, periphery, sea level, activities, parameter arrays): sample one configuration.
3. ``driver``: run fastscapelib-fortran 2.8.4 with marine module, precipitation, time-varying uplift and sea level.
4. ``checks``: T-time acceptance checks (ocean band, occupancy, sea-land statistics).
5. ``runner``: parallel execution (one model per process) and export in the viewer's ``meta.json`` format.

Every rule that is an assumption rather than a sourced value carries an ``evidence_state`` label in the configuration
it produces; see ``docs/work/2026-09-09-q1-pretasks/merged/generator-inputs.csv`` for the sourced distributions.
"""

__version__ = "0.1.0"
