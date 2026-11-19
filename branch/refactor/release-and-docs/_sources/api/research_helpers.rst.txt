Experimental research reports
=============================

Use these pure helpers to report caller-supplied observations in offline
experiments. They do not enforce permissions, validate source provenance,
evaluate task artifacts, inspect causal traces, or measure provider cache hits.
The host owns those checks. See :doc:`../reference/inspiration-primitives` for
stable integration surfaces and :doc:`../inspiration/trouble`
for the remaining Trouble acceptance gaps.

Claim and ledger review
-----------------------

.. automodule:: mechaharness.authority_admission
   :members:

Paired verdict reporting
------------------------

.. automodule:: mechaharness.layered_verdict
   :members:

Selected request-field comparison
----------------------------------

.. automodule:: mechaharness.request_prefix
   :members:
