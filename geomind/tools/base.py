"""A tool: a name, a schema, an effect and a function."""

import copy
import inspect
import json
import re
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
    ``tool_result_limit`` whole in the history for a few turns, for source material the model
    reads again and again; ``"run"`` keeps it whole for the whole run, such as a document page.
    ``sets_input`` marks a write whose result follows from its input alone, so the same call again
    sets the same values (``set_ranges``): with ``repeats_same`` it is answered from its first
    result.
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
        sets_input=False,
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
        self.sets_input = sets_input

    @property
    def is_pure(self):
        """Tell whether a call may run beside others and again in a replay."""
        return self.effect in PURE_EFFECTS

    @property
    def repeats_same(self):
        """Tell whether the same call again, with nothing written between, gives the same result.

        Decided by effect: a pure tool (``read`` or ``compute``) that the engine does not handle
        itself (``runs_alone``: questions, ``finish``), and a write that sets its input
        (``sets_input``). Not a tool whose result may change on its own: an MCP server's tools and
        nested runs are not pure, nor is anything ``external`` or ``execute``. A pure tool that
        reads what a write changes (``simulate`` after ``patch_plant``) is safe because any tool
        that is not pure and ran with success between the two calls, a write, a nested run or a
        server's tool, makes the second one run (``same_result`` in ``geomind.engine.step``).
        """
        return (self.is_pure and not self.runs_alone) or self.sets_input

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

    def card_summary(self, tool_input):
        """Return the sentence an approval card of this call says, or ``None`` for the default."""
        return None

    def kept(self):
        """Return a copy whose results stay whole for a few turns (``keeps_result``).

        For an agent that works from them step after step, such as an engineer from the case and
        the plant.
        """
        kept = copy.copy(self)
        kept.keeps_result = self.keeps_result or True
        return kept

    def renamed(self, name):
        """Return a copy under another name; an agent names a tool by its attribute."""
        renamed = copy.copy(self)
        renamed.name = name
        return renamed

    def unknown_arguments(self, tool_input):
        """Return the names of a call's input that are no argument of this tool, sorted.

        A tool that takes any input (no declared properties and no input model, or
        ``additionalProperties`` allowed) has none.
        """
        if not isinstance(tool_input, dict):
            return []
        properties = self.input_schema.get("properties") or {}
        if self.input_schema.get("additionalProperties") is True:
            return []
        if not properties and self.input_model is None:
            return []
        return sorted(set(tool_input) - set(properties))

    def validate(self, tool_input):
        """Return the keyword arguments of a call, or raise for an input that does not fit.

        An object or array sent as its JSON text is read as that value first, also when only its
        closing brackets are missing or one too many follows it, and ``"None"`` is null where a null
        is accepted (``parsed_inputs``, #67, #87, #89, #112), also with a stray closing bracket in
        the middle deleted (#117). JSON text that still does not parse is refused naming its JSON
        error and where (``json_text_error``, #141).
        """
        tool_input = parsed_inputs(self.input_schema, tool_input)
        unparsed = json_text_error(self.name, self.input_schema, tool_input)
        if unparsed is not None:
            raise unparsed
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


CLOSERS = {"[": "]", "{": "}"}
STRAY_CLOSERS = set("}] \n")
"""What may follow a JSON value in a model's text and still leave it that value (#112)."""
NULL_TEXTS = ("None", "null")
"""A null some models send as text, ``section: "None"``, read as null where the schema takes one."""


def missing_closers(text):
    """Return the brackets that close what ``text`` opened, outside its strings, else ``""``."""
    stack, in_string, escaped = [], False, False
    for char in text:
        if in_string:
            in_string = escaped or char != '"'
            escaped = not escaped and char == "\\"
            continue
        if char == '"':
            in_string = True
        elif char in CLOSERS:
            stack.append(CLOSERS[char])
        elif stack and char == stack[-1]:
            stack.pop()
    return "" if in_string else "".join(reversed(stack))


