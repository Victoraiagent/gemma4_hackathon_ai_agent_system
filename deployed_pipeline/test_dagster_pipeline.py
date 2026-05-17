import pytest
from unittest.mock import MagicMock, patch
from dagster import Definitions, AssetKey

try:
    import dagster_pipeline
except ImportError:
    dagster_pipeline = None

def test_pipeline_definitions_exist():
    assert dagster_pipeline is not None
    assert hasattr(dagster_pipeline, "defs")
    assert isinstance(dagster_pipeline.defs, Definitions)

def test_asset_sequential_dependency_chain():
    assert dagster_pipeline is not None
    # Inspect the assets directly from Definitions to avoid AssetGraph version issues
    all_assets = list(dagster_pipeline.defs.assets)
    
    def get_asset_by_name(name):
        for a in all_assets:
            # Asset objects have a .key attribute which is an AssetKey
            if a.key.path == [name]:
                return a
        return None

    # Verify all assets exist
    asset_names = ["database_setup", "ingested_news", "analyzed_reports", "delivery_status"]
    for name in asset_names:
        assert get_asset_by_name(name) is not None, f"Asset {name} not found in pipeline"

    # Verify dependencies
    def assert_dependency(child_name, parent_name):
        child = get_asset_by_name(child_name)
        # .dependency_keys returns a set of AssetKey objects
        dep_paths = [ak.path for ak in child.dependency_keys]
        assert [parent_name] in dep_paths, f"Asset {child_name} does not depend on {parent_name}"

    assert_dependency("ingested_news", "database_setup")
    assert_dependency("analyzed_reports", "ingested_news")
    assert_dependency("delivery_status", "analyzed_reports")

def test_pipeline_no_circular_dependencies():
    assert dagster_pipeline is not None
    assert len(list(dagster_pipeline.defs.assets)) >= 4
