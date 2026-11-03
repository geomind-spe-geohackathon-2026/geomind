"""A tool: a name, a schema, an effect and a function."""

import copy
import inspect
import typing

from pydantic import ConfigDict, create_model

from geomind.errors import DeclarationError, ToolError, UnknownNameError
from geomind.utils.strings import did_you_mean, join_names

EFFECTS = ("read", "compute", "write", "execute", "external")
PURE_EFFECTS = ("read", "compute")
RENAMED_TOOLS = {
    "read_document": "read_rag",
    "search_documents": "search_rag",
    "rag_read": "read_rag",
    "rag_search": "search_rag",
    "search_knowledge": "search_rag",
}
"""The name a tool had in an older log or recording, by its name now (0.4.22.dev36, dev42)."""


def with_old_names(tools):
    """Return ``{name: tool}`` that also answers to a renamed tool's old name, for old logs."""
    old = {former: tools[now] for former, now in RENAMED_TOOLS.items() if now in tools}
    return {**old, **tools}


def takes_context(function):
    """Tell whether a tool function wants the run: its first parameter is named ``context``."""
    return next(iter(inspect.signature(function).parameters), None) == "context"


class Tool:
    """One action a model can call.

    ``effect`` says what a call touches: ``read``, ``compute``, ``write``, ``execute`` (running
    code) or ``external`` (network or anything outside the run). ``idempotent`` says a call may run
    again after a crash. A function whose first parameter is ``context`` receives the run's context;
    the schema never shows it, and other tools stay plain functions. ``runs_alone`` keeps a pure
    tool out of concurrent dispatch, for tools the engine itself handles. ``reruns_in_replay`` says
    a tool that is not pure runs again in a replay, because all it changes is the run's own log.
    ``input_model`` validates the input fully; without one, as for a toolset from another source,
    only the required and known names of ``input_schema`` are checked. ``late_schemas`` gives the
    schema of an input as a function, called when the tool is offered, for a schema that belongs to
    a package too slow to import with geomind. ``stored_input`` names the input that is the
    reference of a stored result the tool reads: its own long result is a part of that one, so it
    is not stored again and carries that reference. ``keeps_result`` keeps a result up to
    ``tool_result_limit`` whole in the history, unstored, for source material the model reads
    again and again, such as a document page.
    NOTE: the class is shaped like a protocol, so tools from other sources fit without changes.
    """

    def __init__(
        self,
        name,
        description,
        input_schema,
        function,
        *,
        effect,
        idempotent=True,
        timeout=None,
        max_retries=2,
        input_model=None,
        runs_alone=False,
        reruns_in_replay=False,
        late_schemas=None,
        stored_input=None,
        keeps_result=False,
    ):
        """Store the definition; an unknown effect raises."""
        if effect not in EFFECTS:
            suggestion = did_you_mean(effect, EFFECTS)
            raise UnknownNameError(
                f"Tool {name}: effect = {effect!r}; expected one of {join_names(EFFECTS)}"
                f"{suggestion}"
            )
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.function = function
        self.takes_context = takes_context(function)
        self.effect = effect
        self.idempotent = idempotent
        self.timeout = timeout
        self.max_retries = max_retries
        self.input_model = input_model
        self.runs_alone = runs_alone
        self.reruns_in_replay = reruns_in_replay
        self.late_schemas = late_schemas or {}
        self.stored_input = stored_input
        self.keeps_result = keeps_result

    @property
    def is_pure(self):
        """Tell whether a call may run beside others and again in a replay."""
        return self.effect in PURE_EFFECTS

    @property
    def replays(self):
        """Tell whether a replay runs this tool again instead of reusing its recorded result."""
        return self.is_pure or self.reruns_in_replay

    def _offered_schema(self):
        """Return ``input_schema`` with the late schemas in place, their definitions at the top."""
        schema = without_titles(self.input_schema)
        for name, function in self.late_schemas.items():
            late = dict(without_titles(function()))
            definitions = late.pop("$defs", {})
            schema["properties"][name] = late
            if definitions:
                schema.setdefault("$defs", {}).update(definitions)
        return schema

    def schema(self):
        """Return what a provider needs to offer this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self._offered_schema(),
        }

    def for_call(self, session, tool_input):
        """Return the tool the permissions decide one call by: itself by default.

        A tool whose effect depends on the call returns a copy with that effect, as ``call_mcp``
        does for the server tool it calls.
        """
        return self

    def kept(self):
        """Return a copy whose results stay whole for a few turns (``keeps_result``).

        For an agent that works from them step after step, such as an engineer from the case and
        the plant.
        """
        kept = copy.copy(self)
        kept.keeps_result = True
        return kept

    def renamed(self, name):
        """Return a copy under another name; an agent names a tool by its attribute."""
        renamed = copy.copy(self)
        renamed.name = name
        return renamed

    def validate(self, tool_input):
        """Return the keyword arguments of a call, or raise for an input that does not fit."""
        if self.input_model is not None:
            model = self.input_model.model_validate(tool_input)
            return {name: getattr(model, name) for name in type(model).model_fields}
        properties = self.input_schema.get("properties", {})
        missing = set(self.input_schema.get("required", ())) - set(tool_input)
        unknown = set(tool_input) - set(properties) if properties else set()
        if missing or unknown:
            raise ToolError(
                f"{self.name}: missing = {sorted(missing)}, unknown = {sorted(unknown)}; "
                f"expected the names {join_names(properties)}"
            )
        return dict(tool_input)


def _first_line(definition):
    """Return a definition with the first line of its description, the rest being detail."""
    text = definition.get("description")
    if not isinstance(text, str):
        return definition
    return {**definition, "description": text.split("\n")[0]}


def without_titles(schema):
    """Return a copy of a JSON schema without its ``title`` and ``default`` annotations.

    ``required`` already says what may be left out. A property named ``title`` or ``default`` stays:
    its value is a schema, while an annotation is not a mapping.
    """
    if isinstance(schema, list):
        return [without_titles(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "$defs" in schema:
        schema = {
            **schema,
            "$defs": {name: _first_line(item) for name, item in schema["$defs"].items()},
        }
    return {
        key: without_titles(value)
        for key, value in schema.items()
        if not (key in ("title", "default") and not isinstance(value, dict))
    }


def _input_model(function):
    """Return the Pydantic model of a function's signature."""
    hints = typing.get_type_hints(function)
    fields = {}
    parameters = list(inspect.signature(function).parameters.items())
    for name, parameter in parameters[takes_context(function) :]:
        if name not in hints:
            raise DeclarationError(
                f"tool {function.__name__}: parameter = {name!r}; expected a type annotation"
            )
        has_default = parameter.default is not inspect.Parameter.empty
        fields[name] = (hints[name], parameter.default if has_default else ...)
    config = ConfigDict(extra="forbid")
    return create_model(f"{function.__name__}_input", __config__=config, **fields)


