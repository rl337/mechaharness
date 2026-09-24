MechaHarness documentation
==========================

Python agentic harness that separates **how you call models** from **how you
run agent loops**.

.. container:: hero-meta

   .. container:: version-badge

      |release|

   Inference Strategy + harness hierarchy + pyiv Config. Python 3.9+.

.. raw:: html

   <div style="margin: 20px 0; padding: 15px; background: #e8f4f8; border-left: 4px solid #0066cc; border-radius: 4px;">
   <strong>Quick Links:</strong>
   <a href="https://github.com/rl337/mechaharness" style="margin-left: 15px; color: #0066cc; text-decoration: none; font-weight: 500;">GitHub</a>
   <a href="https://pypi.org/project/mechaharness/" style="margin-left: 15px; color: #0066cc; text-decoration: none; font-weight: 500;">PyPI</a>
   <a href="changelog.html" style="margin-left: 15px; color: #0066cc; text-decoration: none; font-weight: 500;">Changelog</a>
   </div>

Installation
------------

.. code-block:: bash

   pip install mechaharness

Guides
------

.. toctree::
   :maxdepth: 2

   architecture
   guides/install
   guides/dependency-injection
   guides/junespark

Reference
---------

.. toctree::
   :maxdepth: 2

   reference/cli
   reference/api
   reference/events
   reference/cost
   reference/access
   reference/judge
   adr/0001-pyiv-config

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
   api/harness
   api/tools

Changelog
---------

.. toctree::
   :maxdepth: 1

   changelog
