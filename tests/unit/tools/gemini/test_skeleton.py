"""The smallest case and plant files, read from gemini's public schemas."""

from geomind.tools.gemini.skeleton import case_skeleton, plant_skeleton, skeleton_of


def test_a_constant_is_kept_and_other_leaves_are_named():
    """A ``const`` is the value; a required leaf without one is ``<name>``."""
    schema = {
        "type": "object",
        "required": ["format", "name"],
        "properties": {"format": {"const": 1}, "name": {"type": "string"}},
    }
    assert skeleton_of(schema, "file") == {"format": 1, "name": "<name>"}


def test_the_case_and_plant_skeletons_carry_gemini_s_header():
    """Both hold gemini's ``format`` and ``kind`` and name the rest."""
    assert plant_skeleton() == {"format": 1, "kind": "plant", "name": "<name>"}
    assert case_skeleton()["kind"] == "case"


def test_the_case_tree_is_read_from_gemini_s_schema(monkeypatch):
    """A key gemini renames shows in the tree at once: there is no copy to keep up to date."""
    import copy

    import gemini as gm

    from geomind.tools.gemini.skeleton import case_tree

    tree = case_tree()
    assert "site.ground.gradient: {value, unit} in" in tree and "time.step*:" in tree
    schema = copy.deepcopy(gm.Case.schema())
    ground = schema["properties"]["site"]["properties"]["ground"]["properties"]
    ground["geothermal_gradient"] = ground.pop("gradient")
    monkeypatch.setattr(gm.Case, "schema", classmethod(lambda cls: schema))
    renamed = case_tree()
    assert "site.ground.geothermal_gradient:" in renamed and "site.ground.gradient:" not in renamed
    assert "capex.drilling: {value, unit} in" in tree and len(tree) < 9000


def test_the_formulator_prompt_carries_the_case_keys():
    """The tree is part of the formulator's system prompt, made when it is rendered."""
    from geomind.agents import Formulator

    assert "## Case keys" in Formulator().prompt.render()


def test_the_economics_keys_are_in_the_tree():
    """The formulator drilled the economics schema 15 times: its keys were not in the tree."""
    import gemini as gm

    from geomind.tools.gemini.skeleton import case_tree, schema_tree

    economics = schema_tree(gm.case.Economics.schema())
    assert all(line in case_tree() for line in economics if not line.endswith("about: object"))


def test_the_plant_tree_is_read_from_gemini_s_schema():
    """The designer's prompt holds the plant file keys and every module type gemini has."""
    import gemini as gm

    from geomind.agents import Designer
    from geomind.tools.gemini.skeleton import plant_tree

    tree = plant_tree()
    assert "connections[]:" in tree and 'kind*: "plant"' in tree
    assert all(name in tree for name in gm.modules.names())
    assert "## Plant file keys" in Designer().prompt.render()
