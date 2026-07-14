from cldk.analysis.java import JavaAnalysis
from .java_analysis import CommonAnalysis, Reachability


class PromptBuilder:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis
        self.common_analysis = CommonAnalysis(analysis)
        self.reachability = Reachability(analysis)

    @staticmethod
    def _is_src_test_path(java_file: str | None) -> bool:
        if not java_file:
            return False
        normalized = java_file.replace("\\", "/")
        return "/src/test/" in normalized or normalized.startswith("src/test/")

    def _is_src_test_class(self, qualified_class_name: str) -> bool:
        try:
            java_file = self.analysis.get_java_file(qualified_class_name)
        except Exception:
            return False
        return self._is_src_test_path(java_file)

    @staticmethod
    def _add_method(
        methods_by_class: dict[str, list[str]],
        class_name: str,
        method_signature: str,
    ) -> None:
        methods = methods_by_class.setdefault(class_name, [])
        if method_signature not in methods:
            methods.append(method_signature)

    def _get_src_test_callees(
        self,
        qualified_class_name: str,
        method_signature: str,
    ) -> dict[str, list[str]]:
        """
        Return direct callees of the test method that are defined under src/test.

        The existing helper-method search is intentionally narrow. This adds test-support
        methods from other src/test classes when CLDK can resolve them through the symbol table.
        """
        called_methods: dict[str, list[str]] = {}

        try:
            callees = self.analysis.get_callees(
                source_class_name=qualified_class_name,
                source_method_declaration=method_signature,
                using_symbol_table=True,
            ).get("callee_details", [])
        except Exception:
            return called_methods

        for callee_details in callees:
            callee_method = callee_details.get("callee_method")
            if not callee_method:
                continue

            callee_class = getattr(callee_method, "klass", None)
            method = getattr(callee_method, "method", None)
            callee_signature = getattr(method, "signature", None)
            if not callee_class or not callee_signature:
                continue

            if (
                callee_class == qualified_class_name
                and callee_signature == method_signature
            ):
                continue

            if self._is_src_test_class(callee_class):
                self._add_method(called_methods, callee_class, callee_signature)

        return called_methods

    def _merge_methods(
        self,
        methods_by_class: dict[str, list[str]],
        additional_methods: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        merged = {
            class_name: list(methods)
            for class_name, methods in methods_by_class.items()
        }
        for class_name, method_signatures in additional_methods.items():
            for method_signature in method_signatures:
                self._add_method(merged, class_name, method_signature)
        return merged

    def get_prompt(self, qualified_class_name: str, test_method_signature: str)-> str:

        
        # Step 1: Identify setup
        # Step 2: Add test method
        # Step 3: Add helper method
        # Step 4: Add teardown
        prompt = ''

        test_class_info = self.analysis.get_class(qualified_class_name=qualified_class_name)
        prompt += '/**************TEST CLASS DECLARATION*************/\n'
        extended_classes = [cls.split(".")[-1] for cls in test_class_info.extends_list]
        implemented_classes = [cls.split(".")[-1] for cls in test_class_info.implements_list]
        test_class_declaration =  f"{' '.join(test_class_info.modifiers)} class {qualified_class_name.split('.')[-1]}"
        test_class_declaration += f" extends {', '.join(extended_classes)}" if test_class_info.extends_list else "" + \
            f" implements {', '.join(implemented_classes)}" if test_class_info.implements_list else ""

        test_class_annotations = "\n".join(test_class_info.annotations) + "\n" if test_class_info.annotations else ""
        prompt += test_class_annotations + test_class_declaration + " {}\n"

        setup_methods = CommonAnalysis(self.analysis).get_setup_methods(qualified_class_name=qualified_class_name)



        
        test_method = self.analysis.get_method(qualified_class_name=qualified_class_name,
                                            qualified_method_name=test_method_signature)
        
        # Debug: Check if we got the right test method
        if test_method is None:
            print(f"WARNING: Could not find test method {qualified_class_name}#{test_method_signature}")
            return f"ERROR: Test method not found: {qualified_class_name}#{test_method_signature}"
        

        
        helper_methods = Reachability(self.analysis).get_helper_methods(qualified_class_name=qualified_class_name,
                                                              method_signature=test_method_signature,
                                                              add_extended_class=True)
        src_test_called_methods = self._get_src_test_callees(
            qualified_class_name=qualified_class_name,
            method_signature=test_method_signature,
        )
        helper_methods = self._merge_methods(helper_methods, src_test_called_methods)
        teardown_methods = CommonAnalysis(self.analysis).get_teardown_methods(qualified_class_name=qualified_class_name)
        if test_method:
            if setup_methods:

                prompt += '/**************TEST SETUP BEGIN*************/\n'

                for setup_method_class in setup_methods:
                    # prompt += f"Actual class: {qualified_class_name} but setup class: {setup_method_class}"
                    setup_methods_per_class = setup_methods[setup_method_class]

                    for setup_method_name in setup_methods_per_class:
                        method_details = self.analysis.get_method(qualified_class_name=setup_method_class,
                                                                  qualified_method_name=setup_method_name)
                        if method_details:
                            method_annotations = "\n".join(method_details.annotations) + "\n" if method_details.annotations else ""
                            prompt += method_annotations + method_details.declaration + method_details.code + '\n'
                prompt += '/**************TEST SETUP END*************/\n'

            prompt += '/**************TEST METHOD BEGIN*************/\n'
            method_annotations = "\n".join(test_method.annotations) + "\n" if test_method.annotations else ""
            prompt += method_annotations + test_method.declaration + test_method.code + '\n'
            prompt += '/**************TEST METHOD END*************/\n'

            if helper_methods:
                prompt += '/**************TEST HELPER METHOD BEGIN*************/\n'

                for helper_method_class in helper_methods:
                    helper_methods_per_class = helper_methods[helper_method_class]

                    for helper_method_name in helper_methods_per_class:
                        method_details = self.analysis.get_method(qualified_class_name=helper_method_class,
                                                                  qualified_method_name=helper_method_name)
                        if method_details:
                            method_annotations = "\n".join(method_details.annotations) + "\n" if method_details.annotations else ""
                            prompt += method_annotations + method_details.declaration + method_details.code + '\n'
                prompt += '/**************TEST HELPER METHOD END*************/\n'

            if teardown_methods:
                prompt += '/**************TEST TEARDOWN BEGIN*************/\n'
                for teardown_method_class in teardown_methods:
                    teardown_methods_per_class = teardown_methods[teardown_method_class]
                    for teardown_method_name in teardown_methods_per_class:
                        method_details = self.analysis.get_method(qualified_class_name=teardown_method_class,
                                                                  qualified_method_name=teardown_method_name)
                        if method_details:
                            method_annotations = "\n".join(method_details.annotations) + (
                                "\n" if method_details.annotations else "")
                            prompt += method_annotations + method_details.declaration + method_details.code + '\n'
                prompt += '/**************TEST TEARDOWN END*************/\n'

        return prompt
