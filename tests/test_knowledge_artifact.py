import json

from atlas.knowledge import KnowledgeArtifact


def _sample() -> KnowledgeArtifact:
    return KnowledgeArtifact(
        id="ka-001",
        domain="security/cve",
        source_id="nvd-feed",
        content={"cve_id": "CVE-2024-0001", "severity": "HIGH"},
        provenance={
            "url": "https://nvd.nist.gov/feeds/json/cve/1.1/",
            "fetched_at": "2024-01-15T10:30:00Z",
            "raw_sha256": "abc123def456",
        },
    )


def test_default_schema_version():
    ka = _sample()
    assert ka.schema_version == 1


def test_round_trip():
    ka = _sample()
    restored = KnowledgeArtifact.from_dict(ka.to_dict())
    assert restored == ka


def test_json_serializable():
    ka = _sample()
    # must not raise
    json.dumps(ka.to_dict())


def test_string_content_round_trip():
    ka = KnowledgeArtifact(
        id="ka-002",
        domain="general",
        source_id="manual",
        content="plain text payload",
        provenance={"endpoint": "/api/v1/data", "fetched_at": "2024-01-15T00:00:00Z", "raw_sha256": "ff00"},
        schema_version=2,
    )
    assert KnowledgeArtifact.from_dict(ka.to_dict()) == ka


def test_frozen():
    ka = _sample()
    try:
        ka.id = "mutated"  # type: ignore[misc]
        assert False, "should be frozen"
    except (AttributeError, TypeError):
        pass
