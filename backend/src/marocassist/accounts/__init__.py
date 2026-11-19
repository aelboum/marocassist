"""Accounts module: the user's personal workspace (one SaaS-OS tenant per
user, decision D-06) and its settings.

No second identity system: users, sessions, tenants, memberships and roles
are SaaS-OS's. This module only decides *when* a personal tenant is created
and records which tenant is a user's personal one.
"""
