import os
from pathlib import Path

from cldk import CLDK
from cldk.analysis import AnalysisLevel



def build_analysis(project_path: str):
    application_name = Path(project_path).name
    analysis_path = Path(__file__).parent.joinpath('output', application_name)
    os.makedirs(analysis_path, exist_ok=True)
    analysis = CLDK(language="java").analysis(
        project_path=project_path,
        analysis_level=AnalysisLevel.symbol_table,
        analysis_json_path=analysis_path,
        eager=False
    )
    return analysis