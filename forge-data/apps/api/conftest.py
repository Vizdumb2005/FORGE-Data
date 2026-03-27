"""Root conftest.py for FORGE API tests.

This file is loaded early to configure warning filters before any imports.
"""

import warnings

# Suppress external library deprecation warnings at import time
warnings.filterwarnings("ignore", category=DeprecationWarning, module="passlib")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="mlflow")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="crypt")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic._internal.config")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
