import re
from enum import Enum
from typing import Optional, Literal

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from hamster.code_analysis.common import CommonAnalysis
from hamster.code_analysis.model.models import TestingFramework
from hamster.extract_statistics.overall_characteristics.overall_characteristics import OverallCharacteristics
from pydantic import BaseModel, Field, model_validator

from angelica.models.config import AgenticConfig, PromptSpec, StoreSpec, LabelingContext
from angelica.models.config import BuiltDocument, LabelingUnit
from coaster_label.config.prompt_builder import PromptBuilder


# LLM-identified data setup labels:
#     "inline_programmatic_data_creation",
#     "mocking_stubbing_data_provision",
#     "file_system_and_resource_data_management",
#     "application_specific_data_setup_via_api",
#     "test_data_builder_factory_helper",
#     "custom_protocol_interaction",
#     "custom_database_helper_methods",
#     "internal_application_data_access",
#     "in_memory_server_setup",
#     "simulated_api_call",
#     "composite_data_load"
#
# LLM-identified data cleanup labels
#     "application_specific_cleanup",
#     "java_api_and_file_system_cleanup",
#     "system_property_manipulation",
#     "try_with_resources_cleanup",
#     "process_management_call",
#     "mixed_cleanup_mechanisms"

DataManipulationLocation = Literal[
    "test_fixture_method", "test_method", "test_annotation", "not_present"
]

DataManipulationMechanism = Literal[
    "framework_annotation",
    "persistence_framework_api_call",
    "database_jdbc_api_call",
    "rest_http_api_call",
    "file_system_resource_api_call",
    "mocking_stubbing_api_call",
    "custom_protocol_api_call",
    "process_management_api_call",
    "in_memory_server_setup",
    "other_java_api_call",
    # "test_helper_builder_call",
    # "application_method_call",
    "does_not_fit_with_any_pattern",
    "not_needed",
    "not_present"
]


class JavaTestLabel(BaseModel):
    is_integration_test: bool = Field(
        description="True if the test class is a web API test (i.e., the test invokes application services), False otherwise."
    )
    data_load_location: DataManipulationLocation = Field(
        description=(
            "Where pre-test data loading/preparation is visible. One of: "
            "test_fixture_method | test_method | test_annotation | not_present. "
            "Do not use the application's behavior under test as data loading unless it is clearly a setup step."
        )
    )
    data_load_mechanism: DataManipulationMechanism = Field(
        description=(
            "One of: framework_annotation | persistence_framework_api_call | database_jdbc_api_call | rest_http_api_call | "
            "file_system_resource_api_call | mocking_stubbing_api_call | custom_protocol_api_call | process_management_api_call | "
            "in_memory_server_setup | other_java_api_call | " 
            # "test_helper_builder_call | " 
            # "application_method_call | "
            "does_not_fit_with_any_pattern | not_needed | not_present. "
            "Choose the primary mechanism that prepares persistent application state before the tested behavior is exercised. "
            "Do not classify the application's behavior under test as data loading merely because it creates or changes data. "
            "Do not classify configuration/property changes as data loading unless they directly create/provision persistent state. "
            # "If the test both prepares persistent state through repositories/entities/helpers and stubs services, prefer "
            # "persistence_framework_api_call for data loading; use mocking_stubbing_api_call only when stubbing/mocking is "
            # "the primary or only data-provisioning mechanism."
        )
    )
    data_load_mechanism_reasoning: str = Field(...)
    data_load_mechanism_is_required: bool = Field(
        description="Whether pre-test data loading/preparation is required for the test to run or reach the behavior being tested."
    )
    data_cleanup_location: DataManipulationLocation = Field(
        description=(
            "Where test data cleanup/reset is visible. One of: "
            "test_fixture_method | test_method | test_annotation | not_present. "
            "Do not use the application's behavior under test as cleanup unless it is clearly restoring/resetting test state."
        )
    )
    data_cleanup_mechanism: DataManipulationMechanism = Field(
        description=(
            "One of: framework_annotation | persistence_framework_api_call | database_jdbc_api_call | rest_http_api_call | "
            "file_system_resource_api_call | mocking_stubbing_api_call | custom_protocol_api_call | process_management_api_call | "
            "in_memory_server_setup | other_java_api_call | " 
            # "test_helper_builder_call | " 
            # "application_method_call | "
            "does_not_fit_with_any_pattern | not_needed | not_present. "
            "Choose the primary mechanism that resets/restores test state, not the application's behavior being verified. "
            "Do not classify configuration/property restoration as data cleanup unless it directly restores persistent state."
        )
    )
    data_cleanup_mechanism_reasoning: str = Field(description="Why you chose the cleanup location/mechanism.")
    data_cleanup_mechanism_is_required: bool = Field(
        description="Whether cleanup/reset is required to prepare or restore test state, excluding the behavior being tested."
    )
    is_test_executed_against_deployed_services: bool = Field(
        description="True if a test requires the application to be deployed, False otherwise."
    )
    test_execution_against_deployed_services_explanation: str = Field("True if test requires app deployed.")
    confidence_score: float = Field(description="Confidence score between 0.0 and 1.0, where 0 is no confidence and 1 is full confidence.")

    @model_validator(mode="after")
    def normalize_absent_optional_manipulation(self):
        if (
            self.data_load_mechanism == "not_present"
            and self.data_load_mechanism_is_required is False
        ):
            self.data_load_mechanism = "not_needed"

        if (
            self.data_cleanup_mechanism == "not_present"
            and self.data_cleanup_mechanism_is_required is False
        ):
            self.data_cleanup_mechanism = "not_needed"

        return self


