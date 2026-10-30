"""A tool: a name, a schema, an effect and a function."""

import copy
import inspect
import typing

from pydantic import ConfigDict, create_model

from geomind.errors import DeclarationError, ToolError, UnknownNameError
from geomind.utils.strings import did_you_mean, first_paragraph, join_names

EFFECTS = ("read", "compute", "write", "execute", "external")
PURE_EFFECTS = ("read", "compute")


def takes_context(function):
    """Tell whether a tool function wants the run: its first parameter is named ``context``."""
    return next(iter(inspect.signature(function).parameters), None) == "context"


class Tool:
    """One action a model can call.

    ``effect`` says what a call touches: ``read``, ``compute``, ``write``, ``execute`` (sandbox
    code) or ``external`` (network or anything outside the run). ``idempotent`` says a call may run
    again after a crash. A function whose first parameter is ``context`` receives the run's context;
    the schema never shows it, and other tools stay plain functions. ``runs_alone`` keeps a pure
    tool out of concurrent dispatch, for tools the engine itself handles. ``reruns_in_replay`` says
    a tool that is not pure runs again in a replay, because all it changes is the run's own log.
    ``input_model`` validates the input fully; without one, as for a toolset from another source,
    only the required and known names of ``input_schema`` are checked.
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

    @property
    def is_pure(self):
        """Tell whether a call may run beside others and again in a replay."""
        return self.effect in PURE_EFFECTS

    @property
    def replays(self):
        """Tell whether a replay runs this tool again instead of reusing its recorded result."""
        return self.is_pure or self.reruns_in_replay

    def schema(self):
        """Return what a provider needs to offer this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

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


def tool(
    *,
    effect,
    idempotent=True,
    timeout=None,
    max_retries=2,
    runs_alone=False,
    reruns_in_replay=False,
):
    """Return a decorator that builds a ``Tool`` from a typed function.

    The schema comes from the signature through Pydantic, the description from the docstring.
    """

    def build(function):
        if not function.__doc__:
            raise DeclarationError(f"tool {function.__name__}: expected a docstring")
        model = _input_model(function)
        return Tool(
            function.__name__,
            first_paragraph(function.__doc__),
            model.model_json_schema(),
            function,
            effect=effect,
            idempotent=idempotent,
            timeout=timeout,
            max_retries=max_retries,
            input_model=model,
            runs_alone=runs_alone,
            reruns_in_replay=reruns_in_replay,
        )

    return build
