from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

REPO_COMPONENTS = str(Path(__file__).parents[1] / "custom_components")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    # De testplugin heeft een eigen custom_components-package; voeg deze repo eraan toe.
    import custom_components

    if REPO_COMPONENTS not in custom_components.__path__:
        custom_components.__path__.append(REPO_COMPONENTS)
    yield