AGREEMENT_FIELDS = (
    "is_integration_test",
    "data_load_location",
    "data_load_mechanism",
    "data_load_mechanism_is_required",
    "data_cleanup_location",
    "data_cleanup_mechanism",
    "data_cleanup_mechanism_is_required",
    "is_test_executed_against_deployed_services",
)


def labels_agree_on_decision_fields(a: BaseModel, b: BaseModel) -> bool:
    """
    Treat labels as agreeing when their categorical/boolean decisions match.

    Reasoning strings, free-text explanations, and confidence scores are intentionally
    excluded because they are expected to vary between independent labelers.
    """
    a_values = a.model_dump()
    b_values = b.model_dump()
    return all(a_values.get(field) == b_values.get(field) for field in AGREEMENT_FIELDS)


PATTERNS = """Known Data Manipulation Patterns applicable for both Data Loading and Data Cleanup patterns (REFERENCE ONLY - Do NOT assume features not in the actual test code):

"framework_annotation: Data is manipulated using framework annotations; e.g., @Sql in Spring."
"persistence_framework_api_call: Data is manipulated using persistent framework method call; e.g., CrudRepository.delete() and CrudRepository.save() in Spring, EntityManager.save() in Jakarta."
"database_jdbc_api_call: Data is manipulated using direct database/JDBC API call; e.g. PreparedStatement.execute(). Don't include if database manipulation is done using framework annotations or persistence framework API calls."
"rest_http_api_call: Data is manipulated via pure REST/HTTP API calls for the resource being tested."
"file_system_resource_api_call: File system or test resources are manipulated via API calls; e.g., Files.readAllLines(...). Don't include if database manipulation is done using framework annotations or persistence framework API calls."
"mocking_stubbing_api_call: Data is manipulated via mocking and stubbing via library API calls; e.g., Mockito.when().thenReturn()."
"custom_protocol_api_call: Data is manipulated via custom client libraries for specific protocols, socket programming, etc."
"process_management_api_call: Data manipulation involves external process management; e.g., ProcessBuider.start(), Process.destroy()"
"in_memory_server_setup: Data manipulation involves the creation of in-memory server instance that serves as data source for the test."
"other_java_api_call: Data is manipulated via other Java API calls than the specific types of API calls used for the other patterns."
"does_not_fit_with_any_pattern: Data manipulation does not fit with any of the known patterns."
"not_needed: Data manipulation is not needed."
"not_present: Data manipulation is needed but not present."
"""
# "data_scripts: Data is manipulated via automation scripts that update the database. "
# "test_helper_builder_call: Data is manipulated via call to test helper/builder/factory methods."
# "application_method_call: Data is manipulated via call to application methods."