def tool_description(docstring):
    """Return what a model reads of a tool: its docstring without the ``NOTE:`` paragraphs.

    Each paragraph is one line, so the usage rules, the shapes and the examples reach the model
    in few tokens.
    """
    paragraphs = inspect.cleandoc(docstring).split("\n\n")
    kept = [" ".join(item.split()) for item in paragraphs if not item.lstrip().startswith("NOTE:")]
    return "\n\n".join(item for item in kept if item)


def tool(
    *,
    effect,
    idempotent=True,
    timeout=None,
    max_retries=2,
    runs_alone=False,
    reruns_in_replay=False,
    late_schemas=None,
    stored_input=None,
    keeps_result=False,
):
    """Return a decorator that builds a ``Tool`` from a typed function.

    The schema comes from the signature through Pydantic, the description from the docstring:
    all of it but its ``NOTE:`` paragraphs, which are for people (``tool_description``).
    """

    def build(function):
        if not function.__doc__:
            raise DeclarationError(f"tool {function.__name__}: expected a docstring")
        model = _input_model(function)
        return Tool(
            function.__name__,
            tool_description(function.__doc__),
            model.model_json_schema(),
            function,
            effect=effect,
            idempotent=idempotent,
            timeout=timeout,
            max_retries=max_retries,
            input_model=model,
            runs_alone=runs_alone,
            reruns_in_replay=reruns_in_replay,
            late_schemas=late_schemas,
            stored_input=stored_input,
            keeps_result=keeps_result,
        )

    return build
