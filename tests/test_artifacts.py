# ABOUTME: Tests for artifact registry with dual persistence (JSON + Markdown).
# ABOUTME: Covers registration, status updates, filtering, serialization, and markdown rendering.

import json
from pathlib import Path

import pytest

from scaffold.artifacts import Artifact, ArtifactRegistry


class TestArtifact:
    """Tests for the Artifact dataclass."""

    def test_default_values(self):
        a = Artifact(name="test-artifact", lane="infrastructure", status="pass", path="results/test.json")
        assert a.name == "test-artifact"
        assert a.lane == "infrastructure"
        assert a.status == "pass"
        assert a.path == "results/test.json"
        assert a.description == ""
        assert a.registered_at is not None
        assert "T" in a.registered_at

    def test_custom_description(self):
        a = Artifact(
            name="my-artifact",
            lane="oracle_alpha",
            status="mixed",
            path="results/oracle/data.json",
            description="Oracle alpha weights for pilot set",
        )
        assert a.description == "Oracle alpha weights for pilot set"

    def test_valid_statuses(self):
        for status in ("pass", "fail", "mixed", "partial", "planning", "superseded"):
            a = Artifact(name="a", lane="l", status=status, path="p")
            assert a.status == status


class TestArtifactRegistration:
    """Tests for registering artifacts in the registry."""

    def test_register_adds_artifact(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        a = Artifact(name="test", lane="infrastructure", status="pass", path="results/test.json")
        reg.register(a)
        assert len(reg.get_by_lane("infrastructure")) == 1

    def test_register_multiple_artifacts(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="a1", lane="infra", status="pass", path="r/a1.json"))
        reg.register(Artifact(name="a2", lane="infra", status="fail", path="r/a2.json"))
        reg.register(Artifact(name="a3", lane="oracle", status="mixed", path="r/a3.json"))
        assert len(reg.get_by_lane("infra")) == 2
        assert len(reg.get_by_lane("oracle")) == 1


class TestStatusUpdates:
    """Tests for updating artifact statuses."""

    def test_update_status(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="test", lane="infra", status="planning", path="r/t.json"))
        reg.update_status("test", "pass")
        artifacts = reg.get_by_lane("infra")
        assert artifacts[0].status == "pass"

    def test_update_status_unknown_artifact_raises(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        with pytest.raises(ValueError, match="Artifact .* not found"):
            reg.update_status("nonexistent", "pass")

    def test_supersede(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="old-result", lane="oracle", status="pass", path="r/old.json"))
        reg.supersede("old-result")
        artifacts = reg.get_by_lane("oracle")
        assert artifacts[0].status == "superseded"

    def test_supersede_unknown_artifact_raises(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        with pytest.raises(ValueError, match="Artifact .* not found"):
            reg.supersede("nonexistent")


class TestGetByLane:
    """Tests for filtering artifacts by lane."""

    def test_get_by_lane_returns_correct_artifacts(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="a1", lane="infra", status="pass", path="r/a1.json"))
        reg.register(Artifact(name="a2", lane="oracle", status="fail", path="r/a2.json"))
        reg.register(Artifact(name="a3", lane="infra", status="mixed", path="r/a3.json"))

        infra = reg.get_by_lane("infra")
        assert len(infra) == 2
        assert {a.name for a in infra} == {"a1", "a3"}

    def test_get_by_lane_empty(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        assert reg.get_by_lane("nonexistent") == []


class TestJsonPersistence:
    """Tests for JSON save/load roundtrip."""

    def test_save_creates_json_file(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="test", lane="infra", status="pass", path="r/t.json"))
        reg.save()
        json_path = tmp_path / ".scaffold" / "artifacts.json"
        assert json_path.exists()

    def test_save_produces_valid_json(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="test", lane="infra", status="pass", path="r/t.json"))
        reg.save()
        json_path = tmp_path / ".scaffold" / "artifacts.json"
        data = json.loads(json_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test"

    def test_load_roundtrip(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(
            Artifact(
                name="artifact1",
                lane="oracle",
                status="pass",
                path="results/oracle/data.json",
                description="Oracle data",
            )
        )
        reg.register(
            Artifact(name="artifact2", lane="infra", status="fail", path="results/infra/log.json")
        )
        reg.save()

        loaded = ArtifactRegistry.load(tmp_path)
        oracle_artifacts = loaded.get_by_lane("oracle")
        assert len(oracle_artifacts) == 1
        assert oracle_artifacts[0].name == "artifact1"
        assert oracle_artifacts[0].description == "Oracle data"

        infra_artifacts = loaded.get_by_lane("infra")
        assert len(infra_artifacts) == 1
        assert infra_artifacts[0].name == "artifact2"
        assert infra_artifacts[0].status == "fail"

    def test_save_also_creates_markdown(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="test", lane="infra", status="pass", path="r/t.json"))
        reg.save()
        md_path = tmp_path / "results" / "RESULTS_INDEX.md"
        assert md_path.exists()


class TestMarkdownRendering:
    """Tests for markdown output format."""

    def test_render_markdown_has_header(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        md = reg.render_markdown()
        assert "# Results Index" in md

    def test_render_markdown_has_rules_section(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        md = reg.render_markdown()
        assert "## Rules" in md
        assert "Every artifact saved under `results/`" in md

    def test_render_markdown_groups_by_lane(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="a1", lane="infrastructure", status="pass", path="r/a1.json"))
        reg.register(Artifact(name="a2", lane="oracle_alpha", status="fail", path="r/a2.json"))
        md = reg.render_markdown()

        assert "## Infrastructure" in md
        assert "## Oracle Alpha" in md
        assert "| a1 |" in md
        assert "| a2 |" in md

    def test_render_markdown_table_format(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(
            Artifact(name="my-artifact", lane="infra", status="pass", path="results/infra/data.json")
        )
        md = reg.render_markdown()
        assert "| Artifact | Lane | Status | Path |" in md
        assert "|---|---|---|---|" in md
        assert "| my-artifact | infra | pass | results/infra/data.json |" in md

    def test_render_markdown_empty_lanes_placeholder(self, tmp_path):
        """Empty registry should not crash, just render header and rules."""
        reg = ArtifactRegistry(tmp_path)
        md = reg.render_markdown()
        # Should render without error
        assert "# Results Index" in md

    def test_render_markdown_lane_header_formatting(self, tmp_path):
        """Lane names with underscores should be title-cased in section headers."""
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="a1", lane="oracle_alpha", status="pass", path="r/a.json"))
        md = reg.render_markdown()
        assert "## Oracle Alpha" in md

    def test_render_markdown_multiple_artifacts_same_lane(self, tmp_path):
        reg = ArtifactRegistry(tmp_path)
        reg.register(Artifact(name="a1", lane="infra", status="pass", path="r/a1.json"))
        reg.register(Artifact(name="a2", lane="infra", status="fail", path="r/a2.json"))
        md = reg.render_markdown()
        assert "| a1 |" in md
        assert "| a2 |" in md