LABELER_SYSTEM = """Role: Java Test Architect.

⚠️ CRITICAL ANTI-HALLUCINATION INSTRUCTIONS ⚠️
1. Analyze ONLY the provided test code below
2. Base your analysis ONLY on what is EXPLICITLY VISIBLE in the test code
3. Do NOT infer or assume the existence of methods, annotations, or features not shown
4. Do NOT mention setUp(), tearDown(), @Before, @After, @BeforeEach, @AfterEach unless you can SEE them in the code
5. If you cannot see a fixture method in the code, the test does NOT use fixtures
6. Be precise, literal, and conservative in your analysis

Data loading vs cleanup rules:
- Data loading means creating, inserting, saving, stubbing, or provisioning state that the test later relies on.
- Data cleanup means deleting, clearing, truncating, resetting, rolling back, expiring, or restoring state.
- Cleanup remains cleanup even when it happens before the test method, such as clearing tables in a fixture to start from an empty database.
- Do NOT classify cleanup operations as data loading.
- If code only clears/removes state and does not create/provision test data, set data_load_* to not_needed or not_present and classify the cleanup in data_cleanup_*.

Primary data manipulation rule:
- Choose the mechanism that primarily manipulates persistent application state needed by the test.
- If a test prepares database/entity state through a repository, DAO, EntityManager, persistence helper, or helper that receives a repository, classify data_load_mechanism as persistence_framework_api_call.
- Do this even if the same test also uses Mockito/given/doReturn stubs for services. Stubs are secondary when persistent state setup is visible.
- Use mocking_stubbing_api_call only when mocks/stubs are the primary or only visible way the test provisions the data/behavior it depends on.

Preparation vs behavior under test:
- data_load_* and data_cleanup_* describe data preparation/reset done so the test can exercise the behavior under test.
- Do NOT classify the application action being tested as data loading or cleanup just because it creates, updates, or deletes persistent state.
- For example, if the test calls an API or service and then asserts that a row was created/deleted, that API/service call is the behavior under test, not data loading/cleanup.
- If a method call prepares preconditions before the main action/assertion, classify that preparation. If a method call is the main action whose effect is asserted, do not classify it as setup/cleanup.

Configuration/state distinction:
- Changes to configuration, properties, feature flags, request limits, environment settings, clocks, or in-memory options are not data loading or data cleanup unless they directly manipulate persistent application state.
- This remains true even when those configuration changes appear in @BeforeEach, setUp(), @AfterEach, or tearDown().
- Only classify setup/teardown code as data_load_* or data_cleanup_* when it creates, inserts, deletes, clears, resets, or restores persisted application data such as database rows, repository entities, files used as persisted state, or external persistent resources.

Pattern taxonomy:
{patterns}

Output JSON Schema:
{schema_json}

Return a JSON object matching the schema exactly.
"""

LABELER_HUMAN = """Analyze this Java test:

{code}

⚠️ REMINDER: Analyze the test above based ONLY on what is EXPLICITLY VISIBLE in the code.
- Do NOT mention setUp(), tearDown(), @Before, @After, @BeforeEach, @AfterEach unless you can SEE them above
- Do NOT infer fixture methods from pattern descriptions
- If you don't see a method or annotation in the code above, it does NOT exist
- Do not count database clearing/resetting as data loading; classify it as cleanup.
- Do not count the application behavior being tested as data loading or cleanup.
- Do not count configuration/property changes as data loading or cleanup unless they directly manipulate persistent state.
"""

