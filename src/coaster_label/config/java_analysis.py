"""
Java code analysis utilities for NL2Test and Test2NL.
"""

import os
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from hamster.code_analysis.common import (
    CommonAnalysis as HamsterCommonAnalysis,
)
from hamster.code_analysis.common import (
    Reachability as HamsterReachability,
)

TEST_DIR = "src/test/java"
from hamster.code_analysis.focal_class_method.focal_class_method import FocalClassMethod
from hamster.code_analysis.model.models import TestingFramework
from hamster.code_analysis.test_statistics import (
    SetupAnalysisInfo,
    TeardownAnalysisInfo,
)
from hamster.code_analysis.utils import constants
from hamster.utils.pretty import RichLog


def _map_class_exception(qualified_class_name: str, e: Exception) -> Exception:
    """Map Hamster ClassNotFoundException to Sakura ClassNotFoundError"""

    return e


def _map_file_exception(qualified_class_name: str, e: Exception) -> Exception:
    """Map Hamster file/compilation unit exceptions to Sakura exceptions"""

    return e


def _map_method_exception(
    qualified_class_name: str, method_signature: str, e: Exception
) -> Exception:
    """Map Hamster MethodNotFoundException to Sakura MethodNotFoundError"""

    return e


@dataclass
class ReachabilityConfig:
    allow_repetition: bool = False  # On same level
    only_helpers: bool = False
    add_extended_class: bool = False


