"""Verify GAIK package installation in CI/CD.

This script tests that the package was installed correctly from PyPI.
It imports all modules, checks APIs, and runs basic functionality tests
without making any actual LLM API calls.
"""

import sys
import importlib
import pkgutil


def test_main_package():
    """Test main package import."""
    print("Testing GAIK package installation...\n")

    import gaik
    print(f"✓ Main package imported successfully (version: {gaik.__version__})")


def test_all_submodules():
    """Discover and test all submodules."""
    print("\nDiscovering and testing all submodules:")

    import gaik
    modules_found = []
    modules_skipped = []

    # Modules that require optional dependencies
    OPTIONAL_MODULES = ["gaik.parsers"]

    for importer, modname, ispkg in pkgutil.walk_packages(
        path=gaik.__path__,
        prefix="gaik.",
        onerror=lambda x: None,
    ):
        try:
            # Skip private/internal modules
            if any(
                part.startswith("_") and part != "__init__"
                for part in modname.split(".")
            ):
                continue

            mod = importlib.import_module(modname)
            modules_found.append(modname)
            print(f"  ✓ {modname}")

            # Test public API of each module
            if hasattr(mod, "__all__"):
                for item in mod.__all__:
                    if not hasattr(mod, item):
                        print(f"    ✗ ERROR: {item} listed in __all__ but not found!")
                        sys.exit(1)
                print(f"    - {len(mod.__all__)} public API items verified")

        except ImportError as e:
            # Check if this is an optional module
            is_optional = any(modname.startswith(opt) for opt in OPTIONAL_MODULES)
            if is_optional:
                modules_skipped.append(modname)
                print(f"  - {modname} (optional, skipped: {str(e)[:80]})")
            else:
                # Core module failed to import - this is a real error
                print(f"  ✗ ERROR importing {modname}: {e}")
                sys.exit(1)
        except Exception as e:
            print(f"  ✗ ERROR importing {modname}: {e}")
            sys.exit(1)

    if not modules_found:
        print("✗ ERROR: No modules found in gaik package!")
        sys.exit(1)

    print(f"\n✓ Successfully tested {len(modules_found)} modules")
    if modules_skipped:
        print(f"  - Skipped {len(modules_skipped)} optional module(s)")


def test_extract_module():
    """Test gaik.extract module functionality."""
    print("\nTesting gaik.extract functionality:")

    try:
        from gaik.extract import (
            SchemaExtractor,
            dynamic_extraction_workflow,
            FieldSpec,
            ExtractionRequirements,
            create_extraction_model,
            sanitize_model_name,
        )

        # Test basic functionality without API calls
        req = ExtractionRequirements(
            use_case_name="Test",
            fields=[
                FieldSpec(
                    field_name="test_field",
                    field_type="str",
                    description="Test",
                    required=True,
                )
            ],
        )

        # Test model creation
        model = create_extraction_model(req)
        assert model.__name__ == "Test_Extraction", "Model name mismatch"

        # Test sanitization
        assert sanitize_model_name("Test! Name") == "Test_Name", "Sanitization failed"

        print("  ✓ gaik.extract functionality tests passed")

    except ImportError:
        print("  - gaik.extract not found (skipped)")
    except Exception as e:
        print(f"  ✗ ERROR testing gaik.extract: {e}")
        sys.exit(1)


def test_provider_registry():
    """Test provider registry."""
    print("\nTesting provider registry:")

    try:
        from gaik.providers import get_provider, PROVIDERS

        # Check all expected providers exist
        expected_providers = ["openai", "anthropic", "google", "azure"]
        for provider_name in expected_providers:
            if provider_name not in PROVIDERS:
                print(f"  ✗ ERROR: Provider {provider_name} not in registry!")
                sys.exit(1)

        # Test getting a provider
        provider = get_provider("openai")
        if provider.default_model != "gpt-4.1":
            print(
                f"  ✗ ERROR: OpenAI default model mismatch: {provider.default_model}"
            )
            sys.exit(1)

        print(f"  ✓ Provider registry tests passed ({len(PROVIDERS)} providers)")

    except ImportError:
        print("  - gaik.providers not found (skipped)")
    except Exception as e:
        print(f"  ✗ ERROR testing gaik.providers: {e}")
        sys.exit(1)


def test_langchain_integration():
    """Test LangChain integration."""
    print("\nTesting LangChain integration:")

    try:
        from langchain_openai import ChatOpenAI
        from gaik.extract import SchemaExtractor, FieldSpec, ExtractionRequirements

        # Create mock LangChain client
        client = ChatOpenAI(api_key="fake-key-for-test", model="gpt-4.1")

        # Test SchemaExtractor accepts LangChain client
        test_req = ExtractionRequirements(
            use_case_name="Test",
            fields=[
                FieldSpec(
                    field_name="test",
                    field_type="str",
                    description="Test",
                    required=True,
                )
            ],
        )
        extractor = SchemaExtractor("test", client=client, requirements=test_req)

        if extractor.client != client:
            print("  ✗ ERROR: SchemaExtractor did not store client correctly")
            sys.exit(1)

        print("  ✓ LangChain integration tests passed")

    except ImportError as e:
        print(f"  - LangChain integration test skipped (import error: {e})")
    except Exception as e:
        print(f"  ✗ ERROR testing LangChain integration: {e}")
        sys.exit(1)


def main():
    """Run all verification tests."""
    test_main_package()
    test_all_submodules()
    test_extract_module()
    test_provider_registry()
    test_langchain_integration()

    print("\n✅ All tests passed successfully!")


if __name__ == "__main__":
    main()