ADJ_SYSTEM = """Role: Adjudicator.

⚠️ CRITICAL ANTI-HALLUCINATION INSTRUCTIONS ⚠️
1. Analyze ONLY the provided test code below
2. Base your decision ONLY on what is EXPLICITLY VISIBLE in the test code
3. Do NOT infer or assume the existence of methods, annotations, or features not shown
4. Do NOT mention setUp(), tearDown(), @Before, @After, @BeforeEach, @AfterEach unless you can SEE them in the code
5. Prefer explicit code signals; be conservative if uncertain
6. If you cannot see a fixture method in the code, the test does NOT use fixtures

Data loading vs cleanup rules:
- Data loading means creating, inserting, saving, stubbing, or provisioning state that the test later relies on.
- Data cleanup means deleting, clearing, truncating, resetting, rolling back, expiring, or restoring state.
- Cleanup remains cleanup even when it happens before the test method, such as clearing tables in a fixture to start from an empty database.
- Do NOT classify cleanup operations as data loading.
- If code only clears/removes state and does not create/provision test data, set data_load_* to not_needed or not_present and classify the cleanup in data_cleanup_*.

Primary data manipulation rule:
- Choose the mechanism that primarily manipulates persistent application state needed by the test.
- If a test prepares database/entity state through a repository, DAO, EntityManager, persistence helper, or helper that receives a repository, classify data_load_mechanism as persistence_framework_api_call.
- Do this even if the same test also uses Mockito/given/doReturn stubs for services. Stubs are secondary when persistent state setup is visible.
- Use mocking_stubbing_api_call only when mocks/stubs are the primary or only visible way the test provisions the data/behavior it depends on.

Preparation vs behavior under test:
- data_load_* and data_cleanup_* describe data preparation/reset done so the test can exercise the behavior under test.
- Do NOT classify the application action being tested as data loading or cleanup just because it creates, updates, or deletes persistent state.
- For example, if the test calls an API or service and then asserts that a row was created/deleted, that API/service call is the behavior under test, not data loading/cleanup.
- If a method call prepares preconditions before the main action/assertion, classify that preparation. If a method call is the main action whose effect is asserted, do not classify it as setup/cleanup.

Configuration/state distinction:
- Changes to configuration, properties, feature flags, request limits, environment settings, clocks, or in-memory options are not data loading or data cleanup unless they directly manipulate persistent application state.
- This remains true even when those configuration changes appear in @BeforeEach, setUp(), @AfterEach, or tearDown().
- Only classify setup/teardown code as data_load_* or data_cleanup_* when it creates, inserts, deletes, clears, resets, or restores persisted application data such as database rows, repository entities, files used as persisted state, or external persistent resources.

Pattern taxonomy:
{patterns}

Output JSON Schema:
{schema_json}
"""

ADJ_HUMAN = """Test code:
{code}

Labeler A's analysis:
{a}

Labeler B's analysis:
{b}

Now review similar examples to validate your decision:
{examples}

⚠️ REMINDER: Make your final decision based on the test code above.
- Use examples only to validate, NOT to add features
- Do NOT mention setUp(), tearDown(), @Before, @After, @BeforeEach, @AfterEach unless you can SEE them in the test code above
- Do NOT infer fixture methods from pattern descriptions or examples
- If you don't see a method or annotation in the test code, it does NOT exist
- Do not count database clearing/resetting as data loading; classify it as cleanup.
- Do not count the application behavior being tested as data loading or cleanup.
- Do not count configuration/property changes as data loading or cleanup unless they directly manipulate persistent state.
"""


def _safe_list(x, limit=50):
    if not x:
        return []
    return list(x)[:limit]


def _regex_imports_and_annotations(raw: str):
    imports = re.findall(r"^import\\s+([^;]+);", raw, flags=re.MULTILINE)
    annotations = re.findall(r"@\\w+(?:\\([^)]*\\))?", raw)
    return sorted(set(imports)), sorted(set(annotations))


def cldk_document_builder(raw_code: str, source: Optional[str], ctx: LabelingContext) -> BuiltDocument:
    """
    Document builder that enriches the LLM input with derived signals.

    ctx.analysis is expected to be a CLDK JavaAnalysis (or compatible) object.
    If ctx.analysis is None, we fall back to regex-only extraction.
    """
    source = source or ""

    imports, annotations = _regex_imports_and_annotations(raw_code)

    # --- OPTIONAL CLDK usage ---
    # We keep this defensive because CLDK APIs may differ by version / available methods.
    # Best practice: only extract small signals that help the LLM.
    cldk_signals = []
    analysis = getattr(ctx, "analysis", None)

    if analysis is not None:
        # Example signals you can try to extract.
        # Adjust to your CLDK version's API.
        #
        # Common useful things:
        # - FQN class name(s)
        # - test methods list
        # - called methods / HTTP client usage
        try:
            # If you can map file path -> class, great. If not, omit.
            # PSEUDO-CODE (replace with real CLDK calls you have):
            #
            # klass_names = analysis.get_classes_in_file(source)
            # cldk_signals.append(f"Classes in file: {klass_names}")
            #
            # For now we just confirm analysis is present:
            cldk_signals.append("CLDK analysis: available")
        except Exception as e:
            cldk_signals.append(f"CLDK analysis: error extracting signals ({type(e).__name__})")


    derived_block = f"""\
=== Derived signals (static + heuristic) ===
Source: {source}
Imports (sample): {_safe_list(imports, 80)}
Annotations (sample): {_safe_list(annotations, 80)}
{"; ".join(cldk_signals) if cldk_signals else "CLDK analysis: not provided"}
=== End derived signals ===
"""

    # What the model sees:
    llm_content = derived_block + "\n\n=== Java test code ===\n" + raw_code

    # What gets embedded for retrieval:
    # Usually better to embed "just code" so semantic similarity is based on code content.
    index_text = raw_code

    return BuiltDocument(
        content=llm_content,
        index_text=index_text,
        metadata={"source": source},
    )


