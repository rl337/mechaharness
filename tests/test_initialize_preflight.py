from mechaharness.graph_templates import GraphTemplateParams, InitializePreflightTemplate, default_graph_templates

def test_template():
    g=InitializePreflightTemplate().instantiate(GraphTemplateParams(goal="x"))
    assert "ready" in g.nodes
    assert "initialize_preflight" in default_graph_templates().names()
