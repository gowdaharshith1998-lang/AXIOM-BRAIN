from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import yaml
from yaml.error import MarkedYAMLError


class PolicyParseError(ValueError):
    pass


class EvalContext(Protocol):
    action: Any
    passport: Any
    entity: Any
    session: Any


class PredicateExpr:
    def evaluate(self, context: EvalContext) -> bool:
        raise NotImplementedError

    def to_source(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class PolicyAction:
    type: str
    reason: str
    guidance: str | None = None
    suggested_alternative: dict[str, Any] | None = None
    approval_required_role: str | None = None
    approval_timeout_seconds: int | None = None


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    description: str
    severity: str
    when: PredicateExpr
    then: PolicyAction
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


@dataclass(frozen=True)
class LiteralExpr(PredicateExpr):
    value: Any

    def evaluate(self, context: EvalContext) -> Any:
        return self.value

    def to_source(self) -> str:
        return repr(self.value)


@dataclass(frozen=True)
class IdentifierExpr(PredicateExpr):
    path: tuple[str, ...]

    def evaluate(self, context: EvalContext) -> Any:
        return _resolve_path(context, self.path)

    def to_source(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class ListExpr(PredicateExpr):
    values: list[PredicateExpr]

    def evaluate(self, context: EvalContext) -> list[Any]:
        return [value.evaluate(context) for value in self.values]

    def to_source(self) -> str:
        return "[" + ", ".join(value.to_source() for value in self.values) + "]"


@dataclass(frozen=True)
class UnaryExpr(PredicateExpr):
    operator: str
    operand: PredicateExpr

    def evaluate(self, context: EvalContext) -> bool:
        if self.operator == "not":
            return not bool(self.operand.evaluate(context))
        raise PolicyParseError(f"unknown unary operator {self.operator!r}")

    def to_source(self) -> str:
        return f"{self.operator} {self.operand.to_source()}"


@dataclass(frozen=True)
class BinaryExpr(PredicateExpr):
    left: PredicateExpr
    operator: str
    right: PredicateExpr

    def evaluate(self, context: EvalContext) -> Any:
        if self.operator == "and":
            return bool(self.left.evaluate(context)) and bool(self.right.evaluate(context))
        if self.operator == "or":
            return bool(self.left.evaluate(context)) or bool(self.right.evaluate(context))

        left = self.left.evaluate(context)
        right = self.right.evaluate(context)
        if self.operator == "==":
            return left == right
        if self.operator == "!=":
            return left != right
        if left is None:
            return False
        if self.operator == "in":
            if isinstance(right, list) and "*" in right:
                return True
            return left in (right or [])
        if self.operator == "contains":
            if isinstance(left, list) and "*" in left:
                return True
            return right in (left or [])
        if self.operator == ">":
            return left > right
        if self.operator == ">=":
            return left >= right
        if self.operator == "<":
            return left < right
        if self.operator == "<=":
            return left <= right
        if self.operator == "-":
            return left - right
        raise PolicyParseError(f"unknown binary operator {self.operator!r}")

    def to_source(self) -> str:
        return f"{self.left.to_source()} {self.operator} {self.right.to_source()}"


@dataclass(frozen=True)
class FunctionExpr(PredicateExpr):
    name: str
    args: list[PredicateExpr] = field(default_factory=list)
    kwargs: dict[str, PredicateExpr] = field(default_factory=dict)

    def evaluate(self, context: EvalContext) -> Any:
        from axiom.policy.predicates import PREDICATES

        func = PREDICATES.get(self.name)
        if func is None:
            raise PolicyParseError(f"unknown predicate {self.name!r}")
        args = [arg.evaluate(context) for arg in self.args]
        kwargs = {key: value.evaluate(context) for key, value in self.kwargs.items()}
        return func(
            context.action,
            context.passport,
            context.entity,
            context.session,
            *args,
            **kwargs,
        )

    def to_source(self) -> str:
        args = [arg.to_source() for arg in self.args]
        args.extend(f"{key}={value.to_source()}" for key, value in self.kwargs.items())
        return f"{self.name}({', '.join(args)})"


TOKEN_RE = re.compile(
    r"""
    (?P<SPACE>\s+)
  | (?P<STRING>"(?:\\.|[^"])*"|'(?:\\.|[^'])*')
  | (?P<OP>==|!=|>=|<=|[()[\],=<>-])
  | (?P<NUMBER>\d+(?:\.\d+)?)
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_\.]*)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


def _tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(source):
        match = TOKEN_RE.match(source, pos)
        if match is None:
            raise PolicyParseError(f"could not parse predicate near column {pos + 1}")
        kind = match.lastgroup or ""
        value = match.group()
        if kind != "SPACE":
            tokens.append(Token(kind, value, pos))
        pos = match.end()
    tokens.append(Token("EOF", "", len(source)))
    return tokens


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _tokenize(source)
        self.index = 0

    def parse(self) -> PredicateExpr:
        expr = self._parse_or()
        self._expect("EOF")
        _validate_predicates(expr)
        return expr

    def _peek(self) -> Token:
        return self.tokens[self.index]

    def _advance(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _match_value(self, *values: str) -> Token | None:
        if self._peek().value in values:
            return self._advance()
        return None

    def _expect(self, kind: str, value: str | None = None) -> Token:
        token = self._peek()
        if token.kind != kind or (value is not None and token.value != value):
            expected = value or kind
            raise PolicyParseError(f"expected {expected!r} near column {token.position + 1}")
        return self._advance()

    def _parse_or(self) -> PredicateExpr:
        expr = self._parse_and()
        while self._peek().value == "or":
            op = self._advance().value
            expr = BinaryExpr(expr, op, self._parse_and())
        return expr

    def _parse_and(self) -> PredicateExpr:
        expr = self._parse_not()
        while self._peek().value == "and":
            op = self._advance().value
            expr = BinaryExpr(expr, op, self._parse_not())
        return expr

    def _parse_not(self) -> PredicateExpr:
        if self._peek().value == "not":
            return UnaryExpr(self._advance().value, self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> PredicateExpr:
        expr = self._parse_additive()
        while self._peek().value in {"==", "!=", ">", ">=", "<", "<=", "in", "contains"}:
            op = self._advance().value
            expr = BinaryExpr(expr, op, self._parse_additive())
        return expr

    def _parse_additive(self) -> PredicateExpr:
        expr = self._parse_postfix()
        while self._peek().value == "-":
            op = self._advance().value
            expr = BinaryExpr(expr, op, self._parse_postfix())
        return expr

    def _parse_postfix(self) -> PredicateExpr:
        expr = self._parse_primary()
        while self._peek().kind == "IDENT" and self.tokens[self.index + 1].value == "(":
            name = self._advance().value
            args, kwargs = self._parse_call_args()
            expr = FunctionExpr(name, [expr, *args], kwargs)
        return expr

    def _parse_primary(self) -> PredicateExpr:
        token = self._peek()
        if token.kind == "STRING":
            return LiteralExpr(self._parse_string(self._advance().value))
        if token.kind == "NUMBER":
            raw = self._advance().value
            return LiteralExpr(float(raw) if "." in raw else int(raw))
        if token.value in {"true", "false"}:
            return LiteralExpr(self._advance().value == "true")
        if token.value == "null":
            self._advance()
            return LiteralExpr(None)
        if token.value == "[":
            return self._parse_list()
        if token.value == "(":
            self._advance()
            expr = self._parse_or()
            self._expect("OP", ")")
            return expr
        if token.kind == "IDENT":
            ident = self._advance().value
            if self._peek().value == "(":
                args, kwargs = self._parse_call_args()
                return FunctionExpr(ident, args, kwargs)
            return IdentifierExpr(tuple(ident.split(".")))
        raise PolicyParseError(f"unexpected token {token.value!r} near column {token.position + 1}")

    def _parse_call_args(self) -> tuple[list[PredicateExpr], dict[str, PredicateExpr]]:
        self._expect("OP", "(")
        args: list[PredicateExpr] = []
        kwargs: dict[str, PredicateExpr] = {}
        if self._match_value(")") is not None:
            return args, kwargs
        while True:
            if (
                self._peek().kind == "IDENT"
                and self.tokens[self.index + 1].value == "="
            ):
                key = self._advance().value
                self._expect("OP", "=")
                kwargs[key] = self._parse_or()
            else:
                args.append(self._parse_or())
            if self._match_value(")") is not None:
                return args, kwargs
            self._expect("OP", ",")

    def _parse_list(self) -> ListExpr:
        self._expect("OP", "[")
        values: list[PredicateExpr] = []
        if self._match_value("]") is not None:
            return ListExpr(values)
        while True:
            values.append(self._parse_or())
            if self._match_value("]") is not None:
                return ListExpr(values)
            self._expect("OP", ",")

    @staticmethod
    def _parse_string(raw: str) -> str:
        return bytes(raw[1:-1], "utf-8").decode("unicode_escape")


def parse_predicate(source: str) -> PredicateExpr:
    return _Parser(source).parse()


def parse_policy_yaml(text: str) -> list[PolicyRule]:
    try:
        document = yaml.safe_load(text) or {}
    except MarkedYAMLError as exc:
        line = (exc.problem_mark.line + 1) if exc.problem_mark else "unknown"
        raise PolicyParseError(f"invalid YAML at line {line}: {exc.problem}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("rules"), list):
        raise PolicyParseError('policy YAML must contain top-level "rules:" list')

    rules: list[PolicyRule] = []
    for index, raw_rule in enumerate(document["rules"], start=1):
        if not isinstance(raw_rule, dict):
            raise PolicyParseError(f"rule {index} must be a mapping")
        try:
            rule_id = _required_str(raw_rule, "rule_id")
            description = _required_str(raw_rule, "description")
            severity = _required_str(raw_rule, "severity")
            when_raw = _required_str(raw_rule, "when")
            then_raw = raw_rule["then"]
        except KeyError as exc:
            raise PolicyParseError(f"rule {index} missing required key {exc.args[0]!r}") from exc
        if severity not in {"info", "warning", "critical"}:
            raise PolicyParseError(f"rule {rule_id!r} has invalid severity {severity!r}")
        if not isinstance(then_raw, dict):
            raise PolicyParseError(f"rule {rule_id!r} then must be a mapping")
        try:
            action_type = _required_str(then_raw, "type")
            reason = _required_str(then_raw, "reason")
            then = PolicyAction(
                type=action_type,
                reason=reason,
                guidance=_optional_str(then_raw, "guidance"),
                suggested_alternative=then_raw.get("suggested_alternative"),
                approval_required_role=_optional_str(then_raw, "approval_required_role"),
                approval_timeout_seconds=then_raw.get("approval_timeout_seconds"),
            )
        except KeyError as exc:
            raise PolicyParseError(f"rule {rule_id!r} action missing key {exc.args[0]!r}") from exc
        if then.type not in {"allow", "correct", "deny", "pause"}:
            raise PolicyParseError(f"rule {rule_id!r} has invalid action {then.type!r}")
        try:
            predicate = parse_predicate(when_raw)
        except PolicyParseError as exc:
            raise PolicyParseError(f"rule {rule_id!r}: {exc}") from exc
        metadata = raw_rule.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise PolicyParseError(f"rule {rule_id!r} metadata must be a mapping")
        rules.append(
            PolicyRule(
                rule_id=rule_id,
                description=description,
                severity=severity,
                when=predicate,
                then=then,
                metadata=metadata,
            )
        )
    return rules


def load_policies_from_dir(path: str | Path) -> list[PolicyRule]:
    root = Path(path)
    rules: list[PolicyRule] = []
    if not root.exists():
        return []
    for file_path in sorted(root.rglob("*.yaml")):
        for rule in parse_policy_yaml(file_path.read_text(encoding="utf-8")):
            rules.append(
                PolicyRule(
                    rule_id=rule.rule_id,
                    description=rule.description,
                    severity=rule.severity,
                    when=rule.when,
                    then=rule.then,
                    metadata={**rule.metadata, "source_file": str(file_path)},
                    source=str(file_path),
                )
            )
    return rules


def _required_str(mapping: dict[str, Any], key: str) -> str:
    value = mapping[key]
    if not isinstance(value, str) or not value:
        raise PolicyParseError(f"{key!r} must be a non-empty string")
    return value


def _optional_str(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PolicyParseError(f"{key!r} must be a string")
    return value


def _resolve_path(context: EvalContext, path: tuple[str, ...]) -> Any:
    if path == ("entity",):
        return context.entity
    if path == ("action",):
        return context.action
    if path == ("passport",):
        return context.passport
    if path == ("confidence",):
        return _payload_get(context.action, "confidence")
    if path[:2] == ("data", "payload"):
        current: Any = getattr(context.action, "payload", {}) or {}
        for part in path[2:]:
            current = _get_value(current, part)
        return current

    root_name = path[0]
    current = getattr(context, root_name, None)
    for part in path[1:]:
        if root_name == "passport" and part == "status":
            return _passport_status(current)
        current = _get_value(current, part)
    return current


def _get_value(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    if hasattr(value, key):
        return getattr(value, key)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return data.get(key)
    return None


def _payload_get(action: Any, key: str) -> Any:
    payload = getattr(action, "payload", {}) or {}
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _passport_status(passport: Any) -> str | None:
    if passport is None:
        return None
    if getattr(passport, "revoked_at", None) is not None:
        return "revoked"
    expires_at = getattr(passport, "expires_at", None)
    if isinstance(expires_at, datetime) and expires_at < datetime.utcnow():
        return "expired"
    return "active"


def _validate_predicates(expr: PredicateExpr) -> None:
    from axiom.policy.predicates import PREDICATES

    if isinstance(expr, FunctionExpr) and expr.name not in PREDICATES:
        raise PolicyParseError(f"unknown predicate {expr.name!r}")
    children: list[PredicateExpr] = []
    if isinstance(expr, UnaryExpr):
        children.append(expr.operand)
    elif isinstance(expr, BinaryExpr):
        children.extend([expr.left, expr.right])
    elif isinstance(expr, FunctionExpr):
        children.extend(expr.args)
        children.extend(expr.kwargs.values())
    elif isinstance(expr, ListExpr):
        children.extend(expr.values)
    for child in children:
        _validate_predicates(child)


def now(_action: Any, _passport: Any, _entity: Any, _session: Any) -> datetime:
    return datetime.utcnow()


def days(_action: Any, _passport: Any, _entity: Any, _session: Any, count: int) -> timedelta:
    return timedelta(days=count)