def careful_examples_formatter(examples):
    """
    Format retrieved examples with clear warnings to prevent hallucinations.
    
    This formatter emphasizes that examples are REFERENCE ONLY and should not
    be used to attribute features to the current test.
    """
    if not examples:
        return "No reference examples available."
    
    formatted = "="*60 + "\n"
    formatted += "REFERENCE EXAMPLES (for validation only - DO NOT use to add features)\n"
    formatted += "="*60 + "\n\n"
    formatted += "These are DIFFERENT tests. Use them only to validate your analysis,\n"
    formatted += "NOT to add features or methods to the current test.\n\n"
    
    for i, ex in enumerate(examples, 1):
        formatted += f"--- Reference Example {i} ---\n"
        
        # Show source
        source = ex.get('source', 'unknown')
        formatted += f"Source: {source}\n"
        
        # Show pattern classification
        pattern = ex.get('pattern_name', 'unknown')
        formatted += f"Pattern: {pattern}\n"
        
        # Show key characteristics (not full code to reduce confusion)
        is_self_contained = ex.get('is_self_contained', 'unknown')
        formatted += f"Self-contained: {is_self_contained}\n"
        
        # Show a brief snippet only (first 300 chars)
        code = ex.get('code', '')
        if code:
            snippet = code[:300].strip()
            if len(code) > 300:
                snippet += "..."
            formatted += f"Code snippet:\n{snippet}\n"
        
        formatted += "\n"
    
    formatted += "="*60 + "\n"
    formatted += "REMINDER: Analyze the CURRENT test, not these examples!\n"
    formatted += "="*60 + "\n"
    
    return formatted


API_TEST_FRAMEWORKS = {
    TestingFramework.SPRING_TEST,
    TestingFramework.REST_ASSURED,
    TestingFramework.MOCKITO,
    TestingFramework.CUCUMBER,
    TestingFramework.POWERMOCK,
    TestingFramework.MOCKMVC,
    TestingFramework.JMOCK,
    TestingFramework.WEBTESTCLIENT,
}

API_TEST_NAME_RE = re.compile(
    r"(?:Api|Controller|Endpoint|Resource|Rest|Mvc|Web).*(?:IT|Test)$|"
    r"(?:IT|Test).*(?:Api|Controller|Endpoint|Resource|Rest|Mvc|Web)$"
)

API_TEST_SIGNAL_RE = re.compile(
    r"\b(?:TestRestTemplate|RestTemplate|MockMvc|WebTestClient|RestAssured)\b|"
    r"\b(?:getForEntity|getForObject|postForEntity|postForObject|mockMvc\.perform|"
    r"webTestClient\.|given\(\)\.when\(\))"
)


def _get_testing_frameworks_for_class_and_parents(
    analysis: JavaAnalysis, class_name: str
):
    """Return frameworks imported by this test class or its inherited test base classes."""
    common_analysis = CommonAnalysis(analysis)
    frameworks = set()
    stack = [class_name]
    seen = set()

    while stack:
        current_class = stack.pop()
        if current_class in seen:
            continue
        seen.add(current_class)

        try:
            frameworks.update(
                common_analysis.get_testing_frameworks_for_class(current_class)
            )
        except Exception:
            pass

        class_info = analysis.get_class(current_class)
        if class_info:
            stack.extend(class_info.extends_list or [])

    return frameworks