class CommonAnalysis:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis
        self._hamster = HamsterCommonAnalysis(analysis)

    def is_test_class(
        self, qualified_class_name: str, testing_frameworks: List[TestingFramework]
    ):
        """
        Determines whether a class is a test class, meaning it contains at least one test method alongside testing
        frameworks.
        Args:
            qualified_class_name: The qualified class name of the class being analyzed.
            testing_frameworks: The testing frameworks imported in the compilation unit containing the class.

        Returns:
            bool: True if the class is a test class, containing a test method, or False otherwise.

        """
        return self._hamster.is_test_class(qualified_class_name, testing_frameworks)

    def is_test_method(
        self,
        method_signature: str,
        qualified_class_name: str,
        testing_frameworks: List[TestingFramework],
    ) -> bool:
        """
        Determines whether a method, uniquely determined by its signature and qualified class name, is a test method.
        Args:
            method_signature: The signature of the method analyzed.
            qualified_class_name: The qualified class name containing the method.
            testing_frameworks: The testing frameworks imported in the compilation unit containing the class.

        Returns:
            bool: True if the method is a test method, False otherwise.

        """
        return self._hamster.is_test_method(
            method_signature, qualified_class_name, testing_frameworks, only_ascii=True
        )

    def get_testing_frameworks_for_class(
        self, qualified_class_name: str
    ) -> List[TestingFramework]:
        """
        Gets a list of the testing frameworks available for a class by looking at its
        associated compilation unit and its imports.
        Args:
            qualified_class_name: The qualified class name of the class being analyzed.

        Returns:
            List: A list of TestingFramework objects for the class's compilation unit.

        """
        try:
            return self._hamster.get_testing_frameworks_for_class(qualified_class_name)
        except Exception as e:
            raise _map_file_exception(qualified_class_name, e)

    def get_ncloc(self, declaration: str, body: str) -> int:
        """
        Get the number of non-comment lines of code.
        Args:
            declaration: The declaration part of the code.
            body: The body part of the code.
        Returns:
            int: Number of non-comment lines.
        """
        return self._hamster.get_ncloc(declaration, body)

    def get_imports_for_class(self, qualified_class_name: str) -> List[str]:
        if not self.analysis.get_class(qualified_class_name):
            return []

        imports: Set[str] = set()
        java_file = self.analysis.get_java_file(
            qualified_class_name=qualified_class_name
        )

        if not java_file:
            RichLog.error(
                f"Java file for {qualified_class_name} not found",
            )

        compilation_unit = self.analysis.get_java_compilation_unit(file_path=java_file)
        if not compilation_unit:
            RichLog.error(
                f"Compilation unit for {qualified_class_name} not found"
            )

        for imp in compilation_unit.imports:
            imports.add(imp)

        return sorted(imports, key=len, reverse=True)

    def module_root_from_java_file(self, java_file: str | None) -> Path | None:
        """Return the absolute module root inferred from a Java file path."""
        if not java_file:
            return None

        resolved_java_file = Path(java_file).expanduser().resolve()
        normalized = resolved_java_file.as_posix()
        for marker in ("/src/main/java", "/src/test/java"):
            if marker in normalized:
                prefix = normalized.split(marker, 1)[0].rstrip("/")
                if not prefix:
                    return None
                candidate = Path(prefix)
                if candidate == Path("."):
                    return None
                return candidate
        return None

    def resolve_module_root(self, qualified_class_name: str) -> Path | None:
        """Resolve the absolute module root using the class's source path."""
        cldk_name = self.get_cldk_class_name(qualified_class_name)
        java_file = self.analysis.get_java_file(qualified_class_name=cldk_name)
        return self.module_root_from_java_file(java_file)

    def resolve_test_base_dir(
        self, module_root: Path | None, *, project_root: Path | None = None
    ) -> Path:
        """Resolve the absolute test root directory for a module."""
        if module_root is None:
            base_root = (
                Path(project_root).expanduser().resolve()
                if project_root is not None
                else Path.cwd().resolve()
            )
            return base_root / TEST_DIR
        return Path(module_root).expanduser().resolve() / TEST_DIR

    def get_referenced_app_classes(self, method_details: JCallable):
        referenced_classes = set()
        for referenced_type in method_details.referenced_types:
            referenced_classes.update(
                self.extract_non_parameterized_types(referenced_type)
            )

        verified_classes = []
        for referenced_class in referenced_classes:
            if self.analysis.get_class(referenced_class) is not None:
                verified_classes.append(referenced_class)

        return sorted(verified_classes, key=len)

    def get_setup_methods(self, qualified_class_name: str) -> Dict[str, List[str]]:
        """
        Returns all setup methods visible to this class, grouped by declaring class.
        Includes inherited methods from superclasses.
        """
        try:
            return SetupAnalysisInfo(self.analysis).get_setup_methods(
                qualified_class_name
            )
        except Exception as e:
            raise _map_file_exception(qualified_class_name, e)

    def get_teardown_methods(self, qualified_class_name: str) -> Dict[str, List[str]]:
        """
        Returns all teardown methods visible to this class, grouped by declaring class.
        Includes inherited methods from superclasses.
        """
        try:
            return TeardownAnalysisInfo(self.analysis).get_teardown_methods(
                qualified_class_name
            )
        except Exception as e:
            raise _map_file_exception(qualified_class_name, e)

    def get_test_methods_in_class(
        self, qualified_class_name: str
    ) -> List[Tuple[str, str]]:
        """
        Returns a list of (qualified_class_name, method_signature) for all test methods in the class.
        A method is considered a test method if is_test_method(...) evaluates to True.
        """
        testing_frameworks = self.get_testing_frameworks_for_class(qualified_class_name)
        results: List[Tuple[str, str]] = []
        for method_sig in self.analysis.get_methods_in_class(qualified_class_name):
            if self.is_test_method(
                method_sig, qualified_class_name, testing_frameworks
            ):
                results.append((qualified_class_name, method_sig))
        return results

    def get_ascii_methods(self, qualified_class_name: str) -> List[JCallable]:
        """Returns all methods in class that is ASCII"""
        valid_methods: List[JCallable] = []
        for method_signature in self.analysis.get_methods_in_class(
            qualified_class_name
        ):
            method_details = self.analysis.get_method(
                qualified_class_name, method_signature
            )
            if method_details.code.isascii():
                valid_methods.append(method_details)
        return sorted(valid_methods, key=lambda x: len(x.signature))

    def categorize_classes(
        self,
    ) -> Tuple[Dict[str, List[str]], List[str], List[str]]:
        """
        Categorize all classes into test classes, application classes, and test utility classes.

        Test utility classes are classes located in test directories (e.g., src/test/java) that
        do not contain any test methods.

        Returns:
            Tuple containing:
                - Dict[str, List[str]]: Mapping of test class names to their test method signatures
                - List[str]: Application class names (production code)
                - List[str]: Test utility class names (test helpers without test methods)
        """
        return self._hamster.categorize_classes()

    def is_subclass_of(self, sub_class: str, super_class: str) -> bool:
        return self._hamster.is_subclass_of(sub_class, super_class)

    def implements_interface(self, class_name: str, interface_name: str) -> bool:
        if not class_name or not interface_name:
            return False

        cls_info = self.analysis.get_class(class_name)
        if not cls_info:
            return False

        stack = []
        seen = set()

        # Consider both implemented interfaces and superclass chain
        stack.extend(cls_info.extends_list or [])
        stack.extend(cls_info.implements_list or [])

        while stack:
            curr = stack.pop()
            if curr in seen:
                continue
            if curr == interface_name:
                return True
            seen.add(curr)

            curr_info = self.analysis.get_class(curr)
            if not curr_info:
                continue

            if curr_info.is_interface:
                # Interfaces can't extend class or abstract class
                stack.extend(curr_info.implements_list or [])
            else:
                stack.extend(curr_info.extends_list or [])
                stack.extend(curr_info.implements_list or [])

        return False

    def is_accessible_from(
        self,
        owner_class: str,
        method_signature: str,
        *,
        accessor_class: Optional[str] = None,
        mode: Literal["public", "same_package", "same_package_or_subclass"] = "public",
    ) -> bool:
        try:
            return self._hamster.is_accessible_from(
                owner_class,
                method_signature,
                accessor_class=accessor_class if accessor_class else "",
                mode=mode,
            )
        except Exception as e:
            # Map both class and method exceptions
            e = _map_class_exception(owner_class, e)
            e = _map_method_exception(owner_class, method_signature, e)
            raise e

    def is_public(self, qualified_class_name: str, method_signature: str) -> bool:
        return self.is_accessible_from(
            qualified_class_name, method_signature, mode="public"
        )

    def is_abstract_class(self, qualified_class_name: str) -> bool:
        """Returns True if the class is abstract."""
        class_details = self.analysis.get_class(qualified_class_name)
        if not class_details or not class_details.modifiers:
            return False
        return "abstract" in class_details.modifiers

    def get_method_visibility(
        self, qualified_class_name: str, method_signature: str
    ) -> Literal["public", "same_package", "same_package_or_subclass"]:
        """
        Determines the visibility level of a method.

        Returns:
            "public" if the method is accessible from anywhere
            "same_package_or_subclass" if the method is accessible from same package or subclasses
            "same_package" if the method is only accessible from the same package
        """
        if self.is_accessible_from(
            qualified_class_name, method_signature, mode="public"
        ):
            return "public"
        elif self.is_accessible_from(
            qualified_class_name, method_signature, mode="same_package_or_subclass"
        ):
            return "same_package_or_subclass"
        else:
            return "same_package"

    # DEPRECATED
    def get_complicated_focal_tests(self) -> Dict[str, List[str]]:
        test_class_map, application_classes, _ = self.categorize_classes()
        complicated_tests = {}

        for test_class in test_class_map:
            testing_frameworks = self.get_testing_frameworks_for_class(test_class)
            setup_methods_dict = self.get_setup_methods(test_class)

            complicated_methods = []

            for method_signature in test_class_map[test_class]:
                try:
                    focal_class_method = FocalClassMethod(
                        self.analysis, application_classes
                    )
                    focal_classes, _, _, _ = focal_class_method.extract_test_scope(
                        test_class, method_signature, setup_methods_dict
                    )

                    is_complicated = len(focal_classes) > 1 or (
                        len(focal_classes) == 1
                        and len(focal_classes[0].focal_method_names) > 1
                    )

                    if is_complicated:
                        complicated_methods.append(method_signature)

                except Exception:
                    continue

            if complicated_methods:
                complicated_tests[test_class] = complicated_methods

        return complicated_tests

    def get_complicated_focal_tests_count(self) -> int:
        complicated_tests = self.get_complicated_focal_tests()
        return sum(len(methods) for methods in complicated_tests.values())

    @staticmethod
    def is_getter_or_setter(method_details: JCallable) -> bool:
        if (
            method_details.signature.startswith("get")
            or method_details.signature.startswith("set")
        ) and len(method_details.code.split("\n")) <= 3:
            return True
        return False


    def get_complete_method_code(self, method_declaration: str, method_code: str) -> str:
        code = method_declaration + " " + method_code
        return self.pretty_indent(code)

    @staticmethod
    def pretty_indent(raw_code_str: str, indent_size: int = 4):
        # Removes new lines and allows for better character-by-character processing
        compact = " ".join(raw_code_str.strip().split())

        result_lines = []
        indent_level = 0
        token = ""
        first_brace = True

        def flush_token():
            # Adds existing token sequence into new line with correct indent level
            nonlocal token
            t = token.strip()
            if t:
                result_lines.append(" " * (indent_level * indent_size) + t)
            token = ""

        i = 0
        while i < len(compact):
            ch = compact[i]

            if ch == '{':
                if first_brace:
                    # Append to the signature line
                    token += " {"
                    flush_token()
                    indent_level += 1
                    first_brace = False
                    i += 1

                else:
                    # Flush old line before bracket
                    flush_token()

                    # Bracket is on own line
                    result_lines.append(" " * (indent_level * indent_size) + "{")
                    indent_level += 1
                    i += 1

            elif ch == '}':
                first_brace = False  # Edge case where code started with '}'

                # Flush line before bracket
                flush_token()

                # Indent level is decreased before bracket print
                indent_level = max(indent_level - 1, 0)
                result_lines.append(" " * (indent_level * indent_size) + "}")
                i += 1

            elif ch == ';':
                # Each semicolon defines new line
                token += ';'
                flush_token()
                i += 1

            else:
                token += ch
                i += 1

        # Flushes trailing sequence
        flush_token()

        return "\n".join(result_lines)

    @staticmethod
    def extract_non_parameterized_types(parameterized_type: str) -> List[str]:
        pattern = re.compile(
            r"[\w\.]+\.[A-Z]\w*"
        )  # Extracts all types ending with a capital word and having a period
        non_parameterized_types = pattern.findall(parameterized_type)
        return non_parameterized_types

    @staticmethod
    def package_of(qualified_class_name: str) -> str:
        i = qualified_class_name.rfind(".")
        return qualified_class_name[:i] if i != -1 else ""

    @staticmethod
    def get_simple_class_name(qualified_class_name: str) -> str:
        i = qualified_class_name.rfind(".")
        return qualified_class_name[i + 1 :] if i != -1 else qualified_class_name

    @staticmethod
    def get_simple_method_name(method_signature: str) -> str:
        paren_index = method_signature.find("(")
        name_part = (
            method_signature[:paren_index] if paren_index != -1 else method_signature
        )
        dot_index = name_part.rfind(".")
        return name_part[dot_index + 1 :] if dot_index != -1 else name_part

    @staticmethod
    def process_callee_signature(callee_signature: str) -> str:
        """
        Processes callee signature
        Args:
            callee_signature:

        Returns:

        """
        pattern = r"\b(?:[a-zA-Z_][\w\.]*\.)+([a-zA-Z_][\w]*)\b|<[^>]*>"

        # Find the part within the parentheses
        start = callee_signature.find("(") + 1
        end = callee_signature.rfind(")")

        # Extract the elements inside the parentheses
        elements = callee_signature[start:end].split(",")

        # Apply the regex to each element
        simplified_elements = [
            re.sub(pattern, r"\1", element.strip()) for element in elements
        ]

        # Reconstruct the string with simplified elements
        return f"{callee_signature[:start]}{', '.join(simplified_elements)}{callee_signature[end:]}"

    @staticmethod
    def simplify_method_signature(method_signature: str) -> str:
        """
        Simplifies a method signature by converting fully qualified parameter types to simple names.
        Removes generic type parameters and preserves array/varargs markers.

        Used for matching method signatures when CLDK returns simple type names but
        we need fully qualified types.

        Note: Does not differentiate standard library type vs. third-party type.

        Example:
            "testMethod(com.google.common.jimfs.Configuration, java.util.List<String>)"
            becomes "testMethod(Configuration, List)"
        """
        paren_start = method_signature.find("(")
        paren_end = method_signature.rfind(")")

        if paren_start == -1 or paren_end == -1:
            return method_signature

        method_name = method_signature[:paren_start]
        params_str = method_signature[paren_start + 1 : paren_end]

        if not params_str.strip():
            return method_signature

        # Remove nested generics iteratively until none remain
        while "<" in params_str:
            new_params = re.sub(r"<[^<>]*>", "", params_str)
            if new_params == params_str:
                break
            params_str = new_params

        elements = params_str.split(",")
        simplified = []

        for element in elements:
            element = element.strip()
            if not element:
                continue

            # Handle array suffix and varargs
            suffix = ""
            while element.endswith("[]"):
                suffix = "[]" + suffix
                element = element[:-2]
            if element.endswith("..."):
                suffix = "..." + suffix
                element = element[:-3]

            # Simplify qualified name to simple name
            if "." in element:
                element = element.rsplit(".", 1)[-1]

            simplified.append(element + suffix)

        return f"{method_name}({', '.join(simplified)})"

    @staticmethod
    def get_cldk_class_name(qualified_class_name: str) -> str:
        """
        Normalize inner class separators for CLDK lookups.
        """
        if "$" not in qualified_class_name:
            return qualified_class_name
        return qualified_class_name.replace("$", ".")

    @staticmethod
    def get_cldk_method_sig(qualified_class_name: str, method_signature: str) -> str:
        """
        Normalize constructor signatures for CLDK lookups, since CLDK expects constructors with name '<init>'.
        """
        simple_class_name = qualified_class_name.split(".")[-1]
        constructor_prefix = f"{simple_class_name}("
        if constructor_prefix not in method_signature:
            return method_signature
        return method_signature.replace(constructor_prefix, "<init>(", 1)

    @staticmethod
    def normalize_path_in_project(filepath: str, project_root: Optional[str]) -> str:
        """
        Normalize absolute compiler paths so that reports focus on project-relative locations.
        """
        if not filepath:
            return filepath
        normalized = filepath.replace("\\", "/")
        if project_root:
            root = str(Path(project_root).expanduser().resolve()).replace("\\", "/")
            root_with_sep = f"{root}/"
            if normalized.lower().startswith(root_with_sep.lower()):
                return normalized[len(root_with_sep) :]
        src_idx = normalized.find("/src/")
        if src_idx != -1:
            return normalized[src_idx + 1 :]
        return os.path.basename(normalized)


