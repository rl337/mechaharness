MechaHarness documentation
==========================

Build model-backed applications with configurable inference providers, agent
loops, tool grants, cost accounting, event logs, and resumable execution graphs.
Requires Python 3.9+. This documentation describes version |release|.

Start without a provider account:

.. code-block:: bash

   pip install mechaharness
   mechaharness run "Hello" --backend mock --family pass_through --model mock

Use :doc:`guides/install` for a first run, :doc:`guides/openai-local` for cloud
or local endpoints, and :doc:`guides/dependency-injection` to configure a host.
See :doc:`architecture` for component ownership and integration boundaries.

Guides
------

.. toctree::
   :maxdepth: 2

   architecture
   guides/install
   guides/dependency-injection
   guides/openai-local
   guides/agent-skills
   guides/user-stories

More guides
-----------

.. toctree::
   :maxdepth: 1
   :glob:

   guides/coding-delegate-suites
   guides/release-preparation
   guides/gastronomic-comparison
   guides/authoring-user-stories

Reference
---------

.. toctree::
   :maxdepth: 1
   :glob:

   reference/*

Maintainer requirements and research
------------------------------------

These pages describe contracts, acceptance gaps, and their sources. Start with
installation and the task guides above when integrating MechaHarness in a host.

.. toctree::
   :maxdepth: 1
   :glob:

   requirements/*
   inspiration/*

API
---

.. toctree::
   :maxdepth: 2

   api/mechaharness
   api/config
   api/di
   api/factory
   api/completer
   api/types
   api/contract
   api/events
   api/access
   api/environment
   api/inference
   api/research_helpers
   api/harness
   api/tools
   api/graph_executor
   api/checkpoint_store
   api/sqlite_checkpoint_store
   api/external_effect

Changelog
---------

.. toctree::
   :maxdepth: 1

   changelog
