import os
from pathlib import Path

from cldk import CLDK
from cldk.analysis import AnalysisLevel


def build_analysis(
    project_path: str,
    *,
    cache_analysis: bool = False,
    analysis_cache_dir: str | None = None,
):
    analysis_path = None
    if cache_analysis:
        application_name = Path(project_path).name
        cache_root = (
            Path(analysis_cache_dir).expanduser()
            if analysis_cache_dir
            else Path(__file__).parent.joinpath("output")
        )
        analysis_path = cache_root.joinpath(application_name)
        os.makedirs(analysis_path, exist_ok=True)

    analysis = CLDK(language="java").analysis(
        project_path=project_path,
        analysis_level=AnalysisLevel.symbol_table,
        analysis_json_path=analysis_path,
        eager=False
    )
    return analysis
