"""The [capture] config section and the DEV_EVENT source type."""

from __future__ import annotations

from pathlib import Path

from wikiforge.config.settings import Config, load_config, write_default_config
from wikiforge.models.enums import SourceType


def test_dev_event_source_type() -> None:
    assert SourceType.DEV_EVENT == "dev_event"


def test_capture_defaults_when_section_absent(tmp_path: Path) -> None:
    # A config with no [capture] section still validates and defaults.
    (tmp_path / "config.toml").write_text('wiki_name = "x"\n' + _MINIMAL_TAIL, encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.capture.auto is True
    assert cfg.capture.summarize is True
    assert cfg.capture.topic_label == "development-log"
    assert cfg.capture.max_diff_lines == 200
    assert cfg.capture.redact is True


def test_default_config_documents_capture(tmp_path: Path) -> None:
    write_default_config(tmp_path, wiki_name="Test")
    cfg = load_config(tmp_path)
    assert isinstance(cfg, Config)
    assert cfg.capture.summarize is True


# A minimal but valid remainder for a config file (all required sections).
_MINIMAL_TAIL = """
[models]
cheap = "c"
flagship = "f"
[pricing."c"]
input = 1.0
[pricing."f"]
input = 1.0
[web_search]
tool_version = "v"
max_uses = 1
[volatility]
LOW = 1
MEDIUM = 1
HIGH = 1
[embedding]
provider = "auto"
voyage_model = "v"
local_model = "l"
dim = 4
local_dim = 4
[retrieval]
rrf_k = 60
top_k = 8
chunk_tokens = 400
chunk_overlap = 40
rerank_model = "r"
[research]
standard_personas = ["a"]
deep_extra = []
max_extra = []
[confidence]
count_target = 5
div_target = 3
w_count = 0.25
w_diversity = 0.25
w_recency = 0.25
w_evidence = 0.25
conflict_penalty_per = 0.1
conflict_penalty_cap = 0.5
"""