STRAY_REPAIRS = 3
"""How many stray closing brackets ``parsed_json`` deletes from one text at most (#117)."""


def parsed_json(text):
    """Return the JSON value of ``text``, also when only its closing brackets are missing (#87).

    nemotron sent a list as JSON text without its final ``]``, and once with one ``}`` too many
    after it (#112), or in the middle, where ``json`` stops (#117): ``"EUR/kg"}}}, "revenue"`` or
    ``}]}``. A closing bracket there that closes nothing open is deleted, up to
    ``STRAY_REPAIRS`` times, and the value is taken only when it has no more closing brackets than
    the text as sent: a bracket moves or goes, none is made up. Nothing else is repaired.
    """
    closers = _closer_count(text)
    for repairs in range(STRAY_REPAIRS + 1):
        value, read, error = _read_json(text)
        if error is None:
            return value if not repairs or _closer_count(read) <= closers else None
        index = _stray_closer(text, error)
        if index is None:
            return None
        text = text[:index] + text[index + 1 :]
    return None


def _closer_count(text):
    """Return how many closing brackets ``text`` has outside its strings."""
    count, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            in_string = escaped or char != '"'
            escaped = not escaped and char == "\\"
        elif char == '"':
            in_string = True
        elif char in "]}":
            count += 1
    return count


def _read_json(text):
    """Return ``(value, text read, None)`` of ``text``, else ``(None, None, error)``.

    The text read is ``text``, with its missing closers added or its stray ones after the value
    dropped; the error is that of ``text`` as sent.
    """
    try:
        return json.loads(text), text, None
    except json.JSONDecodeError as failure:
        error = failure
    completed = text + missing_closers(text)
    try:
        return json.loads(completed), completed, None
    except ValueError:
        pass
    try:
        value, end = json.JSONDecoder().raw_decode(text.strip())
    except ValueError:
        return None, None, error
    rest = text.strip()[end:]
    if set(rest) <= STRAY_CLOSERS:
        return value, text.strip()[:end], None
    return None, None, error


def _stray_closer(text, error):
    """Return the index of the closing bracket where ``json`` stopped that closes nothing open.

    It is the bracket ``json`` stopped at when nothing or another bracket is open there (``}]``
    inside an object); at ``Extra data`` followed by ``,`` the value closed too early, so it is
    the last bracket before. Else ``None``.
    """
    position = error.pos
    char = text[position : position + 1]
    if char in ("}", "]") and missing_closers(text[:position])[:1] != char:
        return position
    if error.msg == "Extra data" and text[position:].lstrip().startswith(","):
        before = text[:position].rstrip()
        if before.endswith(("}", "]")):
            return len(before) - 1
    if char == ":" and missing_closers(text[:position])[:1] == "]":
        early = EARLY_CLOSE.search(text[:position])
        if early is not None:
            return early.start()
    return None


EARLY_CLOSE = re.compile(r'\}\s*,\s*"(?:[^"\\]|\\.)*"\s*$')
"""An object closed before its last key: ``{..., "reason": "x"}, "citation": null}]`` (#129).

``json`` stops at the ``:`` of a key inside a list; the ``}`` before that key is the stray one.
"""


JSON_TYPES = {dict: "object", list: "array"}
"""The JSON schema type of a value ``json.loads`` gives, for the types read from a string."""


def _accepted_types(schema, definitions, seen=()):
    """Return the JSON types a property schema accepts; ``None`` when it accepts any value."""
    if not isinstance(schema, dict):
        return None
    reference = schema.get("$ref", "")
    if reference.startswith("#/$defs/") and reference not in seen:
        name = reference.removeprefix("#/$defs/")
        return _accepted_types(definitions.get(name), definitions, (*seen, reference))
    branches = schema.get("anyOf") or schema.get("oneOf")
    if branches:
        types = set()
        for branch in branches:
            accepted = _accepted_types(branch, definitions, seen)
            if accepted is None:
                return None
            types |= accepted
        return types
    kind = schema.get("type")
    if kind is None:
        return None
    return set(kind) if isinstance(kind, list) else {kind}


