"""Root pytest configuration: makes service packages importable in tests.

Service modules rely on their own directory and the shared `common/` package
being on ``sys.path`` (mirroring the Docker layout where ``/app`` holds the
service files and ``/app/common/``). Adding every service directory here makes
``from common import ...`` and sibling imports such as ``from personality import ...``
resolve during test collection.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICES = os.path.join(ROOT, "services")

sys.path.insert(0, SERVICES)
for name in sorted(os.listdir(SERVICES)):
    path = os.path.join(SERVICES, name)
    if os.path.isdir(path):
        sys.path.insert(0, path)
