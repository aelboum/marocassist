"""MarocAssist backend: a modular monolith built on SaaS-OS (ADR-0001).

Dependency direction is one way only: `marocassist -> saas_os`. SaaS-OS
never imports this package.
"""

__version__ = "0.1.0"
API_VERSION = "v1"