class Reachability:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis
        self._hamster = HamsterReachability(analysis)
        self._reachability_cache: Dict[
            Tuple, Dict[str, List[str]]
        ] = {}  # For Sakura-specific methods

    def get_helper_methods(
        self,
        qualified_class_name: str,
        method_signature: str,
        depth: int = constants.CONTEXT_SEARCH_DEPTH,
        add_extended_class: bool = False,
        allow_repetition: bool = False,
        only_ascii: bool = True,
        test_utility_classes: List[str] | None = None,
    ) -> Dict[str, List[str]]:
        """
        Retrieves the helper methods reachable from the given method within the specified depth.

        Helper methods are methods called (directly or transitively) by the given method that are
        defined in the same class (or an extended class if add_extended_class=True).

        Args:
            qualified_class_name: The qualified name of the class.
            method_signature: The method signature.
            depth: The depth for search in call hierarchy.
            add_extended_class: If set to True, include methods from classes extended by the given class.
            allow_repetition: If set to True, allow visiting the same method multiple times in the same depth level.
            only_ascii: If set to True, only include methods with ASCII characters.
            test_utility_classes: List of test utility class names to include in helper method search.

        Returns:
            Dict[str, List[str]]: A map from class names to method signatures of helper methods.
        """
        return self._hamster.get_helper_methods(
            qualified_class_name,
            method_signature,
            depth,
            add_extended_class,
            allow_repetition,
            only_ascii,
            test_utility_classes,
        )

    def get_concrete_classes(self, interface_class: str) -> List[str]:
        """
        Returns a list of concrete classes that implement the given interface class.

        Args:
            interface_class: The interface class.

        Returns:
            List[str]: List of concrete classes that implement the given interface class.
        """
        return self._hamster.get_concrete_classes(interface_class)

    def get_visible_class_methods(
        self,
        qualified_class_name: str,
        *,
        visibility_mode: Literal[
            "public", "same_package", "same_package_or_subclass"
        ] = "public",
        test_package: Optional[str] = None,
        include_metadata: bool = False,
    ) -> Dict[str, List[Union[str, Dict[str, Any]]]]:
        """
        Retrieves methods reachable from qualified class along its inheritance graph. Precedence looks at the class itself,
        then superclasses, then interfaces (level-order).

        Args:
            qualified_class_name: The qualified name of the class.
            visibility_mode: The visibility mode. Either "public", "same_package", or "same_package_or_subclass".
            test_package: The package of the test class (for deciding whether a subclass is required).
            include_metadata: Include metadata in the output.

        Returns:
            Dict[str, List[str]] mapping owner (class or interface) -> list of method signatures

        Raises:
            ClassNotFoundError: If the qualified_class_name cannot be found.
        """
        common = CommonAnalysis(self.analysis)

        root_details = self.analysis.get_class(qualified_class_name)
        if not root_details:
            RichLog.error(
                f"Class {qualified_class_name} not found (may be externally defined or misspelled)."
            )

        def _accept(owner: str, method_sig: str) -> bool:
            return common.is_accessible_from(
                owner,
                method_sig,
                accessor_class=qualified_class_name,
                mode=visibility_mode,
            )

        def _meta(owner: str, method_sig: str) -> Dict[str, Any]:
            method_details = self.analysis.get_method(owner, method_sig)
            owner_pkg = common.package_of(owner)
            mods = list(method_details.modifiers) if method_details else []
            visibility = (
                "private"
                if "private" in mods
                else "public"
                if "public" in mods
                else "protected"
                if "protected" in mods
                else "package-private"
            )
            # To call the method, a small subclass must be created that calls the method using the subclass type (this)
            requires_subclass = visibility == "protected" and owner_pkg != test_package
            return {
                "method_signature": method_sig,
                "declaring_qualified_class_name": owner,
                "modifiers": mods,
                "visibility": visibility,
                "requires_subclass": requires_subclass,
            }

        result: Dict[str, List[Union[str, Dict[str, Any]]]] = {}
        seen_sigs: set[str] = set()

        def _add_methods(owner: str) -> None:
            for method_sig in self.analysis.get_methods_in_class(owner):
                if method_sig in seen_sigs:
                    continue
                if _accept(owner, method_sig):
                    seen_sigs.add(method_sig)
                    if include_metadata:
                        result.setdefault(owner, []).append(_meta(owner, method_sig))
                    else:
                        result.setdefault(owner, []).append(method_sig)

        # Methods on the class itself
        _add_methods(qualified_class_name)

        # Superclasses in BFS order
        super_queue: deque[str] = deque(root_details.extends_list or [])
        visited_supers: set[str] = set(root_details.extends_list or [])
        super_bfs_order: List[str] = []

        while super_queue:
            sup_cls = super_queue.popleft()
            super_bfs_order.append(sup_cls)
            _add_methods(sup_cls)

            sup_details = self.analysis.get_class(sup_cls)
            if sup_details and sup_details.extends_list:
                for next_sup in sup_details.extends_list:
                    if next_sup not in visited_supers:
                        visited_supers.add(next_sup)
                        super_queue.append(next_sup)

        # Interfaces in BFS order
        iface_queue: deque[str] = deque()
        visited_ifaces: set[str] = set()

        def _enqueue_interfaces(owner: str) -> None:
            owner_details = self.analysis.get_class(owner)
            if owner_details and owner_details.implements_list:
                for iface in owner_details.implements_list:
                    if iface not in visited_ifaces:
                        visited_ifaces.add(iface)
                        iface_queue.append(iface)

        _enqueue_interfaces(qualified_class_name)
        for sup in super_bfs_order:
            _enqueue_interfaces(sup)

        while iface_queue:
            iface = iface_queue.popleft()
            _add_methods(iface)

            iface_details = self.analysis.get_class(iface)
            if iface_details and iface_details.extends_list:
                for parent_iface in iface_details.extends_list:
                    if parent_iface not in visited_ifaces:
                        visited_ifaces.add(parent_iface)
                        iface_queue.append(parent_iface)

        return result

    def get_inherited_classes_and_interfaces(
        self, qualified_class_name: str
    ) -> List[str]:
        """
        Returns all inherited types for the given class, first looking at superclasses then interfaces.
        """
        root_details = self.analysis.get_class(qualified_class_name)
        if not root_details:
            RichLog.error(
                f"Class {qualified_class_name} not found (may be externally defined or misspelled)."
            )

        # Superclasses in level order
        super_queue: deque[str] = deque(root_details.extends_list or [])
        visited_supers: set[str] = set(root_details.extends_list or [])
        super_bfs_order: List[str] = []

        while super_queue:
            sup_cls = super_queue.popleft()
            super_bfs_order.append(sup_cls)

            sup_details = self.analysis.get_class(sup_cls)
            if sup_details and sup_details.extends_list:
                for next_sup in sup_details.extends_list:
                    if next_sup not in visited_supers:
                        visited_supers.add(next_sup)
                        super_queue.append(next_sup)

        # Interfaces in level order (from class and all discovered supers)
        iface_queue: deque[str] = deque()
        visited_ifaces: set[str] = set()
        iface_bfs_order: List[str] = []

        def _enqueue_interfaces(owner: str) -> None:
            owner_details = self.analysis.get_class(owner)
            if owner_details and owner_details.implements_list:
                for iface in owner_details.implements_list:
                    if iface not in visited_ifaces:
                        visited_ifaces.add(iface)
                        iface_queue.append(iface)

        _enqueue_interfaces(qualified_class_name)
        for sup in super_bfs_order:
            _enqueue_interfaces(sup)

        while iface_queue:
            iface = iface_queue.popleft()
            iface_bfs_order.append(iface)

            iface_details = self.analysis.get_class(iface)
            if iface_details and iface_details.extends_list:
                for parent_iface in iface_details.extends_list:
                    if parent_iface not in visited_ifaces:
                        visited_ifaces.add(parent_iface)
                        iface_queue.append(parent_iface)

        return super_bfs_order + iface_bfs_order

    def get_reachable_test_methods(
        self,
        qualified_class_name: str,
        testing_frameworks: List[TestingFramework],
    ) -> Dict[str, List[str]]:
        """
        Retrieves test methods reachable from the qualified class via inheritance.
        Traverses superclasses first (BFS), then interfaces.

        Args:
            qualified_class_name: The qualified name of the class.
            testing_frameworks: Testing frameworks available in this class's compilation unit.

        Returns:
            Dict[str, List[str]] mapping declaring class -> list of test method signatures

        Raises:
            ClassNotFoundError: If the qualified_class_name cannot be found.
        """
        common = CommonAnalysis(self.analysis)

        root_details = self.analysis.get_class(qualified_class_name)
        if not root_details:
            RichLog.error(
                f"Class {qualified_class_name} not found (may be externally defined or misspelled)."
            )

        def _is_test(owner: str, method_sig: str) -> bool:
            owner_frameworks = common.get_testing_frameworks_for_class(owner)
            if not owner_frameworks:
                return False
            return common.is_test_method(method_sig, owner, owner_frameworks)

        result: Dict[str, List[str]] = {}
        seen_sigs: set[str] = set()

        def _add_methods(owner: str) -> None:
            for method_sig in self.analysis.get_methods_in_class(owner):
                if method_sig in seen_sigs:
                    continue
                if _is_test(owner, method_sig):
                    seen_sigs.add(method_sig)
                    result.setdefault(owner, []).append(method_sig)

        # Methods on the class itself
        _add_methods(qualified_class_name)

        # Superclasses in BFS order
        super_queue: deque[str] = deque(root_details.extends_list or [])
        visited_supers: set[str] = set(root_details.extends_list or [])

        while super_queue:
            sup_cls = super_queue.popleft()
            _add_methods(sup_cls)

            sup_details = self.analysis.get_class(sup_cls)
            if sup_details and sup_details.extends_list:
                for next_sup in sup_details.extends_list:
                    if next_sup not in visited_supers:
                        visited_supers.add(next_sup)
                        super_queue.append(next_sup)

        return result