def parsed_inputs(schema, tool_input):
    """Return a call's input with an object or array sent as JSON text read as that value (#67).

    Some models send an object argument as its JSON text (``'{"format": 1}'``). A string for a
    property whose schema accepts an object or an array, and no string, is read with
    ``json.loads`` when that gives a value of an accepted type, also with only its closing brackets
    missing (#87); ``"None"`` or ``"null"`` is null wherever the schema takes a null (#89). Any
    other string stays as sent, so validation refuses it as before. A property that accepts a
    string, or any value, keeps it.
    """
    if not isinstance(tool_input, dict):
        return tool_input
    properties = schema.get("properties", {})
    definitions = schema.get("$defs", {})
    parsed = dict(tool_input)
    for name, value in tool_input.items():
        if not isinstance(value, str) or name not in properties:
            continue
        accepted = _accepted_types(properties[name], definitions)
        if accepted is not None and value in NULL_TEXTS and "null" in accepted:
            parsed[name] = None
            continue
        if accepted is None or "string" in accepted:
            continue
        if not accepted & set(JSON_TYPES.values()) or value.strip()[:1] not in CLOSERS:
            continue
        loaded = parsed_json(value)
        if JSON_TYPES.get(type(loaded)) in accepted:
            parsed[name] = loaded
    return parsed


EXCERPT_CHARACTERS = 40
"""How many characters of a JSON text an error shows on each side of where it stopped."""
PYTHON_LITERALS = {"None": "null", "True": "true", "False": "false"}


def _takes_json_text(schema, definitions):
    """Tell whether a property reads a string as JSON text: an object or array, and no string."""
    accepted = _accepted_types(schema, definitions)
    if accepted is None or "string" in accepted:
        return False
    return bool(accepted & set(JSON_TYPES.values()))


def json_text_error(tool_name, schema, tool_input):
    """Return the error of an object or array sent as JSON text that does not parse, or ``None``.

    pydantic's "Input should be a valid dictionary" named no JSON error, and the model sent the same
    text again (the run: ``build_plant plant`` with ``None`` at char 11246, ``update_state changes``
    at char 161, #141). The error names ``json``'s message, its line, column and character, and the
    text around it; a Python literal there (``None``) is named with its JSON spelling.
    """
    if not isinstance(tool_input, dict):
        return None
    properties = schema.get("properties", {})
    definitions = schema.get("$defs", {})
    for name, value in tool_input.items():
        if not isinstance(value, str) or value.strip()[:1] not in CLOSERS:
            continue
        if name not in properties or not _takes_json_text(properties[name], definitions):
            continue
        try:
            json.loads(value)
        except json.JSONDecodeError as error:
            return _unparsed(tool_name, name, value, error)
    return None


def _unparsed(tool_name, name, text, error):
    """Return the ``ToolError`` of one JSON text and its ``json.JSONDecodeError``."""
    position = error.pos
    before = text[max(position - EXCERPT_CHARACTERS, 0) : position]
    after = text[position : position + EXCERPT_CHARACTERS]
    literal = next((word for word in PYTHON_LITERALS if after.startswith(word)), None)
    hint = f" JSON writes {PYTHON_LITERALS[literal]}, not {literal}." if literal is not None else ""
    return ToolError(
        f"{tool_name}: {name} is JSON text that does not parse: {error.msg} at line "
        f"{error.lineno}, "
        f"column {error.colno} (char {position} of {len(text)}), here: {before}<<here>>{after}."
        f"{hint} Fix it there, and send {name} as the value itself, not as text",
        code="invalid_input",
        path=name,
    )


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
    sets_input=False,
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
            sets_input=sets_input,
        )

    return build
