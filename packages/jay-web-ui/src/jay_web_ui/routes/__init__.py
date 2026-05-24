"""Route registrars for the Web UI server.

Each submodule exposes ``register(server)`` which mounts a coherent group of
endpoints onto ``server.app``. ``server.py`` orchestrates them in one place.

Closures still reference ``server`` (LLM/agent state, history, in-flight task
handles) rather than module-level globals, so behaviour is unchanged from the
original monolithic ``_setup_routes``.
"""
