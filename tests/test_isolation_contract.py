from mechaharness.isolation_contract import IsolationContract, TemplateIOContract


def test_isolation_and_template_io() -> None:
    iso = IsolationContract(effect_scope="ws", budget_share=0.5, cancellable=True)
    assert iso.validate() == []
    io = TemplateIOContract(inputs={"a": "str"}, outputs={"b": "str"}, isolation=iso)
    assert io.validate() == []
    assert io.describe()["budget_semantics"] == "share_parent"


def test_bad_budget_share() -> None:
    assert IsolationContract(budget_share=0).validate()
