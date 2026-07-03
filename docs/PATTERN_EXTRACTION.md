# Pattern Extraction Feature

## Overview

The pattern extraction feature analyzes labeled data that doesn't fit existing patterns and uses an LLM to discover new patterns that could be added to your taxonomy. This is particularly useful when you have examples labeled as "does_not_fit_with_any_pattern" and want to identify common characteristics that warrant creating new pattern categories.

## How It Works

1. **Input**: JSON files containing labeled test data from multiple projects
2. **Analysis**: The system identifies all examples with a specific field value (e.g., `data_load_mechanism: "does_not_fit_with_any_pattern"`)
3. **Pattern Discovery**: An LLM analyzes the reasoning provided for each example and identifies common patterns
4. **Output**: A structured list of newly discovered patterns with:
   - Pattern name and description
   - Distinguishing features
   - Code indicators (method calls, annotations, etc.)
   - Confidence score
   - Number of examples exhibiting the pattern

## Usage

### Command Line Interface

```bash
angelica extract-patterns \
    --config coaster_label/config/coaster_config.py \
    --json-dir coaster_label/config/output \
    --field data_load_mechanism \
    --value does_not_fit_with_any_pattern \
    --reasoning-field data_load_mechanism_reasoning \
    --max-examples 50 \
    --out new_patterns.json
```

### Parameters

- `--config`: Path to your configuration file (defines schema and existing patterns)
- `--json-dir`: Directory containing labeled JSON files (can have subdirectories for different projects)
- `--field`: The field to analyze (e.g., `data_load_mechanism`, `data_cleanup_mechanism`)
- `--value`: The value to filter by (default: `does_not_fit_with_any_pattern`)
- `--reasoning-field`: The field containing reasoning for the label (e.g., `data_load_mechanism_reasoning`)
- `--max-examples`: Maximum number of examples to analyze (default: 50)
- `--out`: Optional output JSON file path for results

### Expected JSON Structure

The JSON files in your `--json-dir` should follow this structure:

```json
{
  "/path/to/TestFile.java": {
    "doc_id": "123",
    "decided_by": "adjudicator_1",
    "final_label": {
      "data_load_mechanism": "does_not_fit_with_any_pattern",
      "data_load_mechanism_reasoning": "The test uses a custom fixture loader that doesn't match any existing patterns...",
      "is_integration_test": true,
      ...
    }
  },
  "/path/to/AnotherTest.java": {
    ...
  }
}
```

## Example Workflow

### 1. Run Labeling on Multiple Projects

First, label your test files across multiple projects:

```bash
# Project 1
angelica label-units \
    --config coaster_label/config/coaster_config.py \
    --project-path /path/to/project1 \
    --analysis-provider coaster_label/config/cldk_analysis_provider.py \
    --out coaster_label/config/output/project1/labels.json

# Project 2
angelica label-units \
    --config coaster_label/config/coaster_config.py \
    --project-path /path/to/project2 \
    --analysis-provider coaster_label/config/cldk_analysis_provider.py \
    --out coaster_label/config/output/project2/labels.json

# ... more projects
```

### 2. Extract New Patterns

Analyze all the "does_not_fit_with_any_pattern" examples:

```bash
angelica extract-patterns \
    --config coaster_label/config/coaster_config.py \
    --json-dir coaster_label/config/output \
    --field data_load_mechanism \
    --value does_not_fit_with_any_pattern \
    --reasoning-field data_load_mechanism_reasoning \
    --max-examples 100 \
    --out new_data_load_patterns.json
```

### 3. Review Results

The output will show discovered patterns:

```
================================================================================
PATTERN EXTRACTION RESULTS
================================================================================

📈 Total examples analyzed: 47
🆕 New patterns discovered: 3

📝 Analysis Summary:
Identified 3 distinct patterns across 47 examples that don't fit existing categories...

================================================================================
DISCOVERED PATTERNS
================================================================================

🔹 Pattern 1: custom_fixture_loader
   Category: data_load_mechanism
   Confidence: 0.85
   Examples: 15

   Description:
   Tests use custom fixture loading mechanisms implemented as utility classes
   or helper methods that programmatically load test data from various sources.

   Distinguishing Features:
   • Custom utility classes for data loading
   • Programmatic data construction in helper methods
   • Not framework-specific annotations or methods

   Code Indicators:
   • TestDataLoader.load()
   • FixtureHelper.setupData()
   • Custom builder patterns for test data

   📋 Example References (for verification):
   1. File: /path/to/project1/TestClass1.java
      Doc ID: 123 | Project: project1
   2. File: /path/to/project2/TestClass2.java
      Doc ID: 456 | Project: project2
   3. File: /path/to/project1/TestClass3.java
      Doc ID: 789 | Project: project1
   ... and 12 more examples
```

### 4. Update Your Taxonomy

Based on the discovered patterns, update your configuration:

```python
# In coaster_config.py

DataManipulationMechanism = Literal[
    "framework_annotation",
    "framework_method_call",
    "rest_api_call",
    "data_scripts",
    "database_query",
    "custom_fixture_loader",  # NEW PATTERN
    "does_not_fit_with_any_pattern",
    "not_needed",
    "not_present",
]

PATTERNS = """Known Data Manipulation Patterns:

"framework_annotation": Data is manipulated using framework annotations; e.g., @Sql in Spring.
"framework_method_call": Data is manipulated using framework method call; e.g., CrudRepository.delete()
"rest_api_call": Data is manipulated via pure REST/HTTP API calls
"data_scripts": Data is manipulated via automation scripts
"database_query": Data is manipulated via database queries
"custom_fixture_loader": Data is loaded using custom utility classes or helper methods  # NEW
"not_present": Data manipulation is needed but not present
"not_needed": Data manipulation is not needed
"does_not_fit_with_any_pattern": Data manipulation pattern does not fit with any of the other patterns
"""
```

### 5. Re-label with Updated Taxonomy

After updating your patterns, you can re-label the data to use the new categories:

```bash
# Re-run labeling with updated config
angelica label-units \
    --config coaster_label/config/coaster_config.py \
    --project-path /path/to/project \
    --analysis-provider coaster_label/config/cldk_analysis_provider.py \
    --fresh-build \
    --out updated_labels.json
```

## Output Format

The `--out` JSON file contains:

```json
{
  "field_name": "data_load_mechanism",
  "field_value": "does_not_fit_with_any_pattern",
  "reasoning_field": "data_load_mechanism_reasoning",
  "total_examples_analyzed": 47,
  "analysis_summary": "Identified 3 distinct patterns...",
  "new_patterns": [
    {
      "pattern_name": "custom_fixture_loader",
      "pattern_description": "Tests use custom fixture loading mechanisms...",
      "pattern_category": "data_load_mechanism",
      "example_count": 15,
      "confidence_score": 0.85,
      "distinguishing_features": [
        "Custom utility classes for data loading",
        "Programmatic data construction in helper methods"
      ],
      "code_indicators": [
        "TestDataLoader.load()",
        "FixtureHelper.setupData()"
      ],
      "example_references": [
        {
          "file_path": "/path/to/project1/TestClass1.java",
          "doc_id": "123",
          "project": "project1"
        },
        {
          "file_path": "/path/to/project2/TestClass2.java",
          "doc_id": "456",
          "project": "project2"
        }
      ]
    }
  ]
}
```

## Tips

1. **Start with a reasonable sample size**: Use `--max-examples 50-100` initially to get quick results
2. **Analyze one field at a time**: Focus on one field (e.g., `data_load_mechanism`) before moving to others
3. **Review confidence scores**: Only consider patterns with confidence > 0.7
4. **Validate with domain experts**: Review discovered patterns with team members familiar with the codebase
5. **Use example references**: The file paths and doc IDs allow you to manually inspect the actual code examples to verify the pattern
6. **Iterate**: After adding new patterns, re-run extraction to see if remaining "does_not_fit" examples reveal more patterns

## Troubleshooting

### No patterns discovered

- Check if examples actually exist with the specified field value
- Increase `--max-examples` to analyze more data
- Review the reasoning fields to ensure they contain meaningful explanations

### Low confidence scores

- The examples might be too diverse to form clear patterns
- Consider analyzing a subset of projects first
- Review the reasoning quality in your labels

### Missing code in examples

- Ensure your JSON files include the code or that the file paths are accessible
- The system will try to read files from disk if code is not in the JSON