def _class_source_text(analysis: JavaAnalysis, class_name: str) -> str:
    java_file = analysis.get_java_file(class_name)
    if not java_file:
        return ""
    try:
        with open(java_file, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _looks_like_api_integration_test_class(analysis: JavaAnalysis, class_name: str) -> bool:
    class_info = analysis.get_class(class_name)
    simple_name = class_name.rsplit(".", 1)[-1]
    parent_names = (
        [parent.rsplit(".", 1)[-1] for parent in (class_info.extends_list or [])]
        if class_info
        else []
    )
    name_candidates = [simple_name, *parent_names]

    if any(API_TEST_NAME_RE.search(name) for name in name_candidates):
        return True

    return bool(API_TEST_SIGNAL_RE.search(_class_source_text(analysis, class_name)))


def unit_enumerator(ctx: LabelingContext):
    """
    Get the units, which can method, or anything
    Args:
        ctx:

    Returns:

    """
    analysis: JavaAnalysis = ctx.require_analysis()
    common_analysis = CommonAnalysis(analysis)
    # Identify only test classes
    selected_class = []
    classes = list(analysis.get_classes().keys())
    for class_name in classes:
        java_file = analysis.get_java_file(class_name)
        if java_file and 'src/test' in java_file:
            # Select only API test classes
            testing_frameworks = _get_testing_frameworks_for_class_and_parents(
                analysis, class_name
            )
            if (
                any(testing_framework in API_TEST_FRAMEWORKS for testing_framework in testing_frameworks)
                # or _looks_like_api_integration_test_class(analysis, class_name)
            ):
                selected_class.append(class_name)
    # selected_class = selected_class [:1]
    for fqcn in selected_class:
        methods_in_class = analysis.get_methods_in_class(fqcn)
        for m in methods_in_class:
            method_details = methods_in_class[m]
            method_sig = method_details.signature
            if '@Test' not in method_details.annotations:
                continue

            # Skip placeholder/comment-only tests with no executable body.
            if common_analysis.get_ncloc(
                method_details.declaration,
                method_details.code,
            ) == 0:
                continue

            yield LabelingUnit(unit_type="method", unit_id=f"{fqcn}#{method_sig}", source=fqcn)


def unit_resolver(unit: LabelingUnit, ctx: LabelingContext) -> BuiltDocument:
    
    analysis = ctx.require_analysis()
    fqcn, method_sig = unit.unit_id.split("#", 1)

    
    # Get the complete prompt with setup, test method, helpers, and teardown
    llm_content = PromptBuilder(analysis).get_prompt(qualified_class_name=fqcn,
                                                test_method_signature=method_sig)

    
    # For index_text, use only the test method code for better semantic matching
    test_method = analysis.get_method(qualified_class_name=fqcn,
                                     qualified_method_name=method_sig)
    index_text = llm_content  # Use full content for now
    if test_method:
        # Optionally use just the test method for indexing
        index_text = test_method.declaration + test_method.code
    
    return BuiltDocument(
        content=llm_content,
        index_text=index_text,
        metadata={"class_fqcn": fqcn, "method_signature": method_sig},
    )

CONFIG = AgenticConfig(
    schema=JavaTestLabel,
    patterns=PATTERNS,
    labeler_a_prompt=PromptSpec(LABELER_SYSTEM, LABELER_HUMAN),
    labeler_b_prompt=PromptSpec(LABELER_SYSTEM, LABELER_HUMAN),
    adjudicator_prompt=PromptSpec(ADJ_SYSTEM, ADJ_HUMAN),
    examples_k=2,  # Reduced from 5 to 2 to minimize hallucinations from retrieved examples
    label_equality_fn=labels_agree_on_decision_fields,
    examples_formatter=careful_examples_formatter,  # Custom formatter to prevent hallucinations
    store_spec=StoreSpec(
        index_fields=(
            "is_self_contained",
            "fit_assessment",
            "pattern_name",
            "is_integration_test",
            "is_test_executed_against_deployed_services",
        )
    ),
    # document_builder=cldk_document_builder,
    unit_enumerator=unit_enumerator,
    unit_resolver=unit_resolver,
    enable_rag=True
)
